"""Tests for Socket.IO broadcast behavior through routes."""

from unittest.mock import AsyncMock, patch

import pytest

from majlisna.api.ws.notify import notify_game_changed, notify_room_changed


@pytest.fixture
def mock_sio():
    """Mock Socket.IO server."""
    with patch("majlisna.api.ws.notify.sio") as mock:
        mock.emit = AsyncMock()
        yield mock


@pytest.fixture
def mock_fetch_room_state():
    with patch("majlisna.api.ws.notify.fetch_room_state", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": "room-1", "players": []}
        yield mock


# ========== Room Broadcasts ==========


async def test_notify_room_changed_emits_to_room(mock_sio, mock_fetch_room_state):  # noqa: ARG001
    """Room state broadcast targets the correct Socket.IO room."""
    await notify_room_changed("room-abc")

    mock_sio.emit.assert_called_once_with("room_state", {"id": "room-1", "players": []}, to="room:room-abc")


async def test_room_notification_failure_does_not_propagate(mock_sio):  # noqa: ARG001
    """If broadcast fails, it doesn't crash the caller."""
    with patch("majlisna.api.ws.notify.fetch_room_state", new_callable=AsyncMock, side_effect=RuntimeError("oops")):
        # Should not raise
        await notify_room_changed("room-abc")


# ========== Game Broadcasts ==========


async def test_game_updated_emits_signal_to_room(mock_sio, mock_fetch_room_state):  # noqa: ARG001
    """Game change emits game_updated to the game room AND the room, not per-user state.

    The room is in the recipient list because `game:{id}` membership is built by
    `auto_join_game_room`, which walks a process-local SID map — with 4 uvicorn
    workers the first `game_updated` of a game would otherwise miss most of the
    table. `room:{id}` membership is established at connect on every worker.
    """
    with patch("majlisna.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value="room-1"):
        await notify_game_changed("game-1")

    # game_updated signal addressed to BOTH rooms in one emit — get_participants
    # merges the recipient sets, so a client in both is delivered to once.
    mock_sio.emit.assert_any_call("game_updated", {"game_id": "game-1"}, to=["game:game-1", "room:room-1"])
    # Also notifies room
    mock_sio.emit.assert_any_call("room_state", {"id": "room-1", "players": []}, to="room:room-1")


async def test_game_broadcast_with_room_notification(mock_sio, mock_fetch_room_state):  # noqa: ARG001
    """Game change with room_id also broadcasts room_state."""
    await notify_game_changed("game-1", room_id="room-1")

    # Room state should be broadcast
    mock_fetch_room_state.assert_called_once_with("room-1")


async def test_game_broadcast_failure_does_not_propagate(mock_sio):
    """If game broadcast fails, it doesn't crash the caller."""
    mock_sio.emit.side_effect = Exception("Redis down")

    with patch("majlisna.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value=None):
        # Should not raise
        await notify_game_changed("game-1")
