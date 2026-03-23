from ipg.api.schemas.shared import BaseModel


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


class SubmitAnswerRequest(BaseModel):
    answer: str


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
    answered_at_hint: int | None
    points: int
    answer_time_ms: int | None = None


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
    hints: list[str]
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
