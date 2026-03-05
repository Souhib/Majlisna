import os
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from ipg.api.controllers.auth import AuthController
from ipg.api.models.table import User
from ipg.api.models.user import UserCreate
from ipg.api.models.view import UserView
from ipg.api.schemas.auth import LoginRequest, LoginResponse, TokenPairResponse
from ipg.api.schemas.error import InvalidTokenError
from ipg.dependencies import get_auth_controller, get_current_user, get_settings
from ipg.settings import Settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false",
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str, settings: Settings) -> None:
    """Set httpOnly auth cookies on the response."""
    is_prod = settings.environment == "production"
    response.set_cookie(
        key="ipg-access-token",
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="ipg-refresh-token",
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies."""
    response.delete_cookie(key="ipg-access-token", path="/")
    response.delete_cookie(key="ipg-refresh-token", path="/api/v1/auth")


@router.post("/register", response_model=UserView, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,  # noqa: ARG001
    *,
    user: UserCreate,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
) -> UserView:
    """Register a new user."""
    new_user = await auth_controller.register(user)
    return UserView.model_validate(new_user)


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,  # noqa: ARG001
    response: Response,
    *,
    login_request: LoginRequest,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Login and get JWT token pair with user data."""
    result = await auth_controller.login(login_request.email, login_request.password)
    _set_auth_cookies(response, result.access_token, result.refresh_token, settings)
    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=result.user,
    )


@router.post("/refresh", response_model=TokenPairResponse)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    response: Response,
    *,
    refresh_token: str | None = None,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    """Refresh access token using refresh token (from param or cookie)."""
    effective_token = refresh_token or request.cookies.get("ipg-refresh-token")
    if not effective_token:
        raise InvalidTokenError("No refresh token provided")

    payload = auth_controller.decode_token(effective_token)
    tokens = auth_controller.create_token_pair(payload.sub, payload.email)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token, settings)
    return tokens


@router.get("/me", response_model=UserView)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserView:
    """Get current authenticated user from token."""
    return UserView.model_validate(current_user)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Logout by clearing auth cookies."""
    _clear_auth_cookies(response)
    return {"status": "ok"}
