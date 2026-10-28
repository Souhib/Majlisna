from majlisna.api.schemas.shared import BaseModel


class TermScriptForms(BaseModel):
    """The Arabic forms of one term, as looked up for a game response."""

    ar: str
    ar_vocalized: str | None = None


class TermScriptEntry(TermScriptForms):
    """One term's Arabic forms, as written by the seed upsert."""

    term: str


class TermScriptUpsertResult(BaseModel):
    """What an upsert of term scripts changed."""

    inserted: int
    updated: int
    unchanged: int
