from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.requests import Request

from majlisna.api.constants import DAILY_WORD_GUESS_RATE_LIMIT, NOTEBOOK_KEEP_RATE_LIMIT
from majlisna.api.controllers.daily_word import DailyWordController
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter, user_or_ip_key
from majlisna.api.schemas.daily_word import DailyWordGuessRequest, DailyWordGuessResponse, DailyWordState
from majlisna.api.schemas.notebook import NotebookKeepResponse
from majlisna.dependencies import get_current_user, get_daily_word_controller, get_optional_current_user

# The word of the day (Kalimat al-yawm, كلمة اليوم): a daily solo puzzle, the same word
# for everyone. Personal — nothing is pushed over Socket.IO, there is no room.
#
# Every move takes `day` (the day the page shows): another day than today in Makkah is
# a 409 DailyWordNotTodayError, so a page left open past midnight there never plays
# yesterday's guess against today's word. Handler names are what the generated
# client's hooks are named after (useGetDailyWord…, useGuessDailyWord…).
router = APIRouter(
    prefix="/daily-word",
    tags=["daily-word"],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=DailyWordState)
async def get_daily_word(
    *,
    lang: str = "en",
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    controller: Annotated[DailyWordController, Depends(get_daily_word_controller)],
) -> DailyWordState:
    """Today's word of the day. Public: anonymous callers see the number, the category
    and hint 1 only. The word itself (`answer`) appears once you have solved it or given up."""
    return await controller.get_today(current_user, lang=lang)


@router.post("/hint", response_model=DailyWordState)
async def reveal_daily_word_hint(
    *,
    lang: str = "en",
    day: date | None = None,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[DailyWordController, Depends(get_daily_word_controller)],
) -> DailyWordState:
    """Reveal the next hint (one point less if you find it). 409 once finished or when all are out."""
    return await controller.reveal_hint(current_user.id, day=day, lang=lang)


@router.post("/guess", response_model=DailyWordGuessResponse)
@limiter.limit(DAILY_WORD_GUESS_RATE_LIMIT, key_func=user_or_ip_key)
async def guess_daily_word(
    request: Request,  # noqa: ARG001 — required by limiter
    *,
    body: DailyWordGuessRequest,
    lang: str = "en",
    day: date | None = None,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[DailyWordController, Depends(get_daily_word_controller)],
) -> DailyWordGuessResponse:
    """Guess today's word, in any language or script. 409 once finished."""
    return await controller.guess(current_user.id, body.answer, day=day, lang=lang)


@router.post("/give-up", response_model=DailyWordState)
async def give_up_daily_word(
    *,
    lang: str = "en",
    day: date | None = None,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[DailyWordController, Depends(get_daily_word_controller)],
) -> DailyWordState:
    """Give up today's word: 0 points, the word revealed. 409 once finished."""
    return await controller.give_up(current_user.id, day=day, lang=lang)


@router.post("/keep", response_model=NotebookKeepResponse)
@limiter.limit(NOTEBOOK_KEEP_RATE_LIMIT, key_func=user_or_ip_key)
async def keep_daily_word(
    request: Request,  # noqa: ARG001 — required by limiter
    *,
    lang: str = "en",
    day: date | None = None,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[DailyWordController, Depends(get_daily_word_controller)],
) -> NotebookKeepResponse:
    """Keep the word of a day you finished in your Kunnash (today by default). Idempotent.
    409 before you have solved it or given up."""
    return await controller.keep(current_user.id, day=day, lang=lang)
