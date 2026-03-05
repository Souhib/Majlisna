"""Route-level tests for /api/v1/users endpoints."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.user import UserController
from ipg.api.models.table import User
from ipg.api.schemas.error import UserAlreadyExistsError, UserNotFoundError
from ipg.dependencies import get_current_user, get_user_controller


def _make_user(user_id=None, username="JohnDoe", email="john.doe@test.com", country="FRA"):
    """Helper to create a User instance for tests."""
    return User(
        id=user_id or uuid4(),
        username=username,
        email_address=email,
        country=country,
        password="securepassword",
    )


def _override_auth(test_app: FastAPI, user: User):
    """Override get_current_user to return a specific user."""
    test_app.dependency_overrides[get_current_user] = lambda: user


# ========== POST /api/v1/users ==========


def test_create_user_success(test_app: FastAPI, client: TestClient):
    """POST /users with valid data returns 201 and the created UserView."""
    # Arrange
    user_id = uuid4()
    mock_controller = Mock(spec=UserController)
    mock_controller.create_user = AsyncMock(return_value=_make_user(user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/users",
        json={
            "username": "JohnDoe",
            "email_address": "john.doe@test.com",
            "country": "FRA",
            "password": "securepassword",
        },
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(user_id)
    assert body["username"] == "JohnDoe"
    assert body["email_address"] == "john.doe@test.com"
    assert body["country"] == "FRA"
    assert "password" not in body

    test_app.dependency_overrides.clear()


def test_create_user_duplicate_email(test_app: FastAPI, client: TestClient):
    """POST /users with an already-existing email returns 409."""
    # Arrange
    mock_controller = Mock(spec=UserController)
    mock_controller.create_user = AsyncMock(side_effect=UserAlreadyExistsError(email_address="john.doe@test.com"))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/users",
        json={
            "username": "JohnDoe",
            "email_address": "john.doe@test.com",
            "country": "FRA",
            "password": "securepassword",
        },
    )

    # Assert
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "UserAlreadyExistsError"
    assert body["error_key"] == "errors.api.userAlreadyExists"
    assert body["message"] == "An account with this email already exists."
    assert body["details"]["email_address"] == "john.doe@test.com"

    test_app.dependency_overrides.clear()


def test_create_user_validation_error(test_app: FastAPI, client: TestClient):
    """POST /users with an invalid email returns 422 validation error."""
    # Arrange
    mock_controller = Mock(spec=UserController)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/users",
        json={
            "username": "JohnDoe",
            "email_address": "not-an-email",
            "country": "FRA",
            "password": "securepassword",
        },
    )

    # Assert
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "ValidationError"
    assert body["error_key"] == "errors.api.validation"

    test_app.dependency_overrides.clear()


# ========== GET /api/v1/users ==========


def test_get_all_users_success(test_app: FastAPI, client: TestClient):
    """GET /users returns 200 and a list of users."""
    # Arrange
    user_id_1 = uuid4()
    user_id_2 = uuid4()
    auth_user = _make_user(user_id_1)
    mock_controller = Mock(spec=UserController)
    mock_controller.get_users = AsyncMock(
        return_value=[
            _make_user(user_id_1),
            _make_user(user_id_2, username="JaneDoe", email="jane.doe@test.com", country="USA"),
        ]
    )
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.get("/api/v1/users")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == str(user_id_1)
    assert body[0]["username"] == "JohnDoe"
    assert body[0]["email_address"] == "john.doe@test.com"
    assert body[0]["country"] == "FRA"
    assert "password" not in body[0]
    assert body[1]["id"] == str(user_id_2)
    assert body[1]["username"] == "JaneDoe"
    assert body[1]["email_address"] == "jane.doe@test.com"
    assert body[1]["country"] == "USA"
    assert "password" not in body[1]

    test_app.dependency_overrides.clear()


def test_get_all_users_empty(test_app: FastAPI, client: TestClient):
    """GET /users returns 200 and an empty list when no users exist."""
    # Arrange
    auth_user = _make_user()
    mock_controller = Mock(spec=UserController)
    mock_controller.get_users = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.get("/api/v1/users")

    # Assert
    assert response.status_code == 200
    assert response.json() == []

    test_app.dependency_overrides.clear()


def test_get_all_users_unauthenticated(test_app: FastAPI, client: TestClient):
    """GET /users without auth returns 401."""
    # Act
    response = client.get("/api/v1/users")

    # Assert
    assert response.status_code == 401

    test_app.dependency_overrides.clear()


# ========== GET /api/v1/users/{user_id} ==========


def test_get_user_by_id_success(test_app: FastAPI, client: TestClient):
    """GET /users/{id} returns 200 and the requested UserView."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.get_user_by_id = AsyncMock(return_value=_make_user(user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.get(f"/api/v1/users/{user_id}")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user_id)
    assert body["username"] == "JohnDoe"
    assert body["email_address"] == "john.doe@test.com"
    assert body["country"] == "FRA"
    assert "password" not in body

    test_app.dependency_overrides.clear()


