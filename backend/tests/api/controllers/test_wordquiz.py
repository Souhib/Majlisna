"""Tests for WordQuiz CRUD controller."""

from types import TracebackType
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.wordquiz import WordQuizController
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.utils.rng import rng


class DrawProbe:
    """Watches a draw: the QuizWord rows it hydrates and the SQL it sends.

    Rows already in the session's identity map are not hydrated again, so expunge
    the session before entering the probe.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._engine = session.bind.sync_engine
        self.hydrated_ids: list[UUID] = []
        self.statements: list[str] = []

    def __enter__(self) -> "DrawProbe":
        event.listen(QuizWord, "load", self._on_load)
        event.listen(self._engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        event.remove(QuizWord, "load", self._on_load)
        event.remove(self._engine, "before_cursor_execute", self._on_execute)

    def _on_load(self, target: QuizWord, context: object) -> None:
        self.hydrated_ids.append(target.id)

    def _on_execute(self, conn, cursor, statement: str, parameters, context, executemany) -> None:  # noqa: ARG002
        self.statements.append(statement)

    def payload_reads(self) -> list[str]:
        """The statements that read a word's hints, i.e. its full row."""
        return [s for s in self.statements if "quiz_word.hints" in s]


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


@pytest.mark.asyncio
async def test_create_quiz_word(create_quiz_word):
    """Creating a quiz word persists it to the database."""
    # Act
    word = await create_quiz_word(word_en="TestWord", category="TestCategory")

    # Assert
    assert word.id is not None
    assert word.word_en == "TestWord"
    assert word.category == "TestCategory"


@pytest.mark.asyncio
async def test_get_random_words(wordquiz_controller: WordQuizController, create_quiz_word):
    """get_random_words returns requested count of random words."""
    # Prepare
    await create_quiz_word(word_en="W1")
    await create_quiz_word(word_en="W2")
    await create_quiz_word(word_en="W3")

    # Act
    result = await wordquiz_controller.get_random_words(2)

    # Assert
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_random_words_with_exclusion(wordquiz_controller: WordQuizController, create_quiz_word):
    """get_random_words respects exclude_ids."""
    # Prepare
    w1 = await create_quiz_word(word_en="W1")
    await create_quiz_word(word_en="W2")

    # Act
    result = await wordquiz_controller.get_random_words(1, exclude_ids=[str(w1.id)])

    # Assert
    assert len(result) == 1
    assert result[0].word_en == "W2"


@pytest.mark.asyncio
async def test_get_random_words_hydrates_only_the_drawn_rows(
    wordquiz_controller: WordQuizController, create_quiz_word, session: AsyncSession
):
    """A draw of n reads the ids, then the n chosen rows — never the whole table.

    It used to load and hydrate every quiz word (191 rows, 332 kB in production) on
    every round, inside the game lock, to keep one.
    """
    # Prepare
    for i in range(8):
        await create_quiz_word(word_en=f"Word{i}")
    session.expunge_all()

    # Act
    with DrawProbe(session) as probe:
        result = await wordquiz_controller.get_random_words(3)

    # Assert
    assert len(result) == 3
    assert len({w.id for w in result}) == 3
    assert len(probe.hydrated_ids) <= 3
    assert probe.payload_reads()
    for statement in probe.payload_reads():
        assert "WHERE quiz_word.id IN" in statement, statement


@pytest.mark.asyncio
async def test_get_random_words_returns_rows_in_draw_order(
    wordquiz_controller: WordQuizController, create_quiz_word, session: AsyncSession
):
    """The rows come back in the order they were drawn, not in the database's order."""
    # Prepare
    for i in range(6):
        await create_quiz_word(word_en=f"Ordered{i}")
    session.expunge_all()
    sample = RecordingSample()

    # Act
    with patch.object(rng, "sample", side_effect=sample):
        result = await wordquiz_controller.get_random_words(5)

    # Assert
    assert [w.id for w in result] == sample.drawn_ids()


@pytest.mark.asyncio
async def test_get_random_words_keeps_the_difficulty_filter(
    wordquiz_controller: WordQuizController, create_quiz_word, session: AsyncSession
):
    """A difficulty with enough words draws only from it; "mixed" draws from all."""
    # Prepare
    for i in range(4):
        await create_quiz_word(word_en=f"Easy{i}")
    for i in range(4):
        hard = await create_quiz_word(word_en=f"Hard{i}")
        hard.difficulty = "hard"
        session.add(hard)
    await session.commit()

    # Act
    hard_draw = await wordquiz_controller.get_random_words(3, difficulty="hard")
    mixed_draw = await wordquiz_controller.get_random_words(8, difficulty="mixed")

    # Assert
    assert {w.difficulty for w in hard_draw} == {"hard"}
    assert len(mixed_draw) == 8


@pytest.mark.asyncio
async def test_get_random_words_falls_back_to_every_word_when_too_few_remain(
    wordquiz_controller: WordQuizController, create_quiz_word
):
    """Excluding (almost) everything still deals a word rather than none."""
    # Prepare
    w1 = await create_quiz_word(word_en="Only1")
    w2 = await create_quiz_word(word_en="Only2")

    # Act
    result = await wordquiz_controller.get_random_words(1, exclude_ids=[str(w1.id), str(w2.id)])

    # Assert
    assert len(result) == 1
    assert result[0].id in {w1.id, w2.id}


@pytest.mark.asyncio
async def test_get_random_words_empty_table(wordquiz_controller: WordQuizController):
    """No words, no draw (the game controller turns that into NoQuizWordsAvailableError)."""
    # Act
    result = await wordquiz_controller.get_random_words(1)

    # Assert
    assert result == []


@pytest.mark.asyncio
async def test_delete_quiz_word(wordquiz_controller: WordQuizController, create_quiz_word, session: AsyncSession):
    """delete removes the quiz word."""
    # Prepare
    word = await create_quiz_word(word_en="ToDelete")

    # Act
    await wordquiz_controller.delete(word.id)

    # Assert
    session.expunge_all()
    remaining = (await session.exec(select(QuizWord))).all()
    assert remaining == []
