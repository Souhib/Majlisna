"""A player the host removed from a room, and may not come back (owner rule (c)).

Kick used to have no lasting effect: ``kick_player`` deleted the ``RoomUserLink`` and
``join_room`` simply inserted a new one, so the kicked player was back in the lobby
with the code and PIN a second later (BR-20). A ban lasts for the room's lifetime; the
host can lift it.

A table of its own, like ``NotebookEntry``: there are no migrations, and ``create_all``
creates a missing table but never ALTERs an existing one. ``created_at`` (UTC-aware) is
``BaseTable``'s. Account deletion deletes the bans OF the user and nulls ``banned_by``
on the bans BY the user (``UserController._purge_user_references``).
"""

from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class RoomBan(BaseTable, table=True):
    """``user_id`` may not join or spectate ``room_id`` while the room lives."""

    __tablename__ = "room_ban"
    __table_args__ = (
        # One ban per (room, player): banning twice is a no-op for the caller to handle,
        # never a second row.
        UniqueConstraint("room_id", "user_id", name="uq_room_ban_room_user"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    room_id: UUID = Field(foreign_key="room.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    # The host who banned, nulled when that account is deleted (the ban stays).
    banned_by: UUID | None = Field(default=None, foreign_key="user.id")
