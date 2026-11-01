"""Route-level tests for the auth endpoints (/api/v1/auth)."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.auth import AuthController
from majlisna.api.models.table import User
from majlisna.api.schemas.auth import LoginResult, LoginUserData, TokenPairResponse
from majlisna.api.schemas.error import (
    InvalidCredentialsError,
    InvalidTokenError,
    SessionRevokedError,
    UserAlreadyExistsError,
    UsernameAlreadyTakenError,
)
from majlisna.api.schemas.social_auth import SocialLoginResult, SocialLoginUserData
from majlisna.dependencies import get_auth_controller, get_current_user, get_social_auth_service

# ========== Register ==========


def test_register_success(test_app: FastAPI, client: TestClient):
    """Registering with valid data returns 201 and all UserView fields."""
    # Arrange
    user_id = uuid.uuid4()
    mock_controller = Mock(spec=AuthController)
    mock_controller.register = AsyncMock(
        return_value=User(
            id=user_id,
            username="testuser",
            email_address="test@example.com",
            country="FRA",
            password="hashedpassword123",
        )
    )
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email_address": "test@example.com",
            "password": "securepassword",
            "country": "FRA",
        },
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == str(user_id)
    assert data["username"] == "testuser"
    assert data["email_address"] == "test@example.com"
    assert data["country"] == "FRA"
    assert "password" not in data

    test_app.dependency_overrides.clear()


def test_register_taken_username_is_a_translatable_409(test_app: FastAPI, client: TestClient):
    """A taken username answers 409 with its own error key, which the register form shows."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.register = AsyncMock(side_effect=UsernameAlreadyTakenError(username="admin"))
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "email_address": "fresh@example.com", "password": "securepassword"},
    )

    # Assert
    assert response.status_code == 409
    data = response.json()
    assert data["error"] == "UsernameAlreadyTakenError"
    assert data["error_key"] == "errors.api.usernameAlreadyTaken"
    assert data["error_params"] == {"username": "admin"}
    test_app.dependency_overrides.clear()


def test_register_duplicate_email(test_app: FastAPI, client: TestClient):
    """Registering with an already-used email returns 409 Conflict."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.register = AsyncMock(side_effect=UserAlreadyExistsError(email_address="taken@example.com"))
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email_address": "taken@example.com",
            "password": "securepassword",
        },
    )

    # Assert
    assert response.status_code == 409
    data = response.json()
    assert data["error"] == "UserAlreadyExistsError"
    assert data["error_key"] == "errors.api.userAlreadyExists"
    assert "taken@example.com" in data["details"]["email_address"]

    test_app.dependency_overrides.clear()


def test_register_validation_error(test_app: FastAPI, client: TestClient):
    """Registering with missing required fields returns 422."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/register",
        json={},
    )

    # Assert
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "ValidationError"
    assert data["error_key"] == "errors.api.validation"

    test_app.dependency_overrides.clear()


def test_register_invalid_country(test_app: FastAPI):
    """Registering with an invalid country code is a translatable 422, never a 500.

    The country validator used to raise a ``ValueError``, whose exception object landed
    in the error's ``ctx``; the validation handler could not serialise it and the general
    handler answered 500 (this test pinned that). It now raises a ``PydanticCustomError``
    (models/user.py). ``raise_server_exceptions=False`` so a regression to a 500 is seen
    as a status, not raised.
    """
    # Arrange
    mock_controller = Mock(spec=AuthController)
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller
    no_raise_client = TestClient(test_app, raise_server_exceptions=False)

    # Act
    response = no_raise_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email_address": "test@example.com",
            "password": "securepassword",
            "country": "XYZ",
        },
    )

    # Assert
    assert response.status_code == 422
    body = response.json()
    assert body["error_key"] == "errors.api.validation"
    assert [error["loc"][-1] for error in body["details"]] == ["country"]
    mock_controller.register.assert_not_called()

    test_app.dependency_overrides.clear()


