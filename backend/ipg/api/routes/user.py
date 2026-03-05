from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ipg.api.controllers.user import UserController
from ipg.api.models.table import User
from ipg.api.models.user import UserCreate, UserUpdate, UserUpdatePassword
from ipg.api.models.view import UserView
from ipg.api.schemas.error import ForbiddenError
from ipg.dependencies import get_current_user, get_user_controller

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=UserView, status_code=201)
async def create_user(
    *,
    user: UserCreate,
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserView:
    return UserView.model_validate(await user_controller.create_user(user))


@router.get("", response_model=Sequence[UserView])
async def get_all_users(
    *,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> Sequence[UserView]:
    return [UserView.model_validate(user) for user in await user_controller.get_users()]


@router.get("/{user_id}", response_model=UserView)
async def get_user_by_id(
    *,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserView:
    return UserView.model_validate(await user_controller.get_user_by_id(user_id))


@router.patch("/{user_id}", response_model=UserView)
async def update_user(
    *,
    user_id: UUID,
    user: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserView:
    if current_user.id != user_id:
        raise ForbiddenError("You can only update your own profile")
    return UserView.model_validate(await user_controller.update_user_by_id(user_id, user))


@router.patch("/{user_id}/password", response_model=UserView)
async def update_user_password(
    *,
    user_id: UUID,
    user_update_password: UserUpdatePassword,
    current_user: Annotated[User, Depends(get_current_user)],
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserView:
    if current_user.id != user_id:
        raise ForbiddenError("You can only change your own password")
    return UserView.model_validate(await user_controller.update_user_password(user_id, user_update_password.password))


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    *,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> None:
    if current_user.id != user_id:
        raise ForbiddenError("You can only delete your own account")
    await user_controller.delete_user(user_id)
