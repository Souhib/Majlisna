"""Route-level tests for room endpoints (prefix /api/v1/rooms)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from majlisna.api.constants import ROOM_INVITE_RATE_LIMIT, ROOM_JOIN_RATE_LIMIT
from majlisna.api.controllers.room import RoomController
from majlisna.api.models.game import GameType
from majlisna.api.models.room import RoomStatus, RoomType
from majlisna.api.models.table import Room, User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.common import StatusResponse
from majlisna.api.schemas.error import (
    NotRoomHostError,
    RoomBannedError,
    RoomBanNotFoundError,
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from majlisna.api.schemas.room import KickPlayerResponse, RoomBanView, RoomInviteResponse
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


def test_leave_room_notifies_the_room_and_its_game(test_app: FastAPI, client: TestClient) -> None:
    """A leave goes through notify_member_removed, which reaches a running game too.

    Leaving mid-game eliminates the leaver; with only a room_state the game pages
    (which refetch on game_updated) stayed on a stale game.
    """
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    mock_room = Room(
        id=room_id, public_id="LEV89", owner_id=uuid4(), password="5678", status=RoomStatus.ONLINE, type=RoomType.ACTIVE
    )
    mock_room.users = []
    mock_room.games = []
    mock_controller.leave_room = AsyncMock(return_value=mock_room)
    test_app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), username="l", email_address="l@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        with (
            patch(
                "majlisna.api.routes.room.get_active_game_id", new_callable=AsyncMock, return_value="game-1"
            ) as lookup,
            patch("majlisna.api.routes.room.notify_member_removed", new_callable=AsyncMock) as notify,
        ):
            # Act
            response = client.patch(f"{BASE_URL}/leave", json={"room_id": str(room_id)})

        # Assert — the game is read BEFORE the leave (which can end it) and signalled
        assert response.status_code == 200
        lookup.assert_awaited_once_with(str(room_id))
        notify.assert_awaited_once_with(str(room_id), "game-1")
    finally:
        test_app.dependency_overrides.clear()


def test_kick_player_notifies_the_room_and_its_game(test_app: FastAPI, client: TestClient) -> None:
    """A kick reaches the running game as well: the kicked player is eliminated from it."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    target_id = uuid4()
    mock_controller.kick_player = AsyncMock(return_value=KickPlayerResponse(message="Player kicked"))
    test_app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), username="h", email_address="h@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        order: list[str] = []
        mock_controller.kick_player.side_effect = lambda *_: (
            order.append("kick") or KickPlayerResponse(message="Player kicked")
        )

        lookup = AsyncMock(side_effect=lambda _room_id: order.append("lookup") or "game-1")

        with (
            patch("majlisna.api.routes.room.get_active_game_id", lookup),
            patch("majlisna.api.routes.room.notify_member_removed", new_callable=AsyncMock) as notify,
        ):
            # Act
            response = client.patch(f"{BASE_URL}/{room_id}/kick", json={"user_id": str(target_id)})

        # Assert — the game is read BEFORE the kick (which can end it) and signalled
        assert response.status_code == 200
        assert order == ["lookup", "kick"]
        notify.assert_awaited_once_with(str(room_id), "game-1")
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


# ========== WP-07: bans, the 403 on join, per-user limits ==========


def _room(public_id: str = "BAN11") -> Room:
    room = Room(
        id=uuid4(),
        public_id=public_id,
        owner_id=uuid4(),
        password="1234",
        status=RoomStatus.ONLINE,
        type=RoomType.ACTIVE,
        created_at=datetime.now(),
    )
    room.users = []
    room.games = []
    return room


class _HeaderAuthenticator:
    """A stand-in for get_current_user: the user named by ``X-Test-User``, recorded on
    the request exactly as the real dependency records it (``request.state.user_id``)."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


@pytest.fixture(name="per_user_client")
def get_per_user_client(test_app: FastAPI):
    """Two signed-in users behind ONE address (the TestClient's), each request naming
    its user; the limiter's memory is wiped so no other test inherits a spent budget."""
    users = {name: User(id=uuid4(), username=name, email_address=f"{name}@test.com") for name in ("first", "second")}
    controller = Mock(spec=RoomController)
    controller.join_room = AsyncMock(return_value=_room())
    controller.join_room_as_spectator = AsyncMock(return_value=_room())
    controller.invite_friend_to_room = AsyncMock(
        return_value=RoomInviteResponse(room_id=str(uuid4()), invited_user_id=str(uuid4()), message="Invite sent")
    )
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_room_controller] = lambda: controller
    limiter.reset()
    with (
        patch("majlisna.api.routes.room.notify_room_changed", new_callable=AsyncMock),
        patch("majlisna.api.routes.room.notify_room_invite", new_callable=AsyncMock),
    ):
        yield TestClient(test_app)
    limiter.reset()
    test_app.dependency_overrides.clear()


