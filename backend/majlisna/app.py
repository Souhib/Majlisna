import traceback
from datetime import UTC, datetime

import logfire
import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import get_scalar_api_reference
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse

from majlisna.api.middleware import LoggingMiddleware, RequestIDMiddleware, SecurityMiddleware
from majlisna.api.rate_limit import rate_limit_exceeded_handler
from majlisna.api.routes.auth import limiter
from majlisna.api.routes.auth import router as auth_router
from majlisna.api.routes.challenge import router as challenge_router
from majlisna.api.routes.chat import router as chat_router
from majlisna.api.routes.codenames import router as codenames_router
from majlisna.api.routes.friend import router as friend_router
from majlisna.api.routes.game import router as game_router
from majlisna.api.routes.mcqquiz import router as mcqquiz_router
from majlisna.api.routes.notebook import router as notebook_router
from majlisna.api.routes.profile import router as profile_router
from majlisna.api.routes.room import router as room_router
from majlisna.api.routes.stats import router as stats_router
from majlisna.api.routes.undercover import router as undercover_router
from majlisna.api.routes.user import router as user_router
from majlisna.api.routes.wordquiz import router as wordquiz_router
from majlisna.api.schemas.error import BaseError, error_response
from majlisna.api.ws import socketio_app
from majlisna.database import get_engine as _get_engine
from majlisna.settings import Settings


def _sentry_sink(message) -> None:
    """Loguru sink that forwards logs to Sentry/GlitchTip.

    WARNING+ → captured as Sentry events (visible as issues in GlitchTip).
    Exceptions logged via logger.exception() → captured as Sentry exceptions.
    Breadcrumbs are handled automatically by the Sentry SDK.
    """
    record = message.record

    if record["level"].no >= 30:  # WARNING+
        sentry_sdk.capture_message(
            record["message"],
            level=record["level"].name.lower(),
        )

    if record["exception"] is not None:
        exc_type, exc_value, exc_tb = record["exception"]
        if exc_value is not None:
            sentry_sdk.capture_exception(exc_value)


def _configure_observability(settings: Settings, app: FastAPI) -> None:
    """Set up Sentry and Logfire if configured."""
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=settings.environment,
        )
        logger.add(_sentry_sink, level="WARNING", filter=lambda record: "majlisna" in record["file"].path)

    if settings.logfire_token:
        logfire.configure(
            service_name="majlisna-api",
            send_to_logfire="if-token-present",
            token=settings.logfire_token,
            console=False,
        )
        logfire.instrument_fastapi(app, capture_headers=True, excluded_urls=["/health", "/scalar"])


def _log_admin_access(settings: Settings) -> None:
    """State at boot whether the game-content endpoints are reachable by anyone.

    ``get_current_admin_user`` fails closed, so an unset ADMIN_EMAILS means those
    endpoints answer 403 to every caller — correct, but indistinguishable from a
    broken deploy when you are looking at a 403 and wondering which of the two it
    is. Logged at INFO, not WARNING: an empty admin list is a valid configuration,
    and app.py routes WARNING+ to the error tracker.

    Only the count and the domains are logged. The addresses are operator config,
    not secrets, but there is no reason to put them in a log stream.
    """
    if not settings.admin_emails:
        logger.info("Admin access: DISABLED (ADMIN_EMAILS is unset — game-content endpoints deny everyone)")
        return
    domains = sorted({email.rpartition("@")[2].casefold() for email in settings.admin_emails})
    logger.info(
        "Admin access: {count} address(es) configured on {domains} (a verified email is also required)",
        count=len(settings.admin_emails),
        domains=", ".join(domains),
    )


# Every REST router, mounted under /api/v1 in this order.
_API_ROUTERS = (
    auth_router,
    user_router,
    room_router,
    game_router,
    undercover_router,
    codenames_router,
    wordquiz_router,
    mcqquiz_router,
    stats_router,
    profile_router,
    friend_router,
    chat_router,
    challenge_router,
    notebook_router,
)


def _include_api_routers(app: FastAPI) -> None:
    """Mount every REST router with the /api/v1 prefix."""
    for router in _API_ROUTERS:
        app.include_router(router, prefix="/api/v1")


def create_app(lifespan) -> FastAPI:
    """Create a FastAPI app with all routers, middleware, and exception handlers."""
    settings = Settings()

    app = FastAPI(title="Majlisna", lifespan=lifespan)
    _configure_observability(settings, app)
    _log_admin_access(settings)
    app.state.limiter = limiter
    # The standard error envelope (translatable `error_key`), not slowapi's bare
    # {"error": "Rate limit exceeded: …"}.
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Middleware stack (order matters: first added = outermost)
    app.add_middleware(SecurityMiddleware, is_production=settings.environment == "production")
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _include_api_routers(app)

    # Mount Socket.IO (separate ASGI app, bypasses FastAPI middleware)
    app.mount("/socket.io", socketio_app)

    @app.get("/scalar", include_in_schema=False)
    async def scalar_html():
        return get_scalar_api_reference(
            openapi_url="/openapi.json",
            title="Majlisna API Scalar",
        )

    @app.get("/health")
    async def health_check():
        """Health check endpoint with DB connectivity verification."""
        db_status = "ok"
        status_code = 200
        try:
            engine = await _get_engine()
            async with AsyncSession(engine) as session:
                # `exec` is typed for Select statements; a raw TextClause has no
                # matching overload. Deliberate — the alternative, `execute`, is the one
                # SQLModel deprecates, and this only needs the round-trip, not the rows.
                await session.exec(text("SELECT 1"))  # ty: ignore[no-matching-overload]
        except Exception:
            db_status = "error"
            status_code = 503
            logger.error("Health check failed: database connectivity error")

        body = {
            "status": "healthy" if status_code == 200 else "degraded",
            "db": db_status,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return JSONResponse(content=body, status_code=status_code)

    @app.exception_handler(NoResultFound)
    async def no_result_found_exception_handler(_request: Request, _exc: NoResultFound):
        return JSONResponse(
            status_code=404,
            content={
                "error_key": "errors.api.resourceNotFound",
                "frontend_message": "Couldn't find requested resource.",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    @app.exception_handler(BaseError)
    async def base_error_exception_handler(_request: Request, exc: BaseError):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "Request validation failed: {path}",
            path=request.url.path,
            method=request.method,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "ValidationError",
                "error_key": "errors.api.validation",
                "message": "Invalid request data. Please check your input.",
                "error_params": None,
                "details": exc.errors(),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unexpected server error: {error} - {message}",
            error=exc.__class__.__name__,
            message=str(exc),
            path=request.url.path,
            method=request.method,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "error_key": "errors.api.internalServer",
                "message": "Something went wrong on our end. Please try again later.",
                "error_params": None,
                "details": {},
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    return app
