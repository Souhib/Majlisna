from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from majlisna.api.controllers.user import UserController
from majlisna.api.models.table import User
from majlisna.api.models.user import UserUpdate, UserUpdatePassword
from majlisna.api.models.view import PublicUserView, UserView
from majlisna.api.schemas.error import ForbiddenError
from majlisna.api.schemas.user import DeleteAccountRequest
from majlisna.dependencies import get_current_user, get_user_controller

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={404: {"description": "Not found"}},
)


# NOTE: `GET /users` (list every user) was removed on purpose. It returned the entire
# user table, unpaginated, to any authenticated caller — a full table scan per call and
# a complete directory of the player base. No client used it: the friends page works
# off `/friends`, and a profile is fetched by id. Same reasoning that removed
# `GET /rooms`. If a people-search is ever needed, add a paginated query endpoint
# rather than a list-everything one.


@router.get("/{user_id}", response_model=PublicUserView)
async def get_user_by_id(
    *,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> PublicUserView:
    """Get a user by id. Returns the public representation only (no email)."""
    return PublicUserView.model_validate(await user_controller.get_user_by_id(user_id))


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
    return UserView.model_validate(
        await user_controller.update_user_password(
            user_id,
            user_update_password.current_password,
            user_update_password.new_password,
        )
    )


# NOTE: `DELETE /users/{user_id}` was removed on purpose. It deleted the caller's own
# account — irreversibly, purging every related row — on nothing more than a valid
# session, while `DELETE /users/me/account` right below does the same thing and
# requires the password. A stolen token was therefore enough to destroy the account,
# which contradicts the rule applied to password changes and account deletion
# everywhere else. No client used it. Account deletion goes through /users/me/account.


@router.delete("/me/account", status_code=204)
async def delete_account(
    *,
    body: DeleteAccountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    user_controller: Annotated[UserController, Depends(get_user_controller)],
) -> None:
    """Delete current user's account. Requires password confirmation."""
    await user_controller.delete_user_account(current_user.id, body.password)
