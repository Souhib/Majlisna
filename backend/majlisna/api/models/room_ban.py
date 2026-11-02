"""A player the host BANNED from a room, who may not come back until the host lifts it.

Kick and ban are two host actions (owner decision, 2 November 2026). A kick
(``kick_player``) only takes the seat, for someone who left without quitting: no row
here, and the player may come back with the code and PIN. A ban (``ban_player``) takes
the seat AND writes this row: join, spectate and accepting an invite answer
``RoomBannedError``, no member may invite them (``InviteeBannedError``), and the PIN
rotates. It lasts for the room's lifetime unless the host lifts it. (Before that
decision every kick wrote one: the kick of BR-20 had no lasting effect at all.)

A table of its own, like ``NotebookEntry`` (added when ``create_all`` was the schema and
never ALTERed a table; in the baseline migration since). ``created_at`` (UTC-aware) is
``BaseTable``'s. Account deletion deletes the bans OF the user and nulls ``banned_by``
on the bans BY the user (``UserController._purge_user_references``).
"""

from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class RoomBan(BaseTable, table=True):
    """``user_id`` may not join, spectate or be invited into ``room_id`` while the room lives."""

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
