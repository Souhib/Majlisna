"""Tests for Socket.IO event handlers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from majlisna.api.schemas.error import InvalidTokenError
from majlisna.api.ws.handlers import _user_sids, auto_join_game_room, connect, disconnect, heartbeat, join_game
from majlisna.api.ws.server import sio as real_sio


@pytest.fixture(autouse=True)
def _clean_user_sids():
    """Clear _user_sids before/after each test."""
    _user_sids.clear()
    yield
    _user_sids.clear()


@pytest.fixture
def mock_sio():
    """Mock Socket.IO server for handler tests."""
    with patch("majlisna.api.ws.handlers.sio") as mock:
        mock.enter_room = AsyncMock()
        mock.emit = AsyncMock()
        mock.disconnect = AsyncMock()
        mock.save_session = AsyncMock()
        mock.get_session = AsyncMock(return_value={"user_id": "u1", "room_id": "room1"})
        yield mock


@pytest.fixture
def mock_connect_dependencies(mock_sio):  # noqa: ARG001
    """Mock all connect handler dependencies."""
    mock_user = MagicMock()
    mock_user.id = "00000000-0000-0000-0000-000000000123"
    mock_user.email = "test@test.com"

    mock_auth_controller = MagicMock()
    mock_auth_controller.decode_token.return_value = MagicMock(email="test@test.com")
    mock_auth_controller.get_user_by_email = AsyncMock(return_value=mock_user)

    mock_session = AsyncMock()
    mock_engine = MagicMock()

    patches = {
        "engine": patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock, return_value=mock_engine),
        "session": patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        "auth": patch("majlisna.api.ws.handlers.AuthController", return_value=mock_auth_controller),
        "heartbeat": patch("majlisna.api.ws.handlers.update_heartbeat", new_callable=AsyncMock),
        "fetch_room": patch("majlisna.api.ws.handlers.fetch_room_state", new_callable=AsyncMock, return_value={}),
    }

    started = {}
    for name, p in patches.items():
        started[name] = p.start()

    # Make AsyncSession work as async context manager
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # Mock session.exec to return a result with .first() returning a mock link
    mock_link = MagicMock()
    mock_session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=mock_link)))

    yield {"user": mock_user, "auth_controller": mock_auth_controller, **started}

    for p in patches.values():
        p.stop()


# ========== auto_join_game_room ==========


async def test_auto_join_awaits_enter_room(mock_sio):
    """enter_room must be awaited, not just called."""
    _user_sids["u1:room1"] = "sid1"
    _user_sids["u2:room1"] = "sid2"
    _user_sids["u3:room2"] = "sid3"

    result = await auto_join_game_room("game1", "room1")

    assert result == 2
    assert mock_sio.enter_room.await_count == 2
    mock_sio.enter_room.assert_any_await("sid1", "game:game1")
    mock_sio.enter_room.assert_any_await("sid2", "game:game1")
    # sid3 is in room2, not room1
    for call in mock_sio.enter_room.await_args_list:
        assert call.args[0] != "sid3"


async def test_auto_join_empty_user_sids(mock_sio):
    """Returns 0 and never calls enter_room when no users connected."""
    result = await auto_join_game_room("game1", "room1")

    assert result == 0
    mock_sio.enter_room.assert_not_awaited()


async def test_auto_join_safe_dict_iteration(mock_sio):
    """Dict mutation during iteration must not raise RuntimeError."""
    _user_sids["u1:room1"] = "sid1"

    async def add_entry_side_effect(_sid, _room):
        # Simulate a concurrent connect modifying _user_sids during await
        _user_sids["u_new:room1"] = "sid_new"

    mock_sio.enter_room.side_effect = add_entry_side_effect

    # Should NOT raise RuntimeError: dictionary changed size during iteration
    result = await auto_join_game_room("game1", "room1")
    assert result == 1


# ========== connect ==========


TEST_ROOM_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_ID = "00000000-0000-0000-0000-000000000123"


async def test_connect_awaits_enter_room(mock_sio, mock_connect_dependencies):  # noqa: ARG001
    """connect must await both enter_room calls."""
    await connect("sid1", {}, {"token": "valid", "room_id": TEST_ROOM_ID})

    assert mock_sio.enter_room.await_count == 2
    mock_sio.enter_room.assert_any_await("sid1", f"room:{TEST_ROOM_ID}")
    mock_sio.enter_room.assert_any_await("sid1", f"user:{TEST_USER_ID}")


async def test_connect_stores_sid_in_user_sids(mock_sio, mock_connect_dependencies):  # noqa: ARG001
    """connect stores the SID in _user_sids."""
    await connect("sid1", {}, {"token": "valid", "room_id": TEST_ROOM_ID})

    assert _user_sids[f"{TEST_USER_ID}:{TEST_ROOM_ID}"] == "sid1"


async def test_connect_deduplicates_tabs(mock_sio, mock_connect_dependencies):  # noqa: ARG001
    """When user reconnects, old SID is disconnected."""
    _user_sids[f"{TEST_USER_ID}:{TEST_ROOM_ID}"] = "old_sid"

    await connect("new_sid", {}, {"token": "valid", "room_id": TEST_ROOM_ID})

    mock_sio.disconnect.assert_awaited_with("old_sid")
    assert _user_sids[f"{TEST_USER_ID}:{TEST_ROOM_ID}"] == "new_sid"


# ========== join_game ==========


async def test_join_game_awaits_enter_room(mock_sio):
    """join_game must await enter_room."""
    room_id = "00000000-0000-0000-0000-000000000001"
    user_id = "00000000-0000-0000-0000-000000000002"
    game_id = "00000000-0000-0000-0000-000000000003"
    mock_sio.get_session.return_value = {"user_id": user_id, "room_id": room_id}

    mock_link = MagicMock()
    mock_game = MagicMock()
    mock_game.room_id = room_id

    mock_result = MagicMock()
    mock_result.first.return_value = mock_link

    mock_game_result = MagicMock()
    mock_game_result.first.return_value = mock_game

    mock_session = AsyncMock()
    # First exec call returns link, second returns game
    mock_session.exec = AsyncMock(side_effect=[mock_result, mock_game_result])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.handlers.update_heartbeat", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.fetch_game_state", new_callable=AsyncMock, return_value={}),
    ):
        await join_game("sid1", {"game_id": game_id})

    assert mock_sio.enter_room.await_count == 1
    mock_sio.enter_room.assert_awaited_with("sid1", f"game:{game_id}")


def _join_game_session(game_room_id: str) -> AsyncMock:
    """A mocked DB session for join_game: the room link, then the game in that room."""
    link_result = MagicMock()
    link_result.first.return_value = MagicMock()
    game = MagicMock()
    game.room_id = game_room_id
    game_result = MagicMock()
    game_result.first.return_value = game
    session = AsyncMock()
    session.exec = AsyncMock(side_effect=[link_result, game_result])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.parametrize(
    ("payload_lang", "session_lang", "expected"),
    [
        ("ar", None, "ar"),  # the join_game payload names it
        (None, "fr", "fr"),  # else the handshake's auth.lang, stored at connect
        ("ar", "fr", "ar"),  # the payload wins: the player switched language since connecting
        (None, None, "en"),  # an older client sends none
        ("xx", None, "en"),  # never an arbitrary string
    ],
)
async def test_join_game_sends_the_initial_state_in_the_players_language(
    mock_sio, payload_lang: str | None, session_lang: str | None, expected: str
):
    """The initial game_state push is resolved in the client's language, not the English default."""
    # Prepare
    room_id = "00000000-0000-0000-0000-000000000001"
    user_id = "00000000-0000-0000-0000-000000000002"
    game_id = "00000000-0000-0000-0000-000000000003"
    session_data = {"user_id": user_id, "room_id": room_id}
    if session_lang:
        session_data["lang"] = session_lang
    mock_sio.get_session.return_value = session_data
    payload = {"game_id": game_id}
    if payload_lang:
        payload["lang"] = payload_lang
    fetch = AsyncMock(return_value={"game_id": game_id})

    # Act
    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=_join_game_session(room_id)),
        patch("majlisna.api.ws.handlers.update_heartbeat", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.fetch_game_state", fetch),
    ):
        await join_game("sid1", payload)

    # Assert
    fetch.assert_awaited_once_with(game_id, user_id, lang=expected)
    mock_sio.emit.assert_awaited_once_with("game_state", {"game_id": game_id}, to="sid1")
    saved = mock_sio.save_session.await_args.args[1]
    assert saved["lang"] == expected


