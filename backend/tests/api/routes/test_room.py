"""Route-level tests for room endpoints (prefix /api/v1/rooms)."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.room import RoomController
from ipg.api.models.game import GameType
from ipg.api.models.room import RoomStatus, RoomType
from ipg.api.models.table import Room, User
from ipg.api.schemas.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from ipg.dependencies import get_current_user, get_room_controller

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
        assert data["password"] == "1234"
        assert data["status"] == RoomStatus.ONLINE.value
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == mock_room.created_at.isoformat()
        assert len(data["users"]) == 1
        assert data["users"][0]["id"] == str(owner_id)
        assert data["users"][0]["username"] == "owner"
        assert data["users"][0]["email_address"] == "owner@test.com"
        assert data["users"][0]["country"] == "FRA"
        assert data["games"] == []
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


# ========== GET /rooms ==========


def test_get_all_rooms_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms returns 200 and a list of RoomView objects."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    owner_id = uuid4()
    room_id_1 = uuid4()
    room_id_2 = uuid4()
    created_at = datetime.now()

    mock_rooms = [
        Room(
            id=room_id_1,
            public_id="AAA11",
            owner_id=owner_id,
            password="1234",
            status=RoomStatus.ONLINE,
            type=RoomType.ACTIVE,
            created_at=created_at,
        ),
        Room(
            id=room_id_2,
            public_id="BBB22",
            owner_id=owner_id,
            password="5678",
            status=RoomStatus.ONLINE,
            type=RoomType.ACTIVE,
            created_at=created_at,
        ),
    ]
    for room in mock_rooms:
        room.users = []
        room.games = []

    mock_controller.get_rooms = AsyncMock(return_value=mock_rooms)
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(BASE_URL)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(room_id_1)
        assert data[0]["public_id"] == "AAA11"
        assert data[0]["owner_id"] == str(owner_id)
        assert data[0]["password"] == "1234"
        assert data[0]["status"] == RoomStatus.ONLINE.value
        assert data[0]["type"] == RoomType.ACTIVE.value
        assert data[0]["created_at"] == created_at.isoformat()
        assert data[0]["users"] == []
        assert data[0]["games"] == []
        assert data[1]["id"] == str(room_id_2)
        assert data[1]["public_id"] == "BBB22"
        assert data[1]["password"] == "5678"
    finally:
        test_app.dependency_overrides.clear()


def test_get_all_rooms_empty(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms returns 200 and an empty list when no rooms exist."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    mock_controller.get_rooms = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(BASE_URL)

        # Assert
        assert response.status_code == 200
        assert response.json() == []
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
        assert data["password"] == "4321"
        assert data["status"] == RoomStatus.ONLINE.value
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == created_at.isoformat()
        assert len(data["users"]) == 1
        assert data["users"][0]["id"] == str(owner_id)
        assert data["users"][0]["username"] == "player1"
        assert data["users"][0]["email_address"] == "player1@test.com"
        assert data["users"][0]["country"] == "USA"
        assert data["games"] == []
    finally:
        test_app.dependency_overrides.clear()


def test_get_room_by_id_not_found(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id} when room does not exist returns 404."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()

    mock_controller.get_room_by_id = AsyncMock(side_effect=RoomNotFoundError(room_id=room_id))
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
    user_id = uuid4()
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
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "user_id": str(user_id),
                "room_id": str(room_id),
                "password": "1234",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "JON55"
        assert data["owner_id"] == str(owner_id)
        assert data["password"] == "1234"
        assert data["status"] == RoomStatus.ONLINE.value
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == created_at.isoformat()
        assert data["users"] == []
        assert data["games"] == []
    finally:
        test_app.dependency_overrides.clear()


def test_join_room_wrong_password(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/join with wrong password raises WrongRoomPasswordError and returns 403."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    user_id = uuid4()

    mock_controller.join_room = AsyncMock(side_effect=WrongRoomPasswordError(room_id=room_id))
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "user_id": str(user_id),
                "room_id": str(room_id),
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
    user_id = uuid4()

    mock_controller.join_room = AsyncMock(side_effect=RoomNotFoundError(room_id=room_id))
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/join",
            json={
                "user_id": str(user_id),
                "room_id": str(room_id),
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
    user_id = uuid4()
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
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/leave",
            json={
                "room_id": str(room_id),
                "user_id": str(user_id),
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(room_id)
        assert data["public_id"] == "LEV88"
        assert data["owner_id"] == str(owner_id)
        assert data["password"] == "5678"
        assert data["status"] == RoomStatus.ONLINE.value
        assert data["type"] == RoomType.ACTIVE.value
        assert data["created_at"] == created_at.isoformat()
        assert data["users"] == []
        assert data["games"] == []
    finally:
        test_app.dependency_overrides.clear()


def test_leave_room_user_not_in_room(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /rooms/leave when user is not in room raises UserNotInRoomError and returns 404."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    user_id = uuid4()

    mock_controller.leave_room = AsyncMock(side_effect=UserNotInRoomError(user_id=user_id, room_id=room_id))
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/leave",
            json={
                "room_id": str(room_id),
                "user_id": str(user_id),
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
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.delete(f"{BASE_URL}/{room_id}")

        # Assert
        assert response.status_code == 204
        assert response.content == b""
    finally:
        test_app.dependency_overrides.clear()
