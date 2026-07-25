from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.game import GameType
from majlisna.api.models.table import Game
from majlisna.database import get_engine


async def fetch_room_state(room_id: str, user_id: str | None = None) -> dict:
    """Fetch room state using existing RoomController. No heartbeat update."""
    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        controller = RoomController(session)
        # Pass a dummy user_id if none provided — get_room_state only uses it for heartbeat
        uid = UUID(user_id) if user_id else UUID("00000000-0000-0000-0000-000000000000")
        result = await controller.get_room_state(room_id=UUID(room_id), user_id=uid, update_heartbeat=False)
        return result.model_dump(mode="json")


async def fetch_game_state(game_id: str, user_id: str) -> dict:
    """Fetch per-user game state using existing controllers. No heartbeat update.

    Handles both players and spectators — the controllers now support spectator SIDs.
    """
    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        game = (await session.exec(select(Game).where(Game.id == UUID(game_id)))).first()
        if not game:
            return {}
        try:
            if game.type == GameType.UNDERCOVER:
                controller = UndercoverGameController(session)
                result = await controller.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return result.model_dump(mode="json")
            elif game.type == GameType.WORD_QUIZ:
                controller = WordQuizGameController(session)
                result = await controller.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return result.model_dump(mode="json")
            elif game.type == GameType.MCQ_QUIZ:
                controller = McqQuizGameController(session)
                result = await controller.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return result.model_dump(mode="json")
            else:
                controller = CodenamesGameController(session)
                result = await controller.get_board(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return result.model_dump(mode="json")
        except Exception:
            logger.exception("Failed to fetch game state for game={}", game_id)
            return {}
