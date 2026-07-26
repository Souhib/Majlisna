from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class QuizWord(BaseTable, table=True):
    __tablename__ = "quiz_word"

    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    word_en: str = Field(index=True)
    word_ar: str | None = None
    word_fr: str | None = None
    accepted_answers: dict | None = Field(default=None, sa_column=Column(JSON))
    # {"en": ["Ibrahim", "Abraham"], "ar": ["إبراهيم", "ابراهيم"], "fr": [...]}
    category: str
    difficulty: str = Field(default="medium", index=True)  # "easy" | "medium" | "hard"
    hints: dict = Field(sa_column=Column(JSON))
    # {"1": {"en": "...", "ar": "...", "fr": "..."}, ..., "6": {...}}
    explanation: dict | None = Field(default=None, sa_column=Column(JSON))
    # {"en": "...", "ar": "...", "fr": "..."}
