"""Tests for Socket.IO notification functions."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from loguru import logger

from majlisna.api.models.game import GameType
from majlisna.api.schemas.common import TimerExpiredAction
from majlisna.api.schemas.error import PlayerRemovedFromGameError
from majlisna.api.schemas.room import RoomInviteView
from majlisna.api.ws.notify import (
    NO_OP_TIMER_ACTIONS,
    _get_room_id_for_game,
    notify_chat_message,
    notify_game_changed,
    notify_member_removed,
    notify_member_removed_by_host,
    notify_room_changed,
    notify_room_invite,
    notify_timer_outcome,
    notify_user_kicked,
)
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
        mock.return_value = {"id": "room-1", "players": [{"user_id": "u-1"}], "active_game_id": None}
        yield mock


# ========== notify_room_changed ==========


async def test_notify_room_broadcasts_room_state(mock_sio, mock_fetch_room_state):
    """Fetches room state and emits to room."""
    await notify_room_changed("room-1")

    mock_fetch_room_state.assert_called_once_with("room-1")
    mock_sio.emit.assert_called_once_with(
        "room_state",
        {"id": "room-1", "players": [{"user_id": "u-1"}], "active_game_id": None},
        to=["member:room-1:u-1"],
    )


async def test_notify_room_does_not_raise_on_failure(mock_sio):  # noqa: ARG001
    """Best-effort — swallows exceptions."""
    with patch("majlisna.api.ws.notify.fetch_room_state", new_callable=AsyncMock, side_effect=Exception("DB error")):
        # Should not raise
        await notify_room_changed("room-1")


# ========== notify_member_removed ==========


async def test_member_removed_mid_game_signals_the_game(mock_sio, mock_fetch_room_state):
    """A leave or kick during a game reaches the game pages, not only the lobby.

    The leaver is eliminated server-side; game pages refetch on game_updated alone
    (no polling while the socket is up), so a room_state alone left the table on a
    stale game with the leaver still describing.
    """
    await notify_member_removed("room-1", "game-1")

    mock_sio.emit.assert_any_call("game_updated", {"game_id": "game-1"}, to=["game:game-1", "room:room-1"])
    mock_fetch_room_state.assert_called_once_with("room-1")


async def test_member_removed_signals_the_game_it_was_given_even_if_it_just_ended(
    mock_sio,
    mock_fetch_room_state,  # noqa: ARG001 — keeps the room-state lookup off the database
):
    """The game read before the removal is signalled, whatever the room says now.

    A kick or a leave can decide the game (the last Undercover gone): the room then
    has no active game, and looking it up after the removal sent only room_state,
    so the rest of the table never left the finished game for its colophon.
    """
    with patch("majlisna.api.ws.notify.get_active_game_id", new_callable=AsyncMock, return_value=None) as lookup:
        await notify_member_removed("room-1", "game-1")

    lookup.assert_not_called()
    mock_sio.emit.assert_any_call("game_updated", {"game_id": "game-1"}, to=["game:game-1", "room:room-1"])


async def test_member_removed_from_lobby_sends_room_state_only(mock_sio, mock_fetch_room_state):
    """No game running: the room state, and no game signal."""
    await notify_member_removed("room-1", None)

    mock_fetch_room_state.assert_called_once_with("room-1")
    events = [c.args[0] for c in mock_sio.emit.call_args_list]
    assert events == ["room_state"]


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
    """A kick: to the player's personal channel, saying it was not a ban (they may come back)."""
    await notify_user_kicked("user-42", "room-1")

    mock_sio.emit.assert_called_once_with("you_were_kicked", {"room_id": "room-1", "banned": False}, to="user:user-42")


async def test_notify_user_kicked_says_when_it_is_a_ban(mock_sio):
    """A ban: the same event, ``banned`` true, so the player's /rooms says they are banned."""
    await notify_user_kicked("user-42", "room-1", banned=True)

    mock_sio.emit.assert_called_once_with("you_were_kicked", {"room_id": "room-1", "banned": True}, to="user:user-42")


