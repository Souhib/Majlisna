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


@pytest.mark.parametrize(("how", "rotates"), [("kick", False), ("ban", True)])
async def test_after_a_removal_the_share_link_is_the_hosts_and_only_a_ban_changes_its_pin(
    room_controller: RoomController, create_user, create_room, how: str, rotates: bool
):
    """A kick keeps the PIN (the player may come back with it); a ban rotates it. Either
    way the removed player is no member and cannot read the link."""

    # Prepare
    owner = await create_user(username="owner", email="owner@test.com")
    guest = await create_user(username="guest", email="guest@test.com")
    room = await create_room(owner=owner)
    room_id, owner_id, guest_id, old_pin = room.id, owner.id, guest.id, room.password
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=old_pin), guest_id)

    # Act
    if how == "kick":
        await room_controller.kick_player(room_id, owner_id, guest_id)
    else:
        await room_controller.ban_player(room_id, owner_id, guest_id)
    result = await room_controller.get_share_link(room_id, owner_id)

    # Assert
    assert (result.password != old_pin) is rotates
    with pytest.raises(UserNotInRoomError):
        await room_controller.get_share_link(room_id, guest_id)
