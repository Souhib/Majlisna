"""BDP-04 and SEC F04 through real Socket.IO clients: a return is announced, a removed seat is cut.

**BDP-04.** A player whose socket dropped and came back, or who went silent long
enough for the sweep to mark them away and then heartbeat again, stayed "away" on
everyone else's screen: ``connect`` answered the room state to the returning socket
alone, ``heartbeat`` answered nothing, and the lobby does not poll while its own
socket is up.

**SEC F04 (socket side).** A kick detached the kicked socket only on the worker that
served the kick (``_user_sids`` is per process): on any other worker it stayed in
``room:{id}`` (whose broadcasts carry the PIN) and ``game:{id}``. Every worker now
audits its own sockets each tick, and ``join_game`` / ``heartbeat`` re-check the seat.

The server is a real python-socketio ``AsyncServer`` running the real handlers on
uvicorn, inside the test's event loop and against the test database. It uses the
in-memory client manager (production adds Redis between workers, which changes who
delivers a broadcast, not what is broadcast). The clients are python-socketio's
synchronous ``Client`` over HTTP long-polling, each in its own threads, like two
phones at the same table.
"""

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
import socketio
import uvicorn
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.disconnect import _handle_permanent_disconnect, _mark_stale_users
from majlisna.api.controllers.room import RoomController
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.table import Room, User
from majlisna.api.ws import handlers, notify
from majlisna.settings import Settings

# How long the rest of the table may take to be told. The product promise is "a
# reconnect clears the 'away' label on the other players' screens within a second",
# and the E2E suite holds it on the real stack; on an idle machine the announcement
# lands here in tens of milliseconds. The bound is wider because these tests share a
# machine with other suites, where one database round trip can take hundreds of
# milliseconds (a 1 s bound failed at a load average of 20-28). The value does not
# carry the proof: this test server runs no sweep loop and nothing else sends a
# room_state, so the only way A can see B back is the announcement, and before the
# fix none was ever sent — the wait ran out whatever its length.
ANNOUNCED_WITHIN_SECONDS = 5.0
# Setup steps (a connect, the first "away" broadcast) are not what is measured; a
# connect took over 10 s on a saturated machine.
SETUP_TIMEOUT_SECONDS = 30.0
# How long the control waits for a broadcast that must not come.
NOTHING_WITHIN_SECONDS = 1.0


class Phone:
    """One browser tab: a python-socketio client and every room_state it was told."""

    def __init__(self, user: User, token: str):
        self.user = user
        self.token = token
        self.client = socketio.Client(reconnection=False)
        self._lock = threading.Lock()
        self._room_states: list[dict] = []
        self.cut = threading.Event()
        self.client.on("room_state", self._on_room_state)
        self.client.on("disconnect", self._on_disconnect)

    def _on_room_state(self, state: dict) -> None:
        with self._lock:
            self._room_states.append(state)

    def _on_disconnect(self, *_reason: object) -> None:
        self.cut.set()

    def room_states(self) -> list[dict]:
        with self._lock:
            return list(self._room_states)

    def sees(self, user_id: UUID) -> dict | None:
        """How the LAST room_state this phone received shows ``user_id`` (None: not listed / nothing yet)."""
        states = self.room_states()
        if not states:
            return None
        return next((p for p in states[-1]["players"] if p["user_id"] == str(user_id)), None)

    async def connect(self, base_url: str, room_id: UUID) -> None:
        await asyncio.to_thread(
            self.client.connect,
            base_url,
            auth={"token": self.token, "room_id": str(room_id)},
            transports=["polling"],
            socketio_path="/socket.io",
            wait_timeout=SETUP_TIMEOUT_SECONDS,
        )

    async def emit(self, event: str, data: object = None) -> None:
        await asyncio.to_thread(self.client.emit, event, data)

    async def hang_up(self) -> None:
        if self.client.connected:
            await asyncio.to_thread(self.client.disconnect)


