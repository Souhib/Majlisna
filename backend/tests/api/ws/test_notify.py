"""Tests for Socket.IO notification functions."""

from unittest.mock import AsyncMock, patch

import pytest

from ipg.api.ws.notify import notify_game_changed, notify_room_changed


@pytest.fixture
def mock_sio():
    """Mock Socket.IO server for notify tests."""
    with patch("ipg.api.ws.notify.sio") as mock:
        mock.emit = AsyncMock()
        yield mock


@pytest.fixture
def mock_fetch_room_state():
    with patch("ipg.api.ws.notify.fetch_room_state", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": "room-1", "players": [], "active_game_id": None}
        yield mock


class TestNotifyRoomChanged:
    """Tests for notify_room_changed."""

    async def test_broadcasts_room_state(self, mock_sio, mock_fetch_room_state):
        """Fetches room state and emits to room."""
        await notify_room_changed("room-1")

        mock_fetch_room_state.assert_called_once_with("room-1")
        mock_sio.emit.assert_called_once_with(
            "room_state", {"id": "room-1", "players": [], "active_game_id": None}, to="room:room-1"
        )

    async def test_does_not_raise_on_failure(self, mock_sio):
        """Best-effort — swallows exceptions."""
        with patch("ipg.api.ws.notify.fetch_room_state", new_callable=AsyncMock, side_effect=Exception("DB error")):
            # Should not raise
            await notify_room_changed("room-1")


class TestNotifyGameChanged:
    """Tests for notify_game_changed."""

    async def test_emits_game_updated_signal(self, mock_sio, mock_fetch_room_state):
        """Emits game_updated signal to game room instead of per-user state."""
        with patch("ipg.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value="room-1"):
            await notify_game_changed("game-1")

        # Signal to game room
        mock_sio.emit.assert_any_call("game_updated", {"game_id": "game-1"}, to="game:game-1")
        # Also notifies room
        mock_fetch_room_state.assert_called_once_with("room-1")

    async def test_uses_provided_room_id(self, mock_sio, mock_fetch_room_state):
        """When room_id is passed, uses it directly instead of looking up."""
        await notify_game_changed("game-1", room_id="room-provided")

        mock_fetch_room_state.assert_called_once_with("room-provided")

    async def test_does_not_raise_on_failure(self, mock_sio):
        """Best-effort — swallows exceptions."""
        mock_sio.emit.side_effect = Exception("Redis down")

        with patch("ipg.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value=None):
            # Should not raise
            await notify_game_changed("game-1")
