from majlisna.api.schemas.shared import BaseModel


class TokenPayload(BaseModel):
    """JWT token payload.

    `type` distinguishes access tokens from refresh tokens. It is optional so
    that legacy tokens (issued before token typing) still decode, but the
    consumers that care (get_current_user, /refresh, Socket.IO) pass an
    `expected_type` to `decode_token` and reject a mismatch.
    """

    sub: str  # user_id
    email: str
    exp: int
    type: str | None = None


class TokenPairResponse(BaseModel):
    """Response with access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginUserData(BaseModel):
    """User data included in login response."""

    id: str
    username: str
    email: str


class LoginResponse(BaseModel):
    """Login response with tokens and user data."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: LoginUserData


class LoginResult(BaseModel):
    """Internal result of login: tokens + user data."""

    access_token: str
    refresh_token: str
    user: LoginUserData


class LoginRequest(BaseModel):
    """Login request body."""

    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str
