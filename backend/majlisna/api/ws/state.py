from uuid import UUID

from fastapi import status
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import DEFAULT_LANGUAGE
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.game import GameType
from majlisna.api.models.table import Game
from majlisna.api.schemas.error import BaseError
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


async def fetch_game_state(game_id: str, user_id: str, lang: str = DEFAULT_LANGUAGE) -> dict:
    """Fetch per-user game state using existing controllers. No heartbeat update.

    Handles both players and spectators — the controllers now support spectator SIDs.

    ``lang`` resolves the hints and meanings exactly as ``GET .../state?lang=`` does.
    It used to be left at the controllers' English default, and the client writes this
    push straight into its query cache for Undercover and Codenames — so an Arabic
    player's game-over meanings were replaced by English ones a moment after the REST
    response had them right.
    """
    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        game = (await session.exec(select(Game).where(Game.id == UUID(game_id)))).first()
        if not game:
            return {}
        try:
            return await _read_game_state(session, game.type, UUID(game_id), UUID(user_id), lang)
        except BaseError as error:
            if error.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                logger.exception("Failed to fetch game state for game={}", game_id)
            # else: a refusal for this caller (a player who left or was removed between
            # join_game's seat check and this read), already logged at INFO by BaseError.
            # Either way there is no state to send.
            return {}
        except Exception:
            logger.exception("Failed to fetch game state for game={}", game_id)
            return {}


async def _read_game_state(session: AsyncSession, game_type: GameType, game_id: UUID, user_id: UUID, lang: str) -> dict:
    """The caller's state of the game, through the controller of its type, as JSON."""
    # A local per branch, not one name rebound to four unrelated controller types: they
    # share no base method (three expose get_state, codenames exposes get_board), so a
    # single variable only hid that from the reader.
    if game_type == GameType.UNDERCOVER:
        undercover = UndercoverGameController(session)
        state = await undercover.get_state(game_id, user_id, lang=lang, update_heartbeat=False)
        return state.model_dump(mode="json")
    if game_type == GameType.WORD_QUIZ:
        wordquiz = WordQuizGameController(session)
        wordquiz_state = await wordquiz.get_state(game_id, user_id, lang=lang, update_heartbeat=False)
        return wordquiz_state.model_dump(mode="json")
    if game_type == GameType.MCQ_QUIZ:
        mcqquiz = McqQuizGameController(session)
        mcqquiz_state = await mcqquiz.get_state(game_id, user_id, lang=lang, update_heartbeat=False)
        return mcqquiz_state.model_dump(mode="json")
    codenames = CodenamesGameController(session)
    board = await codenames.get_board(game_id, user_id, lang=lang, update_heartbeat=False)
    return board.model_dump(mode="json")
