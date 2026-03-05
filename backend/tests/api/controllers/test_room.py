from uuid import uuid4

import pytest
from sqlmodel import select

from ipg.api.controllers.room import RoomController
from ipg.api.models.event import EventCreate
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.room import RoomCreate, RoomJoin, RoomLeave, RoomStatus, RoomType
from ipg.api.models.table import Room, User
from ipg.api.schemas.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)


async def test_create_room_success(room_controller: RoomController, create_user):
    """Creating a room returns a fully populated Room with correct fields and the owner as the sole user."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")

    # Act
    room = await room_controller.create_room(RoomCreate(status=RoomStatus.ONLINE, password="1234", owner_id=owner.id))

    # Assert
    assert room.id is not None
    assert room.public_id is not None
    assert len(room.public_id) == 5
    assert room.owner_id == owner.id
    assert room.type == RoomType.ACTIVE
    assert room.created_at is not None
    assert len(room.users) == 1
    assert room.users[0].id == owner.id


async def test_create_room_owner_already_in_room(create_user, create_room):
    """Creating a second room with the same owner raises UserAlreadyInRoomError."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    await create_room(owner=owner)

    # Act / Assert
    with pytest.raises(UserAlreadyInRoomError):
        await create_room(owner=owner)


async def test_get_rooms_empty(room_controller: RoomController):
    """Getting rooms when none exist returns an empty list."""

    # Arrange — no rooms created

    # Act
    rooms = await room_controller.get_rooms()

    # Assert
    assert len(rooms) == 0


async def test_get_rooms_multiple(create_user, create_room, room_controller: RoomController):
    """Getting rooms after creating two returns a list of length 2."""

    # Arrange
    owner1 = await create_user(username="owner1", email="o1@test.com")
    owner2 = await create_user(username="owner2", email="o2@test.com")
    await create_room(owner=owner1)
    await create_room(owner=owner2)

    # Act
    rooms = await room_controller.get_rooms()

    # Assert
    assert len(rooms) == 2


async def test_get_room_by_id_success(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """Getting a room by its ID returns the correct room with matching id and owner_id."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    found = await room_controller.get_room_by_id(sample_room.id)

    # Assert
    assert found.id == sample_room.id
    assert found.owner_id == sample_owner.id


async def test_get_room_by_id_not_found(room_controller: RoomController):
    """Getting a room with a non-existent UUID raises RoomNotFoundError."""

    # Arrange
    fake_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.get_room_by_id(fake_id)


async def test_join_room_success(create_user, create_room, room_controller: RoomController):
    """Joining a room creates a RoomUserLink for the joiner alongside the owner's link."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner, password="5678")

    # Act
    updated = await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=room.id, password="5678"))

    # Assert — verify via RoomUserLink table directly (identity map may cache stale relationships)
    assert updated.id == room.id
    links = (await room_controller.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room.id))).all()
    assert len(links) == 2
    user_ids = {link.user_id for link in links}
    assert owner.id in user_ids
    assert joiner.id in user_ids


async def test_join_room_wrong_password(create_user, create_room, room_controller: RoomController):
    """Joining a room with the wrong password raises WrongRoomPasswordError."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner, password="5678")

    # Act / Assert
    with pytest.raises(WrongRoomPasswordError):
        await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=room.id, password="0000"))


async def test_join_room_not_found(create_user, room_controller: RoomController):
    """Joining a non-existent room raises RoomNotFoundError."""

    # Arrange
    joiner = await create_user(username="joiner", email="joiner@test.com")
    fake_room_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=fake_room_id, password="1234"))


async def test_join_room_user_not_found(sample_owner: User, sample_room: Room, room_controller: RoomController):  # noqa: ARG001
    """Joining a room with a non-existent user UUID raises UserNotFoundError."""

    # Arrange
    fake_user_id = uuid4()

    # Act / Assert
    with pytest.raises(UserNotFoundError):
        await room_controller.join_room(RoomJoin(user_id=fake_user_id, room_id=sample_room.id, password="1234"))


async def test_join_room_already_in_room_rejoins(create_user, create_room, room_controller: RoomController):
    """Joining a room a second time succeeds (re-join updates heartbeat)."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner, password="5678")
    await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=room.id, password="5678"))

    # Act — join again (should succeed as a re-join)
    updated = await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=room.id, password="5678"))

    # Assert — still only 2 links (no duplicate)
    links = (await room_controller.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room.id))).all()
    assert len(links) == 2
    assert updated.id == room.id