async def test_connect_stores_the_handshake_language(mock_sio, mock_connect_dependencies):  # noqa: ARG001
    """auth.lang is kept in the Socket.IO session (normalised) for join_game to use."""
    # Act
    await connect("sid1", {}, {"token": "t", "room_id": "00000000-0000-0000-0000-000000000001", "lang": "ar"})

    # Assert
    saved = mock_sio.save_session.await_args.args[1]
    assert saved["lang"] == "ar"


# ========== disconnect ==========


async def test_disconnect_cleans_user_sids(mock_sio):
    """disconnect removes the SID from _user_sids."""
    _user_sids["u1:room1"] = "sid1"
    mock_sio.get_session.return_value = {"user_id": "u1", "room_id": "room1"}

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession") as mock_session_cls,
        patch("majlisna.api.ws.handlers.mark_user_disconnected", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.fire_notify_room_changed"),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await disconnect("sid1")

    assert "u1:room1" not in _user_sids


# ========== sio.enter_room is async ==========


def test_sio_enter_room_is_coroutine_function():
    """Documents expectation that enter_room is async."""
    assert asyncio.iscoroutinefunction(real_sio.enter_room)


# ========== Multi-tab deduplication ==========


async def test_old_tab_disconnect_does_not_remove_active_sid(mock_sio):
    """When old tab disconnects, new tab's SID remains in _user_sids.

    The disconnect handler only removes the entry if the disconnecting SID
    matches the stored one. A replaced SID should leave the new entry intact.
    """
    _user_sids["user1:room1"] = "new_sid"

    # Simulate old tab's disconnect — session returns the same user/room
    mock_sio.get_session.return_value = {"user_id": "user1", "room_id": "room1"}

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession") as mock_session_cls,
        patch("majlisna.api.ws.handlers.mark_user_disconnected", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.fire_notify_room_changed"),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        # Disconnect with the OLD sid — should NOT remove new_sid
        await disconnect("old_sid")

    assert _user_sids.get("user1:room1") == "new_sid"


async def test_replaced_socket_disconnect_does_not_mark_the_player_away(mock_sio):
    """A reload's old socket closing must not start the grace clock of a player still here."""
    # Prepare: the reload's new socket already took the old one's place
    _user_sids["user1:room1"] = "new_sid"
    mock_sio.get_session.return_value = {"user_id": "user1", "room_id": "room1"}

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession"),
        patch("majlisna.api.ws.handlers.mark_user_disconnected", new_callable=AsyncMock) as mock_mark,
        patch("majlisna.api.ws.handlers.fire_notify_room_changed") as mock_fire,
    ):
        # Act
        await disconnect("old_sid")

    # Assert
    mock_mark.assert_not_awaited()
    mock_fire.assert_not_called()
    assert _user_sids.get("user1:room1") == "new_sid"


async def test_connect_records_the_new_sid_before_closing_the_old_one(mock_sio, mock_connect_dependencies):  # noqa: ARG001
    """The old socket's disconnect may run inside `sio.disconnect`: it must already see its replacement."""
    # Prepare
    key = f"{TEST_USER_ID}:{TEST_ROOM_ID}"
    _user_sids[key] = "old_sid"
    seen_during_disconnect: list[str | None] = []
    mock_sio.disconnect.side_effect = lambda _sid: seen_during_disconnect.append(_user_sids.get(key))

    # Act
    await connect("new_sid", {}, {"token": "valid", "room_id": TEST_ROOM_ID})

    # Assert
    assert seen_during_disconnect == ["new_sid"]
    assert _user_sids[key] == "new_sid"


async def test_rapid_tab_switches_only_latest_survives(mock_sio):  # noqa: ARG001
    """Opening 5 tabs rapidly: only the last SID should survive."""
    for i in range(5):
        _user_sids["user1:room1"] = f"sid_{i}"

    assert _user_sids["user1:room1"] == "sid_4"
    # Only one entry per user:room key
    room1_entries = [k for k in _user_sids if k == "user1:room1"]
    assert len(room1_entries) == 1


async def test_different_rooms_independent(mock_sio):  # noqa: ARG001
    """Same user in different rooms has independent SID entries."""
    _user_sids["user1:roomA"] = "sid_a"
    _user_sids["user1:roomB"] = "sid_b"

    del _user_sids["user1:roomA"]

    assert _user_sids.get("user1:roomB") == "sid_b"
    assert "user1:roomA" not in _user_sids


async def test_auto_join_with_stale_sids_raises(mock_sio):
    """auto_join_game_room propagates enter_room errors for stale SIDs.

    auto_join_game_room does NOT wrap enter_room in try/except, so a stale
    SID causing enter_room to raise will propagate to the caller.
    """
    _user_sids["user1:room1"] = "stale_sid"

    mock_sio.enter_room = AsyncMock(side_effect=Exception("SID not found"))

    with pytest.raises(Exception, match="SID not found"):
        await auto_join_game_room("game1", "room1")


# ========== connect — rejection cases ==========


async def test_connect_missing_token_rejected(mock_sio):  # noqa: ARG001
    """connect with no auth token raises ConnectionRefusedError."""
    with pytest.raises(ConnectionRefusedError, match="Missing auth token"):
        await connect("sid1", {}, {"room_id": "room1"})


async def test_connect_without_room_is_the_personal_channel(mock_sio, mock_connect_dependencies):
    """No room_id: the player's own channel (room invites), nothing else.

    It used to be refused, and socket.io-client never retries a refused connection,
    so every room invite was "sent" and never arrived.
    """
    await connect("sid1", {}, {"token": "valid"})

    user_id = mock_connect_dependencies["user"].id
    mock_sio.enter_room.assert_awaited_once_with("sid1", f"user:{user_id}")
    mock_sio.save_session.assert_awaited_once_with("sid1", {"user_id": user_id, "room_id": None, "lang": None})
    # no room: no heartbeat, no room state, no membership lookup
    mock_connect_dependencies["heartbeat"].assert_not_awaited()
    mock_connect_dependencies["fetch_room"].assert_not_awaited()
    mock_sio.emit.assert_not_awaited()
    assert _user_sids == {}


async def test_connect_personal_channel_refuses_a_bad_token(mock_sio):
    """The personal channel authenticates like a room connection."""
    mock_auth_controller = MagicMock()
    mock_auth_controller.decode_token.side_effect = InvalidTokenError()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.handlers.AuthController", return_value=mock_auth_controller),
        pytest.raises(ConnectionRefusedError, match="Invalid or expired token"),
    ):
        await connect("sid1", {}, {"token": "expired"})
    mock_sio.enter_room.assert_not_awaited()


