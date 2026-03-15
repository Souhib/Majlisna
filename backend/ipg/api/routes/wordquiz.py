from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED

from ipg.api.controllers.wordquiz_game import WordQuizGameController
from ipg.api.models.table import User
from ipg.api.schemas.common import GameStartResponse, HintRecordResponse, TimerExpiredResponse
from ipg.api.schemas.wordquiz import SubmitAnswerRequest, SubmitAnswerResponse, WordQuizGameState
from ipg.api.ws.handlers import auto_join_game_room
from ipg.api.ws.notify import notify_game_changed, notify_room_changed
from ipg.dependencies import get_current_user, get_wordquiz_game_controller

router = APIRouter(
    prefix="/wordquiz",
    tags=["Word Quiz"],
    responses={404: {"description": "Not found"}},
)


@router.post("/games/{room_id}/start", status_code=HTTP_201_CREATED)
async def start_wordquiz_game(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[WordQuizGameController, Depends(get_wordquiz_game_controller)],
) -> GameStartResponse:
    result = await controller.create_and_start(room_id, current_user.id)
    auto_join_game_room(result.game_id, str(room_id))
    await notify_room_changed(str(room_id))
    await notify_game_changed(result.game_id, str(room_id))
    return result


@router.get("/games/{game_id}/state")
async def get_wordquiz_state(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[WordQuizGameController, Depends(get_wordquiz_game_controller)],
    lang: str = "en",
) -> WordQuizGameState:
    return await controller.get_state(game_id, current_user.id, lang=lang)


@router.post("/games/{game_id}/answer")
async def submit_answer(
    game_id: UUID,
    body: SubmitAnswerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[WordQuizGameController, Depends(get_wordquiz_game_controller)],
) -> SubmitAnswerResponse:
    result = await controller.submit_answer(game_id, current_user.id, body.answer)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/timer-expired")
async def timer_expired(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[WordQuizGameController, Depends(get_wordquiz_game_controller)],
) -> TimerExpiredResponse:
    result = await controller.handle_timer_expired(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/next-round")
async def next_round(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[WordQuizGameController, Depends(get_wordquiz_game_controller)],
) -> GameStartResponse:
    result = await controller.advance_to_next_round(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/hint-viewed")
async def record_hint_viewed(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[WordQuizGameController, Depends(get_wordquiz_game_controller)],
) -> HintRecordResponse:
    return await controller.record_hint_view(game_id, current_user.id)
