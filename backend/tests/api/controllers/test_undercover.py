from uuid import uuid4

import pytest
from sqlalchemy.exc import NoResultFound

from ipg.api.controllers.undercover import UndercoverController
from ipg.api.models.undercover import WordCreate, WordUpdate
from ipg.api.schemas.error import (
    TermPairAlreadyExistsError,
    TermPairNotFoundError,
    WordAlreadyExistsError,
    WordNotFoundByIdError,
    WordNotFoundByNameError,
)

# --- Word CRUD ---


async def test_create_word_success(undercover_controller: UndercoverController):
    """Creating a word with valid data returns a fully populated Word object."""
    # Arrange
    word_create = WordCreate(
        word="mosque",
        category="islamic",
        short_description="Place of worship",
        long_description="A place where Muslims gather for prayer",
    )

    # Act
    word = await undercover_controller.create_word(word_create)

    # Assert
    assert word.id is not None
    assert word.word == "mosque"
    assert word.category == "islamic"
    assert word.short_description == "Place of worship"
    assert word.long_description == "A place where Muslims gather for prayer"


async def test_create_word_duplicate(undercover_controller: UndercoverController, create_word):
    """Creating two words with the same word string raises WordAlreadyExistsError."""
    # Arrange
    await create_word(word="duplicate_word")

    # Act & Assert
    with pytest.raises(WordAlreadyExistsError):
        await undercover_controller.create_word(
            WordCreate(
                word="duplicate_word",
                category="test",
                short_description="short",
                long_description="long",
            )
        )


async def test_get_words_empty(undercover_controller: UndercoverController):
    """Getting all words from an empty database returns an empty list."""
    # Arrange
    # (no words created)

    # Act
    words = await undercover_controller.get_words()

    # Assert
    assert words == []


async def test_get_words_multiple(undercover_controller: UndercoverController, create_word):
    """Getting all words after creating three returns a list of length 3."""
    # Arrange
    await create_word(word="word_one", category="cat_a")
    await create_word(word="word_two", category="cat_b")
    await create_word(word="word_three", category="cat_c")

    # Act
    words = await undercover_controller.get_words()

    # Assert
    assert len(words) == 3


async def test_get_word_by_id_success(undercover_controller: UndercoverController, sample_word):
    """Retrieving a word by its ID returns the correct word with all fields matching."""
    # Arrange
    # (sample_word already created via fixture)

    # Act
    found = await undercover_controller.get_word_by_id(sample_word.id)

    # Assert
    assert found.id == sample_word.id
    assert found.word == sample_word.word
    assert found.category == sample_word.category
    assert found.short_description == sample_word.short_description
    assert found.long_description == sample_word.long_description


async def test_get_word_by_id_not_found(undercover_controller: UndercoverController):
    """Retrieving a word with a nonexistent UUID raises WordNotFoundByIdError."""
    # Arrange
    random_id = uuid4()

    # Act & Assert
    with pytest.raises(WordNotFoundByIdError):
        await undercover_controller.get_word_by_id(random_id)


async def test_get_word_by_word_success(undercover_controller: UndercoverController, sample_word):
    """Retrieving a word by its string value returns the matching word with correct ID."""
    # Arrange
    # (sample_word already created via fixture)

    # Act
    found = await undercover_controller.get_word_by_word(sample_word.word)

    # Assert
    assert found.id == sample_word.id


async def test_get_word_by_word_not_found(undercover_controller: UndercoverController):
    """Retrieving a word with a nonexistent string raises WordNotFoundByNameError."""
    # Arrange
    # (no words created)

    # Act & Assert
    with pytest.raises(WordNotFoundByNameError):
        await undercover_controller.get_word_by_word("nonexistent_word")


async def test_delete_word_success(undercover_controller: UndercoverController, create_word):
    """Deleting an existing word removes it so that get_word_by_id raises WordNotFoundByIdError."""
    # Arrange
    word = await create_word(word="to_delete")

    # Act
    await undercover_controller.delete_word(word.id)

    # Assert
    with pytest.raises(WordNotFoundByIdError):
        await undercover_controller.get_word_by_id(word.id)


async def test_delete_word_not_found(undercover_controller: UndercoverController):
    """Deleting a word with a nonexistent UUID raises NoResultFound."""
    # Arrange
    random_id = uuid4()

    # Act & Assert
    with pytest.raises(NoResultFound):
        await undercover_controller.delete_word(random_id)


async def test_update_word_success(undercover_controller: UndercoverController, create_word):
    """Updating a word changes the specified fields while preserving the original word string."""
    # Arrange
    word = await create_word(
        word="original_word",
        category="original_category",
        short_description="Original short",
        long_description="Original long",
    )
    word_update = WordUpdate(
        word="original_word",
        category="updated_category",
        short_description="Updated short",
        long_description="Updated long",
    )

    # Act
    updated = await undercover_controller.update_word(word.id, word_update)

    # Assert
    assert updated.id == word.id
    assert updated.word == "original_word"
    assert updated.category == "updated_category"
    assert updated.short_description == "Updated short"
    assert updated.long_description == "Updated long"


