import asyncio
import weakref
from collections.abc import Collection
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy import and_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.disconnect import HeartbeatResult, mark_user_disconnected, update_heartbeat
from majlisna.api.controllers.token_auth import AuthenticatedCaller, authenticate_caller
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.table import Game
from majlisna.api.schemas.error import InvalidTokenError, SessionRevokedError, TokenExpiredError
from majlisna.api.utils.multilingual import normalize_lang
from majlisna.api.ws.notify import fire_notify_room_changed, member_channel
from majlisna.api.ws.server import sio
from majlisna.api.ws.state import fetch_game_state, fetch_room_state
from majlisna.database import get_engine
from majlisna.settings import Settings

# Track user→sid mapping for multi-tab deduplication. Keyed "{user_id}:{room_id}",
# both canonical UUID strings. PER PROCESS: with 4 uvicorn workers each holds only its
# own sockets, which is why a kick cannot detach a socket held by another worker
# directly (``audit_local_socket_memberships``).
_user_sids: dict[str, str] = {}

# The AuthSession (the token's ``sid``) behind each socket of THIS worker, personal and
# room sockets alike; a legacy token names none and is not listed. The session was
# checked at connect only, so a socket opened before a logout, a reset or a reuse
# detection kept hearing the room state and the invites (code and PIN) until it happened
# to reconnect (review R5): ``audit_local_socket_memberships`` cuts them every tick.
_socket_sessions: dict[str, UUID] = {}

# The token refusals a handshake answers with a clean ConnectionRefusedError.
_TOKEN_ERRORS = (InvalidTokenError, TokenExpiredError, SessionRevokedError)

# One lock per member of THIS worker ("{user_id}:{room_id}", the ``_user_sids`` key), held by
# every presence write of that member's sockets: present (connect, heartbeat, join_game,
# ``_write_presence``) and away (disconnect, ``_write_absence``). python-socketio runs a
# socket's disconnect handler as soon as its transport closes, while the socket's connect or
# a heartbeat may still be awaiting the database; unordered, their "present" landed after the
# close's away mark, and a tab closed during its handshake read as connected until the sweep
# found its heartbeat stale (20 s), its grace clock starting only then. A lock of this worker
# is enough: python-socketio serves every event of a socket, its disconnect included, in the
# worker that holds the socket. A lock of the member rather than of the socket, so that one
# tab's close is ordered against the writes of the tab that replaced it as well. An entry
# lives while a write holds or awaits it. Tests: tests/api/ws/test_presence_race.py.
_presence_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _presence_lock(key: str) -> asyncio.Lock:
    """The presence lock of one member on this worker (``_presence_locks``)."""
    lock = _presence_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _presence_locks[key] = lock
    return lock


def _is_live(sid: str) -> bool:
    """Whether python-socketio still counts the socket as connected.

    It stops the moment it starts closing the socket (``manager.pre_disconnect``), BEFORE the
    disconnect handler runs: from then on nothing may write this socket's presence.
    """
    return bool(sio.manager.is_connected(sid, "/"))


async def _write_presence(sid: str, user_id: str, room_id: str) -> HeartbeatResult | None:
    """``update_heartbeat`` for a socket still connected; None, writing nothing, for one that is closing or gone.

    Under the member's presence lock: a close that begins while this write is in flight waits
    for it and writes the away mark after; a close that began before it leaves this write
    undone. Either way the close has the last word.
    """
    async with _presence_lock(f"{user_id}:{room_id}"):
        if not _is_live(sid):
            return None
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            return await update_heartbeat(session, user_id, room_id)


async def _write_absence(sid: str, user_id: str, room_id: str) -> bool:
    """Mark the member away for their closed socket ``sid``; True when that flipped the seat.

    Nothing when a newer socket of the same player holds the seat on this worker (a reload, a
    second tab): the player is still here. Asked under the presence lock, so a replacement
    that connected while this close waited for the lock counts too. On another worker, the
    newer socket's heartbeat restores the seat within one interval instead.
    """
    key = f"{user_id}:{room_id}"
    async with _presence_lock(key):
        tracked = _user_sids.get(key)
        if tracked is not None and tracked != sid:
            return False
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            return await mark_user_disconnected(session, user_id, room_id)


