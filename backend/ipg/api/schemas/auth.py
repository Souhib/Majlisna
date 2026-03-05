from ipg.api.schemas.shared import BaseModel


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # user_id
    email: str
    exp: int


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
