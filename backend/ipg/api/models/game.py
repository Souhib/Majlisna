from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from ipg.api.models.shared import DBModel


class GameType(StrEnum):
    UNDERCOVER = "undercover"
    CODENAMES = "codenames"


class GameStatus(StrEnum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class GameBase(DBModel):
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime | None = None
    number_of_players: int = Field(gt=0)
    type: GameType
    game_configurations: dict | None = Field(default_factory=dict, sa_column=Column(JSON))
    live_state: dict | None = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    game_status: GameStatus = GameStatus.WAITING


class GameCreate(GameBase):
    room_id: UUID


class GameUpdate(DBModel):
    start_time: datetime | None = None
    end_time: datetime | None = None
    number_of_players: int | None = None
    type: GameType | None = None
    game_configurations: dict | None = None
