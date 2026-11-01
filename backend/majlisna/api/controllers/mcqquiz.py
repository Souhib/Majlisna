from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.mcqquiz import McqQuestion
from majlisna.api.utils.draw import in_draw_order, pick_ids


class McqQuizController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_random_questions(
        self, count: int, exclude_ids: list[str] | None = None, difficulty: str | None = None
    ) -> list[McqQuestion]:
        """Draw `count` questions, in round order, reading only the rows drawn.

        Excluded ids are skipped; a difficulty (None or "mixed" means all) narrows the
        draw when any question has it; too few left and the draw uses every question.
        """
        pool = (await self.session.exec(select(col(McqQuestion.id), col(McqQuestion.difficulty)))).all()
        drawn_ids = pick_ids(pool, count, exclude_ids, difficulty)
        if not drawn_ids:
            return []
        rows = (await self.session.exec(select(McqQuestion).where(col(McqQuestion.id).in_(drawn_ids)))).all()
        return in_draw_order(rows, drawn_ids)
