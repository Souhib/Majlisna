from collections.abc import Collection
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy import and_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.disconnect import HeartbeatResult, mark_user_disconnected, update_heartbeat
from majlisna.api.controllers.token_auth import authenticate_caller
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


async def _connect_personal(sid: str, token: str) -> None:
    """A connection with no room: the signed-in player's own channel (``user:{id}``).

    The app shell keeps one open on every signed-in page so a friend's room invite
    reaches the player wherever they are. It joins nothing else, sends no room
    state and records no heartbeat: there is no room to be present in.

    It used to be refused ("Missing auth token or room_id"), and socket.io-client
    does not retry a connection the server refuses, so every invite was answered
    "Invite sent" and never arrived.
    """
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            # Type and BOTH claims, like every HTTP request (controllers/token_auth.py).
            caller = await authenticate_caller(session, Settings(), token)
    except _TOKEN_ERRORS as e:
        logger.debug("Socket.IO personal auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e

    user_id = str(caller.user.id)
    _track_session(sid, caller.session_id)
    await sio.save_session(sid, {"user_id": user_id, "room_id": None, "lang": None})
    await sio.enter_room(sid, f"user:{user_id}")
    logger.debug("Socket.IO personal connect: sid={} user={}", sid, user_id)


async def _seated_members(session: AsyncSession, pairs: Collection[tuple[UUID, UUID]]) -> set[tuple[UUID, UUID]]:
    """Which of these (user, room) pairs hold a seat and no ban — ONE statement for all of them.

    A seat is a ``RoomUserLink``; a ``RoomBan`` (owner rule (c): a kick bans for the
    room's lifetime) voids it. The query reads the cross product of the users and rooms
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


async def _authenticate_member(sid: str, token: str, room_uuid: UUID) -> str:
    """The user id behind ``token``, who must hold a seat in the room and no ban; refuse otherwise."""
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
            _track_session(sid, caller.session_id)
            return str(caller.user.id)
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
    """
    if not auth or not auth.get("token"):
        raise ConnectionRefusedError("Missing auth token")

    token = auth["token"]
    raw_room_id = auth.get("room_id")
    if not raw_room_id:
        await _connect_personal(sid, token)
        return

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

    user_id = await _authenticate_member(sid, token, room_uuid)

    # Multi-tab deduplication: disconnect previous SID for this user in same room.
    # The new SID is recorded FIRST, so the old one's `disconnect` sees it has been
    # replaced and does not mark a player who is still here as away.
    user_room_key = f"{user_id}:{room_id}"
    old_sid = _user_sids.get(user_room_key)
    _user_sids[user_room_key] = sid
    if old_sid and old_sid != sid:
        try:
            await sio.disconnect(old_sid)
            logger.debug("Disconnected old SID {} for user {} (new SID {})", old_sid, user_id, sid)
        except Exception:
            pass  # Old SID may already be gone

    # Store session data (user_id bound for correlation logging). `lang` is the
    # language the client plays in; join_game resolves the game state's hints and
    # meanings in it (optional — older clients send none and get English).
    await sio.save_session(sid, {"user_id": user_id, "room_id": room_id, "lang": normalize_lang(auth.get("lang"))})

    # Join Socket.IO rooms: room-specific (chat, game_updated), this member's own
    # channel in the room (the room state, which carries the PIN: notify.member_channel),
    # and the personal user room for invites
    await sio.enter_room(sid, f"room:{room_id}")
    await sio.enter_room(sid, member_channel(room_id, user_id))
    await sio.enter_room(sid, f"user:{user_id}")
    logger.debug("Socket.IO connect: sid={} user={} room={}", sid, user_id, room_id)

    # Update heartbeat in DB — mark user as connected with fresh last_seen_at
    heartbeat_result = None
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            heartbeat_result = await update_heartbeat(session, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat on connect for sid={}", sid)

    # The player came back: everyone else still shows them away (BDP-04). The
    # broadcast reaches this socket too — it has entered room:{room_id} above.
    if heartbeat_result is HeartbeatResult.RESTORED:
        fire_notify_room_changed(room_id)
        return

    # Send initial room state to this client only
    try:
        state = await fetch_room_state(room_id)
        await sio.emit("room_state", state, to=sid)
    except Exception:
        logger.opt(exception=True).warning("Failed to send initial room_state to sid={}", sid)


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
    Each step logs its own failure and the other still runs.
    """
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            if await update_heartbeat(session, user_id, room_id) is HeartbeatResult.RESTORED:
                fire_notify_room_changed(room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat on join_game for sid={}", sid)

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
    worker) cuts the socket; a player the sweep had marked away is announced back.
    """
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id")
    room_id = session_data.get("room_id")
    if not user_id or not room_id:
        return
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            result = await update_heartbeat(session, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat for sid={}", sid)
        return

    if result is HeartbeatResult.NOT_A_MEMBER:
        logger.info("heartbeat refused: user {} has no seat in room {}", user_id, room_id)
        await _forget_and_detach(user_id, room_id, sid)
    elif result is HeartbeatResult.RESTORED:
        fire_notify_room_changed(room_id)


@sio.event
async def disconnect(sid):
    """Mark user as disconnected in DB and clean up SID tracking."""
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id", "unknown")
    room_id = session_data.get("room_id")
    logger.debug("Socket.IO disconnect: sid={} user={} room={}", sid, user_id, room_id)

    # Clean up SID tracking
    _socket_sessions.pop(sid, None)
    replaced = False
    if room_id:
        user_room_key = f"{user_id}:{room_id}"
        tracked_sid = _user_sids.get(user_room_key)
        if tracked_sid == sid:
            _user_sids.pop(user_room_key, None)
        # A newer socket of the same player in the same room (a reload, a second tab)
        # took this one's place: the player is still here. On another worker the
        # newer socket's heartbeat restores `connected` within one interval instead.
        replaced = tracked_sid is not None and tracked_sid != sid

    # Mark user as disconnected in DB (starts grace period)
    if room_id and user_id != "unknown" and not replaced:
        try:
            engine = await get_engine()
            async with AsyncSession(engine) as session:
                flipped = await mark_user_disconnected(session, user_id, room_id)
            # Notify room so other players see the disconnection — only if this flipped
            # the seat: an already-away or removed seat (a kick) is no news.
            if flipped:
                fire_notify_room_changed(room_id)
        except Exception:
            logger.opt(exception=True).warning("Failed to mark user {} as disconnected", user_id)