@pytest.mark.parametrize("banned", [False, True])
async def test_the_room_is_told_which_of_the_hosts_removals_took_a_seat(mock_sio, banned):
    """Every member's activity line says "removed" or "banned", not "left": the event goes to
    the room's channel (it carries no PIN), with the seat and the kind of removal."""
    await notify_member_removed_by_host("room-1", "user-42", banned=banned)

    mock_sio.emit.assert_called_once_with(
        "member_removed_by_host", {"room_id": "room-1", "user_id": "user-42", "banned": banned}, to="room:room-1"
    )


async def test_telling_the_room_of_a_removal_does_not_raise_on_failure(mock_sio):
    """Best effort, like every notify: the removal stands, the lines read "left"."""
    mock_sio.emit.side_effect = RuntimeError("redis down")

    await notify_member_removed_by_host("room-1", "user-42", banned=True)


# ========== notify_room_invite ==========


async def test_notify_room_invite_names_the_stored_invite_and_never_the_pin(mock_sio):
    """The friend's strip gets the invite's id, the room's code and the inviter: the PIN
    stays on the server (a ban rotates it, and an invite sent before then still works)."""
    # Prepare
    invite = RoomInviteView(
        id=UUID("00000000-0000-0000-0000-0000000000a1"),
        room_id=UUID("00000000-0000-0000-0000-0000000000b2"),
        public_id="LULIM",
        invited_by="Yusuf",
        expires_at=datetime(2026, 11, 2, 12, 30, tzinfo=UTC),
    )

    # Act
    await notify_room_invite("user-42", invite)

    # Assert
    mock_sio.emit.assert_called_once_with(
        "room_invite",
        {
            "id": "00000000-0000-0000-0000-0000000000a1",
            "room_id": "00000000-0000-0000-0000-0000000000b2",
            "public_id": "LULIM",
            "invited_by": "Yusuf",
            "expires_at": "2026-11-02T12:30:00Z",
        },
        to="user:user-42",
    )


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


@pytest.mark.parametrize(
    ("game_type", "controller_name", "method"),
    [
        (GameType.UNDERCOVER, "UndercoverGameController", "get_state"),
        (GameType.CODENAMES, "CodenamesGameController", "get_board"),
        (GameType.WORD_QUIZ, "WordQuizGameController", "get_state"),
        (GameType.MCQ_QUIZ, "McqQuizGameController", "get_state"),
    ],
)
async def test_fetch_game_state_reads_the_state_in_the_requested_language(
    game_type: GameType, controller_name: str, method: str
):
    """The Socket.IO push resolves hints and meanings in the client's language, like the REST read.

    It used to call every controller with its English default, and the client writes
    the push into its query cache — so an Arabic player's game-over meanings turned
    English right after the REST response had them in Arabic.
    """
    # Prepare
    mock_game = MagicMock()
    mock_game.type = game_type
    mock_exec_result = MagicMock()
    mock_exec_result.first.return_value = mock_game
    mock_state = MagicMock()
    mock_state.model_dump.return_value = {"ok": True}
    mock_controller = MagicMock()
    setattr(mock_controller, method, AsyncMock(return_value=mock_state))
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_exec_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    game_id = "00000000-0000-0000-0000-000000000001"
    user_id = "00000000-0000-0000-0000-000000000002"

    # Act
    with (
        patch("majlisna.api.ws.state.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.state.AsyncSession", return_value=mock_session),
        patch(f"majlisna.api.ws.state.{controller_name}", return_value=mock_controller),
    ):
        result = await fetch_game_state(game_id, user_id, lang="ar")

    # Assert
    assert result == {"ok": True}
    getattr(mock_controller, method).assert_awaited_once_with(
        UUID(game_id), UUID(user_id), lang="ar", update_heartbeat=False
    )


