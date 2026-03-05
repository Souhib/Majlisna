from uuid import UUID, uuid4

from sqlmodel import Field, Relationship

from ipg.api.models.shared import DBModel
from ipg.api.schemas.shared import BaseTable


class CodenamesWordPack(BaseTable, table=True):
    """A themed pack of words for Codenames games (e.g., 'Islamic Terms', 'Prophets')."""

    __tablename__ = "codenames_word_pack"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None
    is_active: bool = Field(default=True)
    words: list["CodenamesWord"] = Relationship(back_populates="word_pack")


class CodenamesWord(BaseTable, table=True):
    """A single word belonging to a Codenames word pack."""

    __tablename__ = "codenames_word"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    word: str = Field(index=True)
    word_pack_id: UUID = Field(foreign_key="codenames_word_pack.id")
    word_pack: CodenamesWordPack | None = Relationship(back_populates="words")


class CodenamesWordPackCreate(DBModel):
    """Schema for creating a new word pack."""

    name: str
    description: str | None = None


class CodenamesWordCreate(DBModel):
    """Schema for adding a word to a pack."""

    word: str
