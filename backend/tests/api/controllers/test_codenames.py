from datetime import datetime
from types import TracebackType
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.codenames import (
    CodenamesController,
    CodenamesWordNotFoundError,
    CodenamesWordPackAlreadyExistsError,
    CodenamesWordPackNotFoundError,
    NotEnoughWordsError,
)
from majlisna.api.models.codenames import CodenamesWord, CodenamesWordCreate, CodenamesWordPack, CodenamesWordPackCreate
from majlisna.api.utils.cache import cache
from majlisna.api.utils.rng import rng

# --- Word Pack CRUD ---


async def test_create_word_pack_success(codenames_controller: CodenamesController):
    """Creating a word pack with valid data returns a fully populated CodenamesWordPack object."""
    # Arrange
    word_pack_create = CodenamesWordPackCreate(
        name="Islamic Terms",
        description="Common Islamic terminology",
    )

    # Act
    pack = await codenames_controller.create_word_pack(word_pack_create)

    # Assert
    assert isinstance(pack.id, UUID)
    assert pack.name == "Islamic Terms"
    assert pack.description == "Common Islamic terminology"
    assert pack.is_active is True
    assert isinstance(pack.created_at, datetime)
    assert isinstance(pack.updated_at, datetime)


async def test_create_word_pack_duplicate_name(codenames_controller: CodenamesController):
    """Creating two word packs with the same name raises CodenamesWordPackAlreadyExistsError."""
    # Arrange
    word_pack_create = CodenamesWordPackCreate(name="Duplicate Pack")
    await codenames_controller.create_word_pack(word_pack_create)

    # Act & Assert
    with pytest.raises(CodenamesWordPackAlreadyExistsError):
        await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Duplicate Pack"))


async def test_get_word_packs_empty(codenames_controller: CodenamesController):
    """Getting all word packs from an empty database returns an empty list."""
    # Arrange
    # (no packs created)

    # Act
    packs = await codenames_controller.get_word_packs()

    # Assert
    assert len(packs) == 0


async def test_get_word_packs_multiple(codenames_controller: CodenamesController):
    """Getting all word packs after creating two returns a list of length 2."""
    # Arrange
    await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Pack One", description="First pack"))
    await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Pack Two", description="Second pack"))

    # Act
    packs = await codenames_controller.get_word_packs()

    # Assert
    assert len(packs) == 2


async def test_get_word_pack_by_id_success(codenames_controller: CodenamesController):
    """Getting a word pack by ID returns the correct pack with all fields matching."""
    # Arrange
    created_pack = await codenames_controller.create_word_pack(
        CodenamesWordPackCreate(name="Prophets", description="Names of prophets")
    )

    # Act
    found_pack = await codenames_controller.get_word_pack(created_pack.id)

    # Assert
    assert found_pack.id == created_pack.id
    assert found_pack.name == "Prophets"
    assert found_pack.description == "Names of prophets"
    assert found_pack.is_active is True
    assert isinstance(found_pack.created_at, datetime)
    assert isinstance(found_pack.updated_at, datetime)


async def test_get_word_pack_not_found(codenames_controller: CodenamesController):
    """Getting a word pack by a non-existent ID raises CodenamesWordPackNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(CodenamesWordPackNotFoundError):
        await codenames_controller.get_word_pack(non_existent_id)


async def test_delete_word_pack_success(codenames_controller: CodenamesController):
    """Deleting an existing word pack removes it so that get_word_pack raises CodenamesWordPackNotFoundError."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="To Delete"))

    # Act
    await codenames_controller.delete_word_pack(pack.id)

    # Assert
    with pytest.raises(CodenamesWordPackNotFoundError):
        await codenames_controller.get_word_pack(pack.id)


# --- Word CRUD ---


async def test_add_word_success(codenames_controller: CodenamesController):
    """Adding a word to a pack returns a fully populated CodenamesWord object."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Word Pack"))
    word_create = CodenamesWordCreate(word="Quran")

    # Act
    word = await codenames_controller.add_word(word_create, pack.id)

    # Assert
    assert isinstance(word.id, UUID)
    assert word.word == "Quran"
    assert word.word_pack_id == pack.id
    assert isinstance(word.created_at, datetime)
    assert isinstance(word.updated_at, datetime)


async def test_add_word_pack_not_found(codenames_controller: CodenamesController):
    """Adding a word to a non-existent pack raises CodenamesWordPackNotFoundError."""
    # Arrange
    non_existent_pack_id = uuid4()
    word_create = CodenamesWordCreate(word="Orphan")

    # Act & Assert
    with pytest.raises(CodenamesWordPackNotFoundError):
        await codenames_controller.add_word(word_create, non_existent_pack_id)


async def test_get_words_by_pack(codenames_controller: CodenamesController):
    """Getting words by pack after adding two words returns a list of length 2."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Words By Pack"))
    await codenames_controller.add_word(CodenamesWordCreate(word="Salah"), pack.id)
    await codenames_controller.add_word(CodenamesWordCreate(word="Zakat"), pack.id)

    # Act
    words = await codenames_controller.get_words_by_pack(pack.id)

    # Assert
    assert len(words) == 2


