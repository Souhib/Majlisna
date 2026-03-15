from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field

from ipg.api.schemas.shared import BaseTable


class McqQuestion(BaseTable, table=True):
    __tablename__ = "mcq_question"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, unique=True)
    question_en: str = Field(index=True)
    question_ar: str | None = None
    question_fr: str | None = None
    choices: dict = Field(sa_column=Column(JSON))
    # {"0": {"en": "...", "ar": "...", "fr": "..."}, "1": {...}, "2": {...}, "3": {...}}
    correct_answer_index: int
    explanation: dict | None = Field(default=None, sa_column=Column(JSON))
    # {"en": "...", "ar": "...", "fr": "..."}
    category: str
