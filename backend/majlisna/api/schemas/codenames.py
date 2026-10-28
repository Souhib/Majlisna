from datetime import datetime
from uuid import UUID

from pydantic import Field

from majlisna.api.schemas.common import GamePause, PlayerUnlockedAchievements
from majlisna.api.schemas.shared import BaseModel


class StartCodenamesRequest(BaseModel):
    word_pack_ids: list[UUID] | None = None


class GiveClueRequest(BaseModel):
    clue_word: str = Field(min_length=1, max_length=50)
    clue_number: int = Field(ge=0, le=25)


class GuessCardRequest(BaseModel):
    card_index: int


class CodenamesHintViewedRequest(BaseModel):
    word: str = Field(min_length=1, max_length=100)


class GiveClueResponse(BaseModel):
    game_id: str
    clue_word: str
    clue_number: int


class GuessCardResponse(BaseModel):
    game_id: str
    card_index: int | None = None
    card_type: str | None = None
    result: str | None = None
    all_voted: bool | None = None
    vote_changed: bool | None = None
    tied: bool | None = None
    card_votes_count: int | None = None
    total_operatives: int | None = None


class EndTurnResponse(BaseModel):
    game_id: str
    current_team: str


class CodenamesCardView(BaseModel):
    index: int
    word: str
    # Arabic script of `word` (see TermScript). The Latin is on every card for
    # everyone, so this reveals nothing the board does not already show.
    word_ar: str | None = None
    # The same word with harakat. The bare form is ambiguous (أحد = Uhud or "one",
    # ثور, الملك, كلام); null when the vocalisation is not certain.
    word_ar_vocalized: str | None = None
    revealed: bool
    card_type: str | None = None
    hint: str | None = None


class CodenamesPlayerView(BaseModel):
    user_id: str
    username: str
    team: str
    role: str


class CodenamesClueGuess(BaseModel):
    word: str
    word_ar: str | None = None
    word_ar_vocalized: str | None = None
    card_type: str
    correct: bool


class CodenamesClueHistoryEntry(BaseModel):
    team: str
    clue_word: str
    clue_number: int
    guesses: list[CodenamesClueGuess]


class CodenamesTurnState(BaseModel):
    team: str
    clue_word: str | None = None
    clue_number: int
    guesses_made: int
    max_guesses: int
    card_votes: dict


class CodenamesTimerConfig(BaseModel):
    clue_seconds: int
    guess_seconds: int


class CodenamesBoardState(BaseModel):
    game_id: str
    room_id: str
    team: str
    role: str
    is_host: bool
    is_spectator: bool = False
    board: list[CodenamesCardView]
    current_team: str
    red_remaining: int
    blue_remaining: int
    status: str
    current_turn: CodenamesTurnState
    winner: str | None
    clue_history: list[CodenamesClueHistoryEntry]
    timer_config: CodenamesTimerConfig | None = None
    timer_started_at: str | None = None
    players: list[CodenamesPlayerView]
    newly_unlocked_achievements: list[PlayerUnlockedAchievements] | None = None
    # Set while the host has paused the game for the prayer; null otherwise.
    paused: GamePause | None = None
    # Whether pause / resume would accept THIS caller right now — the server's own
    # rule, so the UI shows the button exactly when the request would succeed.
    can_pause: bool = False
    can_resume: bool = False
    # The game-over colophon (see schemas/common.GameColophon): who hosted, and when
    # the game started and ended (UTC). `ended_at` is null while it runs.
    host_username: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