async def _connect_personal(sid: str, token: str) -> bool:
    """A connection with no room: the signed-in player's own channel (``user:{id}``).

    The app shell keeps one open on every signed-in page so a friend's room invite
    reaches the player wherever they are. It joins nothing else, sends no room
    state and records no heartbeat: there is no room to be present in.

    It used to be refused ("Missing auth token or room_id"), and socket.io-client
    does not retry a connection the server refuses, so every invite was answered
    "Invite sent" and never arrived.

    False (refused) when the socket closed while its token was checked: see ``connect``.
    """
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            # Type and BOTH claims, like every HTTP request (controllers/token_auth.py).
            caller = await authenticate_caller(session, Settings(), token)
    except _TOKEN_ERRORS as e:
        logger.debug("Socket.IO personal auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e

    if not _is_live(sid):
        logger.debug("Socket.IO personal connect: sid={} closed during its handshake", sid)
        return False
    user_id = str(caller.user.id)
    _track_session(sid, caller.session_id)
    await sio.save_session(sid, {"user_id": user_id, "room_id": None, "lang": None})
    await sio.enter_room(sid, f"user:{user_id}")
    logger.debug("Socket.IO personal connect: sid={} user={}", sid, user_id)
    return True


async def _seated_members(session: AsyncSession, pairs: Collection[tuple[UUID, UUID]]) -> set[tuple[UUID, UUID]]:
    """Which of these (user, room) pairs hold a seat and no ban — ONE statement for all of them.

    A seat is a ``RoomUserLink``; a ``RoomBan`` (the host's ban, not a plain kick) voids
    it. The query reads the cross product of the users and rooms
    asked about and keeps the asked pairs only.
    """
    if not pairs:
        return set()
    user_ids = {user_id for user_id, _ in pairs}
    room_ids = {room_id for _, room_id in pairs}
    rows = (
        await session.exec(
            select(RoomUserLink.user_id, RoomUserLink.room_id)
            .outerjoin(
                RoomBan,
                and_(
                    col(RoomBan.room_id) == col(RoomUserLink.room_id),
                    col(RoomBan.user_id) == col(RoomUserLink.user_id),
                ),
            )
            .where(col(RoomUserLink.user_id).in_(user_ids))
            .where(col(RoomUserLink.room_id).in_(room_ids))
            .where(col(RoomBan.id).is_(None))
        )
    ).all()
    asked = set(pairs)
    return {(user_id, room_id) for user_id, room_id in rows if (user_id, room_id) in asked}


async def _authenticate_member(sid: str, token: str, room_uuid: UUID) -> AuthenticatedCaller:
    """The caller behind ``token``, who must hold a seat in the room and no ban; refuse otherwise."""
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            # Type and BOTH claims, like every HTTP request (controllers/token_auth.py):
            # resolving on `email` alone let a token of a deleted account into the room
            # of whoever registered the same address next (SEC F09).
            caller = await authenticate_caller(session, Settings(), token)

            # Authorization: the user must actually be a member of this room —
            # otherwise any authenticated user could listen to any room's state
            # (which carries the room PIN) and chat. A banned player is not one, even
            # while a seat row exists.
            if not await _seated_members(session, [(caller.user.id, room_uuid)]):
                raise ConnectionRefusedError("Not a member of this room")
            return caller
    except _TOKEN_ERRORS as e:
        logger.debug("Socket.IO auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e


def _track_session(sid: str, session_id: UUID | None) -> None:
    """Remember the session behind a socket that has been let in (``_socket_sessions``)."""
    if session_id is not None:
        _socket_sessions[sid] = session_id


async def _detach_socket(sid: str, room_id: str) -> None:
    """Cut a LOCAL socket off the room: leave ``room:{id}`` and every ``game:*`` channel, then disconnect.

    Leaving first, so that no broadcast reaches it while its disconnect handler runs.
    ``sio.rooms(sid)`` only knows this worker's sockets, which is all this is given.
    """
    try:
        for name in sio.rooms(sid):
            if name == f"room:{room_id}" or name.startswith(("game:", f"member:{room_id}:")):
                await sio.leave_room(sid, name)
        await sio.disconnect(sid)
        logger.debug("Detached and disconnected sid={} from room:{}", sid, room_id)
    except Exception:
        logger.opt(exception=True).debug("Failed to detach sid={} from room:{}", sid, room_id)


@sio.event
async def connect(sid, environ, auth):  # noqa: ARG001
    """Authenticate user, join room, update heartbeat, and deduplicate connections.

    Without a ``room_id`` the connection is the player's personal channel only
    (``_connect_personal``): room invites and kicks reach it.

    The tab may close at any point of this handshake: python-socketio then runs
    ``disconnect`` at once, beside it. Closed during the token check, the disconnect found
    no session and nothing to mark: the handshake stops there, refused (it used to go on and
    fail on the session of a socket that was gone, a ``KeyError`` out of the handler).
    Closed later, the disconnect has the session and the seat and marks the player away,
    and the heartbeat below is not written (``_write_presence``).
    """
    if not auth or not auth.get("token"):
        raise ConnectionRefusedError("Missing auth token")

    token = auth["token"]
    raw_room_id = auth.get("room_id")
    if not raw_room_id:
        return await _connect_personal(sid, token)

    # The room id is client-supplied and is parsed as a UUID below, inside a block
    # that only catches token errors. A malformed value therefore escaped as an
    # unhandled ValueError: python-socketio only special-cases
    # ConnectionRefusedError, so anything else propagates to the engine.io layer
    # as a server error instead of a clean refusal.
    try:
        room_uuid = UUID(str(raw_room_id))
    except (ValueError, AttributeError, TypeError) as e:
        raise ConnectionRefusedError("Invalid room_id") from e
    # Canonical, like every broadcast's `room:{room_id}` and every `_user_sids` key.
    room_id = str(room_uuid)

    caller = await _authenticate_member(sid, token, room_uuid)
    if not _is_live(sid):
        logger.debug("Socket.IO connect: sid={} closed during its handshake", sid)
        return False
    user_id = str(caller.user.id)
    _track_session(sid, caller.session_id)

    # From the check above to the old tab's disconnect below nothing awaits for real (the
    # session and the channels of a local socket are in this process), so this socket's
    # disconnect, whenever it comes, finds its session and its seat.
    #
    # Store session data (user_id bound for correlation logging). `lang` is the
    # language the client plays in; join_game resolves the game state's hints and
    # meanings in it (optional — older clients send none and get English).
    await sio.save_session(sid, {"user_id": user_id, "room_id": room_id, "lang": normalize_lang(auth.get("lang"))})

    # Multi-tab deduplication: disconnect previous SID for this user in same room.
    # The new SID is recorded FIRST, so the old one's `disconnect` sees it has been
    # replaced and does not mark a player who is still here as away.
    user_room_key = f"{user_id}:{room_id}"
    old_sid = _user_sids.get(user_room_key)
    _user_sids[user_room_key] = sid

    # Join Socket.IO rooms: room-specific (chat, game_updated), this member's own
    # channel in the room (the room state, which carries the PIN: notify.member_channel),
    # and the personal user room for invites (`_welcome_to_room` relies on room:{room_id})
    await sio.enter_room(sid, f"room:{room_id}")
    await sio.enter_room(sid, member_channel(room_id, user_id))
    await sio.enter_room(sid, f"user:{user_id}")
    logger.debug("Socket.IO connect: sid={} user={} room={}", sid, user_id, room_id)

    if old_sid and old_sid != sid:
        try:
            await sio.disconnect(old_sid)
            logger.debug("Disconnected old SID {} for user {} (new SID {})", old_sid, user_id, sid)
        except Exception:
            pass  # Old SID may already be gone

    return await _welcome_to_room(sid, user_id, room_id)


async def _welcome_to_room(sid: str, user_id: str, room_id: str) -> bool:
    """What ends a room socket's handshake: its heartbeat, then the room state; False when the tab has closed.

    The heartbeat marks the player connected with a fresh last_seen_at, unless the tab has
    closed meanwhile (its disconnect marked the player away: that stands, and the handshake
    is refused). A failed heartbeat is logged and the state still sent.
    """
    heartbeat_result = None
    try:
        heartbeat_result = await _write_presence(sid, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat on connect for sid={}", sid)
    else:
        if heartbeat_result is None:
            logger.debug("Socket.IO connect: sid={} closed before its heartbeat", sid)
            return False

    # The player came back: everyone else still shows them away (BDP-04). The
    # broadcast reaches this socket too — it has entered room:{room_id} above.
    if heartbeat_result is HeartbeatResult.RESTORED:
        fire_notify_room_changed(room_id)
        return True

    # Send initial room state to this client only
    try:
        state = await fetch_room_state(room_id)
        await sio.emit("room_state", state, to=sid)
    except Exception:
        logger.opt(exception=True).warning("Failed to send initial room_state to sid={}", sid)
    return True


@sio.event
async def join_game(sid, data):
    """Join a game room to receive per-user game state broadcasts.

    ``data``: ``{"game_id": str, "lang"?: "en" | "ar" | "fr"}``. The initial
    ``game_state`` this sends is resolved in ``lang`` (else the handshake's
    ``auth.lang``, else English), like ``GET .../state?lang=``.

    A socket whose seat is gone (a kick or a leave served by another worker) is
    refused AND cut: it has no business in the room's channels any more.
    """
    if not data or not data.get("game_id"):
        return

    game_id = data["game_id"]
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id")
    room_id = session_data.get("room_id")
    lang = normalize_lang(data.get("lang") or session_data.get("lang"))

    # a personal connection (no room) has no game to join
    if not user_id or not room_id:
        return

    # Validate: user must be in the room and game must belong to that room
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            # Check user is in the room
            link = (
                await session.exec(
                    select(RoomUserLink)
                    .where(RoomUserLink.room_id == UUID(room_id))
                    .where(RoomUserLink.user_id == UUID(user_id))
                )
            ).first()
            if not link:
                logger.warning("join_game rejected: user {} not in room {}", user_id, room_id)
                await _forget_and_detach(user_id, room_id, sid)
                return

            # Check game belongs to this room
            game = (await session.exec(select(Game).where(Game.id == UUID(game_id)))).first()
            if not game or str(game.room_id) != room_id:
                logger.warning("join_game rejected: game {} not in room {}", game_id, room_id)
                return
    except Exception:
        logger.opt(exception=True).warning("join_game validation failed for sid={}", sid)
        return

    # Store game_id (and the language the state is read in) in session and join game room
    session_data["game_id"] = game_id
    session_data["lang"] = lang
    if not await _save_session_of_live_socket(sid, session_data):
        logger.debug("join_game: sid={} went away before it could join game {}", sid, game_id)
        return
    await sio.enter_room(sid, f"game:{game_id}")
    logger.debug("Socket.IO join_game: sid={} user={} game={}", sid, user_id, game_id)
    await _welcome_to_game(sid, user_id, room_id, game_id, lang)


async def _welcome_to_game(sid: str, user_id: str, room_id: str, game_id: str, lang: str) -> None:
    """What follows a socket's entry into a game room: its heartbeat, then its own state.

    The heartbeat, so a player using only Socket.IO is not flagged as disconnected (a
    return is announced to the room); then the initial game state, to this client only.
    Each step logs its own failure and the other still runs. A socket that closed before
    its heartbeat gets neither (``_write_presence``).
    """
    try:
        presence = await _write_presence(sid, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat on join_game for sid={}", sid)
    else:
        if presence is None:
            logger.debug("join_game: sid={} closed before its heartbeat", sid)
            return
        if presence is HeartbeatResult.RESTORED:
            fire_notify_room_changed(room_id)

    try:
        state = await fetch_game_state(game_id, user_id, lang=lang)
        if state:
            await sio.emit("game_state", state, to=sid)
    except Exception:
        logger.opt(exception=True).warning("Failed to send initial game_state to sid={}", sid)


async def _save_session_of_live_socket(sid: str, session_data: dict) -> bool:
    """Save a socket's session; False when the socket is already gone.

    python-engineio answers ``KeyError('Session not found')`` for a sid that has
    disconnected — a page navigating away while a handler was reading the database.
    It used to escape ``join_game`` as "Task exception was never retrieved", an ERROR
    in the log (and a tracked issue in production) for an ordinary race.
    """
    try:
        await sio.save_session(sid, session_data)
    except KeyError:
        return False
    return True


async def auto_join_game_room(game_id: str, room_id: str) -> int:
    """Auto-join this worker's room members into the game's Socket.IO room.

    Called from game start routes so players are already in the game room when the
    first ``game_updated`` event is emitted, instead of racing their own
    ``join_game``.

    **This is an optimisation, not a guarantee.** `_user_sids` is per-process, so
    with 4 uvicorn workers it reaches roughly a quarter of the table. Correctness
    comes from ``notify_game_changed`` addressing ``room:{room_id}`` as well as
    ``game:{game_id}`` — room membership is established at connect on whichever
    worker holds the socket. Do not reintroduce a dependency on this function
    having reached everyone.

    Returns the number of SIDs joined.
    """
    joined = 0
    suffix = f":{room_id}"
    for key, sid in list(_user_sids.items()):
        if key.endswith(suffix):
            await sio.enter_room(sid, f"game:{game_id}")
            joined += 1
    if joined:
        logger.debug("Auto-joined {} SIDs into game:{} from room:{}", joined, game_id, room_id)
    return joined


async def _forget_and_detach(user_id: str, room_id: str, sid: str) -> None:
    """Drop ``sid`` from ``_user_sids`` (only if it is still the tracked one) and cut it off the room."""
    key = f"{user_id}:{room_id}"
    if _user_sids.get(key) == sid:
        _user_sids.pop(key, None)
    await _detach_socket(sid, room_id)


async def remove_user_from_room_socket(user_id: str, room_id: str) -> None:
    """Cut a removed member's socket off the room, on THIS worker (kick, leave, account deletion).

    Leaves ``room:{id}`` (whose broadcasts carry the PIN) and the ``game:{id}``
    channel, then disconnects the socket, so the client stops hearing the room at
    once. ``_user_sids`` is per process: a socket held by another worker is cut by
    that worker's next ``audit_local_socket_memberships`` tick (within
    ``DISCONNECT_CHECK_INTERVAL_SECONDS``), and refused by its own ``heartbeat`` or
    ``join_game`` before that. Kicked users are also told via ``you_were_kicked``
    (emitted first by the route: the local emit is queued before the disconnect).
    """
    sid = _user_sids.pop(f"{user_id}:{room_id}", None)
    if not sid:
        return
    await _detach_socket(sid, room_id)


async def audit_local_socket_memberships(session: AsyncSession) -> int:
    """Cut every socket of THIS worker whose session has ended, or whose seat is gone or banned.

    Returns how many were cut. Runs in every worker on every tick of the checker loop
    (``on_worker_tick``), outside the single-sweeper election: a kick served by another
    worker removes the seat and bans the player, and a logout or a reset revokes the
    session, but only the worker holding the socket can cut it, and the client cannot be
    trusted to leave on ``you_were_kicked``. ONE query for the sessions of all of this
    worker's sockets and ONE for all its (user, room) pairs; none when it holds no socket.
    """
    cut = await _cut_sockets_of_ended_sessions(session)
    return cut + await _cut_sockets_without_a_seat(session)


async def _cut_sockets_of_ended_sessions(session: AsyncSession) -> int:
    """Cut every local socket whose AuthSession is revoked, past ``expires_at`` or gone (review R5)."""
    snapshot = dict(_socket_sessions)
    if not snapshot:
        return 0
    live = set(
        (
            await session.exec(
                select(AuthSession.id)
                .where(col(AuthSession.id).in_(set(snapshot.values())))
                .where(col(AuthSession.revoked_at).is_(None))
                .where(col(AuthSession.expires_at) > datetime.now(UTC))
            )
        ).all()
    )
    ended = [sid for sid, session_id in snapshot.items() if session_id not in live]
    for sid in ended:
        _socket_sessions.pop(sid, None)
        for key in [key for key, tracked in _user_sids.items() if tracked == sid]:
            _user_sids.pop(key, None)
        await _cut_socket(sid)
    if ended:
        logger.info("Socket audit: cut {} socket(s) whose session has ended", len(ended))
    return len(ended)


async def _cut_socket(sid: str) -> None:
    """Take a LOCAL socket off every channel it is in (personal, room, game), then disconnect it."""
    try:
        for name in sio.rooms(sid):
            if name != sid:
                await sio.leave_room(sid, name)
        await sio.disconnect(sid)
    except Exception:
        logger.opt(exception=True).debug("Failed to cut sid={}", sid)


async def _cut_sockets_without_a_seat(session: AsyncSession) -> int:
    """Cut every local room socket whose seat is gone or banned."""
    snapshot = list(_user_sids.items())
    pairs: dict[tuple[UUID, UUID], tuple[str, str]] = {}
    for key, sid in snapshot:
        user_part, _, room_part = key.partition(":")
        try:
            pairs[(UUID(user_part), UUID(room_part))] = (key, sid)
        except ValueError:
            continue
    if not pairs:
        return 0

    seated = await _seated_members(session, pairs.keys())
    cut = 0
    for pair, (key, sid) in pairs.items():
        if pair in seated or _user_sids.get(key) != sid:
            continue
        _user_sids.pop(key, None)
        await _detach_socket(sid, str(pair[1]))
        cut += 1
    if cut:
        logger.info("Socket audit: cut {} socket(s) whose seat is gone", cut)
    return cut


@sio.event
async def heartbeat(sid):
    """Update heartbeat timestamp to prevent stale-user detection.

    Also the cheapest re-check of the seat: no seat any more (a kick served by another
    worker) cuts the socket; a player the sweep had marked away is announced back. A
    heartbeat of a socket that closed before it was written writes nothing
    (``_write_presence``): the close's away mark stands.
    """
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id")
    room_id = session_data.get("room_id")
    if not user_id or not room_id:
        return
    try:
        result = await _write_presence(sid, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat for sid={}", sid)
        return

    if result is None:
        return
    if result is HeartbeatResult.NOT_A_MEMBER:
        logger.info("heartbeat refused: user {} has no seat in room {}", user_id, room_id)
        await _forget_and_detach(user_id, room_id, sid)
    elif result is HeartbeatResult.RESTORED:
        fire_notify_room_changed(room_id)


@sio.event
async def disconnect(sid):
    """Mark user as disconnected in DB and clean up SID tracking.

    python-socketio no longer counts the socket as connected when this runs, so no
    presence write of this socket starts after it; one in flight finishes first, under the
    member's presence lock (``_write_presence``, ``_write_absence``).
    """
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id", "unknown")
    room_id = session_data.get("room_id")
    logger.debug("Socket.IO disconnect: sid={} user={} room={}", sid, user_id, room_id)

    # Clean up SID tracking (at once: a socket that replaces this one must find it gone)
    _socket_sessions.pop(sid, None)
    if room_id:
        user_room_key = f"{user_id}:{room_id}"
        if _user_sids.get(user_room_key) == sid:
            _user_sids.pop(user_room_key, None)

    # Mark user as disconnected in DB (starts grace period), unless a newer socket of the
    # same player took this one's place
    if room_id and user_id != "unknown":
        try:
            flipped = await _write_absence(sid, user_id, room_id)
            # Notify room so other players see the disconnection — only if this flipped
            # the seat: an already-away or removed seat (a kick) is no news.
            if flipped:
                fire_notify_room_changed(room_id)
        except Exception:
            logger.opt(exception=True).warning("Failed to mark user {} as disconnected", user_id)
