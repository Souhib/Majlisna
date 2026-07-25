from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED

from majlisna.api.controllers.codenames import CodenamesController
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.models.codenames import (
    CodenamesWord,
    CodenamesWordCreate,
    CodenamesWordPack,
    CodenamesWordPackCreate,
)
from majlisna.api.models.table import User
from majlisna.api.schemas.codenames import (
    CodenamesBoardState,
    CodenamesHintViewedRequest,
    EndTurnResponse,
    GiveClueRequest,
    GiveClueResponse,
    GuessCardRequest,
    GuessCardResponse,
    StartCodenamesRequest,
)
from majlisna.api.schemas.common import GameStartResponse, HintRecordResponse, TimerExpiredResponse
from majlisna.api.ws.handlers import auto_join_game_room
from majlisna.api.ws.notify import notify_game_changed, notify_room_changed
from majlisna.dependencies import (
    get_codenames_controller,
    get_codenames_game_controller,
    get_current_admin_user,
    get_current_user,
)

router = APIRouter(
    prefix="/codenames",
    tags=["Codenames"],
    responses={404: {"description": "Not found"}},
)


# --- Game Action Endpoints ---


@router.post("/games/{room_id}/start", status_code=HTTP_201_CREATED)
async def start_codenames_game(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
    body: StartCodenamesRequest | None = None,
) -> GameStartResponse:
    word_pack_ids = body.word_pack_ids if body else None
    result = await controller.create_and_start(room_id, current_user.id, word_pack_ids=word_pack_ids)
    await auto_join_game_room(result.game_id, str(room_id))
    await notify_room_changed(str(room_id))
    await notify_game_changed(result.game_id, str(room_id))
    return result


@router.get("/games/{game_id}/board")
async def get_codenames_board(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
    sid: str | None = None,
    lang: str = "en",
) -> CodenamesBoardState:
    return await controller.get_board(game_id, current_user.id, sid=sid, lang=lang)


@router.post("/games/{game_id}/clue")
async def give_clue(
    game_id: UUID,
    body: GiveClueRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> GiveClueResponse:
    result = await controller.give_clue(game_id, current_user.id, body.clue_word, body.clue_number)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/guess")
async def guess_card(
    game_id: UUID,
    body: GuessCardRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> GuessCardResponse:
    result = await controller.guess_card(game_id, current_user.id, body.card_index)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/timer-expired")
async def timer_expired(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> TimerExpiredResponse:
    result = await controller.handle_timer_expired(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


@router.post("/games/{game_id}/hint-viewed")
async def record_hint_viewed(
    game_id: UUID,
    body: CodenamesHintViewedRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> HintRecordResponse:
    return await controller.record_hint_view(game_id, current_user.id, body.word)


@router.post("/games/{game_id}/end-turn")
async def end_turn(
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[CodenamesGameController, Depends(get_codenames_game_controller)],
) -> EndTurnResponse:
    result = await controller.end_turn(game_id, current_user.id)
    await notify_game_changed(str(game_id))
    return result


# ─── Content endpoints (word packs + words) are ADMIN ONLY ────────────────────
#
# Same reasoning as routes/undercover.py: no client calls these, the GETs took no
# authentication at all, and the POST/DELETE routes took only *a* login — so any
# player could delete every word pack and break Codenames for everyone. Content
# is seeded by scripts/generate_fake_data.py. See get_current_admin_user.

# --- Word Packs ---


@router.post("/word-packs", response_model=CodenamesWordPack, status_code=201)
async def create_word_pack(
    *,
    word_pack_create: CodenamesWordPackCreate,
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> CodenamesWordPack:
    """Create a new Codenames word pack."""
    return await codenames_controller.create_word_pack(word_pack_create)


@router.get("/word-packs", response_model=Sequence[CodenamesWordPack])
async def get_word_packs(
    *,
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> Sequence[CodenamesWordPack]:
    """List all Codenames word packs."""
    return await codenames_controller.get_word_packs()


@router.get("/word-packs/{pack_id}", response_model=CodenamesWordPack)
async def get_word_pack(
    *,
    pack_id: UUID,
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> CodenamesWordPack:
    """Get a specific Codenames word pack by ID."""
    return await codenames_controller.get_word_pack(pack_id)


@router.delete("/word-packs/{pack_id}", response_model=None, status_code=204)
async def delete_word_pack(
    *,
    pack_id: UUID,
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
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
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> CodenamesWord:
    """Add a word to a Codenames word pack."""
    return await codenames_controller.add_word(word_create, pack_id)


@router.get("/word-packs/{pack_id}/words", response_model=Sequence[CodenamesWord])
async def get_words_by_pack(
    *,
    pack_id: UUID,
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> Sequence[CodenamesWord]:
    """List all words in a Codenames word pack."""
    return await codenames_controller.get_words_by_pack(pack_id)


@router.delete("/words/{word_id}", response_model=None, status_code=204)
async def delete_word(
    *,
    word_id: UUID,
    admin: Annotated[User, Depends(get_current_admin_user)],  # noqa: ARG001 — admin required
    codenames_controller: CodenamesController = Depends(get_codenames_controller),
) -> None:
    """Delete a Codenames word by ID."""
    await codenames_controller.delete_word(word_id)
