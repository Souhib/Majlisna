import asyncio
from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.table import Game, Room
from majlisna.api.ws.server import sio
from majlisna.api.ws.state import fetch_room_state
from majlisna.database import get_engine

# Strong references to prevent garbage collection of fire-and-forget tasks
_pending_tasks: set[asyncio.Task] = set()


def fire_notify_room_changed(room_id: str) -> None:
    """Schedule room notification (fire-and-forget). Use only from background tasks/event handlers.

    Route handlers should ``await notify_room_changed()`` directly so the
    Socket.IO event is guaranteed to be emitted before the HTTP response.
    """
    task = asyncio.create_task(notify_room_changed(room_id))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


def fire_notify_game_changed(game_id: str, room_id: str | None = None) -> None:
    """Schedule game notification (fire-and-forget). Use only from background tasks/event handlers.

    Route handlers should ``await notify_game_changed()`` directly so the
    Socket.IO event is guaranteed to be emitted before the HTTP response.
    """
    task = asyncio.create_task(notify_game_changed(game_id, room_id))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


async def _get_room_id_for_game(game_id: str) -> str | None:
    """Look up room_id from the Game table."""
    try:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            game = (await session.exec(select(Game).where(Game.id == UUID(game_id)))).first()
            return str(game.room_id) if game and game.room_id else None
    except Exception:
        logger.opt(exception=True).debug("Failed to look up room_id for game={}", game_id)
        return None


async def notify_user_kicked(user_id: str, room_id: str) -> None:
    """Send 'you_were_kicked' event to the user's personal Socket.IO room."""
    try:
        await sio.emit("you_were_kicked", {"room_id": room_id}, to=f"user:{user_id}")
    except Exception:
        logger.opt(exception=True).error("Failed to notify kicked user={} room={}", user_id, room_id)


async def notify_room_invite(friend_user_id: str, room_id: str, invited_by: str) -> None:
    """Send a 'room_invite' event to the invited friend's personal Socket.IO room.

    Looks up the room's public_id/password in a fresh session so the invite carries
    everything the client needs to join. Awaited in the route handler after the
    invite has been validated by the controller. Best-effort: logs on failure.
    """
    try:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            room = (await session.exec(select(Room).where(Room.id == UUID(room_id)))).first()
            if not room:
                return
            await sio.emit(
                "room_invite",
                {
                    "room_id": str(room.id),
                    "public_id": room.public_id,
                    "password": room.password,
                    "invited_by": invited_by,
                },
                to=f"user:{friend_user_id}",
            )
    except Exception:
        logger.opt(exception=True).error("notify_room_invite FAILED for user={} room={}", friend_user_id, room_id)


async def notify_room_changed(room_id: str) -> None:
    """Broadcast fresh room state to all clients in the room.

    Awaited in route handlers to guarantee delivery before the HTTP response.
    """
    try:
        state = await fetch_room_state(room_id)
        await sio.emit("room_state", state, to=f"room:{room_id}")
    except Exception:
        logger.opt(exception=True).error("notify_room_changed FAILED for room={}", room_id)


async def notify_chat_message(room_id: str, message_data: dict) -> None:
    """Broadcast a new chat message to all clients in the room.

    Awaited in route handlers to guarantee delivery before the HTTP response.
    """
    try:
        await sio.emit("chat_message", message_data, to=f"room:{room_id}")
    except Exception:
        logger.opt(exception=True).error("notify_chat_message FAILED for room={}", room_id)


async def notify_game_changed(game_id: str, room_id: str | None = None) -> None:
    """Broadcast game_updated signal to all clients in the game room.

    Awaited in route handlers to guarantee delivery before the HTTP response.

    Instead of sending per-user state from the server (which doesn't work across
    multiple workers since get_participants is per-process), we emit a lightweight
    signal. Each client receives it and invalidates its TanStack Query cache,
    triggering a REST re-fetch of its own role-aware state.

    Always also notifies the room (looks up room_id if not provided).
    """
    try:
        await sio.emit("game_updated", {"game_id": game_id}, to=f"game:{game_id}")
    except Exception:
        logger.opt(exception=True).error("notify_game_changed FAILED for game={}", game_id)

    # Always notify room — look up room_id if not provided
    if not room_id:
        room_id = await _get_room_id_for_game(game_id)
    if room_id:
        await notify_room_changed(room_id)
