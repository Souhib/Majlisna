from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends

from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.models.table import User
from majlisna.api.schemas.challenge import ActiveChallenge
from majlisna.dependencies import get_challenge_controller, get_current_user

router = APIRouter(
    prefix="/challenges",
    tags=["challenges"],
    responses={404: {"description": "Not found"}},
)


@router.get("/active", response_model=Sequence[ActiveChallenge])
async def get_active_challenges(
    *,
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[ChallengeController, Depends(get_challenge_controller)],
) -> Sequence[ActiveChallenge]:
    """Get active daily and weekly challenges for the current user."""
    return await controller.get_active_challenges(current_user.id)


@router.post("/seed", status_code=204)
async def seed_challenges(
    *,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    controller: Annotated[ChallengeController, Depends(get_challenge_controller)],
) -> None:
    """Seed challenge definitions into the database."""
    await controller.seed_challenges()
