from uuid import uuid4

import pytest
from sqlmodel import select

from majlisna.api.controllers.room import RoomController
from majlisna.api.models.game import GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomJoin, RoomType
from majlisna.api.models.table import Room, User
from majlisna.api.schemas.error import (
    BaseError,
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from majlisna.api.schemas.room import RoomSettings


async def test_create_room_success(room_controller: RoomController, create_user):
    """Creating a room returns a fully populated Room with correct fields and the owner as the sole user."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")

    # Act
    room = await room_controller.create_room(owner_id=owner.id, game_type=GameType.UNDERCOVER)

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
    room = await create_room(owner=owner)

    # Act
    updated = await room_controller.join_room(
        RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id
    )

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
    room = await create_room(owner=owner)

    # Act / Assert
    wrong_password = "0000" if room.password != "0000" else "1111"
    with pytest.raises(WrongRoomPasswordError):
        await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=wrong_password), joiner.id)


async def test_join_room_not_found(create_user, room_controller: RoomController):
    """Joining a non-existent room raises RoomNotFoundError."""

    # Arrange
    joiner = await create_user(username="joiner", email="joiner@test.com")

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.join_room(RoomJoin(public_room_id="ZZZZZ", password="1234"), joiner.id)


async def test_join_room_user_not_found(sample_owner: User, sample_room: Room, room_controller: RoomController):  # noqa: ARG001
    """Joining a room with a non-existent user UUID raises UserNotFoundError."""

    # Arrange
    fake_user_id = uuid4()

    # Act / Assert
    with pytest.raises(UserNotFoundError):
        await room_controller.join_room(
            RoomJoin(public_room_id=sample_room.public_id, password=sample_room.password), fake_user_id
        )


async def test_join_room_already_in_room_rejoins(create_user, create_room, room_controller: RoomController):
    """Joining a room a second time succeeds (re-join updates heartbeat)."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)

    # Act — join again (should succeed as a re-join)
    updated = await room_controller.join_room(
        RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id
    )

    # Assert — still only 2 links (no duplicate)
    links = (await room_controller.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room.id))).all()
    assert len(links) == 2
    assert updated.id == room.id


async def test_leave_room_success(create_user, create_room, room_controller: RoomController):
    """Voluntary leave deletes the RoomUserLink entirely while the room stays ACTIVE."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    room_id = room.id
    joiner_id = joiner.id
    room_controller.session.expire_all()

    # Act
    updated = await room_controller.leave_room(room_id, joiner_id)

    # Assert — link is deleted, room stays active
    assert updated.type == RoomType.ACTIVE
    link = (
        await room_controller.session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == joiner_id)
        )
    ).first()
    assert link is None


async def test_leave_room_owner_deactivates(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """When the owner leaves, the room type becomes INACTIVE."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    updated = await room_controller.leave_room(sample_room.id, sample_owner.id)

    # Assert
    assert updated.type == RoomType.INACTIVE


async def test_leave_room_owner_transfers_to_remaining_player(
    create_user, create_room, room_controller: RoomController
):
    """When the owner leaves but other players remain, ownership transfers to the next connected player."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    player2 = await create_user(username="player2", email="player2@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), player2.id)
    room_id = room.id
    owner_id = owner.id
    player2_id = player2.id
    room_controller.session.expire_all()

    # Act
    updated = await room_controller.leave_room(room_id, owner_id)

    # Assert — room stays ACTIVE and ownership transferred to player2
    assert updated.type == RoomType.ACTIVE
    assert updated.owner_id == player2_id


async def test_leave_room_not_found(room_controller: RoomController, create_user):
    """Leaving a non-existent room raises RoomNotFoundError."""

    # Arrange
    user = await create_user(username="user", email="user@test.com")
    fake_room_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.leave_room(fake_room_id, user.id)


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
        await room_controller.leave_room(sample_room.id, other.id)


async def test_leave_room_already_left(create_user, create_room, room_controller: RoomController):
    """Leaving a room twice raises UserNotInRoomError on the second attempt."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    room_id = room.id
    joiner_id = joiner.id
    room_controller.session.expire_all()  # Clear identity map so leave_room re-fetches Room.users
    await room_controller.leave_room(room_id, joiner_id)

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        await room_controller.leave_room(room_id, joiner_id)


