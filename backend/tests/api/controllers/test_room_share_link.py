"""Controller-level tests for room share link."""

import pytest

from majlisna.api.controllers.room import RoomController
from majlisna.api.models.room import RoomJoin
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


async def test_after_a_kick_the_share_link_carries_a_new_pin_the_kicked_player_cannot_read(
    room_controller: RoomController, create_user, create_room
):
    """Owner rule (c): the host shares the rotated PIN, and the kicked player is no member."""

    # Prepare
    owner = await create_user(username="owner", email="owner@test.com")
    guest = await create_user(username="guest", email="guest@test.com")
    room = await create_room(owner=owner)
    room_id, owner_id, guest_id, old_pin = room.id, owner.id, guest.id, room.password
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=old_pin), guest_id)

    # Act
    await room_controller.kick_player(room_id, owner_id, guest_id)
    result = await room_controller.get_share_link(room_id, owner_id)

    # Assert
    assert result.password != old_pin
    with pytest.raises(UserNotInRoomError):
        await room_controller.get_share_link(room_id, guest_id)
