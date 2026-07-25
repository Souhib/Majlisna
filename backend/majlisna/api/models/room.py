from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from majlisna.api.models.game import GameType
from majlisna.api.models.shared import DBModel


class RoomType(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RoomStatus(StrEnum):
    OFFLINE = "offline"
    ONLINE = "online"


class RoomBase(DBModel):
    status: RoomStatus
    password: str = Field(min_length=4, max_length=4)

    @field_validator("password")
    @classmethod
    def check_password_only_digits(cls, v: str) -> str:
        """
        It checks that the password only contains digits
        :param v: The value to be validated
        :return: The room
        """
        if not v.isdigit():
            raise ValueError("Password must only contain digits")
        return v


class RoomCreate(RoomBase):
    owner_id: UUID


class RoomCreateRequest(DBModel):
    """Frontend-facing schema: only game_type is needed."""

    game_type: GameType


class RoomJoin(DBModel):
    """Join request body. The user identity comes from the JWT — never from the body."""

    public_room_id: str
    password: str

    @field_validator("password", mode="before")
    @classmethod
    def coerce_password_to_str(cls, v: object) -> str:
        """Coerce numeric PINs from URL params to strings."""
        return str(v)


class RoomLeave(DBModel):
    """Leave request body. The user identity comes from the JWT — never from the body."""

    room_id: UUID
