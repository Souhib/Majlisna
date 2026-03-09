"""Tests for Socket.IO connection handling."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ipg.api.schemas.error import InvalidTokenError, TokenExpiredError
from ipg.api.ws.handlers import connect, disconnect, join_game


@pytest.fixture
def mock_sio():
    """Create a mock Socket.IO server."""
    with patch("ipg.api.ws.handlers.sio") as mock:
        mock.save_session = AsyncMock()
        mock.get_session = AsyncMock(return_value={})
        mock.enter_room = MagicMock()
        mock.emit = AsyncMock()
        yield mock


@pytest.fixture
def mock_fetch_room_state():
    """Mock fetch_room_state to avoid DB access."""
    with patch("ipg.api.ws.handlers.fetch_room_state", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": "room-1", "players": []}
        yield mock


@pytest.fixture
def mock_fetch_game_state():
    """Mock fetch_game_state to avoid DB access."""
    with patch("ipg.api.ws.handlers.fetch_game_state", new_callable=AsyncMock) as mock:
        mock.return_value = {"game_id": "game-1", "players": []}
        yield mock


class TestConnect:
    """Tests for the connect event handler."""

    async def test_connect_with_valid_token(self, mock_sio, mock_fetch_room_state):
        """Valid JWT + room_id connects, joins room, receives room_state."""
        # Arrange
        user_id = uuid4()
        sid = "test-sid-1"
        auth = {"token": "valid-jwt", "room_id": "room-123"}

        mock_user = MagicMock()
        mock_user.id = user_id

        with (
            patch("ipg.api.ws.handlers.get_engine", new_callable=AsyncMock),
            patch("ipg.api.ws.handlers.AuthController") as mock_auth_cls,
        ):
            mock_auth = MagicMock()
            mock_auth.decode_token.return_value = MagicMock(email="test@test.com")
            mock_auth.get_user_by_email = AsyncMock(return_value=mock_user)
            mock_auth_cls.return_value = mock_auth

            # Act
            await connect(sid, {}, auth)

        # Assert
        mock_sio.save_session.assert_called_once_with(sid, {"user_id": str(user_id), "room_id": "room-123"})
        mock_sio.enter_room.assert_called_once_with(sid, "room:room-123")
        mock_sio.emit.assert_called_once_with("room_state", {"id": "room-1", "players": []}, to=sid)

    async def test_connect_no_token_rejected(self, mock_sio):
        """Missing token raises ConnectionRefusedError."""
        auth = {"room_id": "room-123"}

        with pytest.raises(ConnectionRefusedError, match="Missing auth token"):
            await connect("sid-1", {}, auth)

    async def test_connect_no_room_id_rejected(self, mock_sio):
        """Missing room_id raises ConnectionRefusedError."""
        auth = {"token": "valid-jwt"}

        with pytest.raises(ConnectionRefusedError, match="Missing auth token"):
            await connect("sid-1", {}, auth)

    async def test_connect_no_auth_rejected(self, mock_sio):
        """No auth dict raises ConnectionRefusedError."""
        with pytest.raises(ConnectionRefusedError, match="Missing auth token"):
            await connect("sid-1", {}, None)

    async def test_connect_expired_token_rejected(self, mock_sio):
        """Expired JWT raises ConnectionRefusedError."""
        auth = {"token": "expired-jwt", "room_id": "room-123"}

        with (
            patch("ipg.api.ws.handlers.get_engine", new_callable=AsyncMock),
            patch("ipg.api.ws.handlers.AuthController") as mock_auth_cls,
        ):
            mock_auth = MagicMock()
            mock_auth.decode_token.side_effect = TokenExpiredError()
            mock_auth_cls.return_value = mock_auth

            with pytest.raises(ConnectionRefusedError, match="Invalid or expired token"):
                await connect("sid-1", {}, auth)

    async def test_connect_invalid_token_rejected(self, mock_sio):
        """Invalid JWT raises ConnectionRefusedError."""
        auth = {"token": "bad-jwt", "room_id": "room-123"}

        with (
            patch("ipg.api.ws.handlers.get_engine", new_callable=AsyncMock),
            patch("ipg.api.ws.handlers.AuthController") as mock_auth_cls,
        ):
            mock_auth = MagicMock()
            mock_auth.decode_token.side_effect = InvalidTokenError()
            mock_auth_cls.return_value = mock_auth

            with pytest.raises(ConnectionRefusedError, match="Invalid or expired token"):
                await connect("sid-1", {}, auth)

    async def test_connect_user_not_found_rejected(self, mock_sio):
        """Valid token but nonexistent user raises ConnectionRefusedError."""
        auth = {"token": "valid-jwt", "room_id": "room-123"}

        with (
            patch("ipg.api.ws.handlers.get_engine", new_callable=AsyncMock),
            patch("ipg.api.ws.handlers.AuthController") as mock_auth_cls,
        ):
            mock_auth = MagicMock()
            mock_auth.decode_token.return_value = MagicMock(email="gone@test.com")
            mock_auth.get_user_by_email = AsyncMock(return_value=None)
            mock_auth_cls.return_value = mock_auth

            with pytest.raises(ConnectionRefusedError, match="User not found"):
                await connect("sid-1", {}, auth)


class TestJoinGame:
    """Tests for the join_game event handler."""

    async def test_join_game_success(self, mock_sio, mock_fetch_game_state):
        """Valid join_game stores game_id, joins room, sends game_state."""
        # Arrange
        sid = "test-sid-1"
        user_id = str(uuid4())
        mock_sio.get_session.return_value = {"user_id": user_id, "room_id": "room-1"}

        # Act
        await join_game(sid, {"game_id": "game-123"})

        # Assert
        mock_sio.save_session.assert_called_once_with(
            sid, {"user_id": user_id, "room_id": "room-1", "game_id": "game-123"}
        )
        mock_sio.enter_room.assert_called_once_with(sid, "game:game-123")
        mock_sio.emit.assert_called_once()

    async def test_join_game_no_data_ignored(self, mock_sio):
        """Empty data does nothing."""
        await join_game("sid-1", None)
        mock_sio.enter_room.assert_not_called()

    async def test_join_game_no_game_id_ignored(self, mock_sio):
        """Missing game_id does nothing."""
        await join_game("sid-1", {})
        mock_sio.enter_room.assert_not_called()

    async def test_join_game_no_user_in_session_ignored(self, mock_sio):
        """No user_id in session does nothing."""
        mock_sio.get_session.return_value = {}

        await join_game("sid-1", {"game_id": "game-123"})
        mock_sio.enter_room.assert_not_called()


class TestDisconnect:
    """Tests for the disconnect event handler."""

    async def test_disconnect_logs_user(self, mock_sio):
        """Disconnect reads session and logs — no cleanup actions."""
        # Arrange
        mock_sio.get_session.return_value = {"user_id": "user-123"}

        # Act
        await disconnect("sid-1")

        # Assert — no room/game cleanup calls
        mock_sio.get_session.assert_called_once_with("sid-1")
