"""A socket's presence writes against its own disconnect: the disconnect always has the last word.

python-socketio runs a socket's ``disconnect`` handler as soon as the transport closes,
while that socket's ``connect`` or an event handler (``heartbeat``, ``join_game``) may still
be awaiting. ``connect`` used to write the heartbeat (``connected=True``) after its awaits,
so a tab closed during its handshake had its away mark overwritten and read as "connected"
until the sweep found its heartbeat stale (20 s), its grace clock starting only then; a
``heartbeat`` received just before the close did the same. Now every presence write of a
socket runs under its member's presence lock and only while python-socketio still counts the
socket as connected, and the disconnect takes the same lock: whichever way they interleave,
the disconnect's write lands last.

The Socket.IO server here is a stand-in (``FakeSocketServer``) with python-socketio's order:
a closing socket stops counting as connected (``manager.pre_disconnect``) BEFORE its
``disconnect`` handler runs, and loses its session after. The handlers and, where it says
so, the database are real. The interleavings are forced with pause points, never with
sleeps; every wait is bounded (``_bounded``), so a handler that no longer reaches a pause
point, or a close that waits on what it should not, fails the test instead of hanging the run.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.disconnect import HeartbeatResult
from majlisna.api.controllers.token_auth import AuthenticatedCaller
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Room
from majlisna.api.ws import handlers
from majlisna.settings import Settings

# How long one step of a test may take: a bound, never a synchronisation (the pause points
# force every interleaving). The backend CI job has no timeout of its own.
STEP_TIMEOUT_SECONDS = 5


async def _bounded[T](step: Awaitable[T]) -> T:
    """``step``, or a TimeoutError after ``STEP_TIMEOUT_SECONDS``: a failure rather than a hang."""
    return await asyncio.wait_for(step, STEP_TIMEOUT_SECONDS)


class PausePoint:
    """A place a coroutine stops at until the test lets it go on."""

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self) -> None:
        self.reached.set()
        await self.release.wait()

    async def wait_reached(self) -> None:
        """Until the coroutine stops here (bounded: a handler that never does fails the test)."""
        await _bounded(self.reached.wait())


class FakeSocketServer:
    """The part of python-socketio's ``AsyncServer`` the handlers use, in its disconnect order."""

    def __init__(self) -> None:
        self._live: set[str] = set()
        self._sessions: dict[str, dict] = {}
        self._rooms: dict[str, set[str]] = {}
        self._pause_on_room: dict[str, PausePoint] = {}
        self._pause_next_session_read: PausePoint | None = None
        self.emitted: list[tuple[str, str | None]] = []
        self.manager = SimpleNamespace(is_connected=self._is_connected)

    def open(self, sid: str) -> None:
        """A transport opened: python-socketio has registered the socket, its handshake not yet run."""
        self._live.add(sid)
        self._sessions[sid] = {}
        self._rooms[sid] = {sid}

    def pause_on_entering(self, room: str, point: PausePoint) -> None:
        self._pause_on_room[room] = point

    def pause_next_session_read(self, point: PausePoint) -> None:
        self._pause_next_session_read = point

    def _is_connected(self, sid: str, namespace: str = "/") -> bool:  # noqa: ARG002
        return sid in self._live

    async def get_session(self, sid: str) -> dict:
        """The session, read at once; then a stop if the test asked for one (the handler's next await)."""
        if sid not in self._sessions:
            raise KeyError("Session not found")
        session = self._sessions[sid]
        point, self._pause_next_session_read = self._pause_next_session_read, None
        if point is not None:
            await point()
        return session

    async def save_session(self, sid: str, session: dict) -> None:
        if sid not in self._sessions:
            raise KeyError("Session not found")
        self._sessions[sid] = session

    async def enter_room(self, sid: str, room: str) -> None:
        """Enter, then stop if the test asked to. A socket this worker no longer holds: nothing
        here (the Redis manager publishes the request to the other workers)."""
        if sid in self._live:
            self._rooms[sid].add(room)
        point = self._pause_on_room.pop(room, None)
        if point is not None:
            await point()

    async def leave_room(self, sid: str, room: str) -> None:
        self._rooms.get(sid, set()).discard(room)

    def rooms(self, sid: str) -> list[str]:
        return sorted(self._rooms.get(sid, set()))

    async def emit(self, event: str, data: object = None, to: str | None = None, **_: object) -> None:  # noqa: ARG002
        self.emitted.append((event, to))

    async def disconnect(self, sid: str) -> None:
        """The server cuts a socket (``sio.disconnect``): the same order as a client's close."""
        if sid in self._live:
            await self.close(sid)

    async def close(self, sid: str) -> None:
        """The tab goes away: not connected any more, then the disconnect handler, then the session is gone."""
        self._live.discard(sid)
        await handlers.disconnect(sid)
        self._sessions.pop(sid, None)
        self._rooms.pop(sid, None)


