from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, UniqueConstraint

from majlisna.api.schemas.shared import BaseTable


class FriendshipStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class Friendship(BaseTable, table=True):
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),)

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    requester_id: UUID = Field(foreign_key="user.id", index=True)
    addressee_id: UUID = Field(foreign_key="user.id", index=True)
    status: FriendshipStatus = FriendshipStatus.PENDING
    # created_at / updated_at (UTC-aware, with onupdate) are inherited from BaseTable.
