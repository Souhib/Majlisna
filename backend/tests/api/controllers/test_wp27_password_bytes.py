"""WP-27, SEC F10: bcrypt's limit is 72 BYTES of UTF-8, and bcrypt 5 refuses anything longer.

``hashpw`` / ``checkpw`` raise ``ValueError("password cannot be longer than 72 bytes")``,
while the schemas counted characters (``PASSWORD_MAX_LENGTH`` = 72). So:

- a login with a long password (known address or not) was an unauthenticated 500,
  logged at ERROR and forwarded to the error tracker;
- 40 Arabic letters (80 bytes) passed registration's validation and then failed at
  hashing — a 500 — so an Arabic or French player with a long password could not
  register, change or reset it.

Now: ``verify_password`` answers False (a login is a 401), ``get_password_hash`` raises
``PasswordTooLongError``, and every password field a client sends to register, change
or confirm a deletion checks the byte length (a translated 400). Ported from the
security verification probes (``test_phase_a_ratelimited.py``, F10).
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import BCRYPT_MAX_PASSWORD_BYTES
from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.shared import async_get_password_hash, get_password_hash, verify_password
from majlisna.api.models.table import User
from majlisna.api.models.user import UserCreate, UserUpdatePassword
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.error import PasswordTooLongError
from majlisna.api.schemas.user import DeleteAccountRequest
from majlisna.dependencies import get_email_service, get_session, get_settings
from majlisna.settings import Settings

# 40 characters, 80 bytes of UTF-8: under the old character limit, over bcrypt's.
ARABIC_40_CHARS = "كلمة" * 10
ASCII_80_BYTES = "a" * 80
ASCII_72_BYTES = "b" * BCRYPT_MAX_PASSWORD_BYTES
REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"


def test_the_fixtures_straddle_the_byte_limit():
    """The premise: the Arabic password is short in characters and long in bytes."""
    assert len(ARABIC_40_CHARS) == 40
    assert len(ARABIC_40_CHARS.encode("utf-8")) == 80
    assert len(ASCII_72_BYTES.encode("utf-8")) == BCRYPT_MAX_PASSWORD_BYTES


def _no_email() -> AsyncMock:
    """An email service that sends nothing (a dependency override takes no arguments)."""
    return AsyncMock()


@pytest_asyncio.fixture(name="api")
async def get_api(
    test_app: FastAPI, session: AsyncSession, test_settings: Settings
) -> AsyncGenerator[httpx.AsyncClient]:
    """The real app on the test database; no email leaves; fresh rate-limit budgets."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    test_app.dependency_overrides[get_email_service] = _no_email
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    limiter.reset()
    test_app.dependency_overrides.clear()


# ─── The primitives ───────────────────────────────────────────────────────────


def test_verify_password_answers_false_for_a_password_over_72_bytes():
    """No stored hash can be of such a password, so it simply does not match."""
    # Prepare
    stored = get_password_hash("short-and-known")

    # Act
    long_ascii = verify_password(ASCII_80_BYTES, stored)
    long_arabic = verify_password(ARABIC_40_CHARS, stored)

    # Assert
    assert long_ascii is False
    assert long_arabic is False


def test_hashing_a_password_over_72_bytes_is_password_too_long():
    """bcrypt's ValueError used to escape as a 500."""
    # Act / Assert
    with pytest.raises(PasswordTooLongError) as caught:
        get_password_hash(ARABIC_40_CHARS)
    assert caught.value.status_code == 400
    assert caught.value.error_key == "errors.api.passwordTooLong"


async def test_the_async_hash_raises_the_same_error():
    """The thread-pool wrapper every controller uses lets the translated error through."""
    # Act / Assert
    with pytest.raises(PasswordTooLongError):
        await async_get_password_hash(ASCII_80_BYTES)


def test_72_ascii_bytes_still_hash_and_verify():
    """The control: exactly at the limit is fine."""
    # Act
    stored = get_password_hash(ASCII_72_BYTES)

    # Assert
    assert verify_password(ASCII_72_BYTES, stored) is True


# ─── The schemas: a translated 400 before any hashing ─────────────────────────


@pytest.mark.parametrize("password", [ARABIC_40_CHARS, ASCII_80_BYTES])
def test_registration_refuses_a_password_over_72_bytes(password: str):
    """Characters were counted: 40 Arabic letters passed. The byte check also runs
    before the character bound, so 80 ASCII bytes get the same translated answer."""
    # Act / Assert
    with pytest.raises(PasswordTooLongError):
        UserCreate(username="arabic_user", email_address="ar@test.com", password=password)


@pytest.mark.parametrize("field", ["current_password", "new_password"])
def test_a_password_change_refuses_a_password_over_72_bytes(field: str):
    """Both halves of a change: the new one could never be hashed, the current one never matches."""
    # Prepare
    body = {"current_password": "current-pass", "new_password": "new-password"} | {field: ARABIC_40_CHARS}

    # Act / Assert
    with pytest.raises(PasswordTooLongError):
        UserUpdatePassword(**body)