async def test_get_words_by_pack_not_found(codenames_controller: CodenamesController):
    """Getting words for a non-existent pack raises CodenamesWordPackNotFoundError."""
    # Arrange
    non_existent_pack_id = uuid4()

    # Act & Assert
    with pytest.raises(CodenamesWordPackNotFoundError):
        await codenames_controller.get_words_by_pack(non_existent_pack_id)


async def test_delete_word_success(codenames_controller: CodenamesController):
    """Deleting a word removes it so that the pack's word list becomes empty."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Delete Word Pack"))
    word = await codenames_controller.add_word(CodenamesWordCreate(word="delete_me"), pack.id)

    # Act
    await codenames_controller.delete_word(word.id)

    # Assert
    words = await codenames_controller.get_words_by_pack(pack.id)
    assert len(words) == 0


async def test_delete_word_not_found(codenames_controller: CodenamesController):
    """Deleting a word with a non-existent ID raises CodenamesWordNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(CodenamesWordNotFoundError):
        await codenames_controller.delete_word(non_existent_id)


# --- Random Words ---


async def test_get_random_words_success(codenames_controller: CodenamesController):
    """Getting 25 random words from a pack with 30 words returns 25 unique words."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Random Pack"))
    for i in range(30):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"word_{i}"), pack.id)

    # Act
    words = await codenames_controller.get_random_words(count=25)

    # Assert
    assert len(words) == 25
    word_ids = [w.id for w in words]
    assert len(set(word_ids)) == 25


async def test_get_random_words_never_repeats_a_word_across_the_board(
    codenames_controller: CodenamesController,
):
    """A board never carries the same word twice, even when packs overlap.

    The same term legitimately lives in more than one thematic pack — the seed data
    has Ikhlas, Tafsir and Tajweed in two packs each, with different hints. Sampling
    distinct *rows* therefore dealt the same word onto two of the 25 cards on roughly
    4% of boards, which makes the game unplayable: a one-word clue cannot say which
    of the two identical cards the spymaster meant, and anything addressing a card by
    its word hits whichever it finds first.
    """
    # Arrange — two packs that share every word, as the real packs partly do.
    pack_a = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Pack A"))
    pack_b = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Pack B"))
    for i in range(30):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"shared_{i}"), pack_a.id)
        await codenames_controller.add_word(CodenamesWordCreate(word=f"shared_{i}"), pack_b.id)

    # Act — draw a full board several times; the collision is probabilistic.
    for _ in range(20):
        words = await codenames_controller.get_random_words(count=25)

        # Assert
        assert len(words) == 25
        texts = [w.word for w in words]
        assert len(set(texts)) == 25, f"duplicate word on the board: {texts}"


async def test_get_random_words_counts_available_words_not_rows(
    codenames_controller: CodenamesController,
):
    """Availability is measured in distinct words, so a board is never short-dealt."""
    # Arrange — 60 rows, but only 20 distinct words.
    pack_a = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Dup A"))
    pack_b = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Dup B"))
    for i in range(20):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"dup_{i}"), pack_a.id)
        await codenames_controller.add_word(CodenamesWordCreate(word=f"dup_{i}"), pack_b.id)

    # Act / Assert — 40 rows is not 40 playable cards.
    with pytest.raises(NotEnoughWordsError):
        await codenames_controller.get_random_words(count=25)


async def test_get_random_words_not_enough(codenames_controller: CodenamesController):
    """Requesting more words than available raises NotEnoughWordsError."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Small Pack"))
    for i in range(5):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"small_{i}"), pack.id)

    # Act & Assert
    with pytest.raises(NotEnoughWordsError):
        await codenames_controller.get_random_words(count=25)


async def test_get_random_words_no_active_packs(
    codenames_controller: CodenamesController,
    session,  # noqa: ARG001
):
    """Getting random words when no active packs exist raises NotEnoughWordsError."""
    # Arrange
    # (no packs created at all)

    # Act & Assert
    with pytest.raises(NotEnoughWordsError):
        await codenames_controller.get_random_words(count=25)


async def test_get_random_words_exact_count(codenames_controller: CodenamesController):
    """Getting exactly as many random words as available succeeds without error."""
    # Arrange
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Exact Pack"))
    for i in range(25):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"exact_{i}"), pack.id)

    # Act
    words = await codenames_controller.get_random_words(count=25)

    # Assert
    assert len(words) == 25
    word_ids = [w.id for w in words]
    assert len(set(word_ids)) == 25


