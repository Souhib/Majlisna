from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, Column, Index, UniqueConstraint
from sqlmodel import Field

from majlisna.api.constants import DAILY_WORD_INITIAL_HINTS, DAILY_WORD_PLAY_UNIQUE_COLUMNS
from majlisna.api.schemas.shared import BaseTable

# The word of the day (Kalimat al-yawm, كلمة اليوم). Two tables of their own: there are
# no migrations, and `create_all` creates a missing table but never ALTERs one.


class DailyWord(BaseTable, table=True):
    """The QuizWord of one Makkah day — the same for everyone.

    Drawn lazily by the first request of the day, with ``INSERT … ON CONFLICT DO
    NOTHING`` on ``day`` and a re-read, so two first requests racing agree on the word.
    """

    __tablename__ = "daily_word"

    # The Makkah calendar day (utils/daily_word.makkah_day), not a UTC one.
    day: date = Field(primary_key=True)
    quiz_word_id: UUID = Field(foreign_key="quiz_word.id", index=True)


class DailyWordPlay(BaseTable, table=True):
    """One player's go at one day's word: one row per (user, day).

    Created on the player's first hint, guess or give-up (viewing hint 1 writes
    nothing), with the same race-safe insert. A play is finished once ``solved_at`` is
    set or ``gave_up`` is true; nothing changes it after that.
    """

    __tablename__ = "daily_word_play"
    __table_args__ = (
        UniqueConstraint(*DAILY_WORD_PLAY_UNIQUE_COLUMNS, name="uq_daily_word_play_user_day"),
        # "N players found it today": one day's rows.
        Index("ix_daily_word_play_day", "day"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    day: date = Field(foreign_key="daily_word.day")
    # The rungs of the ladder this player has seen (1..max_hints).
    hints_revealed: int = DAILY_WORD_INITIAL_HINTS
    # Every guess counted; the latest one, and the most recent DAILY_WORD_GUESSES_KEPT.
    attempts: int = 0
    last_guess: str | None = None
    guesses: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # UTC-aware: serialised to the client, where a naive timestamp reads as local time.
    solved_at: datetime | None = Field(
        default=None,
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
    )
    gave_up: bool = False
    # max_hints - hints_revealed + 1 when solved, 0 on a give-up, null while playing.
    score: int | None = None
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
    )