def test_get_user_by_id_not_found(test_app: FastAPI, client: TestClient):
    """GET /users/{id} returns 404 when the user does not exist."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user()
    mock_controller = Mock(spec=UserController)
    mock_controller.get_user_by_id = AsyncMock(side_effect=UserNotFoundError(user_id=user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.get(f"/api/v1/users/{user_id}")

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "UserNotFoundError"
    assert body["error_key"] == "errors.api.userNotFound"
    assert body["message"] == "User not found."

    test_app.dependency_overrides.clear()


# ========== PATCH /api/v1/users/{user_id} ==========


def test_update_user_success(test_app: FastAPI, client: TestClient):
    """PATCH /users/{id} returns 200 and the updated UserView."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.update_user_by_id = AsyncMock(
        return_value=_make_user(user_id, username="UpdatedJohn", email="updated.john@test.com", country="USA")
    )
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.patch(
        f"/api/v1/users/{user_id}",
        json={
            "username": "UpdatedJohn",
            "email_address": "updated.john@test.com",
            "country": "USA",
        },
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user_id)
    assert body["username"] == "UpdatedJohn"
    assert body["email_address"] == "updated.john@test.com"
    assert body["country"] == "USA"
    assert "password" not in body

    test_app.dependency_overrides.clear()


def test_update_user_forbidden(test_app: FastAPI, client: TestClient):
    """PATCH /users/{id} returns 403 when updating another user's profile."""
    # Arrange
    user_id = uuid4()
    other_user_id = uuid4()
    auth_user = _make_user(other_user_id)
    mock_controller = Mock(spec=UserController)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.patch(
        f"/api/v1/users/{user_id}",
        json={
            "username": "Hacker",
            "email_address": "hacker@test.com",
        },
    )

    # Assert
    assert response.status_code == 403

    test_app.dependency_overrides.clear()


def test_update_user_not_found(test_app: FastAPI, client: TestClient):
    """PATCH /users/{id} returns 404 when the user does not exist."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.update_user_by_id = AsyncMock(side_effect=UserNotFoundError(user_id=user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.patch(
        f"/api/v1/users/{user_id}",
        json={
            "username": "UpdatedJohn",
            "email_address": "updated.john@test.com",
            "country": "USA",
        },
    )

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "UserNotFoundError"
    assert body["error_key"] == "errors.api.userNotFound"
    assert body["message"] == "User not found."

    test_app.dependency_overrides.clear()


# ========== PATCH /api/v1/users/{user_id}/password ==========


def test_update_user_password_success(test_app: FastAPI, client: TestClient):
    """PATCH /users/{id}/password returns 200 and the updated UserView."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.update_user_password = AsyncMock(return_value=_make_user(user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.patch(
        f"/api/v1/users/{user_id}/password",
        json={"password": "newsecurepassword"},
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user_id)
    assert body["username"] == "JohnDoe"
    assert body["email_address"] == "john.doe@test.com"
    assert body["country"] == "FRA"
    assert "password" not in body

    test_app.dependency_overrides.clear()


def test_update_user_password_forbidden(test_app: FastAPI, client: TestClient):
    """PATCH /users/{id}/password returns 403 when changing another user's password."""
    # Arrange
    user_id = uuid4()
    other_user_id = uuid4()
    auth_user = _make_user(other_user_id)
    mock_controller = Mock(spec=UserController)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.patch(
        f"/api/v1/users/{user_id}/password",
        json={"password": "newsecurepassword"},
    )

    # Assert
    assert response.status_code == 403

    test_app.dependency_overrides.clear()


def test_update_user_password_not_found(test_app: FastAPI, client: TestClient):
    """PATCH /users/{id}/password returns 404 when the user does not exist."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.update_user_password = AsyncMock(side_effect=UserNotFoundError(user_id=user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.patch(
        f"/api/v1/users/{user_id}/password",
        json={"password": "newsecurepassword"},
    )

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "UserNotFoundError"
    assert body["error_key"] == "errors.api.userNotFound"
    assert body["message"] == "User not found."

    test_app.dependency_overrides.clear()


# ========== DELETE /api/v1/users/{user_id} ==========


def test_delete_user_success(test_app: FastAPI, client: TestClient):
    """DELETE /users/{id} returns 204 on successful deletion."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.delete_user = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.delete(f"/api/v1/users/{user_id}")

    # Assert
    assert response.status_code == 204
    assert response.content == b""

    test_app.dependency_overrides.clear()


def test_delete_user_forbidden(test_app: FastAPI, client: TestClient):
    """DELETE /users/{id} returns 403 when deleting another user's account."""
    # Arrange
    user_id = uuid4()
    other_user_id = uuid4()
    auth_user = _make_user(other_user_id)
    mock_controller = Mock(spec=UserController)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.delete(f"/api/v1/users/{user_id}")

    # Assert
    assert response.status_code == 403

    test_app.dependency_overrides.clear()


def test_delete_user_not_found(test_app: FastAPI, client: TestClient):
    """DELETE /users/{id} returns 404 when the user does not exist."""
    # Arrange
    user_id = uuid4()
    auth_user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.delete_user = AsyncMock(side_effect=UserNotFoundError(user_id=user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.delete(f"/api/v1/users/{user_id}")

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "UserNotFoundError"
    assert body["error_key"] == "errors.api.userNotFound"
    assert body["message"] == "User not found."

    test_app.dependency_overrides.clear()


# ========== Validation edge case ==========


def test_get_user_invalid_uuid(test_app: FastAPI, client: TestClient):
    """GET /users/not-a-uuid returns 422 for an invalid UUID path parameter."""
    # Arrange
    auth_user = _make_user()
    mock_controller = Mock(spec=UserController)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, auth_user)

    # Act
    response = client.get("/api/v1/users/not-a-uuid")

    # Assert
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "ValidationError"
    assert body["error_key"] == "errors.api.validation"

    test_app.dependency_overrides.clear()
