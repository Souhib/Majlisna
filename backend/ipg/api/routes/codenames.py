from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED

from ipg.api.controllers.codenames import CodenamesController
from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.models.codenames import (
    CodenamesWord,
    CodenamesWordCreate,
    CodenamesWordPack,
    CodenamesWordPackCreate,
)
from ipg.api.models.table import User
from ipg.api.schemas.shared import BaseModel
from ipg.dependencies import get_codenames_controller, get_codenames_game_controller, get_current_user

router = APIRouter(
    prefix="/codenames",
    tags=["Codenames"],
    responses={404: {"description": "Not found"}},
)


# --- Request Schemas ---


class StartCodenamesRequest(BaseModel):
    word_pack_ids: list[UUID] | None = None


class GiveClueRequest(BaseModel):
    clue_word: str
    clue_number: int


class GuessCardRequest(BaseModel):
    card_index: int


# --- Game Action Endpoints ---


@router.post("/games/{room_id}/start", status_code=HTTP_201_CREATED)
async def start_codenames_game(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
    body: StartCodenamesRequest | None = None,
) -> dict:
    word_pack_ids = body.word_pack_ids if body else None
    return await controller.create_and_start(room_id, current_user.id, word_pack_ids=word_pack_ids)


@router.get("/games/{game_id}/board")
async def get_codenames_board(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
    sid: str | None = None,
) -> dict:
    return await controller.get_board(game_id, current_user.id, sid=sid)


@router.post("/games/{game_id}/clue")
async def give_clue(
    game_id: UUID,
    body: GiveClueRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> dict:
    return await controller.give_clue(game_id, current_user.id, body.clue_word, body.clue_number)


@router.post("/games/{game_id}/guess")
async def guess_card(
    game_id: UUID,
    body: GuessCardRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> dict:
    return await controller.guess_card(game_id, current_user.id, body.card_index)


@router.post("/games/{game_id}/end-turn")
async def end_turn(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> dict:
    return await controller.end_turn(game_id, current_user.id)


# --- Word Packs ---


@router.post("/word-packs", response_model=CodenamesWordPack, status_code=201)
async def create_word_pack(
    *,
    word_pack_create: CodenamesWordPackCreate,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> CodenamesWordPack:
    """Create a new Codenames word pack."""
    return await codenames_controller.create_word_pack(word_pack_create)


@router.get("/word-packs", response_model=Sequence[CodenamesWordPack])
async def get_word_packs(
    *,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> Sequence[CodenamesWordPack]:
    """List all Codenames word packs."""
    return await codenames_controller.get_word_packs()


@router.get("/word-packs/{pack_id}", response_model=CodenamesWordPack)
async def get_word_pack(
    *,
    pack_id: UUID,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> CodenamesWordPack:
    """Get a specific Codenames word pack by ID."""
    return await codenames_controller.get_word_pack(pack_id)


@router.delete("/word-packs/{pack_id}", response_model=None, status_code=204)
async def delete_word_pack(
    *,
    pack_id: UUID,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> None:
    """Delete a Codenames word pack by ID."""
    await codenames_controller.delete_word_pack(pack_id)


# --- Words ---


@router.post("/word-packs/{pack_id}/words", response_model=CodenamesWord, status_code=201)
async def add_word_to_pack(
    *,
    pack_id: UUID,
    word_create: CodenamesWordCreate,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> CodenamesWord:
    """Add a word to a Codenames word pack."""
    return await codenames_controller.add_word(word_create, pack_id)


@router.get("/word-packs/{pack_id}/words", response_model=Sequence[CodenamesWord])
async def get_words_by_pack(
    *,
    pack_id: UUID,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> Sequence[CodenamesWord]:
    """List all words in a Codenames word pack."""
    return await codenames_controller.get_words_by_pack(pack_id)


@router.delete("/words/{word_id}", response_model=None, status_code=204)
async def delete_word(
    *,
    word_id: UUID,
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> None:
    """Delete a Codenames word by ID."""
    await codenames_controller.delete_word(word_id)
