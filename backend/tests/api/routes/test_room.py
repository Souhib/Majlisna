"""Route-level tests for room endpoints (prefix /api/v1/rooms)."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.room import RoomController
from majlisna.api.models.game import GameType
from majlisna.api.models.room import RoomStatus, RoomType
from majlisna.api.models.table import Room, User
from majlisna.api.schemas.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from majlisna.dependencies import get_current_user, get_room_controller

BASE_URL = "/api/v1/rooms"


# ========== POST /rooms ==========


def test_create_room_success(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms with valid auth returns 201 and the created RoomView."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    owner_id = uuid4()
    mock_user = User(
        id=owner_id,
        username="owner",
        email_address="owner@test.com",
        country="FRA",
        password="securepassword",
    )

    room_id = uuid4()
    mock_room = Room(
        id=room_id,
        public_id="ABC12",
        owner_id=owner_id,
        password="1234",
        status=RoomStatus.ONLINE,
        type=RoomType.ACTIVE,
        created_at=datetime.now(),
    )
    mock_room.users = [mock_user]
    mock_room.games = []

    mock_controller.create_room = AsyncMock(return_value=mock_room)

    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(BASE_URL, json={"game_type": GameType.UNDERCOVER.value})

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "ABC12"
        assert data["owner_id"] == str(owner_id)
        assert "password" not in data
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == mock_room.created_at.isoformat()
        assert len(data["users"]) == 1
        assert data["users"][0]["id"] == str(owner_id)
        assert data["users"][0]["username"] == "owner"
        assert "email_address" not in data["users"][0]
        assert data["users"][0]["country"] == "FRA"
        assert "games" not in data
    finally:
        test_app.dependency_overrides.clear()


def test_create_room_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms without auth override returns 401."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller
    # Note: get_current_user is NOT overridden, so OAuth2 will reject the request.

    try:
        # Act
        response = client.post(BASE_URL, json={"game_type": GameType.UNDERCOVER.value})

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


def test_create_room_owner_already_in_room(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms when owner is already in a room raises UserAlreadyInRoomError and returns 409."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    owner_id = uuid4()
    room_id = uuid4()
    mock_user = User(
        id=owner_id,
        username="owner",
        email_address="owner@test.com",
        country="FRA",
        password="securepassword",
    )

    mock_controller.create_room = AsyncMock(side_effect=UserAlreadyInRoomError(user_id=owner_id, room_id=room_id))

    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(BASE_URL, json={"game_type": GameType.UNDERCOVER.value})

        # Assert
        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "UserAlreadyInRoomError"
        assert data["error_key"] == "errors.api.userAlreadyInRoom"
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /rooms (removed) ==========


def test_room_directory_endpoint_is_gone(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms no longer exists — it leaked the directory of every active room.

    Listing rooms handed any authenticated user each room's public_id, owner and
    member list, which turns a 4-digit PIN into a feasible brute-force target.
    Only POST is mounted on the collection path, so GET must be rejected.
    """
    # Arrange
    mock_user = User(id=uuid4(), username="testuser", email_address="test@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # Act
        response = client.get(BASE_URL)

        # Assert
        assert response.status_code == 405
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /rooms/{room_id} ==========


def test_get_room_by_id_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id} returns 200 and the RoomView with all fields."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    created_at = datetime.now()

    mock_user = User(
        id=owner_id,
        username="player1",
        email_address="player1@test.com",
        country="USA",
        password="securepassword",
    )
    mock_room = Room(
        id=room_id,
        public_id="XYZ99",
        owner_id=owner_id,
        password="4321",
        status=RoomStatus.ONLINE,
        type=RoomType.ACTIVE,
        created_at=created_at,
    )
    mock_room.users = [mock_user]
    mock_room.games = []

    mock_controller.get_room_by_id = AsyncMock(return_value=mock_room)
    auth_user = User(id=uuid4(), username="authuser", email_address="auth@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: auth_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "XYZ99"
        assert data["owner_id"] == str(owner_id)
        assert "password" not in data
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == created_at.isoformat()
        assert len(data["users"]) == 1
        assert data["users"][0]["id"] == str(owner_id)
        assert data["users"][0]["username"] == "player1"
        assert "email_address" not in data["users"][0]
        assert data["users"][0]["country"] == "USA"
        assert "games" not in data
    finally:
        test_app.dependency_overrides.clear()


def test_get_room_by_id_not_found(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id} when room does not exist returns 404."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()

    mock_controller.get_room_by_id = AsyncMock(side_effect=RoomNotFoundError(room_id=room_id))
    auth_user = User(id=uuid4(), username="authuser", email_address="auth@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: auth_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "RoomNotFoundError"
        assert data["error_key"] == "errors.api.roomNotFound"
    finally:
        test_app.dependency_overrides.clear()


# ========== PATCH /rooms/join ==========


def test_join_room_success(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join with valid credentials returns 200 and the RoomView."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    created_at = datetime.now()

    mock_room = Room(
        id=room_id,
        public_id="JON55",
        owner_id=owner_id,
        password="1234",
        status=RoomStatus.ONLINE,
        type=RoomType.ACTIVE,
        created_at=created_at,
    )
    mock_room.users = []
    mock_room.games = []

    mock_controller.join_room = AsyncMock(return_value=mock_room)
    mock_user = User(id=uuid4(), username="joiner", email_address="joiner@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "public_room_id": "JON55",
                "password": "1234",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "JON55"
        assert data["owner_id"] == str(owner_id)
        assert "password" not in data
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == created_at.isoformat()
        assert data["users"] == []
        assert "games" not in data
    finally:
        test_app.dependency_overrides.clear()


def test_join_room_wrong_password(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join with wrong password raises WrongRoomPasswordError and returns 403."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()

    mock_controller.join_room = AsyncMock(side_effect=WrongRoomPasswordError(room_id=room_id))
    mock_user = User(id=uuid4(), username="joiner", email_address="joiner@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "public_room_id": "ABCDE",
                "password": "9999",
            },
        )

        # Assert
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "WrongRoomPasswordError"
        assert data["error_key"] == "errors.api.wrongRoomPassword"
    finally:
        test_app.dependency_overrides.clear()


def test_join_room_not_found(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join when room does not exist raises RoomNotFoundError and returns 404."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()

    mock_controller.join_room = AsyncMock(side_effect=RoomNotFoundError(room_id=room_id))
    mock_user = User(id=uuid4(), username="joiner", email_address="joiner@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "public_room_id": "ZZZZZ",
                "password": "1234",
            },
        )

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "RoomNotFoundError"
        assert data["error_key"] == "errors.api.roomNotFound"
    finally:
        test_app.dependency_overrides.clear()


# ========== PATCH /rooms/leave ==========


def test_leave_room_success(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/leave returns 200 and the updated RoomView."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    created_at = datetime.now()

    mock_room = Room(
        id=room_id,
        public_id="LEV88",
        owner_id=owner_id,
        password="5678",
        status=RoomStatus.ONLINE,
        type=RoomType.ACTIVE,
        created_at=created_at,
    )
    mock_room.users = []
    mock_room.games = []

    mock_controller.leave_room = AsyncMock(return_value=mock_room)
    mock_user = User(id=uuid4(), username="leaver", email_address="leaver@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/leave",
            json={
                "room_id": str(room_id),
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "LEV88"
        assert data["owner_id"] == str(owner_id)
        assert "password" not in data
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == created_at.isoformat()
        assert data["users"] == []
        assert "games" not in data
    finally:
        test_app.dependency_overrides.clear()


def test_leave_room_user_not_in_room(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/leave when user is not in room raises UserNotInRoomError and returns 404."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    user_id = uuid4()

    mock_controller.leave_room = AsyncMock(side_effect=UserNotInRoomError(user_id=user_id, room_id=room_id))
    mock_user = User(id=uuid4(), username="leaver", email_address="leaver@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/leave",
            json={
                "room_id": str(room_id),
            },
        )

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "UserNotInRoomError"
        assert data["error_key"] == "errors.api.userNotInRoom"
    finally:
        test_app.dependency_overrides.clear()


# ========== DELETE /rooms/{room_id} ==========


def test_delete_room_success(test_app: FastAPI, client: TestClient) -> None:
    """DELETE /rooms/{room_id} returns 204 with no content."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()

    mock_controller.delete_room = AsyncMock(return_value=None)
    mock_user = User(id=uuid4(), username="deleter", email_address="deleter@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.delete(f"{BASE_URL}/{room_id}")

        # Assert
        assert response.status_code == 204
        assert response.content == b""
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /rooms/{room_id}/state ==========


def test_get_room_state_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id}/state returns 200 and a dict with players, owner_id, etc."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    mock_user = User(
        id=owner_id,
        username="owner",
        email_address="owner@test.com",
        country="FRA",
        password="securepassword",
    )

    mock_state = {
        "id": str(room_id),
        "public_id": "STA11",
        "password": "1234",
        "owner_id": str(owner_id),
        "active_game_id": None,
        "game_type": None,
        "players": [
            {
                "user_id": str(owner_id),
                "username": "owner",
                "is_connected": True,
                "is_disconnected": False,
                "is_host": True,
                "is_spectator": False,
            }
        ],
        "type": RoomType.ACTIVE.value,
        "settings": None,
    }

    mock_controller.get_room_state = AsyncMock(return_value=mock_state)
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/state")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["owner_id"] == str(owner_id)
        assert len(data["players"]) == 1
        assert data["players"][0]["is_host"] is True
    finally:
        test_app.dependency_overrides.clear()


def test_get_room_state_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id}/state without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/state")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== PATCH /rooms/join-spectator ==========


def test_join_room_as_spectator_success(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join-spectator returns 200 and a RoomView."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    user_id = uuid4()
    created_at = datetime.now()

    mock_user = User(
        id=user_id,
        username="spectator",
        email_address="spectator@test.com",
        country="FRA",
        password="securepassword",
    )

    mock_room = Room(
        id=room_id,
        public_id="SPC22",
        owner_id=owner_id,
        password="1234",
        status=RoomStatus.ONLINE,
        type=RoomType.ACTIVE,
        created_at=created_at,
    )
    mock_room.users = [mock_user]
    mock_room.games = []

    mock_controller.join_room_as_spectator = AsyncMock(return_value=mock_room)
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join-spectator",
            json={"room_id": str(room_id), "password": "1234"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "SPC22"
    finally:
        test_app.dependency_overrides.clear()


def test_join_room_as_spectator_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join-spectator without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join-spectator",
            json={"room_id": str(room_id)},
        )

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== PATCH /rooms/{room_id}/settings ==========


def test_update_room_settings_success(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/{room_id}/settings returns 200 with updated settings."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    mock_user = User(
        id=owner_id,
        username="owner",
        email_address="owner@test.com",
        country="FRA",
        password="securepassword",
    )

    mock_result = {"room_id": str(room_id), "settings": {"description_timer": 120}}
    mock_controller.update_room_settings = AsyncMock(return_value=mock_result)
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/{room_id}/settings",
            json={"description_timer": 120},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == str(room_id)
        assert data["settings"]["description_timer"] == 120
    finally:
        test_app.dependency_overrides.clear()


def test_update_room_settings_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/{room_id}/settings without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/{room_id}/settings",
            json={"description_timer": 120},
        )

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /rooms/{room_id}/rematch ==========


def test_rematch_success(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms/{room_id}/rematch returns 200 with room_id and status."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    owner_id = uuid4()
    mock_user = User(
        id=owner_id,
        username="owner",
        email_address="owner@test.com",
        country="FRA",
        password="securepassword",
    )

    mock_result = {"room_id": str(room_id), "status": "lobby"}
    mock_controller.rematch = AsyncMock(return_value=mock_result)
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/{room_id}/rematch")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == str(room_id)
        assert data["status"] == "lobby"
    finally:
        test_app.dependency_overrides.clear()


def test_rematch_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms/{room_id}/rematch without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/{room_id}/rematch")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== Contract-style validation tests ==========


def test_join_room_wrong_field_name_returns_422(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join with room_id (UUID) instead of public_room_id returns 422."""
    # Arrange — no mocked controller; let Pydantic reject the payload
    room_id = uuid4()
    mock_user = User(id=uuid4(), username="authuser", email_address="auth@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "room_id": str(room_id),
                "password": "1234",
            },
        )

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


def test_leave_room_wrong_field_name_returns_422(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/leave with public_room_id (str) instead of room_id (UUID) returns 422."""
    # Arrange — no mocked controller; let Pydantic reject the payload
    mock_user = User(id=uuid4(), username="authuser", email_address="auth@test.com")
    test_app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/leave",
            json={
                "public_room_id": "ABCDE",
            },
        )

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()
