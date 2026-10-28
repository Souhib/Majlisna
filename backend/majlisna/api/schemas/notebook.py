from datetime import datetime
from uuid import UUID

from pydantic import Field

from majlisna.api.constants import NOTEBOOK_TERM_MAX_LENGTH
from majlisna.api.models.notebook import NotebookGameType
from majlisna.api.schemas.shared import BaseModel

# Field names follow the other word-bearing schemas (CodenamesCardView,
# CodenamesClueGuess, ClueGuess, UndercoverGameState.my_word_*): `word`, `word_ar`,
# `word_ar_vocalized`, so one word chip can render a card, a guess and a kept word.


class KeepWordRequest(BaseModel):
    """Keep one word from a finished game."""

    game_id: UUID
    # The word as the game showed it: the Latin key for Undercover and Codenames,
    # any of the word's three spellings for Word Quiz. Checked against the game.
    word: str = Field(min_length=1, max_length=NOTEBOOK_TERM_MAX_LENGTH)


class NotebookEntryView(BaseModel):
    """A kept word, resolved for display in the requested language."""

    id: UUID
    # The key as the game stored it (Word.word / CodenamesWord.word / QuizWord.word_en).
    word: str
    # The word as the game showed it in the requested language: the Latin key for
    # Undercover and Codenames, word_fr / word_ar / word_en for Word Quiz.
    word_display: str
    game_type: NotebookGameType
    # Arabic script: term_script for Undercover and Codenames; a Word Quiz word's own
    # `word_ar` (the Arabic its game showed), term_script as a fallback.
    word_ar: str | None = None
    # With harakat; null when not certain — and always null for Word Quiz words,
    # which have no vocalised form: show `word_ar` then.
    word_ar_vocalized: str | None = None
    # What the word means, in the requested language when the content has it.
    hint: str | None = None
    source_game_id: UUID | None = None
    kept_at: datetime


class NotebookKeepResponse(BaseModel):
    """The outcome of keeping words: what was new, what was already there."""

    added: int
    already_kept: int
    # Every word this call asked for, kept now or before, in the game's order.
    entries: list[NotebookEntryView]


class NotebookPage(BaseModel):
    """One page of the caller's notebook, newest first."""

    entries: list[NotebookEntryView]
    # Every entry of the caller's notebook, not just this page.
    total: int
    # Pass back as `cursor` for the next page; null on the last page. Opaque.
    next_cursor: str | None = None


class NotebookGameWord(BaseModel):
    """One word a finished game dealt, as the game-over colophon lists it."""

    word: str
    word_display: str
    word_ar: str | None = None
    word_ar_vocalized: str | None = None
    hint: str | None = None
    # Whether the caller's notebook already holds this word (from this game or another).
    kept: bool
    # That entry, for un-keeping it (DELETE /notebook/entries/{entry_id}); null when not kept.
    entry_id: UUID | None = None


class NotebookGameWords(BaseModel):
    """Every word of a finished game, in the order it dealt them, with what is kept."""

    game_id: UUID
    game_type: NotebookGameType
    words: list[NotebookGameWord]


class NotebookWordForms(BaseModel):
    """How one kept word reads for display (internal)."""

    word_display: str
    word_ar: str | None = None
    word_ar_vocalized: str | None = None
    hint: str | None = None


class NotebookContentDetails(BaseModel):
    """What a content table says about one kept word (internal, never returned as is)."""

    # Only a Word Quiz word carries its own Arabic (`QuizWord.word_ar`) and its own
    # spelling per language; the other two games' Arabic lives in term_script.
    word_ar: str | None = None
    word_display: str | None = None
    hint: str | None = None