async def test_leave_room_success(create_user, create_room, room_controller: RoomController):
    """Leaving a room sets the joiner's RoomUserLink.connected to False while the room stays ACTIVE."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner, password="5678")
    await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=room.id, password="5678"))
    # Save IDs before expiring (expire_all makes attribute access trigger sync lazy load)
    room_id = room.id
    joiner_id = joiner.id
    room_controller.session.expire_all()  # Clear identity map so leave_room re-fetches Room.users

    # Act
    updated = await room_controller.leave_room(RoomLeave(room_id=room_id, user_id=joiner_id))

    # Assert — verify via RoomUserLink table directly
    assert updated.type == RoomType.ACTIVE
    link = (
        await room_controller.session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == joiner_id)
        )
    ).one()
    assert link.connected is False


async def test_leave_room_owner_deactivates(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """When the owner leaves, the room type becomes INACTIVE."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    updated = await room_controller.leave_room(RoomLeave(room_id=sample_room.id, user_id=sample_owner.id))

    # Assert
    assert updated.type == RoomType.INACTIVE


async def test_leave_room_not_found(room_controller: RoomController, create_user):
    """Leaving a non-existent room raises RoomNotFoundError."""

    # Arrange
    user = await create_user(username="user", email="user@test.com")
    fake_room_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.leave_room(RoomLeave(room_id=fake_room_id, user_id=user.id))


async def test_leave_room_user_not_in_room(
    sample_owner: User,  # noqa: ARG001
    sample_room: Room,
    create_user,
    room_controller: RoomController,
):
    """Leaving a room the user never joined raises UserNotInRoomError."""

    # Arrange
    other = await create_user(username="other", email="other@test.com")

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        await room_controller.leave_room(RoomLeave(room_id=sample_room.id, user_id=other.id))


async def test_leave_room_already_left(create_user, create_room, room_controller: RoomController):
    """Leaving a room twice raises UserNotInRoomError on the second attempt."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner, password="5678")
    await room_controller.join_room(RoomJoin(user_id=joiner.id, room_id=room.id, password="5678"))
    room_id = room.id
    joiner_id = joiner.id
    room_controller.session.expire_all()  # Clear identity map so leave_room re-fetches Room.users
    await room_controller.leave_room(RoomLeave(room_id=room_id, user_id=joiner_id))

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        await room_controller.leave_room(RoomLeave(room_id=room_id, user_id=joiner_id))


async def test_delete_room_success(sample_owner: User, sample_room: Room, room_controller: RoomController):  # noqa: ARG001
    """Deleting a room makes it unretrievable by get_room_by_id."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    await room_controller.delete_room(sample_room.id)

    # Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.get_room_by_id(sample_room.id)


async def test_delete_room_not_found(room_controller: RoomController):
    """Deleting a non-existent room raises RoomNotFoundError."""

    # Arrange
    fake_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.delete_room(fake_id)


async def test_get_active_room_by_public_id_success(
    sample_owner: User,  # noqa: ARG001
    sample_room: Room,
    room_controller: RoomController,
):
    """Finding a room by its public_id returns the correct room."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    found = await room_controller.get_active_room_by_public_id(sample_room.public_id)

    # Assert
    assert found.id == sample_room.id


async def test_get_active_room_by_public_id_not_found(room_controller: RoomController):
    """Searching for a non-existent public_id raises RoomNotFoundError."""

    # Arrange
    fake_public_id = "XXXXX"

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.get_active_room_by_public_id(fake_public_id)


async def test_create_room_activity_success(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """Creating a room activity returns an Activity with correct name, data, room_id, and user_id."""

    # Arrange
    event_data = {"key": "value"}

    # Act
    activity = await room_controller.create_room_activity(
        sample_room.id,
        EventCreate(name="test_event", data=event_data, user_id=sample_owner.id),
    )

    # Assert
    assert activity.name == "test_event"
    assert activity.data == {"key": "value"}
    assert activity.room_id == sample_room.id
    assert activity.user_id == sample_owner.id


async def test_create_room_activity_room_not_found(room_controller: RoomController):
    """Creating an activity for a non-existent room raises RoomNotFoundError."""

    # Arrange
    fake_room_id = uuid4()
    fake_user_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.create_room_activity(
            fake_room_id,
            EventCreate(name="event", data={}, user_id=fake_user_id),
        )


async def test_check_if_user_is_in_room_true(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """Checking if the owner is in their room returns True."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    result = await room_controller.check_if_user_is_in_room(sample_owner.id, sample_room.id)

    # Assert
    assert result is True


async def test_check_if_user_is_in_room_false(
    sample_owner: User,  # noqa: ARG001
    sample_room: Room,
    create_user,
    room_controller: RoomController,
):
    """Checking if an unrelated user is in a room returns False."""

    # Arrange
    other = await create_user(username="other", email="other@test.com")

    # Act
    result = await room_controller.check_if_user_is_in_room(other.id, sample_room.id)

    # Assert
    assert result is False