async def test_delete_room_success(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """Deleting a room soft-deactivates it and removes all member links."""

    # Arrange — provided by sample_owner and sample_room fixtures

    # Act
    await room_controller.delete_room(sample_room.id, sample_owner.id)

    # Assert — room is soft-deleted (INACTIVE), not hard-deleted
    room = await room_controller.get_room_by_id(sample_room.id)
    assert room.type == RoomType.INACTIVE
    assert room.active_game_id is None


async def test_delete_room_not_found(room_controller: RoomController):
    """Deleting a non-existent room raises RoomNotFoundError."""

    # Arrange
    fake_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.delete_room(fake_id, uuid4())


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


async def test_join_room_as_spectator_success(create_user, create_room, room_controller: RoomController):
    """Joining as spectator creates a RoomUserLink with is_spectator=True."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    spectator = await create_user(username="spectator", email="spectator@test.com")
    room = await create_room(owner=owner)

    # Act
    updated = await room_controller.join_room_as_spectator(room.id, spectator.id, room.password)

    # Assert
    assert updated.id == room.id
    link = (
        await room_controller.session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == spectator.id)
        )
    ).one()
    assert link.is_spectator is True
    assert link.connected is True


async def test_join_room_as_spectator_user_not_found(
    sample_owner: User,  # noqa: ARG001
    sample_room: Room,
    room_controller: RoomController,
):
    """Joining as spectator with a non-existent user raises UserNotFoundError."""

    # Arrange
    fake_user_id = uuid4()

    # Act / Assert
    with pytest.raises(UserNotFoundError):
        await room_controller.join_room_as_spectator(sample_room.id, fake_user_id, sample_room.password)


async def test_join_room_as_spectator_room_not_found(create_user, room_controller: RoomController):
    """Joining as spectator to a non-existent room raises RoomNotFoundError."""

    # Arrange
    user = await create_user(username="spectator", email="spectator@test.com")
    fake_room_id = uuid4()

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await room_controller.join_room_as_spectator(fake_room_id, user.id, "1234")


async def test_update_room_settings_success(
    sample_owner: User,
    sample_room: Room,
    room_controller: RoomController,
):
    """Updating room settings persists the settings dict."""

    # Arrange
    settings = RoomSettings(description_timer=120, voting_timer=90)

    # Act
    result = await room_controller.update_room_settings(sample_room.id, sample_owner.id, settings)

    # Assert
    assert result.room_id == str(sample_room.id)
    assert result.settings.description_timer == 120
    assert result.settings.voting_timer == 90


async def test_update_room_settings_not_host(create_user, create_room, room_controller: RoomController):
    """Updating room settings as non-host raises BaseError(403)."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    non_host = await create_user(username="nonhost", email="nonhost@test.com")
    room = await create_room(owner=owner)

    # Act / Assert
    with pytest.raises(BaseError) as exc_info:
        await room_controller.update_room_settings(room.id, non_host.id, RoomSettings(description_timer=120))
    assert exc_info.value.status_code == 403


async def test_rematch_success(sample_owner: User, sample_room: Room, room_controller: RoomController):  # noqa: ARG001
    """Rematch clears active_game_id and returns lobby status."""

    # Arrange — provided by fixtures

    # Act
    result = await room_controller.rematch(sample_room.id, sample_owner.id)

    # Assert
    assert result.room_id == str(sample_room.id)
    assert result.status == "lobby"


async def test_get_room_state_success(sample_owner: User, sample_room: Room, room_controller: RoomController):
    """Getting room state returns a model with players array and correct structure."""

    # Arrange — provided by fixtures

    # Act
    state = await room_controller.get_room_state(sample_room.id, sample_owner.id)

    # Assert
    assert state.id == str(sample_room.id)
    assert state.owner_id == str(sample_owner.id)
    assert isinstance(state.players, list)
    assert len(state.players) >= 1
    owner_player = next(p for p in state.players if p.user_id == str(sample_owner.id))
    assert owner_player.is_host is True
    assert owner_player.is_connected is True


# === Leave / Rejoin / Ghost Room Prevention ===


async def test_voluntary_leave_no_active_room(create_user, create_room, room_controller: RoomController):
    """After voluntary leave, get_active_room_for_user returns None — no rejoin banner."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    room_id = room.id
    joiner_id = joiner.id
    room_controller.session.expire_all()

    # Act
    await room_controller.leave_room(room_id, joiner_id)

    # Assert — no active room, player is free
    active = await room_controller.get_active_room_for_user(joiner_id)
    assert active is None


async def test_voluntary_leave_can_join_new_room(create_user, create_room, room_controller: RoomController):
    """After voluntary leave, player can join a different room without conflict."""

    # Arrange
    owner1 = await create_user(username="owner1", email="owner1@test.com")
    owner2 = await create_user(username="owner2", email="owner2@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room1 = await create_room(owner=owner1)
    room2 = await create_room(owner=owner2)
    await room_controller.join_room(RoomJoin(public_room_id=room1.public_id, password=room1.password), joiner.id)
    room1_id = room1.id
    room2_id = room2.id
    room2_public_id = room2.public_id
    room2_password = room2.password
    joiner_id = joiner.id
    room_controller.session.expire_all()

    # Act — leave room1, join room2
    await room_controller.leave_room(room1_id, joiner_id)
    await room_controller.join_room(RoomJoin(public_room_id=room2_public_id, password=room2_password), joiner_id)

    # Assert — active room is room2
    active = await room_controller.get_active_room_for_user(joiner_id)
    assert active is not None
    assert active.room_id == str(room2_id)
    assert active.is_connected is True


async def test_voluntary_leave_can_create_new_room(create_user, create_room, room_controller: RoomController):
    """After voluntary leave, player can create a new room without UserAlreadyInRoomError."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    player = await create_user(username="player", email="player@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), player.id)
    room_id = room.id
    player_id = player.id
    room_controller.session.expire_all()

    # Act — leave, then create own room
    await room_controller.leave_room(room_id, player_id)
    new_room = await room_controller.create_room(owner_id=player_id, game_type=GameType.UNDERCOVER)

    # Assert
    assert new_room.owner_id == player_id
    active = await room_controller.get_active_room_for_user(player_id)
    assert active is not None
    assert active.room_id == str(new_room.id)