# ========== Login ==========


def test_login_success(test_app: FastAPI, client: TestClient):
    """Logging in with valid credentials returns 200 and all LoginResponse fields."""
    # Arrange
    user_id = uuid.uuid4()
    mock_controller = Mock(spec=AuthController)
    mock_controller.login = AsyncMock(
        return_value=LoginResult(
            access_token="access.jwt.token",
            refresh_token="refresh.jwt.token",
            expires_in=3600,
            user=LoginUserData(
                id=str(user_id),
                username="testuser",
                email="test@example.com",
            ),
        )
    )
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "securepassword",
        },
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "access.jwt.token"
    # Review INT-06 (SEC F13): the refresh token travels in the httpOnly cookie only — a
    # script in the page must not be able to read a long-lived one out of a body.
    assert "refresh_token" not in data
    assert response.cookies.get("majlisna-refresh-token") == "refresh.jwt.token"
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] == str(user_id)
    assert data["user"]["username"] == "testuser"
    assert data["user"]["email"] == "test@example.com"

    mock_controller.login.assert_awaited_once_with("test@example.com", "securepassword")

    test_app.dependency_overrides.clear()


def test_login_wrong_password(test_app: FastAPI, client: TestClient):
    """Logging in with wrong password returns 401 Unauthorized."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.login = AsyncMock(side_effect=InvalidCredentialsError(email="test@example.com"))
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "wrongpassword",
        },
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "InvalidCredentialsError"
    assert data["error_key"] == "errors.api.invalidCredentials"

    test_app.dependency_overrides.clear()


def test_login_nonexistent_email(test_app: FastAPI, client: TestClient):
    """Logging in with a non-existent email returns 401 Unauthorized."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.login = AsyncMock(side_effect=InvalidCredentialsError(email="nobody@example.com"))
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nobody@example.com",
            "password": "somepassword",
        },
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "InvalidCredentialsError"
    assert data["error_key"] == "errors.api.invalidCredentials"

    test_app.dependency_overrides.clear()


def test_login_validation_error(test_app: FastAPI, client: TestClient):
    """Logging in with missing fields returns 422."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/login",
        json={},
    )

    # Assert
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "ValidationError"
    assert data["error_key"] == "errors.api.validation"

    test_app.dependency_overrides.clear()


# ========== Refresh Token ==========


def test_refresh_token_success(test_app: FastAPI, client: TestClient):
    """The route hands the presented token to the controller and returns the new pair, as cookies too."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.refresh_session = AsyncMock(
        return_value=TokenPairResponse(
            access_token="new.access.token",
            refresh_token="new.refresh.token",
            expires_in=3600,
        )
    )
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "old.refresh.token"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "new.access.token"
    assert "refresh_token" not in data
    assert response.cookies.get("majlisna-refresh-token") == "new.refresh.token"

    mock_controller.refresh_session.assert_awaited_once_with("old.refresh.token")

    test_app.dependency_overrides.clear()


def test_refresh_token_falls_back_to_the_cookie(test_app: FastAPI, client: TestClient):
    """No body: the httpOnly refresh cookie is the token (the browser never sees it)."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.refresh_session = AsyncMock(
        return_value=TokenPairResponse(access_token="a", refresh_token="r", expires_in=900)
    )
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller
    client.cookies.set("majlisna-refresh-token", "cookie.refresh.token")

    # Act
    response = client.post("/api/v1/auth/refresh")

    # Assert
    assert response.status_code == 200
    mock_controller.refresh_session.assert_awaited_once_with("cookie.refresh.token")
    test_app.dependency_overrides.clear()


def test_refresh_token_invalid(test_app: FastAPI, client: TestClient):
    """Refreshing with an invalid token returns 401 Unauthorized."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.refresh_session = AsyncMock(side_effect=InvalidTokenError())
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.token.here"},
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "InvalidTokenError"
    assert data["error_key"] == "errors.api.invalidToken"

    test_app.dependency_overrides.clear()


