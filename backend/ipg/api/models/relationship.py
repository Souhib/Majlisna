from datetime import datetime
from uuid import UUID

from sqlmodel import Field

from ipg.api.models.shared import DBModel


class RoomUserLink(DBModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    room_id: UUID | None = Field(default=None, foreign_key="room.id", index=True)
    user_id: UUID | None = Field(default=None, foreign_key="user.id", index=True)
    joined_at: datetime = Field(default_factory=datetime.now)
    connected: bool = True
    last_seen_at: datetime | None = None
    disconnected_at: datetime | None = None


class RoomGameLink(DBModel, table=True):
    room_id: UUID | None = Field(default=None, foreign_key="room.id", primary_key=True)
    game_id: UUID | None = Field(default=None, foreign_key="game.id", primary_key=True)


class UserGameLink(DBModel, table=True):
    user_id: UUID | None = Field(default=None, foreign_key="user.id", primary_key=True)
    game_id: UUID | None = Field(default=None, foreign_key="game.id", primary_key=True)


class GameTurnLink(DBModel, table=True):
    game_id: UUID | None = Field(default=None, foreign_key="game.id", primary_key=True)
    turn_id: UUID | None = Field(default=None, foreign_key="turn.id", primary_key=True)


class TurnEventLink(DBModel, table=True):
    turn_id: UUID | None = Field(default=None, foreign_key="turn.id", primary_key=True)
    event_id: UUID | None = Field(default=None, foreign_key="event.id", primary_key=True)


class RoomActivityLink(DBModel, table=True):
    activity_id: UUID | None = Field(default=None, foreign_key="activity.id", primary_key=True)
    room_id: UUID | None = Field(default=None, foreign_key="room.id", primary_key=True)
