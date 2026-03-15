from uuid import UUID

from ipg.api.schemas.shared import BaseModel


class RoomPlayerState(BaseModel):
    user_id: str
    username: str
    is_connected: bool
    is_disconnected: bool
    is_host: bool
    is_spectator: bool


class RoomState(BaseModel):
    id: str
    public_id: str
    password: str
    owner_id: str
    active_game_id: str | None = None
    game_type: str | None = None
    players: list[RoomPlayerState]
    type: str
    settings: dict | None = None


class ActiveRoomResponse(BaseModel):
    room_id: str
    public_id: str
    is_connected: bool


class KickPlayerResponse(BaseModel):
    message: str


class UpdateRoomSettingsResponse(BaseModel):
    room_id: str
    settings: dict


class RematchResponse(BaseModel):
    room_id: str
    status: str


class JoinSpectatorRequest(BaseModel):
    room_id: UUID


class KickPlayerRequest(BaseModel):
    user_id: UUID


class RoomSettingsRequest(BaseModel):
    description_timer: int | None = None
    voting_timer: int | None = None
    codenames_clue_timer: int | None = None
    codenames_guess_timer: int | None = None
    enable_mr_white: bool | None = None
    custom_word_packs: list[str] | None = None
    word_quiz_turn_duration: int | None = None
    word_quiz_rounds: int | None = None
    word_quiz_hint_interval: int | None = None
    mcq_quiz_turn_duration: int | None = None
    mcq_quiz_rounds: int | None = None


class RoomInviteRequest(BaseModel):
    friend_user_id: UUID


class RoomInviteResponse(BaseModel):
    room_id: str
    invited_user_id: str
    message: str
