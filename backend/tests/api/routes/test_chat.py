"""Route-level tests for chat endpoints (/api/v1/rooms/{room_id}/messages)."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.chat import ChatController
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.table import User
from majlisna.dependencies import get_chat_controller, get_current_user

BASE_URL = "/api/v1/rooms"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== POST /rooms/{room_id}/messages ==========


@patch("majlisna.api.routes.chat.notify_chat_message", new_callable=AsyncMock)
def test_send_message_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms/{room_id}/messages returns 201 and the ChatMessageView."""
    # Arrange
    user = _mock_user()
    room_id = uuid4()
    msg_id = uuid4()
    created_at = datetime.now()
    mock_controller = Mock(spec=ChatController)
    mock_controller.send_message = AsyncMock(
        return_value=ChatMessage(
            id=msg_id,
            room_id=room_id,
            user_id=user.id,
            username=user.username,
            message="Salam!",
            created_at=created_at,
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_chat_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/{room_id}/messages",
            json={"message": "Salam!"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(msg_id)
        assert data["room_id"] == str(room_id)
        assert data["user_id"] == str(user.id)
        assert data["username"] == "testplayer"
        assert data["message"] == "Salam!"
        mock_controller.send_message.assert_awaited_once_with(room_id, user.id, user.username, "Salam!")
        mock_notify.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()


def test_send_message_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms/{room_id}/messages without auth returns 401."""
    # Arrange
    room_id = uuid4()
    mock_controller = Mock(spec=ChatController)
    test_app.dependency_overrides[get_chat_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/{room_id}/messages",
            json={"message": "Salam!"},
        )

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


def test_send_message_missing_body(test_app: FastAPI, client: TestClient) -> None:
    """POST /rooms/{room_id}/messages with empty body returns 422."""
    # Arrange
    user = _mock_user()
    room_id = uuid4()
    mock_controller = Mock(spec=ChatController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_chat_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/{room_id}/messages", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /rooms/{room_id}/messages ==========


def test_get_messages_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id}/messages returns 200 and a list of ChatMessageView."""
    # Arrange
    user = _mock_user()
    room_id = uuid4()
    msg_id = uuid4()
    created_at = datetime.now()
    mock_controller = Mock(spec=ChatController)
    mock_controller.get_messages = AsyncMock(
        return_value=[
            ChatMessage(
                id=msg_id,
                room_id=room_id,
                user_id=user.id,
                username="testplayer",
                message="Hello",
                created_at=created_at,
            )
        ]
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_chat_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/messages")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(msg_id)
        assert data[0]["message"] == "Hello"
        mock_controller.get_messages.assert_awaited_once_with(room_id, user.id, after_id=None, limit=50)
    finally:
        test_app.dependency_overrides.clear()


def test_get_messages_with_after_id(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id}/messages?after_id=X passes after_id to controller."""
    # Arrange
    user = _mock_user()
    room_id = uuid4()
    after_id = uuid4()
    mock_controller = Mock(spec=ChatController)
    mock_controller.get_messages = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_chat_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/messages?after_id={after_id}&limit=10")

        # Assert
        assert response.status_code == 200
        assert response.json() == []
        mock_controller.get_messages.assert_awaited_once_with(room_id, user.id, after_id=after_id, limit=10)
    finally:
        test_app.dependency_overrides.clear()


def test_get_messages_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id}/messages without auth returns 401."""
    # Arrange
    room_id = uuid4()
    mock_controller = Mock(spec=ChatController)
    test_app.dependency_overrides[get_chat_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/messages")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()
