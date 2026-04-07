import os
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from majlisna.api.controllers.auth import AuthController
from majlisna.api.models.table import User
from majlisna.api.models.user import UserCreate
from majlisna.api.models.view import UserView
from majlisna.api.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenPairResponse,
    VerifyEmailRequest,
)
from majlisna.api.schemas.common import StatusMessageResponse, StatusResponse
from majlisna.api.schemas.error import InvalidTokenError
from majlisna.api.schemas.social_auth import SocialLoginRequest, SocialLoginResponse
from majlisna.api.services.email import EmailService
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.dependencies import (
    get_auth_controller,
    get_current_user,
    get_email_service,
    get_settings,
    get_social_auth_service,
)
from majlisna.settings import Settings

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
    use_secure = settings.frontend_url.startswith("https://")
    response.set_cookie(
        key="majlisna-access-token",
        value=access_token,
        httponly=True,
        secure=use_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="majlisna-refresh-token",
        value=refresh_token,
        httponly=True,
        secure=use_secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies."""
    response.delete_cookie(key="majlisna-access-token", path="/")
    response.delete_cookie(key="majlisna-refresh-token", path="/api/v1/auth")


@router.post("/register", response_model=UserView, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,  # noqa: ARG001
    *,
    user: UserCreate,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> UserView:
    """Register a new user."""
    new_user = await auth_controller.register(user)
    await auth_controller.send_verification_email(new_user, email_service)
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
    effective_token = refresh_token or request.cookies.get("majlisna-refresh-token")
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
async def logout(response: Response) -> StatusResponse:
    """Logout by clearing auth cookies."""
    _clear_auth_cookies(response)
    return StatusResponse(status="ok")


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,  # noqa: ARG001
    *,
    body: ForgotPasswordRequest,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> StatusMessageResponse:
    """Request a password reset email."""
    await auth_controller.request_password_reset(body.email, email_service)
    return StatusMessageResponse(status="ok", message="If the email exists, a reset link has been sent.")


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,  # noqa: ARG001
    *,
    body: ResetPasswordRequest,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
) -> StatusMessageResponse:
    """Reset password using a valid token."""
    await auth_controller.reset_password(body.token, body.new_password)
    return StatusMessageResponse(status="ok", message="Password has been reset successfully.")


@router.post("/verify-email")
async def verify_email(
    *,
    body: VerifyEmailRequest,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
) -> StatusMessageResponse:
    """Verify email address using a valid token."""
    await auth_controller.verify_email(body.token)
    return StatusMessageResponse(status="ok", message="Email verified successfully.")


@router.post("/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,  # noqa: ARG001
    *,
    body: ResendVerificationRequest,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> StatusMessageResponse:
    """Resend email verification."""
    await auth_controller.resend_verification(body.email, email_service)
    return StatusMessageResponse(
        status="ok", message="If the email exists and is unverified, a verification link has been sent."
    )


@router.post("/social/login", response_model=SocialLoginResponse)
@limiter.limit("10/minute")
async def social_login(
    request: Request,  # noqa: ARG001
    response: Response,
    *,
    body: SocialLoginRequest,
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
    social_auth_service: Annotated[SocialAuthService, Depends(get_social_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SocialLoginResponse:
    """Authenticate via Google OAuth2."""
    result = await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token=body.access_token,
    )
    _set_auth_cookies(response, result.access_token, result.refresh_token, settings)
    return result
