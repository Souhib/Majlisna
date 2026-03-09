from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.table import Game
from ipg.api.ws.server import sio
from ipg.api.ws.state import fetch_room_state
from ipg.database import get_engine


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


async def notify_room_changed(room_id: str) -> None:
    """Broadcast fresh room state to all clients in the room. Best-effort."""
    try:
        state = await fetch_room_state(room_id)
        await sio.emit("room_state", state, to=f"room:{room_id}")
    except Exception:
        logger.opt(exception=True).warning("notify_room_changed failed for room={}", room_id)


async def notify_game_changed(game_id: str, room_id: str | None = None) -> None:
    """Broadcast game_updated signal to all clients in the game room. Best-effort.

    Instead of sending per-user state from the server (which doesn't work across
    multiple workers since get_participants is per-process), we emit a lightweight
    signal. Each client receives it and invalidates its TanStack Query cache,
    triggering a REST re-fetch of its own role-aware state.

    Always also notifies the room (looks up room_id if not provided).
    """
    try:
        await sio.emit("game_updated", {"game_id": game_id}, to=f"game:{game_id}")
    except Exception:
        logger.opt(exception=True).warning("notify_game_changed failed for game={}", game_id)

    # Always notify room — look up room_id if not provided
    if not room_id:
        room_id = await _get_room_id_for_game(game_id)
    if room_id:
        await notify_room_changed(room_id)
