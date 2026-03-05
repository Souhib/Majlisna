from datetime import datetime
from uuid import UUID

from ipg.api.models.event import TurnBase
from ipg.api.models.game import GameBase
from ipg.api.models.room import RoomBase, RoomType
from ipg.api.models.table import Event, Game, Room, Turn, User
from ipg.api.models.user import UserBase


class TurnView(TurnBase):
    id: UUID
    game_id: UUID
    game: Game
    events: list[Event]


class GameView(GameBase):
    id: UUID
    room_id: UUID
    user_id: UUID
    room: Room
    users: list[User]
    turns: list[Turn]


class UserView(UserBase):
    id: UUID

    class Config:
        # Custom JSON encoders dictionary
        json_encoders = {UUID: str}  # Convert UUIDs to strings


class RoomView(RoomBase):
    id: UUID
    public_id: str
    owner_id: UUID
    password: str
    created_at: datetime
    type: RoomType
    users: list[UserView] = []
    games: list[Game] = []

    class Config:
        # Custom JSON encoders dictionary
        json_encoders = {UUID: str}  # Convert UUIDs to strings
