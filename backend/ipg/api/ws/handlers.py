from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.auth import AuthController
from ipg.api.controllers.disconnect import mark_user_disconnected, update_heartbeat
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game
from ipg.api.schemas.error import InvalidTokenError, TokenExpiredError
from ipg.api.ws.notify import fire_notify_room_changed
from ipg.api.ws.server import sio
from ipg.api.ws.state import fetch_game_state, fetch_room_state
from ipg.database import get_engine
from ipg.settings import Settings

# Track user→sid mapping for multi-tab deduplication
_user_sids: dict[str, str] = {}


@sio.event
async def connect(sid, environ, auth):  # noqa: ARG001
    """Authenticate user, join room, update heartbeat, and deduplicate connections."""
    if not auth or not auth.get("token") or not auth.get("room_id"):
        raise ConnectionRefusedError("Missing auth token or room_id")

    token = auth["token"]
    room_id = auth["room_id"]

    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            auth_controller = AuthController(session, Settings())  # type: ignore
            payload = auth_controller.decode_token(token)
            user = await auth_controller.get_user_by_email(payload.email)
            if user is None:
                raise ConnectionRefusedError("User not found")
            user_id = str(user.id)
    except (InvalidTokenError, TokenExpiredError) as e:
        logger.debug("Socket.IO auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e

    # Multi-tab deduplication: disconnect previous SID for this user in same room
    user_room_key = f"{user_id}:{room_id}"
    old_sid = _user_sids.get(user_room_key)
    if old_sid and old_sid != sid:
        try:
            await sio.disconnect(old_sid)
            logger.debug("Disconnected old SID {} for user {} (new SID {})", old_sid, user_id, sid)
        except Exception:
            pass  # Old SID may already be gone

    _user_sids[user_room_key] = sid

    # Store session data (user_id bound for correlation logging)
    await sio.save_session(sid, {"user_id": user_id, "room_id": room_id})

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
    """Join a game room to receive per-user game state broadcasts."""
    if not data or not data.get("game_id"):
        return

    game_id = data["game_id"]
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id")
    room_id = session_data.get("room_id")

    if not user_id:
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

    # Store game_id in session and join game room
    session_data["game_id"] = game_id
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
        state = await fetch_game_state(game_id, user_id)
        if state:
            await sio.emit("game_state", state, to=sid)
    except Exception:
        logger.opt(exception=True).warning("Failed to send initial game_state to sid={}", sid)


async def auto_join_game_room(game_id: str, room_id: str) -> int:
    """Auto-join all connected room members into the game's Socket.IO room.

    Called from game start routes so players are already in the game room
    when the first ``game_updated`` event is emitted — eliminates the race
    condition where the event fires before ``join_game`` from the client.

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
    if room_id:
        user_room_key = f"{user_id}:{room_id}"
        if _user_sids.get(user_room_key) == sid:
            _user_sids.pop(user_room_key, None)

    # Mark user as disconnected in DB (starts grace period)
    if room_id and user_id != "unknown":
        try:
            engine = await get_engine()
            async with AsyncSession(engine) as session:
                await mark_user_disconnected(session, user_id, room_id)
            # Notify room so other players see the disconnection
            fire_notify_room_changed(room_id)
        except Exception:
            logger.opt(exception=True).warning("Failed to mark user {} as disconnected", user_id)
