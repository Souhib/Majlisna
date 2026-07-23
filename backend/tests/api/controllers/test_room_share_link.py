"""Controller-level tests for room share link."""

import pytest

from majlisna.api.controllers.room import RoomController
from majlisna.api.schemas.error import UserNotInRoomError


async def test_get_share_link_returns_data_for_member(room_controller: RoomController, create_user, create_room):
    """get_share_link returns public_id and password for a connected room member."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    room = await create_room(owner=owner)

    # Act
    result = await room_controller.get_share_link(room.id, owner.id)

    # Assert
    assert result.public_id == room.public_id
    assert result.password == room.password


async def test_get_share_link_raises_for_non_member(room_controller: RoomController, create_user, create_room):
    """get_share_link raises UserNotInRoomError when user is not in the room."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    outsider = await create_user(username="outsider", email="outsider@test.com")
    room = await create_room(owner=owner)

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        await room_controller.get_share_link(room.id, outsider.id)
