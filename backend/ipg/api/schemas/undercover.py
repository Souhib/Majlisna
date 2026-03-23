from uuid import UUID

from ipg.api.schemas.shared import BaseModel


class DescriptionRequest(BaseModel):
    word: str


class VoteRequest(BaseModel):
    voted_for: UUID


class NextRoundRequest(BaseModel):
    room_id: UUID


class UndercoverHintViewedRequest(BaseModel):
    word: str


class DescriptionOrderEntry(BaseModel):
    user_id: str
    username: str


class SubmitDescriptionResponse(BaseModel):
    game_id: str
    all_described: bool
    word: str


class SubmitVoteResponse(BaseModel):
    game_id: str
    all_voted: bool
    eliminated_player: str | None = None
    eliminated_player_role: str | None = None
    eliminated_player_username: str | None = None
    number_of_votes: int | None = None
    winner: str | None = None


class StartNextRoundResponse(BaseModel):
    game_id: str
    turn_number: int
    description_order: list[DescriptionOrderEntry]


class UndercoverPlayerState(BaseModel):
    user_id: str
    username: str
    is_alive: bool
    is_mayor: bool


class EliminatedPlayer(BaseModel):
    user_id: str
    username: str
    role: str


class VoteEntry(BaseModel):
    voter: str
    voter_id: str
    target: str
    target_id: str


class VoteHistoryRound(BaseModel):
    round: int
    votes: list[VoteEntry]
    eliminated: EliminatedPlayer | None = None


class WordExplanations(BaseModel):
    civilian_word: str
    civilian_word_hint: str | None
    undercover_word: str
    undercover_word_hint: str | None


class MrWhiteGuessRequest(BaseModel):
    guess_word: str


class MrWhiteGuessResponse(BaseModel):
    game_id: str
    correct: bool
    winner: str | None = None


class UndercoverTimerConfig(BaseModel):
    description_seconds: int
    voting_seconds: int


class UndercoverGameState(BaseModel):
    game_id: str
    room_id: str
    is_host: bool
    is_spectator: bool = False
    my_role: str
    my_word: str
    my_word_hint: str | None
    is_alive: bool
    players: list[UndercoverPlayerState]
    eliminated_players: list[EliminatedPlayer]
    turn_number: int
    winner: str | None
    vote_history: list[VoteHistoryRound]
    timer_config: UndercoverTimerConfig | None = None
    timer_started_at: str | None = None
    votes: dict
    has_voted: bool
    turn_phase: str
    description_order: list[DescriptionOrderEntry]
    current_describer_index: int
    descriptions: dict
    word_explanations: WordExplanations | None = None
    mr_white_guesser: str | None = None
