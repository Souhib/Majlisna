from uuid import UUID, uuid4

from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class TermScript(BaseTable, table=True):
    """The Arabic-script forms of a game term, keyed by its exact Latin spelling.

    One row per distinct term across Undercover (``Word.word``) and Codenames
    (``CodenamesWord.word``). It is a table of its own, not columns on those two,
    because it was added when ``create_all`` was the schema, which never ALTERs an
    existing table (in the baseline migration since).
    """

    __tablename__ = "term_script"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # The exact string stored in Word.word / CodenamesWord.word — the join key.
    term: str = Field(index=True, unique=True)
    # As normally written, no harakat ("صبر", "الفاتحة").
    ar: str
    # Fully or conventionally vocalised ("صَبْر"); null when not certain.
    ar_vocalized: str | None = None
