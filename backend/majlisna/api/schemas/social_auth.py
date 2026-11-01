"""Schemas for social authentication (Google Sign-In)."""

from pydantic import Field

from majlisna.api.schemas.shared import BaseModel


class SocialLoginRequest(BaseModel):
    """Request schema for social login endpoint."""

    provider: str = Field(
        ...,
        description="Social auth provider: 'google'",
        pattern="^google$",
    )
    access_token: str = Field(
        ...,
        description="OAuth2 access token from Google (web custom button flow)",
    )


class SocialLoginResponse(BaseModel):
    """Response schema for social login endpoint (the refresh token is the httpOnly cookie)."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")
    is_new_user: bool = Field(..., description="Whether a new account was created")
    user: "SocialLoginUserData" = Field(..., description="User data")


class SocialLoginResult(SocialLoginResponse):
    """Internal result of a Google sign-in: the response plus the refresh token the route
    sets as the httpOnly cookie, never in the body (review INT-06, SEC F13)."""

    refresh_token: str = Field(..., description="JWT refresh token")


class SocialLoginUserData(BaseModel):
    """User data included in social login response."""

    id: str
    username: str
    email: str


class SocialTokenPayload(BaseModel):
    """Verified payload extracted from Google's userinfo API."""

    sub: str = Field(..., description="Google's unique subject identifier")
    email: str = Field(..., description="User's email address")
    email_verified: bool = Field(default=False, description="Whether Google verified the email")
    first_name: str | None = Field(default=None, description="User's first name")
    last_name: str | None = Field(default=None, description="User's last name")
    picture: str | None = Field(default=None, description="Profile picture URL")