async def test_join_game_ignored_on_the_personal_channel(mock_sio):
    """A personal connection has no room, so it has no game to join."""
    mock_sio.get_session.return_value = {"user_id": "u1", "room_id": None}
    await join_game("sid1", {"game_id": "00000000-0000-0000-0000-000000000001"})
    mock_sio.enter_room.assert_not_awaited()
    mock_sio.emit.assert_not_awaited()


async def test_connect_invalid_token_rejected(mock_sio):  # noqa: ARG001
    """connect with expired/invalid token raises ConnectionRefusedError."""
    mock_auth_controller = MagicMock()
    mock_auth_controller.decode_token.side_effect = InvalidTokenError()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.handlers.AuthController", return_value=mock_auth_controller),
        pytest.raises(ConnectionRefusedError, match="Invalid or expired token"),
    ):
        await connect("sid1", {}, {"token": "expired", "room_id": TEST_ROOM_ID})


@pytest.mark.asyncio
async def test_connect_malformed_room_id_is_refused_not_crashed(mock_sio):  # noqa: ARG001
    """A client-supplied room_id that is not a UUID must be a clean refusal.

    It is parsed with `UUID(...)` inside a block that only catches token errors, so
    a malformed value escaped as an unhandled ValueError — and python-socketio only
    special-cases ConnectionRefusedError, so anything else reaches the engine.io
    layer as a server error.
    """
    with pytest.raises(ConnectionRefusedError, match="Invalid room_id"):
        await connect("sid1", {}, {"token": "valid", "room_id": "not-a-uuid"})


