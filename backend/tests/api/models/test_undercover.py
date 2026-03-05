"""Tests for undercover model validation."""

from uuid import uuid4

import pytest
from faker import Faker

from ipg.api.models.undercover import TermPairCreate, WordCreate


def test_create_word_with_all_required_fields(faker: Faker):
    """Creating a word with all fields succeeds."""

    # Arrange
    word = faker.word()
    category = faker.word()
    short_description = faker.sentence()
    long_description = faker.paragraph()

    # Act
    new_word = WordCreate(
        word=word,
        category=category,
        short_description=short_description,
        long_description=long_description,
    )

    # Assert
    assert new_word.word == word
    assert new_word.category == category
    assert new_word.short_description == short_description
    assert new_word.long_description == long_description


def test_check_words_are_different_raises_error_when_words_are_same():
    """Creating a term pair with the same word1_id and word2_id raises ValueError."""

    # Arrange
    same_id = uuid4()

    # Act / Assert
    with pytest.raises(ValueError, match="Words have to be different"):
        TermPairCreate(word1_id=same_id, word2_id=same_id)


def test_check_words_are_different_succeeds_when_words_are_different():
    """Creating a term pair with different word IDs succeeds."""

    # Arrange
    word1_id = uuid4()
    word2_id = uuid4()

    # Act
    term_pair = TermPairCreate(word1_id=word1_id, word2_id=word2_id)

    # Assert
    assert term_pair.word1_id == word1_id
    assert term_pair.word2_id == word2_id
