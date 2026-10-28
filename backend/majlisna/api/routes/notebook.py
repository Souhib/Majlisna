from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request

from majlisna.api.constants import (
    NOTEBOOK_CURSOR_MAX_LENGTH,
    NOTEBOOK_KEEP_RATE_LIMIT,
    NOTEBOOK_PAGE_DEFAULT_LIMIT,
    NOTEBOOK_PAGE_MAX_LIMIT,
)
from majlisna.api.controllers.notebook import NotebookController
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter, user_or_ip_key
from majlisna.api.schemas.notebook import KeepWordRequest, NotebookGameWords, NotebookKeepResponse, NotebookPage
from majlisna.dependencies import get_current_user, get_notebook_controller

# The Kunnash (كُنّاش): a player's notebook of words kept from finished games. It is
# personal — nothing here is pushed over Socket.IO, there is no room to notify.
#
# Handler names are what the generated client's hooks are named after
# (useListNotebookEntries…), so they say "notebook" rather than a bare "entries".
router = APIRouter(
    prefix="/notebook",
    tags=["notebook"],
    responses={404: {"description": "Not found"}},
)


@router.get("/games/{game_id}", response_model=NotebookGameWords)
async def get_notebook_game_words(
    *,
    game_id: UUID,
    lang: str = "en",
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[NotebookController, Depends(get_notebook_controller)],
) -> NotebookGameWords:
    """Every word of a finished game you took part in, in the order it dealt them, with
    whether each is already in your notebook (and its entry id, to un-keep it).

    403 while the game is in progress or if you did not play it; 400 for an MCQ game.
    """
    return await controller.get_game_words(game_id, current_user.id, lang=lang)


@router.post("/games/{game_id}/keep", response_model=NotebookKeepResponse)
@limiter.limit(NOTEBOOK_KEEP_RATE_LIMIT, key_func=user_or_ip_key)
async def keep_notebook_game_words(
    request: Request,  # noqa: ARG001 — required by limiter
    *,
    game_id: UUID,
    lang: str = "en",
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[NotebookController, Depends(get_notebook_controller)],
) -> NotebookKeepResponse:
    """Keep every word of a finished game you took part in. Keeping a word twice is a no-op.

    403 while the game is in progress or if you did not play it; 400 for an MCQ game.
    """
    return await controller.keep_game_words(game_id, current_user.id, lang=lang)


@router.post("/entries", response_model=NotebookKeepResponse)
@limiter.limit(NOTEBOOK_KEEP_RATE_LIMIT, key_func=user_or_ip_key)
async def keep_notebook_word(
    request: Request,  # noqa: ARG001 — required by limiter
    *,
    body: KeepWordRequest,
    lang: str = "en",
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[NotebookController, Depends(get_notebook_controller)],
) -> NotebookKeepResponse:
    """Keep one word of a finished game you took part in. 404 if the game never dealt it."""
    return await controller.keep_word(current_user.id, body, lang=lang)


@router.get("", response_model=NotebookPage)
async def list_notebook_entries(
    *,
    lang: str = "en",
    limit: int = Query(default=NOTEBOOK_PAGE_DEFAULT_LIMIT, ge=1, le=NOTEBOOK_PAGE_MAX_LIMIT),
    cursor: str | None = Query(default=None, min_length=1, max_length=NOTEBOOK_CURSOR_MAX_LENGTH),
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[NotebookController, Depends(get_notebook_controller)],
) -> NotebookPage:
    """Your kept words, newest first, with their Arabic forms and meaning in `lang`.

    Pass the previous page's `next_cursor` as `cursor` for the next one.
    """
    return await controller.list_entries(current_user.id, lang=lang, limit=limit, cursor=cursor)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_notebook_entry(
    *,
    entry_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[NotebookController, Depends(get_notebook_controller)],
) -> None:
    """Remove a word from your notebook. Someone else's entry is a 404, like a missing one."""
    await controller.delete_entry(current_user.id, entry_id)