async def _until(condition: Callable[[], bool], timeout: float) -> bool:
    """Whether ``condition`` became true within ``timeout`` seconds (checked every 20 ms)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.02)
    return True


async def _drain_notifications() -> None:
    """Let every fire-and-forget broadcast finish while the test database is still patched in."""
    while notify._pending_tasks:
        await asyncio.gather(*list(notify._pending_tasks), return_exceptions=True)


@pytest_asyncio.fixture(name="live_server")
async def get_live_server(engine: AsyncEngine, test_settings: Settings) -> AsyncIterator[str]:
    """The real handlers behind a real Socket.IO server on an ephemeral port; yields its URL."""
    # A short ping interval: a long-poll returns at least every second, so a client's
    # disconnect (which waits for its pending poll) takes a second, not the default 25 s.
    server = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        ping_interval=1,
        ping_timeout=5,
        logger=False,
        engineio_logger=False,
    )
    for event in ("connect", "join_game", "heartbeat", "disconnect"):
        server.on(event, getattr(handlers, event))
    app = socketio.ASGIApp(server, socketio_path="/socket.io")
    test_engine = AsyncMock(return_value=engine)
    handlers._user_sids.clear()
    handlers._socket_sessions.clear()
    with (
        patch.object(handlers, "sio", server),
        patch.object(notify, "sio", server),
        patch("majlisna.api.ws.handlers.get_engine", test_engine),
        patch("majlisna.api.ws.notify.get_engine", test_engine),
        patch("majlisna.api.ws.state.get_engine", test_engine),
        patch("majlisna.api.ws.handlers.Settings", return_value=test_settings),
    ):
        uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_level="warning"))
        serving = asyncio.create_task(uv.serve())
        assert await _until(lambda: uv.started, SETUP_TIMEOUT_SECONDS), "the test server did not start"
        port = uv.servers[0].sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            uv.should_exit = True
            await serving
            await _drain_notifications()
            handlers._user_sids.clear()
            handlers._socket_sessions.clear()


@pytest_asyncio.fixture(name="table")
async def get_table(session: AsyncSession, create_user, create_room, test_settings: Settings) -> dict:
    """A lobby: A (host) and B and C seated, each with a real access token."""
    auth = AuthController(session, test_settings)
    host = await create_user(username="phone_a", email="phone_a@test.com")
    room: Room = await create_room(owner=host)
    guests = [
        await create_user(username="phone_b", email="phone_b@test.com"),
        await create_user(username="phone_c", email="phone_c@test.com"),
    ]
    session.add_all(
        [RoomUserLink(room_id=room.id, user_id=g.id, connected=True, last_seen_at=datetime.now()) for g in guests]
    )
    await session.commit()
    phones = [Phone(u, auth.create_access_token(str(u.id), u.email_address)) for u in (host, *guests)]
    return {"room": room, "a": phones[0], "b": phones[1], "c": phones[2]}


@pytest_asyncio.fixture(name="seated")
async def get_seated(live_server: str, table: dict) -> AsyncIterator[dict]:
    """A and B connected to the room (C stays offline unless a test connects it)."""
    phones: list[Phone] = [table["a"], table["b"], table["c"]]
    await table["a"].connect(live_server, table["room"].id)
    await table["b"].connect(live_server, table["room"].id)
    try:
        yield {**table, "url": live_server}
    finally:
        for phone in phones:
            await phone.hang_up()
        await _drain_notifications()


async def _link(session: AsyncSession, room_id: UUID, user_id: UUID) -> RoomUserLink | None:
    return (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == room_id)
            .where(RoomUserLink.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).first()


# ─── BDP-04 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_player_who_drops_and_reconnects_is_seen_back_within_a_second(seated: dict):
    """B's socket drops (A sees B away), then B reconnects: A is told B is back."""
    # Prepare — B drops
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    await b.hang_up()
    assert await _until(lambda: (a.sees(b.user.id) or {}).get("is_connected") is False, SETUP_TIMEOUT_SECONDS)
    assert a.sees(b.user.id)["away_seconds_left"] is not None

    # Act — B comes back on a new socket
    back = Phone(b.user, b.token)
    await back.connect(seated["url"], seated["room"].id)
    try:
        # Assert
        assert await _until(lambda: (a.sees(b.user.id) or {}).get("is_connected") is True, ANNOUNCED_WITHIN_SECONDS)
        assert a.sees(b.user.id)["away_seconds_left"] is None
    finally:
        await back.hang_up()