# ========== heartbeat ==========


async def test_heartbeat_updates_last_seen(mock_sio):
    """heartbeat event calls update_heartbeat with correct user_id and room_id."""
    mock_sio.get_session.return_value = {"user_id": "u1", "room_id": "room1"}

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.handlers.update_heartbeat", new_callable=AsyncMock) as mock_heartbeat,
    ):
        await heartbeat("sid1")

    mock_heartbeat.assert_awaited_once_with(mock_session, "u1", "room1")


async def test_heartbeat_no_session_data_returns_early(mock_sio):
    """heartbeat with missing session data returns without error."""
    mock_sio.get_session.return_value = {}

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock) as mock_engine,
        patch("majlisna.api.ws.handlers.update_heartbeat", new_callable=AsyncMock) as mock_heartbeat,
    ):
        # Should not raise
        await heartbeat("sid1")

    mock_engine.assert_not_awaited()
    mock_heartbeat.assert_not_awaited()


# ========== disconnect — DB interactions ==========


async def test_disconnect_marks_user_disconnected(mock_sio):
    """disconnect event calls mark_user_disconnected."""
    _user_sids["u1:room1"] = "sid1"
    mock_sio.get_session.return_value = {"user_id": "u1", "room_id": "room1"}

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.handlers.mark_user_disconnected", new_callable=AsyncMock) as mock_mark,
        patch("majlisna.api.ws.handlers.fire_notify_room_changed"),
    ):
        await disconnect("sid1")

    mock_mark.assert_awaited_once_with(mock_session, "u1", "room1")


