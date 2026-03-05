"""Tests for room model validation."""

import random

import pytest
from faker import Faker

from ipg.api.models.room import RoomCreate, RoomStatus


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