@pytest.mark.asyncio
async def test_a_silent_player_who_heartbeats_again_is_seen_back_within_a_second(seated: dict, session: AsyncSession):
    """B's socket stays up but goes silent; the sweep marks B away; B heartbeats: A is told B is back."""
    # Prepare — B silent past HEARTBEAT_STALE_SECONDS, the sweep marks B away and broadcasts it
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    room_id: UUID = seated["room"].id
    link = await _link(session, room_id, b.user.id)
    assert link is not None
    link.last_seen_at = datetime.now() - timedelta(seconds=60)
    session.add(link)
    await session.commit()
    assert str(room_id) in await _mark_stale_users(session)
    await notify.notify_room_changed(str(room_id))  # what the checker loop's on_room_changed does
    assert await _until(lambda: (a.sees(b.user.id) or {}).get("is_connected") is False, SETUP_TIMEOUT_SECONDS)

    # Act
    await b.emit("heartbeat")

    # Assert
    assert await _until(lambda: (a.sees(b.user.id) or {}).get("is_connected") is True, ANNOUNCED_WITHIN_SECONDS)


@pytest.mark.asyncio
async def test_a_heartbeat_of_a_present_player_broadcasts_nothing(seated: dict):
    """The control: the every-10-seconds heartbeat of a player who never left is not news."""
    # Prepare — each connect answers its own socket's initial state; wait for both, so a
    # slow one cannot arrive inside the window below and read as a broadcast
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    assert await _until(lambda: bool(a.room_states()) and bool(b.room_states()), SETUP_TIMEOUT_SECONDS)
    await _drain_notifications()
    before = len(a.room_states())

    # Act
    await b.emit("heartbeat")
    await asyncio.sleep(NOTHING_WITHIN_SECONDS)

    # Assert
    assert len(a.room_states()) == before


# ─── SEC F04: a removed seat cuts the socket, whichever worker holds it ──


async def _kick_elsewhere(session: AsyncSession, room_id: UUID, host_id: UUID, user_id: UUID) -> None:
    """A kick served by ANOTHER worker: the seat and the game go, a ban is written, and
    this worker's socket of the player is never told (its ``_user_sids`` is not that
    worker's)."""
    link = await _link(session, room_id, user_id)
    assert link is not None
    session.add(RoomBan(room_id=room_id, user_id=user_id, banned_by=host_id))
    await _handle_permanent_disconnect(session, link)


@pytest.mark.asyncio
async def test_the_next_audit_tick_cuts_a_socket_kicked_on_another_worker(seated: dict, session: AsyncSession):
    """The kicked socket leaves room:{id} and is disconnected by this worker's next tick; it hears nothing more."""
    # Prepare
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    room_id: UUID = seated["room"].id
    await _kick_elsewhere(session, room_id, a.user.id, b.user.id)
    assert b.client.connected

    # Act — this worker's tick
    cut = await handlers.audit_local_socket_memberships(session)
    await session.commit()

    # Assert — cut, and no longer in the room's broadcasts (which carry the PIN)
    assert cut == 1
    assert await _until(b.cut.is_set, ANNOUNCED_WITHIN_SECONDS)
    heard_by_b = len(b.room_states())
    await notify.notify_room_changed(str(room_id))
    assert await _until(lambda: a.sees(b.user.id) is None and len(a.room_states()) > 0, SETUP_TIMEOUT_SECONDS)
    assert len(b.room_states()) == heard_by_b


