"""WP-24: the MCQ draw reads ids first, then only the questions it keeps.

`get_random_questions` used to load and hydrate every question (609 rows, 925 kB in
production) on every MCQ start to keep ten.
"""

from types import TracebackType
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import event
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.mcqquiz import McqQuizController
from majlisna.api.models.mcqquiz import McqQuestion
from majlisna.api.utils.rng import rng


class DrawProbe:
    """Watches a draw: the McqQuestion rows it hydrates and the SQL it sends.

    Rows already in the session's identity map are not hydrated again, so expunge
    the session before entering the probe.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._engine = session.bind.sync_engine
        self.hydrated_ids: list[UUID] = []
        self.statements: list[str] = []

    def __enter__(self) -> "DrawProbe":
        event.listen(McqQuestion, "load", self._on_load)
        event.listen(self._engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        event.remove(McqQuestion, "load", self._on_load)
        event.remove(self._engine, "before_cursor_execute", self._on_execute)

    def _on_load(self, target: McqQuestion, context: object) -> None:
        self.hydrated_ids.append(target.id)

    def _on_execute(self, conn, cursor, statement: str, parameters, context, executemany) -> None:  # noqa: ARG002
        self.statements.append(statement)

    def payload_reads(self) -> list[str]:
        """The statements that read a question's choices, i.e. its full row."""
        return [s for s in self.statements if "mcq_question.choices" in s]


class RecordingSample:
    """A deterministic stand-in for rng.sample (the last k, last first) that keeps its draw."""

    def __init__(self) -> None:
        self.drawn: list = []

    def __call__(self, population, k: int) -> list:
        self.drawn = list(reversed(list(population)))[:k]
        return list(self.drawn)

    def drawn_ids(self) -> list:
        """The drawn ids, whether the draw was made over rows, id rows or bare ids."""
        return [getattr(item, "id", item) for item in self.drawn]


async def add_questions(session: AsyncSession, difficulties: list[str]) -> list[McqQuestion]:
    """One question per difficulty given, committed."""
    questions = [
        McqQuestion(
            question_en=f"Question {i}?",
            choices={str(c): {"en": f"Choice {c}"} for c in range(4)},
            correct_answer_index=0,
            explanation={"en": f"Because {i}."},
            category="Pillars of Islam",
            difficulty=difficulty,
        )
        for i, difficulty in enumerate(difficulties)
    ]
    session.add_all(questions)
    await session.commit()
    return questions


async def test_draw_of_n_hydrates_only_the_n_drawn_questions(session: AsyncSession):
    """A draw of n returns n distinct questions and reads at most n full rows."""
    # Prepare
    await add_questions(session, ["medium"] * 9)
    session.expunge_all()
    controller = McqQuizController(session)

    # Act
    with DrawProbe(session) as probe:
        result = await controller.get_random_questions(3)

    # Assert
    assert len(result) == 3
    assert len({q.id for q in result}) == 3
    assert len(probe.hydrated_ids) <= 3
    assert probe.payload_reads()
    for statement in probe.payload_reads():
        assert "WHERE mcq_question.id IN" in statement, statement


async def test_draw_returns_questions_in_draw_order(session: AsyncSession):
    """The questions are the rounds, in order: they follow the draw, not the database."""
    # Prepare
    await add_questions(session, ["medium"] * 6)
    session.expunge_all()
    controller = McqQuizController(session)
    sample = RecordingSample()

    # Act
    with patch.object(rng, "sample", side_effect=sample):
        result = await controller.get_random_questions(5)

    # Assert
    assert [q.id for q in result] == sample.drawn_ids()


async def test_draw_keeps_the_difficulty_filter(session: AsyncSession):
    """A difficulty with enough questions draws only from it; "mixed" draws from all."""
    # Prepare
    await add_questions(session, ["easy"] * 4 + ["hard"] * 4)
    controller = McqQuizController(session)

    # Act
    hard_draw = await controller.get_random_questions(3, difficulty="hard")
    mixed_draw = await controller.get_random_questions(8, difficulty="mixed")

    # Assert
    assert {q.difficulty for q in hard_draw} == {"hard"}
    assert len(mixed_draw) == 8


async def test_draw_skips_excluded_questions(session: AsyncSession):
    """Excluded ids are never drawn while enough others remain."""
    # Prepare
    questions = await add_questions(session, ["medium"] * 5)
    excluded = {str(q.id) for q in questions[:2]}
    controller = McqQuizController(session)

    # Act
    result = await controller.get_random_questions(3, exclude_ids=list(excluded))

    # Assert
    assert len(result) == 3
    assert not {str(q.id) for q in result} & excluded


async def test_draw_falls_back_to_every_question_when_too_few_match(session: AsyncSession):
    """Too few questions left after the filters: the draw uses the whole set."""
    # Prepare
    questions = await add_questions(session, ["easy", "easy", "hard"])
    controller = McqQuizController(session)

    # Act
    result = await controller.get_random_questions(3, exclude_ids=[str(questions[0].id)], difficulty="hard")

    # Assert
    assert {q.id for q in result} == {q.id for q in questions}


async def test_draw_from_an_empty_table(session: AsyncSession):
    """No questions, no draw (the game controller raises NoMcqQuestionsAvailableError)."""
    # Prepare
    controller = McqQuizController(session)

    # Act
    result = await controller.get_random_questions(10)

    # Assert
    assert result == []
