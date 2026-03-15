from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED

from ipg.api.controllers.mcqquiz_game import McqQuizGameController
from ipg.api.models.table import User
from ipg.api.schemas.common import GameStartResponse, TimerExpiredResponse
from ipg.api.schemas.mcqquiz import McqQuizGameState, McqSubmitAnswerRequest, McqSubmitAnswerResponse
from ipg.api.ws.handlers import auto_join_game_room
from ipg.api.ws.notify import notify_game_changed, notify_room_changed
from ipg.dependencies import get_current_user, get_mcqquiz_game_controller

router = APIRouter(
    prefix="/mcqquiz",
    tags=["MCQ Quiz"],
    responses={404: {"description": "Not found"}},
)


@router.post("/games/{room_id}/start", status_code=HTTP_201_CREATED)
async def start_mcqquiz_game(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[McqQuizGameController, Depends(get_mcqquiz_game_controller)],
) -> GameStartResponse:
    result = await controller.create_and_start(room_id, current_user.id)
    auto_join_game_room(result.game_id, str(room_id))
    await notify_room_changed(str(room_id))
    await notify_game_changed(result.game_id, str(room_id))
    return result


@router.get("/games/{game_id}/state")
async def get_mcqquiz_state(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[McqQuizGameController, Depends(get_mcqquiz_game_controller)],
    lang: str = "en",
) -> McqQuizGameState:
    return await controller.get_state(game_id, current_user.id, lang=lang)


@router.post("/games/{game_id}/answer")
async def submit_answer(
    game_id: UUID,
    body: McqSubmitAnswerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[McqQuizGameController, Depends(get_mcqquiz_game_controller)],
) -> McqSubmitAnswerResponse:
    result = await controller.submit_answer(game_id, current_user.id, body.choice_index)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/timer-expired")
async def timer_expired(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[McqQuizGameController, Depends(get_mcqquiz_game_controller)],
) -> TimerExpiredResponse:
    result = await controller.handle_timer_expired(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/next-round")
async def next_round(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[McqQuizGameController, Depends(get_mcqquiz_game_controller)],
) -> GameStartResponse:
    result = await controller.advance_to_next_round(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result
