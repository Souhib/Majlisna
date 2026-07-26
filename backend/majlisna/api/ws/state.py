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
            # A local per branch, not one name rebound to four unrelated controller
            # types: they share no base method (three expose get_state, codenames
            # exposes get_board), so a single variable only hid that from the reader.
            if game.type == GameType.UNDERCOVER:
                undercover = UndercoverGameController(session)
                state = await undercover.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return state.model_dump(mode="json")
            if game.type == GameType.WORD_QUIZ:
                wordquiz = WordQuizGameController(session)
                wordquiz_state = await wordquiz.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return wordquiz_state.model_dump(mode="json")
            if game.type == GameType.MCQ_QUIZ:
                mcqquiz = McqQuizGameController(session)
                mcqquiz_state = await mcqquiz.get_state(UUID(game_id), UUID(user_id), update_heartbeat=False)
                return mcqquiz_state.model_dump(mode="json")
            codenames = CodenamesGameController(session)
            board = await codenames.get_board(UUID(game_id), UUID(user_id), update_heartbeat=False)
            return board.model_dump(mode="json")
        except Exception:
            logger.exception("Failed to fetch game state for game={}", game_id)
            return {}