async def test_update_word_not_found(undercover_controller: UndercoverController):
    """Updating a word with a nonexistent UUID raises WordNotFoundByIdError."""
    # Arrange
    random_id = uuid4()
    word_update = WordUpdate(
        word="any",
        category="any",
        short_description="any",
        long_description="any",
    )

    # Act & Assert
    with pytest.raises(WordNotFoundByIdError):
        await undercover_controller.update_word(random_id, word_update)


# --- Category ---


async def test_get_words_by_category(undercover_controller: UndercoverController, create_word):
    """Filtering words by category returns only the words belonging to that category."""
    # Arrange
    await create_word(word="word_a1", category="category_a")
    await create_word(word="word_a2", category="category_a")
    await create_word(word="word_b1", category="category_b")

    # Act
    result = await undercover_controller.get_words_by_category("category_a")

    # Assert
    assert len(result) == 2


# --- Term Pair CRUD ---


async def test_create_term_pair_success(undercover_controller: UndercoverController, create_word):
    """Creating a term pair with two valid words returns a fully populated TermPair object."""
    # Arrange
    word1 = await create_word(word="term_one")
    word2 = await create_word(word="term_two")

    # Act
    term_pair = await undercover_controller.create_term_pair(word1.id, word2.id)

    # Assert
    assert term_pair.id is not None
    assert term_pair.word1_id == word1.id
    assert term_pair.word2_id == word2.id


async def test_create_term_pair_duplicate(undercover_controller: UndercoverController, create_word):
    """Creating the same term pair twice raises TermPairAlreadyExistsError."""
    # Arrange
    word1 = await create_word(word="dup_pair_one")
    word2 = await create_word(word="dup_pair_two")
    await undercover_controller.create_term_pair(word1.id, word2.id)

    # Act & Assert
    with pytest.raises(TermPairAlreadyExistsError):
        await undercover_controller.create_term_pair(word1.id, word2.id)


async def test_get_term_pairs_empty(undercover_controller: UndercoverController):
    """Getting all term pairs from an empty database returns an empty list."""
    # Arrange
    # (no term pairs created)

    # Act
    pairs = await undercover_controller.get_term_pairs()

    # Assert
    assert pairs == []


async def test_get_term_pairs_multiple(undercover_controller: UndercoverController, create_word):
    """Getting all term pairs after creating three returns a list of length 3."""
    # Arrange
    for i in range(3):
        w1 = await create_word(word=f"multi_a{i}")
        w2 = await create_word(word=f"multi_b{i}")
        await undercover_controller.create_term_pair(w1.id, w2.id)

    # Act
    pairs = await undercover_controller.get_term_pairs()

    # Assert
    assert len(pairs) == 3


async def test_get_term_pair_by_id_success(undercover_controller: UndercoverController, create_word):
    """Retrieving a term pair by its ID returns the correct pair with all fields matching."""
    # Arrange
    word1 = await create_word(word="pair_find_one")
    word2 = await create_word(word="pair_find_two")
    term_pair = await undercover_controller.create_term_pair(word1.id, word2.id)

    # Act
    found = await undercover_controller.get_term_pair_by_id(term_pair.id)

    # Assert
    assert found.id == term_pair.id
    assert found.word1_id == word1.id
    assert found.word2_id == word2.id


async def test_get_term_pair_by_id_not_found(undercover_controller: UndercoverController):
    """Retrieving a term pair with a nonexistent UUID raises TermPairNotFoundError."""
    # Arrange
    random_id = uuid4()

    # Act & Assert
    with pytest.raises(TermPairNotFoundError):
        await undercover_controller.get_term_pair_by_id(random_id)


async def test_get_random_term_pair_success(undercover_controller: UndercoverController, create_word):
    """Getting a random term pair when one exists returns a valid pair with correct word1_id."""
    # Arrange
    word1 = await create_word(word="random_one")
    word2 = await create_word(word="random_two")
    term_pair = await undercover_controller.create_term_pair(word1.id, word2.id)

    # Act
    result = await undercover_controller.get_random_term_pair()

    # Assert
    assert result.word1_id == term_pair.word1_id


async def test_get_random_term_pair_empty(undercover_controller: UndercoverController):
    """Getting a random term pair from an empty database raises NoResultFound."""
    # Arrange
    # (no term pairs created)

    # Act & Assert
    with pytest.raises(NoResultFound):
        await undercover_controller.get_random_term_pair()


async def test_delete_term_pair_success(undercover_controller: UndercoverController, create_word):
    """Deleting an existing term pair removes it so that get_term_pair_by_id raises TermPairNotFoundError."""
    # Arrange
    word1 = await create_word(word="del_pair_one")
    word2 = await create_word(word="del_pair_two")
    term_pair = await undercover_controller.create_term_pair(word1.id, word2.id)

    # Act
    await undercover_controller.delete_term_pair(term_pair.id)

    # Assert
    with pytest.raises(TermPairNotFoundError):
        await undercover_controller.get_term_pair_by_id(term_pair.id)