@pytest.fixture(autouse=True)
def _no_socket_left_behind() -> Iterator[None]:
    handlers._user_sids.clear()
    handlers._socket_sessions.clear()
    yield
    handlers._user_sids.clear()
    handlers._socket_sessions.clear()


@pytest.fixture(name="server")
def get_server() -> Iterator[FakeSocketServer]:
    fake = FakeSocketServer()
    with patch.object(handlers, "sio", fake):
        yield fake


@pytest.fixture(name="announced")
def get_announced() -> Iterator[MagicMock]:
    """Every room the handlers told about a presence change (``fire_notify_room_changed``)."""
    with patch.object(handlers, "fire_notify_room_changed") as fire:
        yield fire


@pytest_asyncio.fixture(name="on_the_test_database")
async def get_on_the_test_database(engine: AsyncEngine, test_settings: Settings) -> AsyncIterator[None]:
    """The handlers' own sessions on the test database; no room state read for the sockets."""
    with (
        patch.object(handlers, "get_engine", AsyncMock(return_value=engine)),
        patch.object(handlers, "Settings", return_value=test_settings),
        patch.object(handlers, "fetch_room_state", AsyncMock(return_value={})),
    ):
        yield


@pytest_asyncio.fixture(name="lobby")
async def get_lobby(session: AsyncSession, create_user, create_room, test_settings: Settings) -> SimpleNamespace:
    """A lobby: the host, and a guest seated with a real access token."""
    host = await create_user(username="race_host", email="race_host@test.com")
    room: Room = await create_room(owner=host)
    guest = await create_user(username="race_guest", email="race_guest@test.com")
    link = RoomUserLink(room_id=room.id, user_id=guest.id, connected=True, last_seen_at=datetime.now())
    session.add(link)
    await session.commit()
    token = AuthController(session, test_settings).create_access_token(str(guest.id), guest.email_address)
    return SimpleNamespace(room=room, guest=guest, token=token, key=f"{guest.id}:{room.id}")


async def _away_since(session: AsyncSession, room_id: UUID, user_id: UUID, *, seconds: int) -> datetime:
    """Mark the seat away for ``seconds`` already (the phone dropped earlier); answers when it left."""
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
        )
    ).one()
    left_at = datetime.now() - timedelta(seconds=seconds)
    link.connected = False
    link.disconnected_at = left_at
    link.last_seen_at = left_at
    session.add(link)
    await session.commit()
    return left_at


async def _seat(engine: AsyncEngine, room_id: UUID, user_id: UUID) -> RoomUserLink:
    """The seat as the database holds it now (a fresh session)."""
    async with AsyncSession(engine) as fresh:
        return (
            await fresh.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
            )
        ).one()


# ─── The database's last word ───────────────────────────────────────────────


