"""A friend's invite to a room, kept on the server so that it needs no PIN.

The invite used to be a Socket.IO push carrying the room's code AND PIN, stored nowhere:
the PIN rotates (then on a kick, now on a ban), so an invite sent before it opened a join
that was refused. Now the push names this row, and ``RoomController.accept_invite`` seats
the invitee without the PIN, through the join path (ban, one room at a time).

A kick leaves the invites alone (the player may come back through one). A ban deletes the
room's invites the banned player sent and those sent to them, and no member may invite
them until the host lifts it (``InviteeBannedError``).

One live invite per (room, invitee): inviting again refreshes the row (same id, the latest
inviter, a new ``expires_at``). Taking a player's seat in the room consumes it, through
the invite or a join with the code and PIN (``RoomController._take_seat``).
``created_at`` / ``updated_at`` (UTC-aware) are ``BaseTable``'s; ``expires_at`` is aware
too and reads back naive on SQLite (compare it through ``controllers/auth.utc_instant``).

No foreign key declares ON DELETE: account deletion deletes the invites the user sent and
received (``UserController._purge_user_references``), closing a room deletes its invites
(``RoomController.delete_room``), a ban deletes the banned player's (``ban_player``), and ``scripts/purge_seed_data.py`` deletes those of the
rooms it removes. Issuing an invite purges every expired one.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, UniqueConstraint
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class RoomInvite(BaseTable, table=True):
    """``inviter_id`` invited ``invitee_id`` to ``room_id``, until ``expires_at``."""

    __tablename__ = "room_invite"
    __table_args__ = (
        # One live invite per (room, invitee): a re-invite is an upsert on this pair. Its
        # index also serves the room's lookups (room_id leads), so room_id has no other.
        UniqueConstraint("room_id", "invitee_id", name="uq_room_invite_room_invitee"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    room_id: UUID = Field(foreign_key="room.id")
    # The member who sent it (the latest, after a re-invite).
    inviter_id: UUID = Field(foreign_key="user.id", index=True)
    invitee_id: UUID = Field(foreign_key="user.id", index=True)
    expires_at: datetime = Field(
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
        index=True,
    )