def test_a_deletion_confirmation_refuses_a_password_over_72_bytes():
    # Act / Assert
    with pytest.raises(PasswordTooLongError):
        DeleteAccountRequest(password=ARABIC_40_CHARS)


def test_passwords_at_the_limit_pass_every_schema():
    """The control for the three schemas."""
    # Act
    created = UserCreate(username="ascii_user", email_address="ascii@test.com", password=ASCII_72_BYTES)
    change = UserUpdatePassword(current_password=ASCII_72_BYTES, new_password=ASCII_72_BYTES)
    deletion = DeleteAccountRequest(password=ASCII_72_BYTES)

    # Assert
    assert created.password == ASCII_72_BYTES
    assert change.new_password == ASCII_72_BYTES
    assert deletion.password == ASCII_72_BYTES


# ─── The real stack ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_with_a_password_over_72_bytes_is_a_401(api: httpx.AsyncClient, create_user):
    """Unknown address (the dummy-hash path) and known address alike: 401, never 500."""
    # Prepare
    await create_user(username="known", email="known@test.com", password="password123")

    # Act
    unknown = await api.post(LOGIN_URL, json={"email": "nobody@test.com", "password": ASCII_80_BYTES})
    known = await api.post(LOGIN_URL, json={"email": "known@test.com", "password": ARABIC_40_CHARS})

    # Assert
    assert unknown.status_code == 401
    assert unknown.json()["error_key"] == "errors.api.invalidCredentials"
    assert known.status_code == 401
    assert known.json()["error_key"] == "errors.api.invalidCredentials"


@pytest.mark.asyncio
async def test_registering_40_arabic_characters_is_a_translated_400(api: httpx.AsyncClient, session: AsyncSession):
    """It passed validation and then 500'd at hashing; nothing is created now."""
    # Act
    response = await api.post(
        REGISTER_URL,
        json={"username": "arabic_pw", "email_address": "arabic_pw@test.com", "password": ARABIC_40_CHARS},
    )

    # Assert
    assert response.status_code == 400
    assert response.json()["error_key"] == "errors.api.passwordTooLong"
    assert response.json()["details"] == {"max_bytes": BCRYPT_MAX_PASSWORD_BYTES}
    stored = (await session.exec(select(User).where(User.email_address == "arabic_pw@test.com"))).first()
    assert stored is None


@pytest.mark.asyncio
async def test_registering_72_ascii_bytes_still_works(api: httpx.AsyncClient, session: AsyncSession):
    """The control from the probe: 201, and the password then opens the account."""
    # Act
    response = await api.post(
        REGISTER_URL,
        json={"username": "ascii_pw", "email_address": "ascii_pw@test.com", "password": ASCII_72_BYTES},
    )

    # Assert
    assert response.status_code == 201, response.text
    stored = (await session.exec(select(User).where(User.email_address == "ascii_pw@test.com"))).one()
    assert verify_password(ASCII_72_BYTES, stored.password) is True


@pytest.mark.asyncio
async def test_a_password_change_to_40_arabic_characters_is_a_translated_400(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, create_user
):
    """The change used to pass validation and 500 at hashing; the stored hash is untouched."""
    # Prepare
    user = await create_user(username="changer", email="changer@test.com", password="password123")
    old_hash = user.password
    login = await auth_controller.login("changer@test.com", "password123")

    # Act
    response = await api.patch(
        f"/api/v1/users/{user.id}/password",
        json={"current_password": "password123", "new_password": ARABIC_40_CHARS},
        headers={"Authorization": f"Bearer {login.access_token}"},
    )

    # Assert
    assert response.status_code == 400
    assert response.json()["error_key"] == "errors.api.passwordTooLong"
    session.expunge_all()
    stored = (await session.exec(select(User).where(User.id == user.id))).one()
    assert stored.password == old_hash


@pytest.mark.asyncio
async def test_a_reset_to_40_arabic_characters_is_refused_and_changes_nothing(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """The reset schema still counts characters; the hash refuses, nothing is written."""
    # Prepare
    user = await create_user(username="resetter", email="resetter@test.com", password="password123")
    user_id, old_hash = user.id, user.password
    email_service = AsyncMock()
    await auth_controller.request_password_reset("resetter@test.com", email_service)
    reset_url = email_service.send_password_reset_email.await_args.args[2]
    token = reset_url.split("token=", 1)[1]

    # Act / Assert
    with pytest.raises(PasswordTooLongError):
        await auth_controller.reset_password(token, ARABIC_40_CHARS)
    await session.rollback()
    session.expunge_all()
    stored = (await session.exec(select(User).where(User.id == user_id))).one()
    assert stored.password == old_hash
