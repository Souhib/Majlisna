from enum import StrEnum
from uuid import UUID

from pydantic import Field

from majlisna.api.constants import (
    MAX_CUSTOM_WORD_PACKS,
    MAX_HINT_INTERVAL_SECONDS,
    MAX_QUIZ_ROUNDS,
    MAX_TIMER_SECONDS,
    MIN_HINT_INTERVAL_SECONDS,
    MIN_QUIZ_ROUNDS,
    MIN_TIMER_SECONDS,
)
from majlisna.api.schemas.shared import BaseModel


class DifficultyLevel(StrEnum):
    """Quiz difficulty a host may select. "mixed" means "don't filter"."""

    MIXED = "mixed"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RoomPlayerState(BaseModel):
    user_id: str
    username: str
    is_connected: bool
    is_disconnected: bool
    is_host: bool
    is_spectator: bool


class RoomSettings(BaseModel):
    game_type: str | None = None
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
    word_quiz_difficulty: str | None = None
    mcq_quiz_difficulty: str | None = None


class RoomState(BaseModel):
    id: str
    public_id: str
    password: str
    owner_id: str
    active_game_id: str | None = None
    game_type: str | None = None
    players: list[RoomPlayerState]
    type: str
    settings: RoomSettings | None = None


class ActiveRoomResponse(BaseModel):
    room_id: str
    public_id: str
    is_connected: bool


class KickPlayerResponse(BaseModel):
    message: str


class UpdateRoomSettingsResponse(BaseModel):
    room_id: str
    settings: RoomSettings


class RematchResponse(BaseModel):
    room_id: str
    status: str


class JoinSpectatorRequest(BaseModel):
    room_id: UUID
    password: str  # Room PIN — required, spectating is not a bypass around the password


class KickPlayerRequest(BaseModel):
    user_id: UUID


class RoomSettingsRequest(BaseModel):
    """Host-supplied room settings.

    Every numeric field is bounded. These values are copied verbatim into
    ``Room.settings`` and then into a game's ``live_state`` at start, so an
    unbounded value is not just cosmetic: ``word_quiz_rounds=10_000_000`` makes
    game creation try to draw ten million questions, and a negative timer makes
    the timer-expiry check pass immediately and spin the round forward.
    """

    description_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    voting_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    codenames_clue_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    codenames_guess_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    enable_mr_white: bool | None = None
    custom_word_packs: list[str] | None = Field(default=None, max_length=MAX_CUSTOM_WORD_PACKS)
    word_quiz_turn_duration: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    word_quiz_rounds: int | None = Field(default=None, ge=MIN_QUIZ_ROUNDS, le=MAX_QUIZ_ROUNDS)
    word_quiz_hint_interval: int | None = Field(
        default=None, ge=MIN_HINT_INTERVAL_SECONDS, le=MAX_HINT_INTERVAL_SECONDS
    )
    mcq_quiz_turn_duration: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    mcq_quiz_rounds: int | None = Field(default=None, ge=MIN_QUIZ_ROUNDS, le=MAX_QUIZ_ROUNDS)
    word_quiz_difficulty: DifficultyLevel | None = None
    mcq_quiz_difficulty: DifficultyLevel | None = None


class RoomInviteRequest(BaseModel):
    friend_user_id: UUID


class RoomInviteResponse(BaseModel):
    room_id: str
    invited_user_id: str
    message: str


class ShareLinkResponse(BaseModel):
    public_id: str
    password: str