@pytest.mark.parametrize("was_away", [False, True], ids=["present", "away-for-30s"])
@pytest.mark.usefixtures("on_the_test_database")
async def test_a_tab_closed_during_its_handshake_stays_away(
    server: FakeSocketServer,
    announced: MagicMock,
    lobby: SimpleNamespace,
    session: AsyncSession,
    engine: AsyncEngine,
    was_away: bool,
):
    """The handshake had the seat (session saved) but not yet its heartbeat when the tab closed.

    The close marks the player away; the handshake must not mark them back. A player whose
    phone had dropped earlier keeps the grace clock that started then.
    """
    # Prepare — the handshake stops right before its heartbeat (its last channel entered)
    left_at = await _away_since(session, lobby.room.id, lobby.guest.id, seconds=30) if was_away else None
    before_heartbeat = PausePoint()
    server.pause_on_entering(f"user:{lobby.guest.id}", before_heartbeat)
    server.open("sid-guest")

    # Act — the tab closes while the handshake waits
    handshake = asyncio.create_task(
        handlers.connect("sid-guest", {}, {"token": lobby.token, "room_id": str(lobby.room.id)})
    )
    await before_heartbeat.wait_reached()
    await _bounded(server.close("sid-guest"))
    before_heartbeat.release.set()
    await _bounded(handshake)

    # Assert
    seat = await _seat(engine, lobby.room.id, lobby.guest.id)
    assert seat.connected is False
    if was_away:
        assert seat.disconnected_at == left_at
        announced.assert_not_called()
    else:
        assert seat.disconnected_at is not None
        announced.assert_called_once_with(str(lobby.room.id))
    assert lobby.key not in handlers._user_sids
    assert ("room_state", "sid-guest") not in server.emitted


@pytest.mark.usefixtures("on_the_test_database")
async def test_a_heartbeat_received_before_the_close_does_not_bring_the_player_back(
    server: FakeSocketServer, announced: MagicMock, lobby: SimpleNamespace, engine: AsyncEngine
):
    """The heartbeat event came in, then the tab closed before the heartbeat was written."""
    # Prepare — a seated socket; its next heartbeat stops before reading its session
    server.open("sid-guest")
    await server.save_session("sid-guest", {"user_id": str(lobby.guest.id), "room_id": str(lobby.room.id)})
    handlers._user_sids[lobby.key] = "sid-guest"
    received = PausePoint()
    server.pause_next_session_read(received)

    # Act
    beat = asyncio.create_task(handlers.heartbeat("sid-guest"))
    await received.wait_reached()
    await _bounded(server.close("sid-guest"))
    received.release.set()
    await _bounded(beat)

    # Assert
    seat = await _seat(engine, lobby.room.id, lobby.guest.id)
    assert seat.connected is False
    assert seat.disconnected_at is not None
    announced.assert_called_once_with(str(lobby.room.id))


# ─── A close during the write waits for it ──────────────────────────────────


async def test_a_disconnect_during_the_heartbeat_write_is_written_after_it(server: FakeSocketServer):
    """The close arrives while the heartbeat's write is in flight: the away mark is written second."""
    # Prepare — the heartbeat's write stops in the middle; every write is recorded in order
    writes: list[str] = []
    mid_write = PausePoint()

    async def heartbeat_write(*_: object) -> HeartbeatResult:
        await mid_write()
        writes.append("present")
        return HeartbeatResult.REFRESHED

    async def away_write(*_: object) -> bool:
        writes.append("away")
        return True

    server.open("sid1")
    await server.save_session("sid1", {"user_id": "u1", "room_id": "room1"})
    handlers._user_sids["u1:room1"] = "sid1"

    with (
        patch.object(handlers, "get_engine", AsyncMock()),
        patch.object(handlers, "AsyncSession", return_value=_db_session()),
        patch.object(handlers, "update_heartbeat", heartbeat_write),
        patch.object(handlers, "mark_user_disconnected", away_write),
        patch.object(handlers, "fire_notify_room_changed"),
    ):
        # Act — the close is under way before the write goes on
        beat = asyncio.create_task(handlers.heartbeat("sid1"))
        await mid_write.wait_reached()
        closing = asyncio.create_task(server.close("sid1"))
        mid_write.release.set()
        await _bounded(asyncio.gather(beat, closing))

    # Assert
    assert writes == ["present", "away"]


# ─── A handshake whose socket is already gone ───────────────────────────────


