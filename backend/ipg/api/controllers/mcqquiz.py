import random
from collections.abc import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.mcqquiz import McqQuestion
from ipg.api.utils.cache import cache

MCQ_QUESTIONS_CACHE_KEY = "mcqquiz:questions"
CACHE_TTL_SECONDS = 3600


class McqQuizController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[McqQuestion]:
        cached = cache.get(MCQ_QUESTIONS_CACHE_KEY)
        if cached is not None:
            return cached  # type: ignore[return-value]
        questions = (await self.session.exec(select(McqQuestion))).all()
        cache.set(MCQ_QUESTIONS_CACHE_KEY, questions, CACHE_TTL_SECONDS)
        return questions

    async def get_random_questions(self, count: int, exclude_ids: list[str] | None = None) -> list[McqQuestion]:
        all_questions = (await self.session.exec(select(McqQuestion))).all()
        available = [q for q in all_questions if not exclude_ids or str(q.id) not in exclude_ids]
        if len(available) < count:
            available = list(all_questions)
        return random.sample(list(available), min(count, len(available)))
