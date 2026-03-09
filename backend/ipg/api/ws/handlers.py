from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.auth import AuthController
from ipg.api.schemas.error import InvalidTokenError, TokenExpiredError
from ipg.api.ws.server import sio
from ipg.api.ws.state import fetch_game_state, fetch_room_state
from ipg.database import get_engine
from ipg.settings import Settings

_settings = Settings()  # type: ignore


@sio.event
async def connect(sid, environ, auth):  # noqa: ARG001
    """Authenticate user and join room on connection."""
    if not auth or not auth.get("token") or not auth.get("room_id"):
        raise ConnectionRefusedError("Missing auth token or room_id")

    token = auth["token"]
    room_id = auth["room_id"]

    try:
        engine = await get_engine()
        async with AsyncSession(engine) as session:
            auth_controller = AuthController(session, _settings)
            payload = auth_controller.decode_token(token)
            user = await auth_controller.get_user_by_email(payload.email)
            if user is None:
                raise ConnectionRefusedError("User not found")
            user_id = str(user.id)
    except (InvalidTokenError, TokenExpiredError) as e:
        logger.debug("Socket.IO auth failed for sid={}: {}", sid, e)
        raise ConnectionRefusedError("Invalid or expired token") from e

    # Store session data
    await sio.save_session(sid, {"user_id": user_id, "room_id": room_id})

    # Join Socket.IO room
    sio.enter_room(sid, f"room:{room_id}")
    logger.debug("Socket.IO connect: sid={} user={} room={}", sid, user_id, room_id)

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

    if not user_id:
        return

    # Store game_id in session and join game room
    session_data["game_id"] = game_id
    await sio.save_session(sid, session_data)
    sio.enter_room(sid, f"game:{game_id}")
    logger.debug("Socket.IO join_game: sid={} user={} game={}", sid, user_id, game_id)

    # Send initial game state to this client only
    try:
        state = await fetch_game_state(game_id, user_id)
        if state:
            await sio.emit("game_state", state, to=sid)
    except Exception:
        logger.opt(exception=True).warning("Failed to send initial game_state to sid={}", sid)


@sio.event
async def disconnect(sid):
    """Log disconnect. No game/room cleanup — last_seen_at staleness handles it."""
    session_data = await sio.get_session(sid)
    user_id = session_data.get("user_id", "unknown")
    logger.debug("Socket.IO disconnect: sid={} user={}", sid, user_id)
