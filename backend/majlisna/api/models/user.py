import re
from urllib.parse import urlsplit

import pycountry
import pydantic
from pydantic import EmailStr
from pydantic import Field as PydanticField
from pydantic_core import PydanticCustomError
from sqlmodel import AutoString, Field

from majlisna.api.constants import (
    ALLOWED_AVATAR_HOST_SUFFIXES,
    AVATAR_HOST_PATTERN,
    AVATAR_URL_MAX_LENGTH,
    AVATAR_URL_SCHEME,
    BCRYPT_MAX_PASSWORD_BYTES,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    USERNAME_PATTERN,
)
from majlisna.api.models.shared import DBModel
from majlisna.api.schemas.error import InvalidAvatarUrlError, PasswordTooLongError

_AVATAR_HOST = re.compile(AVATAR_HOST_PATTERN)


def _invalid_country() -> PydanticCustomError:
    """The country check's error: a 422. Not a ``ValueError``, whose exception object
    lands in the error's ``ctx``, which the app's validation handler cannot serialise —
    every unknown country answered a 500."""
    return PydanticCustomError("invalid_country", "Country must be a valid 3-letter country code")


def password_fits_bcrypt(password: str) -> bool:
    """Whether bcrypt can take ``password``: at most ``BCRYPT_MAX_PASSWORD_BYTES`` of UTF-8.

    bcrypt's limit is in BYTES. bcrypt 5 raises past it (a 500 at registration, a 500 at
    login), and the schemas counted characters: 40 Arabic letters are 80 bytes (SEC F10).
    """
    return len(password.encode("utf-8")) <= BCRYPT_MAX_PASSWORD_BYTES


def refuse_password_over_bcrypt_limit(value: object) -> object:
    """The password fields' ``mode="before"`` check: ``PasswordTooLongError``, a translated 400.

    Before the field's own constraints on purpose, so a password too long in bytes gets
    this answer whether or not it is also over ``PASSWORD_MAX_LENGTH`` characters (which
    stays on the field for the OpenAPI schema). Anything but a str is left to the field.
    """
    if isinstance(value, str) and not password_fits_bcrypt(value):
        raise PasswordTooLongError()
    return value


def avatar_url_is_allowed(url: str) -> bool:
    """An https URL on Google's avatar CDN (``ALLOWED_AVATAR_HOST_SUFFIXES``), bounded (SEC F15).

    Any string used to be stored and shown on the public profile: a third-party image
    tracks every visitor's address, and ``javascript:`` or a 20 000-character value went
    in too. Strict on purpose — the UI never sets it, Google sign-in does:

    - at most ``AVATAR_URL_MAX_LENGTH`` characters, no whitespace or control character,
      and no backslash: a browser reads a backslash as a slash, so ``evil.example``
      followed by a backslash, ``@`` and the CDN's host is evil's URL to a browser while
      ``urlsplit`` sees the CDN's;
    - the scheme is https, with no userinfo and no explicit port;
    - the host is plain DNS labels ending in an allowed suffix, so ``evilgoogleusercontent.com``
      and ``googleusercontent.com.evil.example`` are refused.
    """
    if len(url) > AVATAR_URL_MAX_LENGTH or "\\" in url:
        return False
    if any(character.isspace() or not character.isprintable() for character in url):
        return False
    host = _plain_https_host(url)
    return host is not None and any(host.endswith(suffix) for suffix in ALLOWED_AVATAR_HOST_SUFFIXES)


def _plain_https_host(url: str) -> str | None:
    """The host of an https URL without userinfo or explicit port, if it is plain DNS labels."""
    parts = urlsplit(url)
    if parts.scheme != AVATAR_URL_SCHEME or "@" in parts.netloc:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname or ""
    if port is not None or not _AVATAR_HOST.fullmatch(host):
        return None
    return host


class UserBase(DBModel):
    username: str = Field(default=None, index=True, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH)
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
            raise _invalid_country()
        return v


class UserCreate(DBModel):
    """Fields a client may provide at registration.

    Deliberately does NOT inherit UserBase: that would let a client set
    security-sensitive fields (email_verified, auth_provider, google_sub) via
    mass assignment — e.g. self-verify their email or pre-empt an OAuth link.
    """

    username: str = PydanticField(
        min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN
    )
    email_address: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    country: str | None = None
    bio: str | None = Field(default=None, max_length=200)

    _password_fits_bcrypt = pydantic.field_validator("password", mode="before")(refuse_password_over_bcrypt_limit)

    @pydantic.field_validator("country")
    @classmethod
    def country_code(cls, v: str | None) -> str | None:
        """Validate the country is a real 3-letter ISO code."""
        if v and pycountry.countries.get(alpha_3=v.upper()) is None:
            raise _invalid_country()
        return v


class UserUpdate(DBModel):
    """Fields a user may edit on their own profile.

    Deliberately does NOT inherit UserBase: that would let a client PATCH
    security-sensitive fields (email_verified, email_address, auth_provider,
    google_sub) via mass assignment. Only these safe fields are editable.
    """

    # Same shape rule as registration (UserCreate): no whitespace, no markup or "@" —
    # a rename to "admin " would otherwise pass the case-insensitive taken check.
    username: str | None = PydanticField(
        default=None, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN
    )
    country: str | None = None
    bio: str | None = Field(default=None, max_length=200)
    # Never set by the UI (Google sign-in fills it); bounded by `avatar_url_is_allowed`.
    profile_picture_url: str | None = Field(default=None, max_length=AVATAR_URL_MAX_LENGTH)

    @pydantic.field_validator("profile_picture_url", mode="before")
    @classmethod
    def avatar_on_googles_cdn(cls, v: object) -> object:
        """``InvalidAvatarUrlError`` (a translated 400) for anything ``avatar_url_is_allowed`` refuses.

        Before the field's ``max_length``, so an over-long URL gets the same answer. None
        clears the picture.
        """
        if isinstance(v, str) and not avatar_url_is_allowed(v):
            raise InvalidAvatarUrlError()
        return v

    @pydantic.field_validator("country")
    @classmethod
    def country_code(cls, v: str | None) -> str | None:
        """Validate the country is a real 3-letter ISO code."""
        if v and pycountry.countries.get(alpha_3=v.upper()) is None:
            raise _invalid_country()
        return v


class UserUpdatePassword(DBModel):
    """A password change: both passwords are checked in bytes (SEC F10)."""

    current_password: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    _passwords_fit_bcrypt = pydantic.field_validator("current_password", "new_password", mode="before")(
        refuse_password_over_bcrypt_limit
    )