def _limit_count(limit: str) -> int:
    return int(limit.split("/", maxsplit=1)[0])


def test_the_join_limit_is_counted_per_user(per_user_client: TestClient) -> None:
    """SEC F03: per IP, one noisy phone locked the whole home connection out of joining
    (and a spoofed address bought a fresh budget); per user, the 11th join of one
    player is a 429 while another player on the same address joins."""
    # Prepare
    body = {"public_room_id": "BAN11", "password": "1234"}
    for _ in range(_limit_count(ROOM_JOIN_RATE_LIMIT)):
        assert per_user_client.patch(f"{BASE_URL}/join", json=body, headers={"X-Test-User": "first"}).status_code == 200

    # Act
    limited = per_user_client.patch(f"{BASE_URL}/join", json=body, headers={"X-Test-User": "first"})
    other = per_user_client.patch(f"{BASE_URL}/join", json=body, headers={"X-Test-User": "second"})

    # Assert
    assert limited.status_code == 429
    assert limited.json()["error_key"] == "errors.api.rateLimitExceeded"
    assert other.status_code == 200


def test_the_spectator_join_limit_is_counted_per_user(per_user_client: TestClient) -> None:
    """The spectator door takes a PIN too, so it shares the join rule."""
    # Prepare
    body = {"room_id": str(uuid4()), "password": "1234"}
    for _ in range(_limit_count(ROOM_JOIN_RATE_LIMIT)):
        response = per_user_client.patch(f"{BASE_URL}/join-spectator", json=body, headers={"X-Test-User": "first"})
        assert response.status_code == 200

    # Act
    limited = per_user_client.patch(f"{BASE_URL}/join-spectator", json=body, headers={"X-Test-User": "first"})
    other = per_user_client.patch(f"{BASE_URL}/join-spectator", json=body, headers={"X-Test-User": "second"})

    # Assert
    assert limited.status_code == 429
    assert other.status_code == 200


def test_the_invite_limit_is_counted_per_user(per_user_client: TestClient) -> None:
    """SEC F15: invites had no limit at all, so one player could spam every friend."""
    # Prepare
    url = f"{BASE_URL}/{uuid4()}/invite"
    body = {"friend_user_id": str(uuid4())}
    for _ in range(_limit_count(ROOM_INVITE_RATE_LIMIT)):
        assert per_user_client.post(url, json=body, headers={"X-Test-User": "first"}).status_code == 200

    # Act
    limited = per_user_client.post(url, json=body, headers={"X-Test-User": "first"})
    other = per_user_client.post(url, json=body, headers={"X-Test-User": "second"})

    # Assert
    assert limited.status_code == 429
    assert other.status_code == 200


def test_a_banned_player_joining_answers_403_room_banned(test_app: FastAPI, client: TestClient) -> None:
    """The envelope the client translates: errors.api.roomBanned."""
    # Prepare
    room_id = uuid4()
    controller = Mock(spec=RoomController)
    controller.join_room = AsyncMock(side_effect=RoomBannedError(room_id=room_id))
    test_app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), username="b", email_address="b@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: controller

    try:
        # Act
        response = client.patch(f"{BASE_URL}/join", json={"public_room_id": "BAN11", "password": "1234"})

        # Assert
        assert response.status_code == 403
        assert response.json()["error_key"] == "errors.api.roomBanned"
    finally:
        test_app.dependency_overrides.clear()


