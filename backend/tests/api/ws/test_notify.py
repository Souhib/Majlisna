"""Tests for Socket.IO notification functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from majlisna.api.models.game import GameType
from majlisna.api.ws.notify import notify_chat_message, notify_game_changed, notify_room_changed, notify_user_kicked
from majlisna.api.ws.state import fetch_game_state
from majlisna.api.ws.state import fetch_room_state as state_fetch_room_state


@pytest.fixture
def mock_sio():
    """Mock Socket.IO server for notify tests."""
    with patch("majlisna.api.ws.notify.sio") as mock:
        mock.emit = AsyncMock()
        yield mock


@pytest.fixture
def mock_fetch_room_state():
    with patch("majlisna.api.ws.notify.fetch_room_state", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": "room-1", "players": [], "active_game_id": None}
        yield mock


# ========== notify_room_changed ==========


async def test_notify_room_broadcasts_room_state(mock_sio, mock_fetch_room_state):
    """Fetches room state and emits to room."""
    await notify_room_changed("room-1")

    mock_fetch_room_state.assert_called_once_with("room-1")
    mock_sio.emit.assert_called_once_with(
        "room_state", {"id": "room-1", "players": [], "active_game_id": None}, to="room:room-1"
    )


async def test_notify_room_does_not_raise_on_failure(mock_sio):  # noqa: ARG001
    """Best-effort — swallows exceptions."""
    with patch("majlisna.api.ws.notify.fetch_room_state", new_callable=AsyncMock, side_effect=Exception("DB error")):
        # Should not raise
        await notify_room_changed("room-1")


# ========== notify_game_changed ==========


async def test_notify_game_emits_game_updated_signal(mock_sio, mock_fetch_room_state):
    """Emits game_updated signal to game room instead of per-user state."""
    with patch("majlisna.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value="room-1"):
        await notify_game_changed("game-1")

    # Signal addressed to the game room AND the room (see notify_game_changed for
    # why the room is required: game-room membership is per-worker).
    mock_sio.emit.assert_any_call("game_updated", {"game_id": "game-1"}, to=["game:game-1", "room:room-1"])
    # Also notifies room
    mock_fetch_room_state.assert_called_once_with("room-1")


async def test_notify_game_uses_provided_room_id(mock_sio, mock_fetch_room_state):  # noqa: ARG001
    """When room_id is passed, uses it directly instead of looking up."""
    await notify_game_changed("game-1", room_id="room-provided")

    mock_fetch_room_state.assert_called_once_with("room-provided")


async def test_notify_game_does_not_raise_on_failure(mock_sio):
    """Best-effort — swallows exceptions."""
    mock_sio.emit.side_effect = Exception("Redis down")

    with patch("majlisna.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value=None):
        # Should not raise
        await notify_game_changed("game-1")


# ========== notify_chat_message ==========


async def test_notify_chat_message_emits_event(mock_sio):
    """notify_chat_message emits to correct Socket.IO room."""
    message_data = {"user_id": "u1", "text": "salam", "timestamp": "2026-01-01T00:00:00"}

    await notify_chat_message("room-1", message_data)

    mock_sio.emit.assert_called_once_with("chat_message", message_data, to="room:room-1")


# ========== notify_user_kicked ==========


async def test_notify_user_kicked_emits_event(mock_sio):
    """notify_user_kicked emits to personal user room."""
    await notify_user_kicked("user-42", "room-1")

    mock_sio.emit.assert_called_once_with("you_were_kicked", {"room_id": "room-1"}, to="user:user-42")


# ========== fetch_room_state ==========


async def test_fetch_room_state_returns_state():
    """fetch_room_state returns proper room state dict."""
    mock_result = MagicMock()
    mock_result.model_dump.return_value = {"id": "room-1", "players": [], "active_game_id": None}

    mock_controller = MagicMock()
    mock_controller.get_room_state = AsyncMock(return_value=mock_result)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    room_id = "00000000-0000-0000-0000-000000000001"

    with (
        patch("majlisna.api.ws.state.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.state.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.state.RoomController", return_value=mock_controller),
    ):
        result = await state_fetch_room_state(room_id)

    assert result == {"id": "room-1", "players": [], "active_game_id": None}
    mock_controller.get_room_state.assert_awaited_once()


# ========== fetch_game_state ==========


async def test_fetch_game_state_returns_state():
    """fetch_game_state returns state for valid game/user."""
    mock_game = MagicMock()
    mock_game.type = GameType.UNDERCOVER

    mock_exec_result = MagicMock()
    mock_exec_result.first.return_value = mock_game

    mock_state = MagicMock()
    mock_state.model_dump.return_value = {"phase": "describe", "players": []}

    mock_controller = MagicMock()
    mock_controller.get_state = AsyncMock(return_value=mock_state)

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_exec_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.state.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.state.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.state.UndercoverGameController", return_value=mock_controller),
    ):
        result = await fetch_game_state("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002")

    assert result == {"phase": "describe", "players": []}


async def test_fetch_game_state_not_found():
    """fetch_game_state returns empty dict for non-existent game."""
    mock_exec_result = MagicMock()
    mock_exec_result.first.return_value = None

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_exec_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.state.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.state.AsyncSession", return_value=mock_session),
    ):
        result = await fetch_game_state("00000000-0000-0000-0000-000000000099", "00000000-0000-0000-0000-000000000002")

    assert result == {}


async def test_notify_game_still_reaches_the_room_when_the_game_room_is_empty(mock_sio, mock_fetch_room_state):  # noqa: ARG001
    """No client has called join_game yet — the room is what carries the signal.

    This is the shape of the first `game_updated` of every game: the start route
    emits it before clients have navigated to the game page, so `game:{id}` holds
    only whatever `auto_join_game_room` managed to add on this one worker.
    """
    await notify_game_changed("game-fresh", room_id="room-fresh")

    emitted = [call for call in mock_sio.emit.await_args_list if call.args[0] == "game_updated"]
    assert len(emitted) == 1, "game_updated must be a single emit, not one per room"
    assert emitted[0].kwargs["to"] == ["game:game-fresh", "room:room-fresh"]


async def test_notify_game_without_a_resolvable_room_still_emits_to_the_game_room():
    """A game whose room cannot be resolved must not lose its signal entirely."""
    with (
        patch("majlisna.api.ws.notify._get_room_id_for_game", new_callable=AsyncMock, return_value=None),
        patch("majlisna.api.ws.notify.sio") as mock,
    ):
        mock.emit = AsyncMock()
        await notify_game_changed("orphan-game")

    mock.emit.assert_awaited_once_with("game_updated", {"game_id": "orphan-game"}, to=["game:orphan-game"])
