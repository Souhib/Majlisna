import random
from collections.abc import Sequence
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import CACHE_TTL_GAME_CONTENT_SECONDS
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.utils.cache import cache

QUIZ_WORDS_CACHE_KEY = "wordquiz:words"


class WordQuizController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[QuizWord]:
        cached = cache.get(QUIZ_WORDS_CACHE_KEY)
        if cached is not None:
            return cached  # type: ignore[return-value]
        words = (await self.session.exec(select(QuizWord))).all()
        cache.set(QUIZ_WORDS_CACHE_KEY, words, CACHE_TTL_GAME_CONTENT_SECONDS)
        return words

    async def create(self, quiz_word: QuizWord) -> QuizWord:
        self.session.add(quiz_word)
        await self.session.commit()
        await self.session.refresh(quiz_word)
        cache.invalidate(QUIZ_WORDS_CACHE_KEY)
        return quiz_word

    async def delete(self, word_id: UUID) -> None:
        word = (await self.session.exec(select(QuizWord).where(QuizWord.id == word_id))).one()
        await self.session.delete(word)
        await self.session.commit()
        cache.invalidate(QUIZ_WORDS_CACHE_KEY)

    async def get_random_words(
        self, count: int, exclude_ids: list[str] | None = None, difficulty: str | None = None
    ) -> list[QuizWord]:
        all_words = (await self.session.exec(select(QuizWord))).all()
        available = [w for w in all_words if not exclude_ids or str(w.id) not in exclude_ids]
        # Filter by difficulty if specified (None or "mixed" means all difficulties)
        if difficulty and difficulty != "mixed":
            filtered = [w for w in available if w.difficulty == difficulty]
            if filtered:
                available = filtered
        if len(available) < count:
            available = list(all_words)
        return random.sample(list(available), min(count, len(available)))
