from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.utils.draw import in_draw_order, pick_ids


class WordQuizController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, quiz_word: QuizWord) -> QuizWord:
        self.session.add(quiz_word)
        await self.session.commit()
        await self.session.refresh(quiz_word)
        return quiz_word

    async def delete(self, word_id: UUID) -> None:
        word = (await self.session.exec(select(QuizWord).where(QuizWord.id == word_id))).one()
        await self.session.delete(word)
        await self.session.commit()

    async def get_random_words(
        self, count: int, exclude_ids: list[str] | None = None, difficulty: str | None = None
    ) -> list[QuizWord]:
        """Draw `count` words, in drawn order, reading only the rows drawn.

        Excluded ids are skipped; a difficulty (None or "mixed" means all) narrows the
        draw when any word has it; too few left and the draw uses every word.
        """
        pool = (await self.session.exec(select(col(QuizWord.id), col(QuizWord.difficulty)))).all()
        drawn_ids = pick_ids(pool, count, exclude_ids, difficulty)
        if not drawn_ids:
            return []
        rows = (await self.session.exec(select(QuizWord).where(col(QuizWord.id).in_(drawn_ids)))).all()
        return in_draw_order(rows, drawn_ids)
