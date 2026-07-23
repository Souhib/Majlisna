from uuid import UUID

from pydantic import Field

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
