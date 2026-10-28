from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import TOKEN_TYPE_ACCESS, AuthController
from majlisna.api.controllers.disconnect import mark_user_disconnected, update_heartbeat
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game
from majlisna.api.schemas.error import InvalidTokenError, TokenExpiredError
from majlisna.api.utils.multilingual import normalize_lang
from majlisna.api.ws.notify import fire_notify_room_changed
from majlisna.api.ws.server import sio
from majlisna.api.ws.state import fetch_game_state, fetch_room_state
from majlisna.database import get_engine
from majlisna.settings import Settings

# Track user→sid mapping for multi-tab deduplication
_user_sids: dict[str, str] = {}


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
            auth_controller = AuthController(session, Settings())
            payload = auth_controller.decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
            user = await auth_controller.get_user_by_email(payload.email)
    except (InvalidTokenError, TokenExpiredError) as e:
        logger.debug("Socket.IO personal auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e
    if user is None:
        raise ConnectionRefusedError("User not found")

    user_id = str(user.id)
    await sio.save_session(sid, {"user_id": user_id, "room_id": None, "lang": None})
    await sio.enter_room(sid, f"user:{user_id}")
    logger.debug("Socket.IO personal connect: sid={} user={}", sid, user_id)


async def _authenticate_member(sid: str, token: str, room_uuid: UUID) -> str:
    """The user id behind ``token``, who must be a member of the room; refuse otherwise."""
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            auth_controller = AuthController(session, Settings())
            payload = auth_controller.decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
            user = await auth_controller.get_user_by_email(payload.email)
            if user is None:
                raise ConnectionRefusedError("User not found")

            # Authorization: the user must actually be a member of this room —
            # otherwise any authenticated user could listen to any room's state
            # (which carries the room PIN) and chat.
            link = (
                await session.exec(
                    select(RoomUserLink).where(RoomUserLink.room_id == room_uuid).where(RoomUserLink.user_id == user.id)
                )
            ).first()
            if not link:
                raise ConnectionRefusedError("Not a member of this room")
            return str(user.id)
    except (InvalidTokenError, TokenExpiredError) as e:
        logger.debug("Socket.IO auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e


@sio.event
async def connect(sid, environ, auth):  # noqa: ARG001
    """Authenticate user, join room, update heartbeat, and deduplicate connections.

    Without a ``room_id`` the connection is the player's personal channel only
    (``_connect_personal``): room invites and kicks reach it.
    """
    if not auth or not auth.get("token"):
        raise ConnectionRefusedError("Missing auth token")

    token = auth["token"]
    room_id = auth.get("room_id")
    if not room_id:
        await _connect_personal(sid, token)
        return

    # The room id is client-supplied and is parsed as a UUID below, inside a block
    # that only catches token errors. A malformed value therefore escaped as an
    # unhandled ValueError: python-socketio only special-cases
    # ConnectionRefusedError, so anything else propagates to the engine.io layer
    # as a server error instead of a clean refusal.
    try:
        room_uuid = UUID(str(room_id))
    except (ValueError, AttributeError, TypeError) as e:
        raise ConnectionRefusedError("Invalid room_id") from e

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

    # Join Socket.IO rooms: room-specific + personal user room for invites
    await sio.enter_room(sid, f"room:{room_id}")
    await sio.enter_room(sid, f"user:{user_id}")
    logger.debug("Socket.IO connect: sid={} user={} room={}", sid, user_id, room_id)

    # Update heartbeat in DB — mark user as connected with fresh last_seen_at
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            await update_heartbeat(session, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat on connect for sid={}", sid)

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
    await sio.save_session(sid, session_data)
    await sio.enter_room(sid, f"game:{game_id}")
    logger.debug("Socket.IO join_game: sid={} user={} game={}", sid, user_id, game_id)

    # Update heartbeat so players using only Socket.IO don't get flagged as disconnected
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            await update_heartbeat(session, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat on join_game for sid={}", sid)

    # Send initial game state to this client only
    try:
        state = await fetch_game_state(game_id, user_id, lang=lang)
        if state:
            await sio.emit("game_state", state, to=sid)
    except Exception:
        logger.opt(exception=True).warning("Failed to send initial game_state to sid={}", sid)


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


async def remove_user_from_room_socket(user_id: str, room_id: str) -> None:
    """Detach a user's SID from a room's Socket.IO room (kick/leave).

    Stops the client from receiving further room broadcasts (which carry the
    room PIN) after they are no longer a member. Best-effort: the `_user_sids`
    map is per-process, so with multiple workers only SIDs on this worker are
    detached — kicked users are also disconnected client-side via
    ``you_were_kicked``.
    """
    sid = _user_sids.pop(f"{user_id}:{room_id}", None)
    if not sid:
        return
    try:
        await sio.leave_room(sid, f"room:{room_id}")
        logger.debug("Detached sid={} from room:{} (user={})", sid, room_id, user_id)
    except Exception:
        logger.opt(exception=True).debug("Failed to detach sid={} from room:{}", sid, room_id)


@sio.event
async def heartbeat(sid):
    """Update heartbeat timestamp to prevent stale-user detection."""
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id")
    room_id = session_data.get("room_id")
    if not user_id or not room_id:
        return
    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            await update_heartbeat(session, user_id, room_id)
    except Exception:
        logger.opt(exception=True).warning("Failed to update heartbeat for sid={}", sid)


@sio.event
async def disconnect(sid):
    """Mark user as disconnected in DB and clean up SID tracking."""
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id", "unknown")
    room_id = session_data.get("room_id")
    logger.debug("Socket.IO disconnect: sid={} user={} room={}", sid, user_id, room_id)

    # Clean up SID tracking
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
                await mark_user_disconnected(session, user_id, room_id)
            # Notify room so other players see the disconnection
            fire_notify_room_changed(room_id)
        except Exception:
            logger.opt(exception=True).warning("Failed to mark user {} as disconnected", user_id)
