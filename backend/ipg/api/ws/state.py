from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.controllers.room import RoomController
from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.models.table import Game
from ipg.database import get_engine


async def fetch_room_state(room_id: str, user_id: str | None = None) -> dict:
    """Fetch room state using existing RoomController. No heartbeat update."""
    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        controller = RoomController(session)
        # Pass a dummy user_id if none provided — get_room_state only uses it for heartbeat
        uid = UUID(user_id) if user_id else UUID("00000000-0000-0000-0000-000000000000")
        return await controller.get_room_state(room_id=UUID(room_id), user_id=uid, update_heartbeat=False)


async def fetch_game_state(game_id: str, user_id: str) -> dict:
    """Fetch per-user game state using existing controllers. No heartbeat update."""
    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        game = (await session.exec(select(Game).where(Game.id == UUID(game_id)))).first()
        if not game:
            return {}
        if game.type.value == "undercover":
            controller = UndercoverGameController(session)
            return await controller.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
        else:
            controller = CodenamesGameController(session)
            return await controller.get_board(UUID(game_id), UUID(user_id), update_heartbeat=False)
