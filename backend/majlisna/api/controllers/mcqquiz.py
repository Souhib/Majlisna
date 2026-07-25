from collections.abc import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import CACHE_TTL_GAME_CONTENT_SECONDS
from majlisna.api.models.mcqquiz import McqQuestion
from majlisna.api.utils.cache import cache
from majlisna.api.utils.rng import rng

MCQ_QUESTIONS_CACHE_KEY = "mcqquiz:questions"


class McqQuizController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[McqQuestion]:
        cached = cache.get(MCQ_QUESTIONS_CACHE_KEY)
        if cached is not None:
            return cached  # type: ignore[return-value]
        questions = (await self.session.exec(select(McqQuestion))).all()
        cache.set(MCQ_QUESTIONS_CACHE_KEY, questions, CACHE_TTL_GAME_CONTENT_SECONDS)
        return questions

    async def get_random_questions(
        self, count: int, exclude_ids: list[str] | None = None, difficulty: str | None = None
    ) -> list[McqQuestion]:
        all_questions = (await self.session.exec(select(McqQuestion))).all()
        available = [q for q in all_questions if not exclude_ids or str(q.id) not in exclude_ids]
        # Filter by difficulty if specified (None or "mixed" means all difficulties)
        if difficulty and difficulty != "mixed":
            filtered = [q for q in available if q.difficulty == difficulty]
            if filtered:
                available = filtered
        if len(available) < count:
            available = list(all_questions)
        return rng.sample(list(available), min(count, len(available)))
