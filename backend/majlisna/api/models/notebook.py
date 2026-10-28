from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Index, UniqueConstraint
from sqlmodel import Field

from majlisna.api.constants import NOTEBOOK_UNIQUE_COLUMNS
from majlisna.api.models.game import GameType
from majlisna.api.schemas.shared import BaseTable


class NotebookGameType(StrEnum):
    """The games whose words can be kept. Values match ``GameType``; MCQ has none."""

    UNDERCOVER = GameType.UNDERCOVER.value
    CODENAMES = GameType.CODENAMES.value
    WORD_QUIZ = GameType.WORD_QUIZ.value


class NotebookEntry(BaseTable, table=True):
    """One word a player kept from a finished game — a line of their Kunnash (كُنّاش).

    A table of its own, like ``TermScript``: there are no migrations, and
    ``create_all`` creates a missing table but never ALTERs an existing one.

    ``term`` is the Latin key exactly as the game stored it (``Word.word``,
    ``CodenamesWord.word``, ``QuizWord.word_en``); the Arabic forms and the hint are
    resolved at read time from ``term_script`` and the content tables, so fixing a
    spelling there fixes every notebook.
    """

    __tablename__ = "notebook_entry"
    __table_args__ = (
        # Keeping a word twice is a no-op: the keep endpoints insert with
        # ON CONFLICT DO NOTHING on exactly these columns.
        UniqueConstraint(*NOTEBOOK_UNIQUE_COLUMNS, name="uq_notebook_entry_user_type_term"),
        # The listing: one user's entries, newest first.
        Index("ix_notebook_entry_user_kept_at", "user_id", "kept_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    term: str
    game_type: NotebookGameType
    # The game the word was first kept from. Kept on a re-keep from another game.
    source_game_id: UUID | None = Field(default=None, foreign_key="game.id")
    # UTC-aware: serialised to the client, where a naive timestamp reads as local time.
    kept_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
    )
