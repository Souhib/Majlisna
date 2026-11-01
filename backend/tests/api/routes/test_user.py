"""Route-level tests for /api/v1/users endpoints."""

from unittest.mock import AsyncMock, Mock, call, patch
from uuid import uuid4

from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.controllers.user import UserController
from majlisna.api.models.table import User
from majlisna.api.schemas.error import UserNotFoundError
from majlisna.api.schemas.user import DepartedRoom
from majlisna.dependencies import get_current_user, get_social_auth_service, get_user_controller


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


# ========== GET /api/v1/users ==========


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
    assert "email_address" not in body
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
        json={"current_password": "oldpassword", "new_password": "newsecurepassword"},
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
        json={"current_password": "oldpassword", "new_password": "newsecurepassword"},
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
        json={"current_password": "oldpassword", "new_password": "newsecurepassword"},
    )

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "UserNotFoundError"
    assert body["error_key"] == "errors.api.userNotFound"
    assert body["message"] == "User not found."

    test_app.dependency_overrides.clear()


# ========== DELETE /api/v1/users/{user_id} ==========


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


def test_list_all_users_endpoint_is_gone(test_app: FastAPI, client: TestClient):
    """`GET /users` must stay removed.

    It returned the whole user table, unpaginated, to any authenticated caller — a
    full table scan per call and a complete directory of the player base. Nothing
    used it.
    """
    # Arrange
    mock_user = User(id=uuid4(), username="testuser", email_address="test@example.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user

    # Act
    response = client.get("/api/v1/users")

    # Assert
    assert response.status_code == 404

    test_app.dependency_overrides.clear()


def test_delete_user_by_id_endpoint_is_gone(test_app: FastAPI, client: TestClient):
    """`DELETE /users/{user_id}` must stay removed.

    It destroyed the caller's own account irreversibly on nothing but a valid
    session, while `/users/me/account` does the same thing and requires the
    password — so a stolen token was enough.
    """
    # Arrange
    user_id = uuid4()
    mock_user = User(id=user_id, username="testuser", email_address="test@example.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user

    # Act
    response = client.delete(f"/api/v1/users/{user_id}")

    # Assert
    assert response.status_code == 405  # the path exists for GET/PATCH, not DELETE

    test_app.dependency_overrides.clear()


# ========== DELETE /api/v1/users/me/account (WP-27) ==========


def test_delete_account_detaches_and_notifies_every_room_it_left(test_app: FastAPI, client: TestClient):
    """SEC F05: the deletion leaves each room like a leave does — the socket is cut off the
    room and the room (and its game, read before the departure) hears it."""
    # Arrange
    user = _make_user()
    lobby_id, table_id, game_id = uuid4(), uuid4(), uuid4()
    mock_controller = Mock(spec=UserController)
    mock_controller.delete_user_account = AsyncMock(
        return_value=[DepartedRoom(room_id=lobby_id), DepartedRoom(room_id=table_id, game_id=game_id)]
    )
    social_auth_service = Mock()
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_social_auth_service] = lambda: social_auth_service
    _override_auth(test_app, user)

    try:
        with (
            patch("majlisna.api.routes.user.remove_user_from_room_socket", new=AsyncMock()) as detach,
            patch("majlisna.api.routes.user.notify_member_removed", new=AsyncMock()) as notify,
        ):
            # Act
            response = client.request("DELETE", "/api/v1/users/me/account", json={"password": "securepassword"})

        # Assert
        assert response.status_code == 204
        mock_controller.delete_user_account.assert_awaited_once_with(
            user.id, "securepassword", google_access_token=None, social_auth_service=social_auth_service
        )
        assert detach.await_args_list == [call(str(user.id), str(lobby_id)), call(str(user.id), str(table_id))]
        assert notify.await_args_list == [call(str(lobby_id), None), call(str(table_id), str(game_id))]
    finally:
        test_app.dependency_overrides.clear()


def test_delete_account_passes_the_google_confirmation_through(test_app: FastAPI, client: TestClient):
    """SEC F14: a Google-only account confirms with a Google access token instead."""
    # Arrange
    user = _make_user()
    mock_controller = Mock(spec=UserController)
    mock_controller.delete_user_account = AsyncMock(return_value=[])
    social_auth_service = Mock()
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_social_auth_service] = lambda: social_auth_service
    _override_auth(test_app, user)

    try:
        # Act
        response = client.request("DELETE", "/api/v1/users/me/account", json={"google_access_token": "ya29.token"})

        # Assert
        assert response.status_code == 204
        mock_controller.delete_user_account.assert_awaited_once_with(
            user.id, None, google_access_token="ya29.token", social_auth_service=social_auth_service
        )
    finally:
        test_app.dependency_overrides.clear()


def test_update_user_password_keeps_only_the_callers_session(test_app: FastAPI, client: TestClient):
    """SEC F01: the route hands the caller's session (request.state.session_id) to the controller."""
    # Arrange
    user_id = uuid4()
    session_id = uuid4()
    user = _make_user(user_id)
    mock_controller = Mock(spec=UserController)
    mock_controller.update_user_password = AsyncMock(return_value=_make_user(user_id))
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller

    def _authenticated(request: Request) -> User:
        request.state.session_id = session_id
        return user

    test_app.dependency_overrides[get_current_user] = _authenticated

    try:
        # Act
        response = client.patch(
            f"/api/v1/users/{user_id}/password",
            json={"current_password": "oldpassword", "new_password": "newsecurepassword"},
        )

        # Assert
        assert response.status_code == 200
        mock_controller.update_user_password.assert_awaited_once_with(
            user_id, "oldpassword", "newsecurepassword", keep_session_id=session_id
        )
    finally:
        test_app.dependency_overrides.clear()


def test_update_user_with_an_unknown_country_is_a_422_not_a_500(test_app: FastAPI):
    """The country check raised a ValueError, whose exception object the app's validation
    handler put in the body and could not serialise: every bad country was a 500."""
    # Arrange
    user_id = uuid4()
    mock_controller = Mock(spec=UserController)
    test_app.dependency_overrides[get_user_controller] = lambda: mock_controller
    _override_auth(test_app, _make_user(user_id))

    try:
        # Act
        response = TestClient(test_app, raise_server_exceptions=False).patch(
            f"/api/v1/users/{user_id}", json={"country": "XYZ"}
        )

        # Assert
        assert response.status_code == 422
        assert response.json()["error_key"] == "errors.api.validation"
        mock_controller.update_user_by_id.assert_not_called()
    finally:
        test_app.dependency_overrides.clear()
