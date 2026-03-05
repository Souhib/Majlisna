from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ipg.api.controllers.game import GameController
from ipg.api.models.game import GameCreate, GameUpdate
from ipg.api.models.table import Game
from ipg.api.schemas.game import GameHistoryEntry
from ipg.dependencies import get_game_controller

router = APIRouter(
    prefix="/games",
    tags=["games"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=Game, status_code=201)
async def create_game(
    *,
    game_create: GameCreate,
    game_controller: GameController = Depends(get_game_controller),
) -> Game:
    return Game.model_validate(await game_controller.create_game(game_create))


@router.get("", response_model=list[Game])
async def get_all_undercover_games(
    *,
    game_controller: GameController = Depends(get_game_controller),
) -> list[Game]:
    return [Game.model_validate(game) for game in await game_controller.get_games()]


@router.get("/user/{user_id}", response_model=list[GameHistoryEntry])
async def get_games_by_user(
    *,
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
    game_controller: Annotated[GameController, Depends(get_game_controller)],
) -> list[GameHistoryEntry]:
    """Get a user's game history, most recent first."""
    return list(await game_controller.get_games_by_user(user_id, limit=limit))


@router.get("/{game_id}", response_model=Game)
async def get_undercover_game(
    *,
    game_id: UUID,
    game_controller: GameController = Depends(get_game_controller),
) -> Game:
    return Game.model_validate(await game_controller.get_game_by_id(game_id))


@router.patch("/{game_id}", response_model=Game)
async def update_undercover_game(
    *,
    game_id: UUID,
    game_update: GameUpdate,
    game_controller: GameController = Depends(get_game_controller),
) -> Game:
    return Game.model_validate(await game_controller.update_game(game_id, game_update))


@router.patch("/{game_id}/end", response_model=Game)
async def end_undercover_game(
    *,
    game_id: UUID,
    game_controller: GameController = Depends(get_game_controller),
) -> Game:
    return Game.model_validate(await game_controller.end_game(game_id))


@router.delete("/{game_id}", status_code=204)
async def delete_undercover_game(
    *,
    game_id: UUID,
    game_controller: GameController = Depends(get_game_controller),
):
    await game_controller.delete_game(game_id)


# @router.post("/{game_id}/turns", response_model=Turn, status_code=201)
# async def create_turn(
#     *,
#     game_id: UUID,
#     game_controller: GameController = Depends(get_game_controller),
# ) -> Game:
#     return Game.model_validate(await game_controller.create_turn(game_id))
#
#
# @router.post("/{game_id}/events", response_model=Turn, status_code=201)
# async def create_event(
#     *,
#     game_id: UUID,
#     event_create: EventCreate,
#     game_controller: GameController = Depends(get_game_controller),
# ) -> Game:
#     return Game.model_validate(await game_controller.create_turn_event(game_id, event_create))
