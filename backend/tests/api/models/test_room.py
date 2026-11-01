"""Tests for room model validation."""

import random

import pytest
from faker import Faker
from pydantic import ValidationError

from majlisna.api.constants import MIN_QUIZ_TURN_SECONDS
from majlisna.api.models.room import RoomCreate, RoomStatus
from majlisna.api.schemas.room import RoomSettingsRequest


def test_room_password_with_non_digit_characters(faker: Faker):
    """Creating a room with non-digit password raises ValueError."""

    # Arrange
    password = "abcd"

    # Act / Assert
    with pytest.raises(ValueError):
        RoomCreate(
            owner_id=faker.uuid4(),
            status=random.choice(list(RoomStatus)),
            password=password,
        )


def test_room_password_with_less_than_4_characters(faker: Faker):
    """Creating a room with fewer than 4 digits raises ValueError."""

    # Arrange
    password = "12"

    # Act / Assert
    with pytest.raises(ValueError):
        RoomCreate(
            owner_id=faker.uuid4(),
            status=random.choice(list(RoomStatus)),
            password=password,
        )


def test_room_password_valid(faker: Faker):
    """Creating a room with a valid 4-digit password succeeds."""

    # Arrange
    password = "1234"

    # Act
    room = RoomCreate(
        owner_id=faker.uuid4(),
        status=RoomStatus.ONLINE,
        password=password,
    )

    # Assert
    assert room.password == "1234"
    assert room.status == RoomStatus.ONLINE


@pytest.mark.parametrize("field", ["word_quiz_turn_duration", "mcq_quiz_turn_duration"])
@pytest.mark.parametrize("seconds", [0, 2, MIN_QUIZ_TURN_SECONDS - 1])
def test_a_quiz_turn_shorter_than_the_minimum_is_rejected(field: str, seconds: int):
    """BR-17: a quiz round of 0-2 s expired the moment it opened (elapsed >= duration - 2).

    Undercover and Codenames read 0 as "no limit"; the quizzes have no such value.
    """
    # Act / Assert
    with pytest.raises(ValidationError):
        RoomSettingsRequest(**{field: seconds})


@pytest.mark.parametrize("field", ["word_quiz_turn_duration", "mcq_quiz_turn_duration"])
def test_the_quiz_turn_minimum_itself_is_accepted(field: str):
    """The shortest round the settings UI offers (10 s for The Quiz) stays valid."""
    # Act
    settings = RoomSettingsRequest(**{field: MIN_QUIZ_TURN_SECONDS})

    # Assert
    assert getattr(settings, field) == MIN_QUIZ_TURN_SECONDS


def test_an_untimed_undercover_turn_is_still_accepted():
    """0 keeps meaning "no time limit" for the games that read it that way."""
    # Act
    settings = RoomSettingsRequest(description_timer=0, voting_timer=0, codenames_clue_timer=0)

    # Assert
    assert settings.description_timer == 0