async def test_delete_word_pack_not_found(codenames_controller: CodenamesController):
    """Deleting a word pack with a non-existent ID raises CodenamesWordPackNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(CodenamesWordPackNotFoundError):
        await codenames_controller.delete_word_pack(non_existent_id)


# --- WP-24: no ORM rows in the cache, a draw reads only what it keeps ---


class WordDrawProbe:
    """Watches a draw: the CodenamesWord rows it hydrates and the SQL it sends.

    Rows already in the session's identity map are not hydrated again, so expunge
    the session before entering the probe.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._engine = session.bind.sync_engine
        self.hydrated_ids: list[UUID] = []
        self.statements: list[str] = []

    def __enter__(self) -> "WordDrawProbe":
        event.listen(CodenamesWord, "load", self._on_load)
        event.listen(self._engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        event.remove(CodenamesWord, "load", self._on_load)
        event.remove(self._engine, "before_cursor_execute", self._on_execute)

    def _on_load(self, target: CodenamesWord, context: object) -> None:
        self.hydrated_ids.append(target.id)

    def _on_execute(self, conn, cursor, statement: str, parameters, context, executemany) -> None:  # noqa: ARG002
        self.statements.append(statement)

    def payload_reads(self) -> list[str]:
        """The statements that read a word's hint, i.e. its full row."""
        return [s for s in self.statements if "codenames_word.hint" in s]


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


def orm_rows_in_cache() -> list[SQLModel]:
    """Every SQLModel instance the process-wide TTLCache holds, inside lists or not."""
    found: list[SQLModel] = []
    for _, value in cache._store.values():
        items = value if isinstance(value, list | tuple) else [value]
        found.extend(item for item in items if isinstance(item, SQLModel))
    return found


async def test_get_word_packs_leaves_no_orm_row_in_the_cache(codenames_controller: CodenamesController):
    """The admin list used to park its ORM rows in TTLCache for an hour."""
    # Prepare
    await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Cached Pack"))

    # Act
    packs = await codenames_controller.get_word_packs()

    # Assert
    assert [p.name for p in packs] == ["Cached Pack"]
    assert orm_rows_in_cache() == []


async def test_get_word_packs_sees_a_pack_added_by_another_worker(
    codenames_controller: CodenamesController, session: AsyncSession
):
    """`invalidate()` reaches one worker in four: a pack created elsewhere must show."""
    # Prepare
    await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Here"))
    assert len(await codenames_controller.get_word_packs()) == 1
    session.add(CodenamesWordPack(name="Elsewhere"))
    await session.commit()

    # Act
    packs = await codenames_controller.get_word_packs()

    # Assert
    assert {p.name for p in packs} == {"Here", "Elsewhere"}


async def test_get_random_words_hydrates_only_the_board(
    codenames_controller: CodenamesController, session: AsyncSession
):
    """A board of 25 reads the ids and texts, then only the 25 words it deals."""
    # Prepare
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Big Pack"))
    for i in range(40):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"big_{i}"), pack.id)
    session.expunge_all()

    # Act
    with WordDrawProbe(session) as probe:
        words = await codenames_controller.get_random_words(count=25)

    # Assert
    assert len(words) == 25
    assert len({w.word for w in words}) == 25
    assert len(probe.hydrated_ids) <= 25
    assert probe.payload_reads()
    for statement in probe.payload_reads():
        assert "WHERE codenames_word.id IN" in statement, statement


async def test_get_random_words_from_chosen_packs_only(codenames_controller: CodenamesController):
    """`pack_ids` limits the draw to those packs, active or not."""
    # Prepare
    chosen = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Chosen"))
    other = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Other"))
    for i in range(25):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"chosen_{i}"), chosen.id)
        await codenames_controller.add_word(CodenamesWordCreate(word=f"other_{i}"), other.id)

    # Act
    words = await codenames_controller.get_random_words(count=25, pack_ids=[chosen.id])

    # Assert
    assert {w.word_pack_id for w in words} == {chosen.id}


async def test_get_random_words_skips_inactive_packs(codenames_controller: CodenamesController, session: AsyncSession):
    """Without `pack_ids`, only the active packs deal."""
    # Prepare
    active = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Active"))
    inactive = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Inactive"))
    for i in range(25):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"active_{i}"), active.id)
        await codenames_controller.add_word(CodenamesWordCreate(word=f"inactive_{i}"), inactive.id)
    inactive.is_active = False
    session.add(inactive)
    await session.commit()

    # Act
    words = await codenames_controller.get_random_words(count=25)

    # Assert
    assert {w.word_pack_id for w in words} == {active.id}


async def test_get_random_words_returns_the_board_in_draw_order(
    codenames_controller: CodenamesController, session: AsyncSession
):
    """The cards are laid out in the order they were drawn, not in the database's."""
    # Prepare
    pack = await codenames_controller.create_word_pack(CodenamesWordPackCreate(name="Order Pack"))
    for i in range(30):
        await codenames_controller.add_word(CodenamesWordCreate(word=f"order_{i}"), pack.id)
    session.expunge_all()
    sample = RecordingSample()

    # Act
    with patch.object(rng, "sample", side_effect=sample):
        words = await codenames_controller.get_random_words(count=25)

    # Assert
    assert [w.id for w in words] == sample.drawn_ids()
