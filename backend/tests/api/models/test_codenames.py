"""Tests for codenames model validation."""

from ipg.api.models.codenames import CodenamesWordCreate, CodenamesWordPackCreate


def test_create_word_pack_with_name_and_description():
    """Creating a word pack with name and description succeeds."""

    # Arrange
    name = "Islamic Terms"
    description = "Common Islamic terminology"

    # Act
    pack = CodenamesWordPackCreate(name=name, description=description)

    # Assert
    assert pack.name == name
    assert pack.description == description


def test_create_word_pack_with_name_only():
    """Creating a word pack with only a name (no description) succeeds."""

    # Arrange / Act
    pack = CodenamesWordPackCreate(name="Prophets")

    # Assert
    assert pack.name == "Prophets"
    assert pack.description is None


def test_create_word():
    """Creating a codenames word with a word string succeeds."""

    # Arrange / Act
    word = CodenamesWordCreate(word="Quran")

    # Assert
    assert word.word == "Quran"
