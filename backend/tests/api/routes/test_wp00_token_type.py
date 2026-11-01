"""TQ-01, HTTP half: a refresh token never authenticates an ordinary request.

Every earlier test of ``get_current_user`` replaced ``decode_token`` with a Mock that
answered ``type="access"``, so removing ``expected_type=TOKEN_TYPE_ACCESS`` passed the
whole suite. These go through the real app with real JWTs and the test database.

(The package spec says ``GET /api/v1/users/me``; there is no such route — the
authenticated "who am I" read is ``GET /api/v1/auth/me``.)
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.user import UserController
from majlisna.api.models.table import User
from majlisna.dependencies import ACCESS_TOKEN_COOKIE, get_session, get_settings
from majlisna.settings import Settings

ME_URL = "/api/v1/auth/me"


@pytest_asyncio.fixture(name="api")
async def get_api(
    test_app: FastAPI, session: AsyncSession, test_settings: Settings
) -> AsyncGenerator[httpx.AsyncClient]:
    """An async client on the real app, on the test database and the test JWT key."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture(name="member")
async def get_member(create_user) -> User:
    return await create_user(username="member", email="member@test.com")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_an_access_token_reads_me(api: httpx.AsyncClient, auth_controller: AuthController, member: User):
    """The control: the same account, with the right kind of token, is answered."""
    # Prepare
    token = auth_controller.create_access_token(str(member.id), member.email_address)

    # Act
    response = await api.get(ME_URL, headers=_bearer(token))

    # Assert
    assert response.status_code == 200
    assert response.json()["id"] == str(member.id)


@pytest.mark.asyncio
async def test_a_refresh_token_as_bearer_is_refused(
    api: httpx.AsyncClient, auth_controller: AuthController, member: User
):
    """A real refresh token of a real account: 401, the standard envelope, no user data."""
    # Prepare
    token = auth_controller.create_refresh_token(str(member.id), member.email_address)

    # Act
    response = await api.get(ME_URL, headers=_bearer(token))

    # Assert
    assert response.status_code == 401
    body = response.json()
    assert body["error_key"] == "errors.api.invalidToken"
    assert "email_address" not in body


@pytest.mark.asyncio
async def test_a_refresh_token_in_the_access_cookie_is_refused(
    api: httpx.AsyncClient, auth_controller: AuthController, member: User
):
    """The cookie path takes precedence over the header, and checks the type too."""
    # Prepare
    token = auth_controller.create_refresh_token(str(member.id), member.email_address)
    api.cookies.set(ACCESS_TOKEN_COOKIE, token)

    # Act
    response = await api.get(ME_URL)

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_an_old_token_of_a_re_registered_address_is_refused(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, member: User, create_user
):
    """SEC F09 on HTTP: the address now belongs to another account; the old token's
    ``sub`` no longer matches, so it reads nothing."""
    # Prepare
    old_token = auth_controller.create_access_token(str(member.id), member.email_address)
    address = member.email_address
    await UserController(session).delete_user(member.id)
    newcomer = await create_user(username="newcomer", email=address)

    # Act
    old = await api.get(ME_URL, headers=_bearer(old_token))
    fresh = await api.get(ME_URL, headers=_bearer(auth_controller.create_access_token(str(newcomer.id), address)))

    # Assert
    assert old.status_code == 401
    assert fresh.status_code == 200
    assert fresh.json()["id"] == str(newcomer.id)


@pytest.mark.asyncio
async def test_a_token_whose_sub_names_no_account_is_refused(
    api: httpx.AsyncClient, auth_controller: AuthController, member: User
):
    """A real, well-signed token whose two claims disagree."""
    # Prepare
    token = auth_controller.create_access_token(str(uuid4()), member.email_address)

    # Act
    response = await api.get(ME_URL, headers=_bearer(token))

    # Assert
    assert response.status_code == 401
