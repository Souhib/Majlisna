from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Field

from ipg.api.models.shared import DBModel


class EventBase(DBModel):
    name: str
    data: dict[str, Any]


class EventCreate(EventBase):
    user_id: UUID


class TurnBase(DBModel):
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime | None = None
    completed: bool = False
