from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, ForeignKey
from sqlmodel import Field, Relationship

from ipg.api.models.codenames import CodenamesWord, CodenamesWordPack  # noqa: F401
from ipg.api.models.event import TurnBase
from ipg.api.models.game import GameBase
from ipg.api.models.relationship import (
    GameTurnLink,
    RoomActivityLink,
    RoomGameLink,
    RoomUserLink,
    TurnEventLink,
    UserGameLink,
)
from ipg.api.models.room import RoomBase, RoomType
from ipg.api.models.shared import DBModel
from ipg.api.models.user import UserBase


class Room(RoomBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    public_id: str = Field(min_length=5, max_length=5, unique=True, index=True)
    owner_id: UUID | None = Field(default=None, foreign_key="user.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.now)
    type: RoomType = RoomType.ACTIVE
    active_game_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("game.id", use_alter=True, name="fk_room_active_game_id"), nullable=True),
    )
    users: list["User"] = Relationship(
        back_populates="rooms",
        link_model=RoomUserLink,
        sa_relationship_kwargs={"secondary": "roomuserlink"},
    )
    games: list["Game"] = Relationship(back_populates="room", link_model=RoomGameLink)
    activities: list["Activity"] = Relationship(back_populates="room", link_model=RoomActivityLink)


class Game(GameBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    room_id: UUID | None = Field(foreign_key="room.id")
    user_id: UUID | None = Field(foreign_key="user.id")
    room: Room = Relationship(back_populates="games", link_model=RoomGameLink)
    users: list["User"] = Relationship(back_populates="games", link_model=UserGameLink)
    turns: list["Turn"] = Relationship(back_populates="game", link_model=GameTurnLink)


class User(UserBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    password: str = Field(min_length=5)
    rooms: list[Room] = Relationship(back_populates="users", link_model=RoomUserLink)
    games: list[Game] = Relationship(back_populates="users", link_model=UserGameLink)


class Event(DBModel, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    name: str
    data: dict[str, Any] = Field(sa_column=Column(JSON))
    turn_id: UUID | None = Field(foreign_key="turn.id")
    user_id: UUID | None = Field(foreign_key="user.id")
    timestamp: datetime = Field(default_factory=datetime.now)
    turn: "Turn" = Relationship(back_populates="events", link_model=TurnEventLink)


class Activity(DBModel, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    room_id: UUID | None = Field(foreign_key="room.id")
    user_id: UUID | None = Field(foreign_key="user.id")
    name: str
    data: dict[str, Any] = Field(sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=datetime.now)
    room: "Room" = Relationship(back_populates="activities", link_model=RoomActivityLink)


class Turn(TurnBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    game_id: UUID | None = Field(foreign_key="game.id")
    game: Game = Relationship(back_populates="turns", link_model=GameTurnLink)
    events: list[Event] = Relationship(back_populates="turn", link_model=TurnEventLink)