def test_refresh_of_a_revoked_session_is_a_translatable_401(test_app: FastAPI, client: TestClient):
    """The client reads errors.api.sessionRevoked as "you were signed out" (not a plain expiry)."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.refresh_session = AsyncMock(side_effect=SessionRevokedError())
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

    # Act
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "reused.refresh.token"})

    # Assert
    assert response.status_code == 401
    assert response.json()["error_key"] == "errors.api.sessionRevoked"
    test_app.dependency_overrides.clear()


# ========== Logout ==========


def test_logout_revokes_the_presented_session_and_clears_the_cookies(test_app: FastAPI, client: TestClient):
    """The bearer access token and the refresh cookie both reach the controller."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.logout = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller
    client.cookies.set("majlisna-refresh-token", "cookie.refresh.token")

    # Act
    response = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer bearer.access.token"})

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_controller.logout.assert_awaited_once_with(
        access_token="bearer.access.token", refresh_token="cookie.refresh.token"
    )
    cleared = " ".join(response.headers.get_list("set-cookie"))
    assert 'majlisna-access-token=""' in cleared
    assert 'majlisna-refresh-token=""' in cleared
    test_app.dependency_overrides.clear()


# ========== The access token must name one account, by both claims ==========


@pytest.mark.asyncio
async def test_access_token_is_rejected_when_sub_and_email_disagree(auth_controller: AuthController, create_user):
    """Resolving the caller on `email` alone let a token outlive its account.

    `sub` was decoded and never looked at, so a token stayed valid across a
    delete-and-re-register of the same address: whoever next registered that
    mailbox inherited every session still holding the old token. `/auth/refresh`
    had always checked this; the request path had not.
    """
    # Arrange — a real, well-signed token whose `sub` names another user than the row
    # its `email` resolves to (no decode_token mock: TQ-01)
    await create_user(username="newowner", email="reused@example.com")
    token = auth_controller.create_access_token(str(uuid.uuid4()), "reused@example.com")
    request = Mock(cookies={})

    # Act / Assert
    with pytest.raises(InvalidTokenError):
        await get_current_user(request, token, auth_controller)


@pytest.mark.asyncio
async def test_access_token_is_accepted_when_both_claims_agree(auth_controller: AuthController, create_user):
    """The ordinary path is unchanged."""
    # Arrange
    owner = await create_user(username="owner", email="owner@example.com")
    user_id = owner.id
    token = auth_controller.create_access_token(str(user_id), owner.email_address)
    request = Mock(cookies={})

    # Act
    user = await get_current_user(request, token, auth_controller)

    # Assert
    assert user.id == user_id


# ========== Google sign-in ==========


def _no_google() -> Mock:
    """The Google service, unused: the controller's social_login is mocked."""
    return Mock()


def test_social_login_sets_the_refresh_cookie_and_keeps_it_out_of_the_body(test_app: FastAPI, client: TestClient):
    """Review INT-06: like login and refresh, the Google sign-in answered the refresh token in its JSON."""
    # Arrange
    mock_controller = Mock(spec=AuthController)
    mock_controller.social_login = AsyncMock(
        return_value=SocialLoginResult(
            access_token="g.access",
            refresh_token="g.refresh",
            expires_in=900,
            is_new_user=False,
            user=SocialLoginUserData(id=str(uuid.uuid4()), username="g", email="g@gmail.com"),
        )
    )
    test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_social_auth_service] = _no_google

    # Act
    response = client.post("/api/v1/auth/social/login", json={"provider": "google", "access_token": "google-token"})

    # Assert
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["access_token"] == "g.access"
    assert "refresh_token" not in data
    assert response.cookies.get("majlisna-refresh-token") == "g.refresh"

    test_app.dependency_overrides.clear()
