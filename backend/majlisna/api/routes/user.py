from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from majlisna.api.constants import PASSWORD_CHANGE_RATE_LIMIT
from majlisna.api.controllers.user import UserController
from majlisna.api.models.table import User
from majlisna.api.models.user import UserUpdate, UserUpdatePassword
from majlisna.api.models.view import PublicUserView, UserView
from majlisna.api.rate_limit import limiter, user_or_ip_key
from majlisna.api.schemas.error import ForbiddenError
from majlisna.api.schemas.user import DeleteAccountRequest
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.api.ws.handlers import remove_user_from_room_socket
from majlisna.api.ws.notify import notify_member_removed
from majlisna.dependencies import get_current_user, get_social_auth_service, get_user_controller

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
@limiter.limit(PASSWORD_CHANGE_RATE_LIMIT, key_func=user_or_ip_key)
async def update_user_password(
    request: Request,
    *,
    user_id: UUID,
    user_update_password: UserUpdatePassword,
    current_user: Annotated[User, Depends(get_current_user)],
    user_controller: Annotated[UserController, Depends(get_user_controller)],
    social_auth_service: Annotated[SocialAuthService, Depends(get_social_auth_service)],
) -> UserView:
    """Set the password, confirmed by the current one or, for a Google-only account, by a
    fresh Google access token naming it; every OTHER session is signed out (SEC F01).

    A Google-only account that sets one can then sign in with it, and still with Google.
    """
    if current_user.id != user_id:
        raise ForbiddenError("You can only change your own password")
    return UserView.model_validate(
        await user_controller.update_user_password(
            user_id,
            user_update_password.current_password,
            user_update_password.new_password,
            google_access_token=user_update_password.google_access_token,
            social_auth_service=social_auth_service,
            # The caller's session, recorded by get_current_user (None for a legacy token).
            keep_session_id=getattr(request.state, "session_id", None),
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
    social_auth_service: Annotated[SocialAuthService, Depends(get_social_auth_service)],
) -> None:
    """Delete the current user's account, confirmed by the password or, for a Google
    account, a fresh Google access token naming it.

    The account first leaves every room like a leave does (its game is played on
    without it), so each room is told, and the socket cut off it, as the leave route does.
    """
    departed = await user_controller.delete_user_account(
        current_user.id,
        body.password,
        google_access_token=body.google_access_token,
        social_auth_service=social_auth_service,
    )
    for room in departed:
        await remove_user_from_room_socket(str(current_user.id), str(room.room_id))
        await notify_member_removed(str(room.room_id), str(room.game_id) if room.game_id else None)
