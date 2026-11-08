from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from majlisna.api.controllers.profile import ProfileController
from majlisna.api.models.table import User
from majlisna.api.schemas.profile import PublicProfile, UpdateBioRequest
from majlisna.dependencies import get_current_user, get_profile_controller

router = APIRouter(
    prefix="/profiles",
    tags=["profiles"],
    responses={404: {"description": "Not found"}},
)


@router.get("/users/{user_id}", response_model=PublicProfile)
async def get_public_profile(
    *,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    profile_controller: Annotated[ProfileController, Depends(get_profile_controller)],
) -> PublicProfile:
    """Get a player's profile (username, bio, games played). Signed-in players only (owner
    decision, 8 November 2026), like their country and picture (``GET /users/{id}``)."""
    return await profile_controller.get_public_profile(user_id)


@router.patch("/me", response_model=PublicProfile)
async def update_my_profile(
    *,
    body: UpdateBioRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    profile_controller: Annotated[ProfileController, Depends(get_profile_controller)],
) -> PublicProfile:
    """Update the current user's bio."""
    await profile_controller.update_bio(current_user.id, body.bio)
    return await profile_controller.get_public_profile(current_user.id)
