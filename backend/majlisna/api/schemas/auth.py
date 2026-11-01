from pydantic import Field

from majlisna.api.constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from majlisna.api.schemas.shared import BaseModel


class TokenPayload(BaseModel):
    """JWT token payload.

    `type` distinguishes access tokens from refresh tokens. It is optional so
    that legacy tokens (issued before token typing) still decode, but the
    consumers that care (get_current_user, /refresh, Socket.IO) pass an
    `expected_type` to `decode_token` and reject a mismatch.

    `sid` names the server-side session (`AuthSession.id`) on both tokens, `jti` the
    single-use identity of a refresh token, `iat` the instant of issue (SEC F01). All
    three are optional only so that tokens minted before sessions existed still decode:
    a legacy access token is accepted until it expires, a legacy refresh token is
    upgraded into a session (`AuthController.refresh_session`).
    """

    sub: str  # user_id
    email: str
    exp: int
    type: str | None = None
    sid: str | None = None
    jti: str | None = None
    iat: int | None = None


class TokenPairResponse(BaseModel):
    """A fresh pair, inside the server only: the route sets the refresh token as a cookie.

    Never a response body (review INT-06, SEC F13): the refresh token travels in the
    httpOnly cookie alone, so a script running in the page cannot read a long-lived
    one. The body is ``AccessTokenResponse``.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Access token lifetime in seconds — clients schedule refresh from this.


class AccessTokenResponse(BaseModel):
    """What ``/auth/refresh`` answers: the access token; the refresh token is in the httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Access token lifetime in seconds — clients schedule refresh from this.


class LoginUserData(BaseModel):
    """User data included in login response."""

    id: str
    username: str
    email: str


class LoginResponse(BaseModel):
    """Login response: the access token and user data (the refresh token is the httpOnly cookie)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Access token lifetime in seconds.
    user: LoginUserData


class LoginResult(BaseModel):
    """Internal result of login: tokens + user data."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: LoginUserData


class LoginRequest(BaseModel):
    """Login request body."""

    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str
