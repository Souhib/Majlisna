from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED

from ipg.api.controllers.undercover import UndercoverController
from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.models.table import User
from ipg.api.models.undercover import TermPair, TermPairCreate, Word, WordCreate
from ipg.api.schemas.common import GameStartResponse, HintRecordResponse, TimerExpiredResponse
from ipg.api.schemas.undercover import (
    DescriptionRequest,
    NextRoundRequest,
    StartNextRoundResponse,
    SubmitDescriptionResponse,
    SubmitVoteResponse,
    UndercoverGameState,
    UndercoverHintViewedRequest,
    VoteRequest,
)
from ipg.api.ws.handlers import auto_join_game_room
from ipg.api.ws.notify import notify_game_changed, notify_room_changed
from ipg.dependencies import get_current_user, get_undercover_controller, get_undercover_game_controller

router = APIRouter(
    prefix="/undercover",
    tags=["undercover"],
    responses={404: {"description": "Not found"}},
)


# --- Game Action Endpoints ---


@router.post("/games/{room_id}/start", status_code=HTTP_201_CREATED)
async def start_undercover_game(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
) -> GameStartResponse:
    result = await controller.create_and_start(room_id, current_user.id)
    auto_join_game_room(result.game_id, str(room_id))
    await notify_room_changed(str(room_id))
    await notify_game_changed(result.game_id, str(room_id))
    return result


@router.get("/games/{game_id}/state")
async def get_undercover_state(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
    sid: str | None = None,
    lang: str = "en",
) -> UndercoverGameState:
    return await controller.get_state(game_id, current_user.id, sid=sid, lang=lang)


@router.post("/games/{game_id}/describe")
async def submit_description(
    game_id: UUID,
    body: DescriptionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
) -> SubmitDescriptionResponse:
    result = await controller.submit_description(game_id, current_user.id, body.word)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/vote")
async def submit_vote(
    game_id: UUID,
    body: VoteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
) -> SubmitVoteResponse:
    result = await controller.submit_vote(game_id, current_user.id, body.voted_for)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/timer-expired")
async def timer_expired(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
) -> TimerExpiredResponse:
    result = await controller.handle_timer_expired(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/hint-viewed")
async def record_hint_viewed(
    game_id: UUID,
    body: UndercoverHintViewedRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
) -> HintRecordResponse:
    return await controller.record_hint_view(game_id, current_user.id, body.word)


@router.post("/games/{game_id}/next-round")
async def start_next_round(
    game_id: UUID,
    body: NextRoundRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[UndercoverGameController, Depends(get_undercover_game_controller)],
) -> StartNextRoundResponse:
    result = await controller.start_next_round(game_id, body.room_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


@router.post("/words", response_model=Word, status_code=201)
async def create_word(
    *,
    word_create: WordCreate,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> Word:
    return await undercover_controller.create_word(word_create)


@router.get("/words", response_model=Sequence[Word])
async def get_all_words(
    *,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> Sequence[Word]:
    return await undercover_controller.get_words()


@router.get("/words/{word_id}", response_model=Word)
async def get_word_by_id(
    *,
    word_id: UUID,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> Word:
    return await undercover_controller.get_word_by_id(word_id)


@router.get("/words/search/{word}", response_model=Word)
async def get_word_by_word(
    *,
    word: str,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> Word:
    return await undercover_controller.get_word_by_word(word)


@router.delete("/words/{word_id}", response_model=None, status_code=204)
async def delete_word(
    *,
    word_id: UUID,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> None:
    await undercover_controller.delete_word(word_id)


@router.post("/termpair", response_model=TermPair, status_code=201)
async def create_term_pair(
    *,
    term_pair_create: TermPairCreate,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> TermPair:
    return await undercover_controller.create_term_pair(term_pair_create.word1_id, term_pair_create.word2_id)


@router.get("/termpair", response_model=Sequence[TermPair])
async def get_all_term_pairs(
    *,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> Sequence[TermPair]:
    return await undercover_controller.get_term_pairs()


@router.get("/termpair/{term_pair_id}", response_model=TermPair)
async def get_term_pair_by_id(
    *,
    term_pair_id: UUID,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> TermPair:
    return await undercover_controller.get_term_pair_by_id(term_pair_id)


@router.get("/termpair/search/random", response_model=TermPair)
async def get_random_term_pair(
    *,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> TermPair:
    return await undercover_controller.get_random_term_pair()


@router.delete("/termpair/{term_pair_id}", response_model=None, status_code=204)
async def delete_term_pair(
    *,
    term_pair_id: UUID,
    undercover_controller: UndercoverController = Depends(get_undercover_controller),
) -> None:
    await undercover_controller.delete_term_pair(term_pair_id)