def test_the_host_lists_the_bans(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{id}/bans returns the RoomBanView rows of the controller, for the caller."""
    # Prepare
    room_id, host_id, banned_id = uuid4(), uuid4(), uuid4()
    banned_at = datetime.now(UTC)
    controller = Mock(spec=RoomController)
    controller.list_bans = AsyncMock(
        return_value=[RoomBanView(user_id=banned_id, username="troll", banned_at=banned_at)]
    )
    test_app.dependency_overrides[get_current_user] = lambda: User(id=host_id, username="h", email_address="h@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/bans")

        # Assert
        assert response.status_code == 200
        rows = response.json()
        assert [(row["user_id"], row["username"]) for row in rows] == [(str(banned_id), "troll")]
        assert datetime.fromisoformat(rows[0]["banned_at"]) == banned_at
        controller.list_bans.assert_awaited_once_with(room_id, host_id)
    finally:
        test_app.dependency_overrides.clear()


def test_a_member_listing_the_bans_answers_403(test_app: FastAPI, client: TestClient) -> None:
    """Host only, enforced in the controller: NotRoomHostError → 403."""
    # Prepare
    controller = Mock(spec=RoomController)
    controller.list_bans = AsyncMock(side_effect=NotRoomHostError())
    test_app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), username="m", email_address="m@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{uuid4()}/bans")

        # Assert
        assert response.status_code == 403
        assert response.json()["error_key"] == "errors.api.notRoomHost"
    finally:
        test_app.dependency_overrides.clear()


def test_lifting_a_ban_answers_status_and_pushes_the_room(test_app: FastAPI, client: TestClient) -> None:
    """DELETE /rooms/{id}/bans/{user_id}: StatusResponse, then room_state to the lobby."""
    # Prepare
    room_id, host_id, banned_id = uuid4(), uuid4(), uuid4()
    controller = Mock(spec=RoomController)
    controller.lift_ban = AsyncMock(return_value=StatusResponse(status="lifted"))
    test_app.dependency_overrides[get_current_user] = lambda: User(id=host_id, username="h", email_address="h@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: controller

    try:
        with patch("majlisna.api.routes.room.notify_room_changed", new_callable=AsyncMock) as notify:
            # Act
            response = client.delete(f"{BASE_URL}/{room_id}/bans/{banned_id}")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "lifted"}
        controller.lift_ban.assert_awaited_once_with(room_id, host_id, banned_id)
        notify.assert_awaited_once_with(str(room_id))
    finally:
        test_app.dependency_overrides.clear()


def test_lifting_an_absent_ban_answers_404(test_app: FastAPI, client: TestClient) -> None:
    """RoomBanNotFoundError → 404 errors.api.roomBanNotFound, and nothing is pushed."""
    # Prepare
    room_id, banned_id = uuid4(), uuid4()
    controller = Mock(spec=RoomController)
    controller.lift_ban = AsyncMock(side_effect=RoomBanNotFoundError(room_id=room_id, user_id=banned_id))
    test_app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), username="h", email_address="h@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: controller

    try:
        with patch("majlisna.api.routes.room.notify_room_changed", new_callable=AsyncMock) as notify:
            # Act
            response = client.delete(f"{BASE_URL}/{room_id}/bans/{banned_id}")

        # Assert
        assert response.status_code == 404
        assert response.json()["error_key"] == "errors.api.roomBanNotFound"
        notify.assert_not_awaited()
    finally:
        test_app.dependency_overrides.clear()


def test_a_kick_detaches_the_socket_before_the_new_pin_is_pushed(test_app: FastAPI, client: TestClient) -> None:
    """The kicked player is told and detached BEFORE the room_state carrying the new PIN goes out."""
    # Prepare
    room_id, target_id = uuid4(), uuid4()
    order: list[str] = []
    controller = Mock(spec=RoomController)
    controller.kick_player = AsyncMock(
        side_effect=lambda *_: order.append("kick") or KickPlayerResponse(message="Player kicked")
    )
    test_app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), username="h", email_address="h@test.com")
    test_app.dependency_overrides[get_room_controller] = lambda: controller

    try:
        with (
            patch("majlisna.api.routes.room.get_active_game_id", AsyncMock(return_value=None)),
            patch(
                "majlisna.api.routes.room.notify_user_kicked",
                AsyncMock(side_effect=lambda *_: order.append("told")),
            ),
            patch(
                "majlisna.api.routes.room.remove_user_from_room_socket",
                AsyncMock(side_effect=lambda *_: order.append("detached")),
            ),
            patch(
                "majlisna.api.routes.room.notify_member_removed",
                AsyncMock(side_effect=lambda *_: order.append("room_state")),
            ),
        ):
            # Act
            response = client.patch(f"{BASE_URL}/{room_id}/kick", json={"user_id": str(target_id)})

        # Assert
        assert response.status_code == 200
        assert order == ["kick", "told", "detached", "room_state"]
    finally:
        test_app.dependency_overrides.clear()
