from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.requests import Request

from majlisna.api.constants import ROOM_RIDDLE_DAILY_LIMIT, ROOM_RIDDLE_RATE_LIMIT
from majlisna.api.controllers.riddle import RiddleController
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter, user_or_ip_key
from majlisna.api.schemas.riddle import RoomRiddle
from majlisna.dependencies import get_current_user, get_riddle_controller

# Samar riddles (السَّمَر) while a table waits: the lobby, and between two questions of
# The Quiz. A read for the room's members only; nothing is pushed over Socket.IO (each
# member gets a riddle of their own). The handler name is what the generated hook is
# named after (useGetRoomRiddle…).
router = APIRouter(
    prefix="/rooms",
    tags=["rooms"],
    responses={404: {"description": "Not found"}},
)


@router.get("/{room_id}/riddle", response_model=RoomRiddle)
@limiter.limit(ROOM_RIDDLE_RATE_LIMIT, key_func=user_or_ip_key)
@limiter.limit(ROOM_RIDDLE_DAILY_LIMIT, key_func=user_or_ip_key)
async def get_room_riddle(
    request: Request,  # noqa: ARG001 — required by limiter
    *,
    room_id: UUID,
    lang: str = "en",
    current_user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[RiddleController, Depends(get_riddle_controller)],
) -> RoomRiddle:
    """A riddle for the waiting table: the vaguest hint of a Kalimat word, and its answer
    (which the client keeps back until the game starts). Members of the room only (403);
    never today's word of the day, never an answer of the room's running quiz, and none
    while another game is played (409)."""
    return await controller.get_room_riddle(room_id, current_user.id, lang=lang)
