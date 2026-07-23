import pycountry
import pydantic
from pydantic import EmailStr
from sqlmodel import AutoString, Field

from majlisna.api.models.shared import DBModel


class UserBase(DBModel):
    username: str = Field(default=None, index=True, min_length=3)
    email_address: EmailStr = Field(unique=True, index=True, sa_type=AutoString)
    country: str | None = None
    email_verified: bool = Field(default=False)
    bio: str | None = Field(default=None, max_length=200)
    google_sub: str | None = Field(default=None, max_length=255, index=True, unique=True)
    auth_provider: str = Field(default="email", max_length=20)
    profile_picture_url: str | None = Field(default=None)

    @pydantic.field_validator("country")
    @classmethod
    def country_code(cls, v: str):
        """
        It checks that the country code is a valid 3-letter country code
        :param v: The value to be validated
        :return: The country code
        """
        if v and pycountry.countries.get(alpha_3=v.upper()) is None:
            raise ValueError("Country must be a valid 3-letter country code")
        return v


class UserCreate(UserBase):
    password: str


class UserUpdate(DBModel):
    """Fields a user may edit on their own profile.

    Deliberately does NOT inherit UserBase: that would let a client PATCH
    security-sensitive fields (email_verified, email_address, auth_provider,
    google_sub) via mass assignment. Only these safe fields are editable.
    """

    username: str | None = Field(default=None, min_length=3)
    country: str | None = None
    bio: str | None = Field(default=None, max_length=200)
    profile_picture_url: str | None = None

    @pydantic.field_validator("country")
    @classmethod
    def country_code(cls, v: str | None) -> str | None:
        """Validate the country is a real 3-letter ISO code."""
        if v and pycountry.countries.get(alpha_3=v.upper()) is None:
            raise ValueError("Country must be a valid 3-letter country code")
        return v


class UserUpdatePassword(DBModel):
    current_password: str
    new_password: str
