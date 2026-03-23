from ipg.api.schemas.shared import BaseModel


class McqSubmitAnswerRequest(BaseModel):
    choice_index: int


class McqSubmitAnswerResponse(BaseModel):
    correct: bool
    points_earned: int


class McqQuizPlayerState(BaseModel):
    user_id: str
    username: str
    total_score: int
    current_round_answered: bool
    current_round_points: int


class McqQuizRoundResult(BaseModel):
    user_id: str
    username: str
    chose_correct: bool
    points: int


class McqQuizGameState(BaseModel):
    game_id: str
    room_id: str
    is_host: bool
    is_spectator: bool = False
    current_round: int
    total_rounds: int
    round_phase: str  # "playing" | "results" | "game_over"
    question: str
    choices: list[str]  # 4 items resolved to lang
    correct_answer_index: int | None = None  # only in results/game_over
    explanation: str | None = None  # only in results/game_over
    turn_duration_seconds: int
    round_started_at: str | None = None
    players: list[McqQuizPlayerState]
    my_answered: bool
    my_points: int
    round_results: list[McqQuizRoundResult]
    winner: str | None = None
    leaderboard: list[McqQuizPlayerState]
    game_over: bool
    ready_players: list[str] = []
    ready_count: int = 0
    total_players: int = 0