async def test_disconnect_fires_room_notification(mock_sio):
    """disconnect fires fire_notify_room_changed."""
    _user_sids["u1:room1"] = "sid1"
    mock_sio.get_session.return_value = {"user_id": "u1", "room_id": "room1"}

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
        patch("majlisna.api.ws.handlers.mark_user_disconnected", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.fire_notify_room_changed") as mock_fire,
    ):
        await disconnect("sid1")

    mock_fire.assert_called_once_with("room1")


# ========== join_game — invalid game ==========


async def test_join_game_invalid_game_returns_early(mock_sio):
    """join_game with game not belonging to room returns without joining."""
    room_id = "00000000-0000-0000-0000-000000000001"
    user_id = "00000000-0000-0000-0000-000000000002"
    game_id = "00000000-0000-0000-0000-000000000003"
    mock_sio.get_session.return_value = {"user_id": user_id, "room_id": room_id}

    mock_link = MagicMock()

    # Game belongs to a different room
    mock_game = MagicMock()
    mock_game.room_id = "00000000-0000-0000-0000-999999999999"

    mock_result = MagicMock()
    mock_result.first.return_value = mock_link

    mock_game_result = MagicMock()
    mock_game_result.first.return_value = mock_game

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(side_effect=[mock_result, mock_game_result])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("majlisna.api.ws.handlers.get_engine", new_callable=AsyncMock),
        patch("majlisna.api.ws.handlers.AsyncSession", return_value=mock_session),
    ):
        await join_game("sid1", {"game_id": game_id})

    # Should NOT have joined the game room
    mock_sio.enter_room.assert_not_awaited()
