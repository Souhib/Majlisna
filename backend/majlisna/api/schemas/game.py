from datetime import datetime
from uuid import UUID

from majlisna.api.models.game import GameType
from majlisna.api.schemas.shared import BaseModel


class GameHistoryEntry(BaseModel):
    """A game history row for a user's game list."""

    id: UUID
    type: GameType
    start_time: datetime
    end_time: datetime | None
    number_of_players: int
    winner: str | None = None
    user_role: str | None = None
    user_won: bool | None = None
    game_status: str | None = None


class GameSummaryPlayer(BaseModel):
    """A player entry in a game summary."""

    user_id: str
    username: str
    role: str
    team: str | None = None


# --- Undercover vote history ---


class VoteHistoryEntry(BaseModel):
    """A single vote: voter → target."""

    voter: str
    target: str


class EliminatedInfo(BaseModel):
    """Info about a player eliminated in a round."""

    username: str
    role: str
    user_id: str | None = None


class VoteRound(BaseModel):
    """One round of voting in an Undercover game."""

    round: int
    votes: list[VoteHistoryEntry]
    eliminated: EliminatedInfo | None = None


# --- Codenames clue history ---


class ClueGuess(BaseModel):
    """A single guess made during a clue."""

    word: str
    word_ar: str | None = None
    word_ar_vocalized: str | None = None
    # The word's meaning in the summary's `lang` (the card's hint), or null.
    hint: str | None = None
    card_type: str
    correct: bool


class ClueHistoryEntry(BaseModel):
    """One clue + its guesses in a Codenames game."""

    team: str
    clue_word: str
    clue_number: int
    guesses: list[ClueGuess] = []


# --- Word explanations ---


class UndercoverWordExplanations(BaseModel):
    """Word pair used in an Undercover game."""

    civilian_word: str | None = None
    civilian_word_ar: str | None = None
    civilian_word_ar_vocalized: str | None = None
    # Each word's meaning in the summary's `lang` (shared fallback chain), or null.
    civilian_word_hint: str | None = None
    undercover_word: str | None = None
    undercover_word_ar: str | None = None
    undercover_word_ar_vocalized: str | None = None
    undercover_word_hint: str | None = None


class GameSummary(BaseModel):
    """Detailed game summary for the detail modal."""

    id: UUID
    type: GameType
    start_time: datetime
    end_time: datetime | None
    number_of_players: int
    winner: str | None = None
    game_status: str | None = None
    players: list[GameSummaryPlayer]
    vote_history: list[VoteRound] | None = None
    clue_history: list[ClueHistoryEntry] | None = None
    word_explanations: UndercoverWordExplanations | None = None
