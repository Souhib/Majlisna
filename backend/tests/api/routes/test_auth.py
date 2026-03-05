"""Route-level tests for the auth endpoints (/api/v1/auth)."""

import uuid
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.auth import AuthController
from ipg.api.models.table import User
from ipg.api.schemas.auth import LoginResult, LoginUserData, TokenPairResponse, TokenPayload
from ipg.api.schemas.error import InvalidCredentialsError, InvalidTokenError, UserAlreadyExistsError
from ipg.dependencies import get_auth_controller


class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    def test_register_success(self, test_app: FastAPI, client: TestClient):
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

    def test_register_duplicate_email(self, test_app: FastAPI, client: TestClient):
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

    def test_register_validation_error(self, test_app: FastAPI, client: TestClient):
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

    def test_register_invalid_country(self, test_app: FastAPI, client: TestClient):
        """Registering with an invalid country code triggers a validation error.

        The pydantic v2 field_validator on country raises a ValueError which
        FastAPI catches as a RequestValidationError. Due to a serialization
        issue (ValueError in ctx is not JSON-serializable), the app's
        validation handler falls through to the general exception handler,
        resulting in a 500. We use raise_server_exceptions=False to capture it.
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
        assert response.status_code == 500

        test_app.dependency_overrides.clear()


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    def test_login_success(self, test_app: FastAPI, client: TestClient):
        """Logging in with valid credentials returns 200 and all LoginResponse fields."""
        # Arrange
        user_id = uuid.uuid4()
        mock_controller = Mock(spec=AuthController)
        mock_controller.login = AsyncMock(
            return_value=LoginResult(
                access_token="access.jwt.token",
                refresh_token="refresh.jwt.token",
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
        assert data["refresh_token"] == "refresh.jwt.token"
        assert data["token_type"] == "bearer"
        assert data["user"]["id"] == str(user_id)
        assert data["user"]["username"] == "testuser"
        assert data["user"]["email"] == "test@example.com"

        mock_controller.login.assert_awaited_once_with("test@example.com", "securepassword")

        test_app.dependency_overrides.clear()

    def test_login_wrong_password(self, test_app: FastAPI, client: TestClient):
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

    def test_login_nonexistent_email(self, test_app: FastAPI, client: TestClient):
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

    def test_login_validation_error(self, test_app: FastAPI, client: TestClient):
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


class TestRefreshToken:
    """Tests for POST /api/v1/auth/refresh."""

    def test_refresh_token_success(self, test_app: FastAPI, client: TestClient):
        """Refreshing with a valid token returns 200 and all TokenPairResponse fields."""
        # Arrange
        mock_controller = Mock(spec=AuthController)
        mock_controller.decode_token = Mock(
            return_value=TokenPayload(
                sub="user-123",
                email="test@example.com",
                exp=9999999999,
            )
        )
        mock_controller.create_token_pair = Mock(
            return_value=TokenPairResponse(
                access_token="new.access.token",
                refresh_token="new.refresh.token",
            )
        )
        test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/auth/refresh",
            params={"refresh_token": "old.refresh.token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new.access.token"
        assert data["refresh_token"] == "new.refresh.token"
        assert data["token_type"] == "bearer"

        mock_controller.decode_token.assert_called_once_with("old.refresh.token")
        mock_controller.create_token_pair.assert_called_once_with("user-123", "test@example.com")

        test_app.dependency_overrides.clear()

    def test_refresh_token_invalid(self, test_app: FastAPI, client: TestClient):
        """Refreshing with an invalid token returns 401 Unauthorized."""
        # Arrange
        mock_controller = Mock(spec=AuthController)
        mock_controller.decode_token = Mock(side_effect=InvalidTokenError())
        test_app.dependency_overrides[get_auth_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/auth/refresh",
            params={"refresh_token": "invalid.token.here"},
        )

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "InvalidTokenError"
        assert data["error_key"] == "errors.api.invalidToken"

        test_app.dependency_overrides.clear()
