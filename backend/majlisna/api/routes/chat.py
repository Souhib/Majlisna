from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from majlisna.api.controllers.chat import ChatController
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.table import User
from majlisna.api.schemas.chat import ChatMessageView, SendMessageRequest
from majlisna.api.ws.notify import notify_chat_message
from majlisna.dependencies import get_chat_controller, get_current_user

router = APIRouter(
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)


def _to_view(msg: ChatMessage) -> ChatMessageView:
    return ChatMessageView(
        id=msg.id,
        room_id=msg.room_id,
        user_id=msg.user_id,
        username=msg.username,
        message=msg.message,
        created_at=msg.created_at.isoformat(),
    )


@router.post("/rooms/{room_id}/messages", response_model=ChatMessageView, status_code=201)
async def send_message(
    *,
    room_id: UUID,
    body: SendMessageRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_controller: Annotated[ChatController, Depends(get_chat_controller)],
) -> ChatMessageView:
    """Send a chat message to a room."""
    msg = await chat_controller.send_message(room_id, current_user.id, current_user.username, body.message)
    view = _to_view(msg)
    await notify_chat_message(str(room_id), view.model_dump(mode="json"))
    return view


@router.get("/rooms/{room_id}/messages", response_model=Sequence[ChatMessageView])
async def get_messages(
    *,
    room_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_controller: Annotated[ChatController, Depends(get_chat_controller)],
    after_id: UUID | None = Query(default=None, description="Get messages after this ID"),
    limit: int = Query(default=50, ge=1, le=100),
) -> Sequence[ChatMessageView]:
    """Get chat messages for a room, supports incremental polling via after_id."""
    messages = await chat_controller.get_messages(room_id, current_user.id, after_id=after_id, limit=limit)
    return [_to_view(m) for m in messages]
