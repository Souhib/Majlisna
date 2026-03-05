from datetime import datetime
from uuid import UUID, uuid4

import pytest

from ipg.api.controllers.codenames import (
    CodenamesController,
    CodenamesWordNotFoundError,
    CodenamesWordPackAlreadyExistsError,
    CodenamesWordPackNotFoundError,
    NotEnoughWordsError,
)
from ipg.api.models.codenames import CodenamesWordCreate, CodenamesWordPackCreate

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
