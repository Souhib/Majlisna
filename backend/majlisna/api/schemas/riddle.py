from uuid import UUID

from majlisna.api.schemas.shared import BaseModel
from majlisna.api.schemas.wordquiz import WordQuizCategory


class RoomRiddleAnswer(BaseModel):
    """The riddle's answer, as the notebook shows a Kalimat word. The client keeps it back
    until the game starts, or until the player asks for it."""

    # The word as Kalimat shows it in `lang`: word_fr / word_ar / word_en.
    word_display: str
    word_ar: str | None
    # With harakat; null when not certain (most quiz words): show `word_ar` then.
    word_ar_vocalized: str | None


class RoomRiddle(BaseModel):
    """A samar riddle for a table that waits: the vaguest rung of a Kalimat word.

    Existing content only: the rung and the answer are the word's own, never written
    for the riddle. Never today's word of the day, nor a recent one, nor an answer of
    the room's running quiz.
    """

    # The word's id: what tells one riddle from the next on the client.
    id: UUID
    # The word's theme, so the client asks "who is it?", "where is it?" or "what is it?".
    category: WordQuizCategory | None
    # Rung 1 of the word's ladder, in `lang`.
    hint: str
    answer: RoomRiddleAnswer
