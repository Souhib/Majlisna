import traceback
from datetime import UTC, datetime
from uuid import UUID

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import get_scalar_api_reference
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse

from ipg.api.middleware import LoggingMiddleware, RequestIDMiddleware, SecurityMiddleware
from ipg.api.routes.auth import limiter
from ipg.api.routes.auth import router as auth_router
from ipg.api.routes.codenames import router as codenames_router
from ipg.api.routes.game import router as game_router
from ipg.api.routes.room import router as room_router
from ipg.api.routes.stats import router as stats_router
from ipg.api.routes.undercover import router as undercover_router
from ipg.api.routes.user import router as user_router
from ipg.api.schemas.error import BaseError
from ipg.database import get_engine as _get_engine
from ipg.settings import Settings


def create_app(lifespan) -> FastAPI:
    """Create a FastAPI app with all routers, middleware, and exception handlers."""
    settings = Settings()  # type: ignore

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=settings.environment,
        )

    app = FastAPI(title="IPG", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Middleware stack (order matters: first added = outermost)
    app.add_middleware(SecurityMiddleware, is_production=settings.environment == "production")
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,  # type: ignore
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers with /api/v1 prefix
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(room_router, prefix="/api/v1")
    app.include_router(game_router, prefix="/api/v1")
    app.include_router(undercover_router, prefix="/api/v1")
    app.include_router(codenames_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")

    @app.get("/scalar", include_in_schema=False)
    async def scalar_html():
        return get_scalar_api_reference(
            openapi_url="/openapi.json",
            title="IPG API Scalar",
        )

    @app.get("/health")
    async def health_check():
        """Health check endpoint with DB connectivity verification."""
        db_status = "ok"
        status_code = 200
        try:
            engine = await _get_engine()
            async with AsyncSession(engine) as session:
                await session.exec(text("SELECT 1"))
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
        details_status_codes = {400, 409, 422, 429}
        should_include_details = exc.status_code in details_status_codes

        serializable_details = {}
        if should_include_details and exc.details:
            serializable_details = {k: str(v) if isinstance(v, UUID) else v for k, v in exc.details.items()}

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "error_key": exc.error_key,
                "message": exc.frontend_message,
                "error_params": exc.error_params,
                "details": serializable_details if should_include_details else {},
                "timestamp": exc.timestamp.isoformat(),
            },
        )

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
