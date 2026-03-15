import random
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from ipg.api.controllers.room import RoomController
from ipg.api.models.room import RoomCreate, RoomCreateRequest, RoomJoin, RoomLeave, RoomStatus
from ipg.api.models.table import User
from ipg.api.models.view import RoomView
from ipg.api.schemas.room import (
    ActiveRoomResponse,
    JoinSpectatorRequest,
    KickPlayerRequest,
    KickPlayerResponse,
    RematchResponse,
    RoomInviteRequest,
    RoomInviteResponse,
    RoomSettingsRequest,
    RoomState,
    UpdateRoomSettingsResponse,
)
from ipg.api.ws.notify import notify_room_changed, notify_user_kicked
from ipg.dependencies import get_current_user, get_room_controller

router = APIRouter(
    prefix="/rooms",
    tags=["rooms"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=RoomView, status_code=HTTP_201_CREATED)
async def create_room(
    *,
    body: RoomCreateRequest,  # noqa: ARG001
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    password = f"{random.randint(0, 9999):04d}"
    room_create = RoomCreate(
        status=RoomStatus.ONLINE,
        password=password,
        owner_id=current_user.id,
    )
    return RoomView.model_validate(await room_controller.create_room(room_create))


@router.get("", response_model=list[RoomView])
async def get_all_rooms(
    *,
    room_controller: RoomController = Depends(get_room_controller),
) -> list[RoomView]:
    return [RoomView.model_validate(room) for room in await room_controller.get_rooms()]


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
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    return RoomView.model_validate(await room_controller.get_room_by_id(room_id))


@router.get("/{room_id}/state")
async def get_room_state(
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomState:
    """Get room state with player connection status. Updates heartbeat."""
    return await room_controller.get_room_state(room_id, current_user.id)


@router.patch("/join", response_model=RoomView)
async def join_room(
    *,
    room_join: RoomJoin,
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    result = await room_controller.join_room(room_join)
    await notify_room_changed(str(result.id))
    return RoomView.model_validate(result)


@router.patch("/leave", response_model=RoomView)
async def leave_room(
    *,
    room_leave: RoomLeave,
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    result = await room_controller.leave_room(room_leave)
    await notify_room_changed(str(result.id))
    return RoomView.model_validate(result)


@router.patch("/join-spectator", response_model=RoomView)
async def join_room_as_spectator(
    *,
    body: JoinSpectatorRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    """Join a room as a spectator (watch-only mode)."""
    result = await room_controller.join_room_as_spectator(body.room_id, current_user.id)
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
    await notify_room_changed(str(room_id))
    return result


@router.patch("/{room_id}/settings")
async def update_room_settings(
    room_id: UUID,
    body: RoomSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    room_controller: RoomController = Depends(get_room_controller),
) -> UpdateRoomSettingsResponse:
    settings = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await room_controller.update_room_settings(room_id, current_user.id, settings)
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
    return await room_controller.invite_friend_to_room(room_id, current_user.id, body.friend_user_id)


@router.delete("/{room_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_room(
    *,
    room_id: UUID,
    room_controller: RoomController = Depends(get_room_controller),
) -> None:
    await room_controller.delete_room(room_id)
