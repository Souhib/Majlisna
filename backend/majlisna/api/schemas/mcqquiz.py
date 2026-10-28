from datetime import datetime

from majlisna.api.schemas.common import GamePause, PlayerUnlockedAchievements
from majlisna.api.schemas.shared import BaseModel


class McqSubmitAnswerRequest(BaseModel):
    choice_index: int


class McqSubmitAnswerResponse(BaseModel):
    correct: bool
    points_earned: int


class McqQuizPlayerState(BaseModel):
    user_id: str
    username: str
    # While a question is open this is the score BEFORE the round (its points are
    # withheld until the reveal) — points are earned at lock-in, so a live total told
    # the table who had been right. From the results phase on it includes the round.
    total_score: int
    current_round_answered: bool
    # 0 for everyone while the question is open; the round's points from the reveal on.
    current_round_points: int


class McqQuizRoundResult(BaseModel):
    user_id: str
    username: str
    chose_correct: bool
    points: int
    # Which choice they locked in (0-3), null if they did not answer — public once the
    # round has resolved, like every other part of the reveal.
    choice_index: int | None = None
    # How long after the question opened they locked in, in ms (null if no answer).
    answer_time_ms: int | None = None


class McqQuizGameState(BaseModel):
    game_id: str
    room_id: str
    is_host: bool
    is_spectator: bool = False
    current_round: int
    total_rounds: int
    round_phase: str  # "playing" | "results" | "game_over"
    question: str
    difficulty: str | None = None  # "easy" | "medium" | "hard"
    choices: list[str]  # 4 items resolved to lang
    correct_answer_index: int | None = None  # only in results/game_over
    explanation: str | None = None  # only in results/game_over
    turn_duration_seconds: int
    round_started_at: str | None = None
    players: list[McqQuizPlayerState]
    my_answered: bool
    # 0 while the question is open (withheld like everyone's); the round's points after.
    my_points: int
    round_results: list[McqQuizRoundResult]
    # The reveal, from the server so it survives a reload. All null while the question
    # is open; set in the results and game_over phases.
    # How many players locked in each choice, indexed like `choices` (always 4 long).
    choice_tallies: list[int] | None = None
    # The caller's own choice (0-3) and how long they took, in ms; null if they did
    # not answer (or are a spectator).
    my_choice_index: int | None = None
    my_answer_time_ms: int | None = None
    winner: str | None = None
    leaderboard: list[McqQuizPlayerState]
    game_over: bool
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
    # The game-over colophon (see schemas/common.py for the shared rule): who hosted,
    # and when the game started and ended (UTC). `ended_at` is null while it runs.
    host_username: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
