import random
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from ipg.api.controllers.room import RoomController
from ipg.api.models.room import RoomCreate, RoomCreateRequest, RoomJoin, RoomLeave, RoomStatus
from ipg.api.models.table import User
from ipg.api.models.view import RoomView
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
) -> dict:
    """Get room state with player connection status. Updates heartbeat."""
    return await room_controller.get_room_state(room_id, current_user.id)


@router.patch("/join", response_model=RoomView)
async def join_room(
    *,
    room_join: RoomJoin,
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    return RoomView.model_validate(await room_controller.join_room(room_join))


@router.patch("/leave", response_model=RoomView)
async def leave_room(
    *,
    room_leave: RoomLeave,
    room_controller: RoomController = Depends(get_room_controller),
) -> RoomView:
    return RoomView.model_validate(await room_controller.leave_room(room_leave))


@router.delete("/{room_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_room(
    *,
    room_id: UUID,
    room_controller: RoomController = Depends(get_room_controller),
) -> None:
    await room_controller.delete_room(room_id)
