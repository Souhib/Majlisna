from datetime import datetime
from uuid import UUID

from pydantic import Field

from majlisna.api.schemas.common import GamePause, PlayerUnlockedAchievements
from majlisna.api.schemas.shared import BaseModel


class DescriptionRequest(BaseModel):
    word: str = Field(min_length=1, max_length=100)


class VoteRequest(BaseModel):
    voted_for: UUID


class NextRoundRequest(BaseModel):
    room_id: UUID


class UndercoverHintViewedRequest(BaseModel):
    word: str = Field(min_length=1, max_length=100)


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
    """The host's "next round", or a player's "I'm ready" (owner rule (d)).

    ``advanced`` says which: True when the next round opened (the host forced it, or
    this mark completed the quorum) — then ``turn_number`` and ``description_order``
    describe it; False when the call only marked the caller ready — then the ready
    fields describe the resolved round still waiting.
    """

    game_id: str
    advanced: bool
    turn_number: int | None = None
    description_order: list[DescriptionOrderEntry] = []
    # user_ids of the players asked (alive, not the host) who are ready, in arrival order.
    ready_players: list[str] = []
    ready_count: int = 0
    # How many are asked: the alive players but the host (all of them with no host).
    ready_quorum: int = 0


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


class MrWhiteGuessRecord(BaseModel):
    """What the eliminated Mr. White guessed: ``word`` is null when his time ran out."""

    word: str | None = None
    correct: bool


class VoteHistoryRound(BaseModel):
    round: int
    votes: list[VoteEntry]
    eliminated: EliminatedPlayer | None = None
    mr_white_guess: MrWhiteGuessRecord | None = None


class WordExplanations(BaseModel):
    civilian_word: str
    civilian_word_ar: str | None = None
    civilian_word_ar_vocalized: str | None = None
    civilian_word_hint: str | None
    undercover_word: str
    undercover_word_ar: str | None = None
    undercover_word_ar_vocalized: str | None = None
    undercover_word_hint: str | None


class MrWhiteGuessRequest(BaseModel):
    guess_word: str = Field(min_length=1, max_length=100)


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
    # Arabic forms of the caller's OWN word only (never the other side's), and
    # null for Mr. White and spectators, exactly like the hint.
    my_word_ar: str | None = None
    my_word_ar_vocalized: str | None = None
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
    round_resolved: bool = False
    # The ready quorum between rounds (owner rule (d)), filled only while the resolved
    # round waits for the next one; empty / 0 / False otherwise. Same meaning as in
    # StartNextRoundResponse; `is_ready` is the caller's own mark.
    ready_players: list[str] = []
    ready_count: int = 0
    ready_quorum: int = 0
    is_ready: bool = False
    description_order: list[DescriptionOrderEntry]
    current_describer_index: int
    descriptions: dict
    word_explanations: WordExplanations | None = None
    mr_white_guesser: str | None = None
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