@pytest.mark.asyncio
async def test_the_kick_routes_own_push_never_hands_the_new_pin_to_a_socket_held_elsewhere(
    seated: dict, session: AsyncSession
):
    """Owner rule (c) rotates the PIN so the kicked player cannot come back; their socket must not hear it.

    The kick route detaches the kicked socket on ITS worker only; one held by another
    worker is cut by that worker's next audit tick, up to 5 s later — after the route's
    own room_state push, which carries the new PIN. The push is addressed to the
    members the state lists, so a socket whose seat is gone is never among them.
    """
    # Prepare — B's socket is held by "another worker": this one does not know its sid
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    room_id: UUID = seated["room"].id
    assert await _until(lambda: bool(a.room_states()) and bool(b.room_states()), SETUP_TIMEOUT_SECONDS)
    await _drain_notifications()
    old_pin = (await session.exec(select(Room.password).where(Room.id == room_id))).one()
    handlers._user_sids.pop(f"{b.user.id}:{room_id}", None)
    heard_by_b = len(b.room_states())

    # Act — the kick route, step by step (routes/room.py::kick_player)
    await RoomController(session).kick_player(room_id, a.user.id, b.user.id)
    await notify.notify_user_kicked(str(b.user.id), str(room_id))
    await handlers.remove_user_from_room_socket(str(b.user.id), str(room_id))
    await notify.notify_member_removed(str(room_id), None)

    # Assert — A is told the new PIN, B's socket (still connected, in room:{id}) is not
    new_pin = (
        await session.exec(select(Room.password).where(Room.id == room_id).execution_options(populate_existing=True))
    ).one()
    assert new_pin != old_pin
    assert await _until(
        lambda: bool(a.room_states()) and a.room_states()[-1]["password"] == new_pin, SETUP_TIMEOUT_SECONDS
    )
    await asyncio.sleep(NOTHING_WITHIN_SECONDS)
    assert b.client.connected
    assert len(b.room_states()) == heard_by_b
    assert all(state["password"] != new_pin for state in b.room_states())


@pytest.mark.asyncio
async def test_join_game_after_a_kick_is_refused_and_cut(seated: dict, session: AsyncSession):
    """Before the tick even runs, a kicked page asking for the game is refused and its socket cut."""
    # Prepare
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    await _kick_elsewhere(session, seated["room"].id, a.user.id, b.user.id)

    # Act
    await b.emit("join_game", {"game_id": "00000000-0000-0000-0000-000000000099"})

    # Assert
    assert await _until(b.cut.is_set, ANNOUNCED_WITHIN_SECONDS)


@pytest.mark.asyncio
async def test_a_kicked_player_cannot_reconnect_to_the_room(seated: dict, session: AsyncSession):
    """The socket half of SEC F04's re-join: a new handshake of the banned, unseated player is refused."""
    # Prepare
    a: Phone = seated["a"]
    b: Phone = seated["b"]
    room_id: UUID = seated["room"].id
    await _kick_elsewhere(session, room_id, a.user.id, b.user.id)
    retry = Phone(b.user, b.token)

    # Act / Assert
    with pytest.raises(socketio.exceptions.ConnectionError):
        await retry.connect(seated["url"], room_id)
    assert not retry.client.connected


@pytest.mark.asyncio
async def test_the_audit_leaves_a_seated_member_alone(seated: dict, session: AsyncSession):
    """The control: a tick with every seat intact cuts nobody."""
    # Prepare
    a: Phone = seated["a"]
    b: Phone = seated["b"]

    # Act
    cut = await handlers.audit_local_socket_memberships(session)
    await session.commit()
    await asyncio.sleep(0.3)

    # Assert
    assert cut == 0
    assert a.client.connected
    assert b.client.connected


@pytest.mark.asyncio
async def test_a_banned_player_cannot_connect_even_with_a_seat_row(seated: dict, session: AsyncSession):
    """A ban voids the seat at the handshake too (owner rule (c)): the row alone is not membership."""
    # Prepare — C still has a seat row, and a ban (a kick whose departure is still in flight)
    a: Phone = seated["a"]
    c: Phone = seated["c"]
    session.add(RoomBan(room_id=seated["room"].id, user_id=c.user.id, banned_by=a.user.id))
    await session.commit()

    # Act / Assert
    with pytest.raises(socketio.exceptions.ConnectionError):
        await c.connect(seated["url"], seated["room"].id)
    assert not c.client.connected
