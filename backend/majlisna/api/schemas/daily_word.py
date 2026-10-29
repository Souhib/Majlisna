from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from majlisna.api.constants import DAILY_WORD_ANSWER_MAX_LENGTH
from majlisna.api.schemas.shared import BaseModel
from majlisna.api.schemas.wordquiz import WordQuizCategory


class DailyWordStatus(StrEnum):
    """Where the caller stands with today's word. Anonymous callers are always not_started."""

    NOT_STARTED = "not_started"
    PLAYING = "playing"
    SOLVED = "solved"
    GAVE_UP = "gave_up"


class DailyWordAnswer(BaseModel):
    """The word itself — sent once, and only once, the caller has finished (solved or gave up)."""

    # The word as Kalimat shows it in `lang`: word_fr / word_ar / word_en.
    word_display: str
    word_ar: str | None
    # With harakat; null when not certain (most quiz words): show `word_ar` then.
    word_ar_vocalized: str | None
    # What the word means in `lang` (QuizWord.explanation, else the last rung).
    explanation: str | None
    # Whether the caller's notebook already holds it, and that entry (to un-keep it).
    kept: bool
    entry_id: UUID | None


class DailyWordState(BaseModel):
    """Today's word of the day, as the caller may see it.

    Before the caller has finished, nothing here names the word: `hints` is the
    revealed PREFIX of the ladder only, and `answer` is null. Every field is always
    sent (null where it does not apply).
    """

    # The Makkah calendar day, and its number (#1 on the epoch).
    day: date
    number: int
    # The word's theme (constants.WORD_QUIZ_CATEGORY_KEYS); null for one outside the map.
    category: WordQuizCategory | None
    # The ladder's length (6 for every seeded word), and the rungs revealed so far, in `lang`.
    max_hints: int
    hints: list[str]
    hints_revealed: int
    status: DailyWordStatus
    attempts: int
    # The caller's most recent tries, oldest first (a solved play ends with the right one).
    guesses: list[str]
    # max_hints - hints_revealed + 1 once solved, 0 once given up, null before.
    score: int | None
    # Consecutive Makkah days solved ending today (or yesterday while today is open);
    # null for an anonymous caller.
    streak: int | None
    best_streak: int | None
    # How many players have found today's word.
    solvers_today: int
    # When the next word comes out: the next midnight in Makkah, as a UTC instant.
    next_day_at: datetime
    answer: DailyWordAnswer | None


class DailyWordGuessRequest(BaseModel):
    """A guess at today's word, in any language or script."""

    answer: str = Field(min_length=1, max_length=DAILY_WORD_ANSWER_MAX_LENGTH)


class DailyWordGuessResponse(BaseModel):
    """Whether the guess found the word, and the caller's state after it."""

    correct: bool
    state: DailyWordState