def _mcq_state_session() -> AsyncMock:
    """A mocked DB session for fetch_game_state whose game is a running MCQ quiz."""
    game = MagicMock()
    game.type = GameType.MCQ_QUIZ
    exec_result = MagicMock()
    exec_result.first.return_value = game
    session = AsyncMock()
    session.exec = AsyncMock(return_value=exec_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


async def _fetch_game_state_logging(failure: Exception) -> tuple[dict, list[str]]:
    """fetch_game_state with the controller failing as given; the WARNING+ levels it logged."""
    controller = MagicMock()
    controller.get_state = AsyncMock(side_effect=failure)
    levels: list[str] = []
    sink_id = logger.add(lambda message: levels.append(message.record["level"].name), level="WARNING")
    try:
        with (
            patch("majlisna.api.ws.state.get_engine", new_callable=AsyncMock),
            patch("majlisna.api.ws.state.AsyncSession", return_value=_mcq_state_session()),
            patch("majlisna.api.ws.state.McqQuizGameController", return_value=controller),
        ):
            result = await fetch_game_state(
                "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"
            )
    finally:
        logger.remove(sink_id)
    return result, levels


async def test_fetch_game_state_for_a_player_no_longer_in_the_game_is_no_server_error():
    """A refusal for this caller is not a failure of the server.

    join_game checks the seat, then reads the state: a player who leaves in between
    (their page was joining the game as they left) is refused by the game's own
    get_state with a 4xx. It was logged with logger.exception, an ERROR with a
    traceback (a tracked issue in production; seen in the E2E gate's backend log),
    while BaseError already logs every 4xx at INFO ("Expected 4xx log at INFO").
    """
    # Act
    result, levels = await _fetch_game_state_logging(PlayerRemovedFromGameError(user_id="u", game_id="g"))

    # Assert — no state to send, and nothing at WARNING or above
    assert result == {}
    assert levels == []


async def test_fetch_game_state_still_logs_a_real_failure_as_an_error():
    # Act
    result, levels = await _fetch_game_state_logging(RuntimeError("the database went away"))

    # Assert
    assert result == {}
    assert levels == ["ERROR"]


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


# ========== timer-expired outcomes (BDP-03, SEC F08) ==========


def test_the_no_op_timer_answers_are_exactly_those_that_change_nothing():
    """Only a true no-op may skip the broadcast: one that hid a real change would leave
    the table on a stale game. ``none`` is Undercover's "no timed phase" (it writes the
    state back unchanged); every other answer moves the game."""
    expected = {
        TimerExpiredAction.PAUSED,
        TimerExpiredAction.TIMER_NOT_EXPIRED,
        TimerExpiredAction.NOT_PLAYING,
        TimerExpiredAction.ROUND_ALREADY_RESOLVED,
        TimerExpiredAction.NONE,
    }
    assert set(NO_OP_TIMER_ACTIONS) == expected


@pytest.mark.parametrize("action", list(TimerExpiredAction))
async def test_a_timer_outcome_is_broadcast_only_when_it_changed_the_game(action: TimerExpiredAction):
    """N clients fire one timer; the one call that acted reaches the table, the N-1 others do not."""
    # Act
    with patch("majlisna.api.ws.notify.notify_game_changed", new_callable=AsyncMock) as notify:
        await notify_timer_outcome("game-1", action)

    # Assert
    if action in NO_OP_TIMER_ACTIONS:
        notify.assert_not_awaited()
    else:
        notify.assert_awaited_once_with("game-1")


async def test_the_room_lookup_reads_the_room_id_alone(engine, sample_game, count_statements):
    """BDP-03: resolving a game's room loaded the whole Game row, its live_state JSON
    included, on every game broadcast — a third full read of the state per mutation."""
    # Prepare
    live_state_reads = count_statements("live_state")

    # Act
    with patch("majlisna.api.ws.notify.get_engine", new=AsyncMock(return_value=engine)):
        room_id = await _get_room_id_for_game(str(sample_game.id))

    # Assert
    assert room_id == str(sample_game.room_id)
    assert live_state_reads.count == 0


async def test_the_room_lookup_of_an_unknown_game_is_none(engine):
    """No game, no room: the signal still goes to the game room alone."""
    # Act
    with patch("majlisna.api.ws.notify.get_engine", new=AsyncMock(return_value=engine)):
        room_id = await _get_room_id_for_game("00000000-0000-0000-0000-0000000000aa")

    # Assert
    assert room_id is None
