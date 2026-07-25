from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from majlisna.api.controllers.game import GameController
from majlisna.api.models.table import User
from majlisna.api.schemas.game import GameHistoryEntry, GameSummary
from majlisna.dependencies import get_current_user, get_game_controller

router = APIRouter(
    prefix="/games",
    tags=["games"],
    responses={404: {"description": "Not found"}},
)

# NOTE: This router intentionally exposes ONLY read endpoints for game history and
# post-game summaries, both authenticated. The generic Game CRUD (create / list-all /
# raw get-by-id / update / end / delete) was removed on purpose: it was entirely
# unauthenticated and leaked the raw `live_state` (roles + secret words) of any game,
# letting a player read the endpoint mid-game to cheat, and letting anyone mutate or
# delete any game. Games are created and mutated exclusively through the per-game
# routers (/undercover, /codenames, /wordquiz, /mcqquiz), which enforce auth,
# membership, and role-aware sanitization.


@router.get("/user/{user_id}", response_model=list[GameHistoryEntry])
async def get_games_by_user(
    *,
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
    current_user: Annotated[User, Depends(get_current_user)],
    game_controller: Annotated[GameController, Depends(get_game_controller)],
) -> list[GameHistoryEntry]:
    """Get a user's game history, most recent first.

    Games still in progress are only included when a user reads their OWN
    history — each entry exposes the subject's role, which is a secret while the
    game runs.
    """
    return list(await game_controller.get_games_by_user(user_id, limit=limit, requester_id=current_user.id))


@router.get("/{game_id}/summary", response_model=GameSummary)
async def get_game_summary(
    *,
    game_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    game_controller: Annotated[GameController, Depends(get_game_controller)],
) -> GameSummary:
    """Get a detailed game summary with players, roles, and history.

    Participants only, and only once the game is over — the payload contains
    every role and the secret words (see ``GameController.get_game_summary``).
    """
    return await game_controller.get_game_summary(game_id, current_user.id)
