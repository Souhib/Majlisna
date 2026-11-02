from datetime import datetime
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
    MIN_QUIZ_TURN_SECONDS,
    MIN_TIMER_SECONDS,
)
from majlisna.api.models.game import GameType
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
    # While the member is away (disconnected): whole seconds, rounded up, before the
    # server removes them — "away · 9:58". Null while connected. Computed when the state
    # is read (and pushed over Socket.IO), so the client counts down from it locally.
    # The grace depends on the room: 600 s in the lobby, 180 s in a running game,
    # 45 min while the game is paused for the prayer. 0 means "due at the next sweep".
    away_seconds_left: int | None = None


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
    # When this state was read (epoch ms, taken before its first query). Two reads can
    # reach a client out of order (a socket's connect read just before a change, sent
    # after the change's own push): the client keeps the state read last. Every change is
    # pushed by a read made after its commit, so the newest read is the true one.
    as_of_ms: int


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

    ``game_type`` is the host's pick in the lobby. It lives in the room's settings
    (``get_room_state`` reads it from there while no game runs) so every guest's
    lobby describes the game the host chose, not the one the room was opened for.
    """

    game_type: GameType | None = None
    description_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    voting_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    codenames_clue_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    codenames_guess_timer: int | None = Field(default=None, ge=MIN_TIMER_SECONDS, le=MAX_TIMER_SECONDS)
    enable_mr_white: bool | None = None
    custom_word_packs: list[str] | None = Field(default=None, max_length=MAX_CUSTOM_WORD_PACKS)
    # The quizzes have no "no limit" value: a round of 0-2 s expired the moment it opened
    # (their expiry is elapsed >= duration - tolerance), so they get their own minimum
    # (BR-17). Undercover and Codenames keep 0 = untimed.
    word_quiz_turn_duration: int | None = Field(default=None, ge=MIN_QUIZ_TURN_SECONDS, le=MAX_TIMER_SECONDS)
    word_quiz_rounds: int | None = Field(default=None, ge=MIN_QUIZ_ROUNDS, le=MAX_QUIZ_ROUNDS)
    word_quiz_hint_interval: int | None = Field(
        default=None, ge=MIN_HINT_INTERVAL_SECONDS, le=MAX_HINT_INTERVAL_SECONDS
    )
    mcq_quiz_turn_duration: int | None = Field(default=None, ge=MIN_QUIZ_TURN_SECONDS, le=MAX_TIMER_SECONDS)
    mcq_quiz_rounds: int | None = Field(default=None, ge=MIN_QUIZ_ROUNDS, le=MAX_QUIZ_ROUNDS)
    word_quiz_difficulty: DifficultyLevel | None = None
    mcq_quiz_difficulty: DifficultyLevel | None = None


class RoomInviteRequest(BaseModel):
    friend_user_id: UUID


class RoomInviteView(BaseModel):
    """A friend's invite to a room, as the invitee sees it: the ``room_invite`` push to
    their personal channel and ``GET /rooms/invites``. Never the room's PIN: the invite
    is accepted by its id (``POST /rooms/invites/{id}/accept``), so a PIN rotated by a
    kick after it was sent does not stop it.

    ``public_id`` is the room's code and ``invited_by`` the inviter's username (what the
    strip shows); ``expires_at`` is UTC.
    """

    id: UUID
    room_id: UUID
    public_id: str
    invited_by: str
    expires_at: datetime


class RoomInviteResponse(BaseModel):
    room_id: str
    invited_user_id: str
    message: str
    # The stored invite, as pushed to the friend (the route hands it to notify_room_invite).
    invite: RoomInviteView


class ShareLinkResponse(BaseModel):
    public_id: str
    password: str


class RoomBanView(BaseModel):
    """A player the host kicked from the room, who may not come back until lifted.

    Served to the host only (``GET /rooms/{id}/bans``). ``banned_at`` is the ban's
    ``created_at`` (UTC).
    """

    user_id: UUID
    username: str
    banned_at: datetime
