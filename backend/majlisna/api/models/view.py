from datetime import datetime
from uuid import UUID

from majlisna.api.models.room import RoomType
from majlisna.api.models.shared import DBModel
from majlisna.api.models.user import UserBase


class UserView(UserBase):
    """Full user representation — only ever returned to the user themselves
    (register, /me, own profile updates). Never use for other users."""

    id: UUID


class PublicUserView(DBModel):
    """User representation safe to expose to OTHER users.

    Declares only non-sensitive public-profile fields — email_address,
    google_sub, auth_provider and email_verified are never read nor serialized.
    """

    id: UUID
    username: str
    country: str | None = None
    bio: str | None = None
    profile_picture_url: str | None = None


class RoomView(DBModel):
    """Public room representation.

    Intentionally does NOT inherit RoomBase: the room PIN (`password`) and
    `games` (whose `live_state` leaks in-progress roles/words) must never
    leave this boundary. Members-only data (PIN, full state) is served by the
    authenticated `/rooms/{id}/state` endpoint instead.
    """

    id: UUID
    public_id: str
    owner_id: UUID
    created_at: datetime
    type: RoomType
    users: list[PublicUserView] = []
