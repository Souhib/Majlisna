from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from majlisna.api.controllers.room import RoomController
from majlisna.api.models.error import UserNotInRoomError
from majlisna.api.models.room import RoomCreateRequest, RoomJoin, RoomLeave
from majlisna.api.models.table import User
from majlisna.api.models.view import RoomView
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.room import (
    ActiveRoomResponse,
    JoinSpectatorRequest,
    KickPlayerRequest,
    KickPlayerResponse,
    RematchResponse,
    RoomInviteRequest,
    RoomInviteResponse,
    RoomSettings,
    RoomSettingsRequest,
    RoomState,
    ShareLinkResponse,
    UpdateRoomSettingsResponse,
)
from majlisna.api.ws.handlers import remove_user_from_room_socket
from majlisna.api.ws.notify import notify_room_changed, notify_room_invite, notify_user_kicked
from majlisna.dependencies import get_current_user, get_room_controller

router = APIRouter(
    prefix="/rooms",
    tags=["rooms"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=RoomView, status_code=HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_room(
    request: Request,  # noqa: ARG001
    *,
    body: RoomCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    room = await room_controller.create_room(owner_id=current_user.id, game_type=body.game_type)
    return RoomView.model_validate(room)


# NOTE: `GET /rooms` (list every active room) was removed on purpose. No client
# used it, and it handed any authenticated user the full directory of live rooms
# — their public_id, owner and member list. Combined with a 4-digit PIN and a
# per-IP-only rate limit on `PATCH /rooms/join`, that turned "guess a room" into
# "enumerate every room, then brute-force 10 000 PINs". Rooms are joined by code
# shared out-of-band; there is no product need for a directory.


@router.get("/active")
async def get_active_room(
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> ActiveRoomResponse | None:
    """Get the user's active room, if any."""
    return await room_controller.get_active_room_for_user(current_user.id)


@router.get("/{room_id}", response_model=RoomView)
async def get_room(
    *,
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    """Get a room. Members only — the response never leaks the PIN or game state."""
    room = await room_controller.get_room_by_id(room_id)
    if not await room_controller.check_if_user_is_in_room(current_user.id, room_id):
        raise UserNotInRoomError(user_id=current_user.id, room_id=room_id)  # type: ignore
    return RoomView.model_validate(room)


@router.get("/{room_id}/state")
async def get_room_state(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomState:
    """Get room state with player connection status. Updates heartbeat. Members only."""
    return await room_controller.get_room_state(room_id, current_user.id)


@router.get("/{room_id}/share-link")
async def get_share_link(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> ShareLinkResponse:
    """Get room share link data (public_id + password for URL construction)."""
    return await room_controller.get_share_link(room_id, current_user.id)


@router.patch("/join", response_model=RoomView)
@limiter.limit("10/minute")
async def join_room(
    request: Request,  # noqa: ARG001
    *,
    room_join: RoomJoin,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    """Join a room with public id + PIN. Identity comes from the JWT (rate-limited against PIN brute-force)."""
    result = await room_controller.join_room(room_join, current_user.id)
    await notify_room_changed(str(result.id))
    return RoomView.model_validate(result)


@router.patch("/leave", response_model=RoomView)
async def leave_room(
    *,
    room_leave: RoomLeave,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    """Leave a room. Identity comes from the JWT — users can only remove themselves."""
    result = await room_controller.leave_room(room_leave.room_id, current_user.id)
    await remove_user_from_room_socket(str(current_user.id), str(room_leave.room_id))
    await notify_room_changed(str(result.id))
    return RoomView.model_validate(result)


@router.patch("/join-spectator", response_model=RoomView)
@limiter.limit("10/minute")
async def join_room_as_spectator(
    request: Request,  # noqa: ARG001
    *,
    body: JoinSpectatorRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    """Join a room as a spectator (watch-only mode). Requires the room PIN."""
    result = await room_controller.join_room_as_spectator(body.room_id, current_user.id, body.password)
    await notify_room_changed(str(result.id))
    return RoomView.model_validate(result)


@router.patch("/{room_id}/kick")
async def kick_player(
    room_id: UUID,
    body: KickPlayerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> KickPlayerResponse:
    """Kick a player from the room. Host only."""
    result = await room_controller.kick_player(room_id, current_user.id, body.user_id)
    await notify_user_kicked(str(body.user_id), str(room_id))
    await remove_user_from_room_socket(str(body.user_id), str(room_id))
    await notify_room_changed(str(room_id))
    return result


@router.patch("/{room_id}/settings")
async def update_room_settings(
    room_id: UUID,
    body: RoomSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> UpdateRoomSettingsResponse:
    result = await room_controller.update_room_settings(room_id, current_user.id, RoomSettings(**body.model_dump()))
    await notify_room_changed(str(room_id))
    return result


@router.post("/{room_id}/rematch")
async def rematch(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RematchResponse:
    result = await room_controller.rematch(room_id, current_user.id)
    await notify_room_changed(str(room_id))
    return result


@router.post("/{room_id}/invite")
async def invite_friend_to_room(
    room_id: UUID,
    body: RoomInviteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomInviteResponse:
    """Invite a friend to join the room."""
    result = await room_controller.invite_friend_to_room(room_id, current_user.id, body.friend_user_id)
    await notify_room_invite(str(body.friend_user_id), str(room_id), current_user.username)
    return result


@router.delete("/{room_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_room(
    *,
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> None:
    """Delete (deactivate) a room. Owner only."""
    await room_controller.delete_room(room_id, current_user.id)