async def test_disconnect_shows_active_room(create_user, create_room, room_controller: RoomController):
    """A disconnected player (connected=False, link preserved) still sees active room for rejoin."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    joiner_id = joiner.id

    # Simulate disconnect (heartbeat staleness sets connected=False, NOT a voluntary leave)
    link = (
        await room_controller.session.exec(
            select(RoomUserLink).where(RoomUserLink.user_id == joiner_id, RoomUserLink.connected == True)  # noqa: E712
        )
    ).one()
    link.connected = False
    room_controller.session.add(link)
    await room_controller.session.commit()

    # Assert — active room returned with is_connected=False (rejoin banner should show)
    active = await room_controller.get_active_room_for_user(joiner_id)
    assert active is not None
    assert active.room_id == str(room.id)
    assert active.is_connected is False


async def test_disconnect_then_rejoin(create_user, create_room, room_controller: RoomController):
    """A disconnected player can rejoin the same room and become connected again."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    joiner_id = joiner.id
    public_id = room.public_id
    room_pw = room.password

    # Simulate disconnect
    link = (
        await room_controller.session.exec(
            select(RoomUserLink).where(RoomUserLink.user_id == joiner_id, RoomUserLink.connected == True)  # noqa: E712
        )
    ).one()
    link.connected = False
    room_controller.session.add(link)
    await room_controller.session.commit()

    # Act — rejoin
    await room_controller.join_room(RoomJoin(public_room_id=public_id, password=room_pw), joiner_id)

    # Assert — connected again
    active = await room_controller.get_active_room_for_user(joiner_id)
    assert active is not None
    assert active.is_connected is True


async def test_disconnect_leave_via_banner_frees_player(create_user, create_room, room_controller: RoomController):
    """A disconnected player who clicks 'Leave' on the rejoin banner is fully freed."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    room_id = room.id
    joiner_id = joiner.id

    # Simulate disconnect
    link = (
        await room_controller.session.exec(
            select(RoomUserLink).where(RoomUserLink.user_id == joiner_id, RoomUserLink.connected == True)  # noqa: E712
        )
    ).one()
    link.connected = False
    room_controller.session.add(link)
    await room_controller.session.commit()
    room_controller.session.expire_all()

    # Act — player clicks "Leave" on the rejoin banner
    await room_controller.leave_room(room_id, joiner_id)

    # Assert — fully freed, no active room
    active = await room_controller.get_active_room_for_user(joiner_id)
    assert active is None

    # Can create a new room
    new_room = await room_controller.create_room(owner_id=joiner_id, game_type=GameType.UNDERCOVER)
    assert new_room.owner_id == joiner_id


async def test_voluntary_leave_can_rejoin_via_code(create_user, create_room, room_controller: RoomController):
    """After voluntary leave, player can still rejoin the same room using the room code."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    joiner = await create_user(username="joiner", email="joiner@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), joiner.id)
    room_id = room.id
    joiner_id = joiner.id
    public_id = room.public_id
    room_pw = room.password
    room_controller.session.expire_all()

    # Act — leave, then rejoin with room code
    await room_controller.leave_room(room_id, joiner_id)
    await room_controller.join_room(RoomJoin(public_room_id=public_id, password=room_pw), joiner_id)

    # Assert — back in the room
    active = await room_controller.get_active_room_for_user(joiner_id)
    assert active is not None
    assert active.room_id == str(room_id)
    assert active.is_connected is True


async def test_no_ghost_room_after_all_leave(create_user, create_room, room_controller: RoomController):
    """When all players voluntarily leave, the room becomes INACTIVE — no ghost room."""

    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    player2 = await create_user(username="player2", email="player2@test.com")
    room = await create_room(owner=owner)
    await room_controller.join_room(RoomJoin(public_room_id=room.public_id, password=room.password), player2.id)
    room_id = room.id
    owner_id = owner.id
    player2_id = player2.id
    room_controller.session.expire_all()

    # Act — both leave
    await room_controller.leave_room(room_id, player2_id)
    room_controller.session.expire_all()
    await room_controller.leave_room(room_id, owner_id)

    # Assert — room is INACTIVE, no active room for either
    db_room = (await room_controller.session.exec(select(Room).where(Room.id == room_id))).one()
    assert db_room.type == RoomType.INACTIVE
    assert await room_controller.get_active_room_for_user(owner_id) is None
    assert await room_controller.get_active_room_for_user(player2_id) is None
