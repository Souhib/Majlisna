from collections.abc import Sequence
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import CHAT_MESSAGE_MAX_LENGTH
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.schemas.error import UserNotInRoomError


class ChatController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _ensure_member(self, room_id: UUID, user_id: UUID) -> None:
        """Raise UserNotInRoomError unless the user is a member of the room.

        Membership is checked by the existence of a RoomUserLink, NOT by the
        `connected` flag: a member who is briefly disconnected (Socket.IO
        reconnection / grace period) must still be able to read and post chat.
        A non-member has no link at all, which is exactly what we reject.
        """
        link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == user_id,
                )
            )
        ).first()
        if not link:
            raise UserNotInRoomError(user_id=user_id, room_id=room_id)

    async def send_message(self, room_id: UUID, user_id: UUID, username: str, message: str) -> ChatMessage:
        """Send a chat message to a room. Only room members may post."""
        await self._ensure_member(room_id, user_id)
        msg = ChatMessage(
            room_id=room_id, user_id=user_id, username=username, message=message[:CHAT_MESSAGE_MAX_LENGTH]
        )
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def get_messages(
        self, room_id: UUID, user_id: UUID, after_id: UUID | None = None, limit: int = 50
    ) -> Sequence[ChatMessage]:
        """Get the most recent messages for a room, oldest-first. Members only.

        Optionally filter to messages after a specific message ID for incremental polling.

        The ``limit`` window is taken from the NEWEST end. Ordering ascending
        before applying the limit returned the OLDEST ``limit`` rows, so once a
        room passed 50 messages the chat panel opened on the very first messages
        of the session and never showed the recent ones — it only appends what
        arrives afterwards over Socket.IO, so the gap was permanent.
        """
        await self._ensure_member(room_id, user_id)
        query = select(ChatMessage).where(ChatMessage.room_id == room_id)

        if after_id:
            # Get the timestamp of the after_id message
            ref_msg = (await self.session.exec(select(ChatMessage).where(ChatMessage.id == after_id))).first()
            if ref_msg:
                query = query.where(ChatMessage.created_at > ref_msg.created_at)

        query = query.order_by(ChatMessage.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
        newest_first = (await self.session.exec(query)).all()
        return list(reversed(newest_first))
