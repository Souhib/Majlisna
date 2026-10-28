from datetime import datetime
from enum import StrEnum

from pydantic import Field

from majlisna.api.schemas.common import GamePause, PlayerUnlockedAchievements
from majlisna.api.schemas.shared import BaseModel


class TrilingualText(BaseModel):
    """A text value in English, Arabic, and French."""

    en: str
    ar: str = ""
    fr: str = ""


class TrilingualAnswers(BaseModel):
    """Accepted answers per language."""

    en: list[str] = []
    ar: list[str] = []
    fr: list[str] = []


class QuizWordCreate(BaseModel):
    word_en: str
    word_ar: str | None = None
    word_fr: str | None = None
    accepted_answers: TrilingualAnswers | None = None
    category: str
    hints: dict[str, TrilingualText]
    explanation: TrilingualText | None = None


class WordQuizCategory(StrEnum):
    """The theme of a Word Quiz word, as a stable key the client translates.

    ``QuizWord.category`` is the stored English label ("Islamic History"); its key
    comes from ``constants.WORD_QUIZ_CATEGORY_KEYS``. A theme, not a kind: "Islamic
    History" holds battles and scholars alike, so the client words it ("a prophet",
    "a place", "from the Qur'an"…) per key.
    """

    PROPHETS = "prophets"
    COMPANIONS = "companions"
    PLACES = "places"
    QURAN = "quran"
    ISLAMIC_HISTORY = "islamic_history"
    ISLAMIC_CONCEPTS = "islamic_concepts"
    DAILY_LIFE = "daily_life"


class SubmitAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=100)


class SubmitAnswerResponse(BaseModel):
    correct: bool
    points_earned: int
    hint_number: int


class WordQuizPlayerState(BaseModel):
    user_id: str
    username: str
    total_score: int
    current_round_answered: bool
    current_round_points: int
    answered_at_hint: int | None = None


class WordQuizRoundResult(BaseModel):
    user_id: str
    username: str
    # The hint (1-6) on screen when they found it; null if they did not.
    answered_at_hint: int | None
    points: int
    answer_time_ms: int | None = None
    # What they typed, as typed (trimmed): the answer that found the word, else their
    # last wrong try, else null. Only ever sent once the round has resolved — a
    # correct one IS the answer.
    typed_answer: str | None = None
    # How many answers they submitted this round (wrong tries included).
    attempts: int = 0


class WordQuizTimerConfig(BaseModel):
    turn_duration_seconds: int
    hint_interval_seconds: int


class WordQuizGameState(BaseModel):
    game_id: str
    room_id: str
    is_host: bool
    is_spectator: bool = False
    current_round: int
    total_rounds: int
    round_phase: str  # "playing" | "results" | "game_over"
    hints_revealed: int
    # Only the hints released so far — NEVER the whole ladder. Scoring is
    # `max_hints - hint_number + 1`, so shipping all six at round start let
    # anyone reading the network tab answer from the most specific hint at t=0
    # and take full marks while honest players waited. See
    # WordQuizGameController._resolve_hints.
    hints: list[str]
    # Sent explicitly because `hints` is now a prefix: the client can no longer
    # infer the ladder length from it, and "hint 2/6" must not read "2/2".
    max_hints: int
    difficulty: str | None = None  # "easy" | "medium" | "hard"
    # The current word's theme (shown during play: "Round 3 of 7 · a prophet"); null
    # for a category outside WordQuizCategory or a game started before it was stored.
    category: WordQuizCategory | None = None
    turn_duration_seconds: int
    hint_interval_seconds: int
    round_started_at: str | None = None
    players: list[WordQuizPlayerState]
    my_answered: bool
    my_points: int
    round_results: list[WordQuizRoundResult]
    correct_answer: str | None = None
    explanation: str | None = None
    winner: str | None = None
    leaderboard: list[WordQuizPlayerState]
    game_over: bool
    timer_config: WordQuizTimerConfig | None = None
    ready_players: list[str] = []
    ready_count: int = 0
    total_players: int = 0
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
