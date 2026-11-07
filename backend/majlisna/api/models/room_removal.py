"""A player the host REMOVED from a room (a kick), so that the host can still ban them.

Ban after removal (owner request, 3 November 2026). A ban used to need a seat: a host who
pressed Remove and then decided "we don't want them back" could not ban until the player
sat down again. ``kick_player`` now writes this row in the departure's transaction, the
host lists the removed players (``RoomController.list_removals``), and ``ban_player``
accepts a player who has no seat but has this row: the ``RoomBan``, the invites deleted and
the new PIN as for a seated player, and no departure (there is no seat to take).

A record, not a ban: the player may still come back with the code and PIN or an invite,
and taking a seat again deletes it (``RoomController._take_seat`` and the spectator's seat,
which then ask for a ban once more: a ban of the removed player committed meanwhile). The
ban deletes it too. One per (room, player): a second kick refreshes it (the latest host,
``updated_at`` = the latest removal, what the host's list shows and sorts by).

No foreign key declares ON DELETE (like every other): closing a room deletes its records
(``RoomController.delete_room``), account deletion deletes the records OF the user and nulls
``removed_by`` on the records BY the user (``UserController._purge_user_references``, as for
``RoomBan.banned_by``), and ``scripts/purge_seed_data.py`` deletes those of the rooms it
removes. ``created_at`` / ``updated_at`` (UTC-aware, read back naive on SQLite) are
``BaseTable``'s.
"""

from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class RoomRemoval(BaseTable, table=True):
    """``removed_by`` removed ``user_id`` from ``room_id`` (Remove), and they have not sat down again since."""

    __tablename__ = "room_removal"
    __table_args__ = (
        # One record per (room, player): a second kick is an upsert on this pair. Its index
        # leads with room_id, which serves the room's own lookups (the host's list, closing a
        # room, the seed purge): room_id has no other index.
        UniqueConstraint("room_id", "user_id", name="uq_room_removal_room_user"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    room_id: UUID = Field(foreign_key="room.id")
    # Indexed for account deletion (the records OF the user, and BY the user).
    user_id: UUID = Field(foreign_key="user.id", index=True)
    # The host who removed (the latest, after a second kick), nulled when that account is deleted.
    removed_by: UUID | None = Field(default=None, foreign_key="user.id", index=True)