@pytest.mark.parametrize("room_id", [None, "00000000-0000-0000-0000-000000000001"], ids=["personal", "room"])
async def test_a_handshake_closed_during_its_token_check_leaves_nothing_behind(
    server: FakeSocketServer, room_id: str | None
):
    """The close came while the token was being checked: its disconnect found no session, nothing to undo.

    The handshake then stops: no session tracked for the session audit, no seat tracked for
    the tab deduplication, no channel, no heartbeat. It used to go on and fail on the
    session of a socket that no longer existed (``KeyError`` out of the handler).
    """
    # Prepare
    user = MagicMock(id=UUID("00000000-0000-0000-0000-000000000123"))
    checking_token = PausePoint()

    async def slow_token_check(*_: object) -> AuthenticatedCaller:
        await checking_token()
        return AuthenticatedCaller(user=user, session_id=uuid4())

    seat_check = MagicMock(all=MagicMock(return_value=[(user.id, UUID(room_id))] if room_id else []))
    session = _db_session()
    session.exec = AsyncMock(return_value=seat_check)
    heartbeat_write = AsyncMock(return_value=HeartbeatResult.REFRESHED)
    server.open("sid1")
    auth = {"token": "t"} | ({"room_id": room_id} if room_id else {})

    with (
        patch.object(handlers, "get_engine", AsyncMock()),
        patch.object(handlers, "AsyncSession", return_value=session),
        patch.object(handlers, "authenticate_caller", slow_token_check),
        patch.object(handlers, "update_heartbeat", heartbeat_write),
        patch.object(handlers, "fire_notify_room_changed"),
    ):
        # Act
        handshake = asyncio.create_task(handlers.connect("sid1", {}, auth))
        await checking_token.wait_reached()
        await _bounded(server.close("sid1"))
        checking_token.release.set()
        accepted = await _bounded(handshake)

    # Assert
    assert accepted is False
    assert handlers._user_sids == {}
    assert handlers._socket_sessions == {}
    heartbeat_write.assert_not_awaited()
    assert server.emitted == []


async def test_join_game_for_a_socket_closed_before_its_heartbeat_writes_nothing(server: FakeSocketServer):
    """The socket entered the game's channel, then closed: no heartbeat, no state for a socket that is gone."""
    # Prepare
    room_id = "00000000-0000-0000-0000-000000000001"
    user_id = "00000000-0000-0000-0000-000000000002"
    game_id = "00000000-0000-0000-0000-000000000003"
    server.open("sid1")
    await server.save_session("sid1", {"user_id": user_id, "room_id": room_id})
    handlers._user_sids[f"{user_id}:{room_id}"] = "sid1"
    entered = PausePoint()
    server.pause_on_entering(f"game:{game_id}", entered)
    heartbeat_write = AsyncMock(return_value=HeartbeatResult.REFRESHED)
    fetch_state = AsyncMock(return_value={"game_id": game_id})

    with (
        patch.object(handlers, "get_engine", AsyncMock()),
        patch.object(handlers, "AsyncSession", side_effect=_sessions(_join_game_session(room_id))),
        patch.object(handlers, "update_heartbeat", heartbeat_write),
        patch.object(handlers, "mark_user_disconnected", AsyncMock(return_value=True)),
        patch.object(handlers, "fetch_game_state", fetch_state),
        patch.object(handlers, "fire_notify_room_changed"),
    ):
        # Act
        joining = asyncio.create_task(handlers.join_game("sid1", {"game_id": game_id}))
        await entered.wait_reached()
        await _bounded(server.close("sid1"))
        entered.release.set()
        await _bounded(joining)

    # Assert
    heartbeat_write.assert_not_awaited()
    fetch_state.assert_not_awaited()
    assert server.emitted == []


# ─── Helpers ────────────────────────────────────────────────────────────────


def _db_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _join_game_session(game_room_id: str) -> AsyncMock:
    """join_game's validation: the seat, then the game, in that room."""
    seat = MagicMock(first=MagicMock(return_value=MagicMock()))
    game = MagicMock(first=MagicMock(return_value=MagicMock(room_id=game_room_id)))
    session = _db_session()
    session.exec = AsyncMock(side_effect=[seat, game])
    return session


def _sessions(*first: AsyncMock) -> Callable[..., AsyncMock]:
    """An ``AsyncSession`` stand-in: ``first`` in order, then a fresh mocked session each time."""
    queue = list(first)
    return lambda *_args, **_kwargs: queue.pop(0) if queue else _db_session()
