"""Kick and ban are two host actions (owner decision, 2 November 2026).

A KICK is for someone who left without quitting: it removes the seat (mid-game, the
departure rules: a leaver, neither a win nor a loss), and that is all. No ban, no new
PIN: the player comes back with the same code and PIN, or through an invite.

A BAN is for someone the table does not want back: everything a kick does, plus a
``RoomBan`` row (join and spectate answer ``RoomBannedError``, 403), a new PIN (a banned
player could otherwise come back under another account with the share link they hold),
and the room's invites they sent or were sent are deleted. The host lists and lifts the
bans; lifting re-seats nobody and does not restore the old PIN.

It replaces owner rule (c), "a kick bans for the room's lifetime and rotates the PIN"
(BR-20, SEC F04: the kick used to be a removal undone a second later, so every kick
became a ban; the owner wants both).
"""

from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import LEFT_PLAYER_IDS_KEY
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomJoin
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.error import (
    CannotBanYourselfError,
    CannotKickYourselfError,
    NotRoomHostError,
    RoomBannedError,
    RoomBanNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)

REMOVALS = ["kick", "ban"]


async def _fresh_room(session: AsyncSession, room_id: UUID) -> Room:
    session.expunge_all()
    return (await session.exec(select(Room).where(Room.id == room_id))).one()


async def _link(session: AsyncSession, room_id: UUID, user_id: UUID) -> RoomUserLink | None:
    session.expunge_all()
    return (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
        )
    ).first()


async def _bans(session: AsyncSession, room_id: UUID) -> list[RoomBan]:
    session.expunge_all()
    return list((await session.exec(select(RoomBan).where(RoomBan.room_id == room_id))).all())


async def _seated_room(session: AsyncSession, create_user, create_room) -> dict:
    """A host and a seated guest: ids, the room's code and its PIN."""
    host = await create_user(username="host", email="host@test.com")
    guest = await create_user(username="guest", email="guest@test.com")
    room = await create_room(owner=host)
    ids = {"host": host.id, "guest": guest.id, "room": room.id, "code": room.public_id, "old_pin": room.password}
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"])
    return ids


async def _remove(session: AsyncSession, ids: dict, how: str) -> None:
    """The host takes the guest's seat: a kick (Remove) or a ban (Ban)."""
    controller = RoomController(session)
    if how == "kick":
        await controller.kick_player(ids["room"], ids["host"], ids["guest"])
    else:
        await controller.ban_player(ids["room"], ids["host"], ids["guest"])


async def _kicked_room(session: AsyncSession, create_user, create_room) -> dict:
    ids = await _seated_room(session, create_user, create_room)
    await _remove(session, ids, "kick")
    return ids


async def _banned_room(session: AsyncSession, create_user, create_room) -> dict:
    ids = await _seated_room(session, create_user, create_room)
    await _remove(session, ids, "ban")
    return ids


# ========== Both: the seat goes ==========


@pytest.mark.parametrize("how", REMOVALS)
async def test_a_removal_takes_the_seat(session: AsyncSession, create_user, create_room, how: str):
    """Kick or ban, the guest's link is gone and the room state no longer lists them."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)

    # Act
    await _remove(session, ids, how)

    # Assert
    assert await _link(session, ids["room"], ids["guest"]) is None
    state = await RoomController(session).get_room_state(ids["room"], ids["host"], update_heartbeat=False)
    assert [player.user_id for player in state.players] == [str(ids["host"])]


@pytest.mark.parametrize("how", REMOVALS)
async def test_only_the_host_removes_and_the_target_stays(session: AsyncSession, create_user, create_room, how: str):
    """A member's kick or ban is NotRoomHostError (403): no seat lost, no ban, the same PIN."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)
    member = await create_user(username="member", email="member@test.com")
    member_id = member.id
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), member_id)
    controller = RoomController(session)

    # Act / Assert
    with pytest.raises(NotRoomHostError):
        if how == "kick":
            await controller.kick_player(ids["room"], member_id, ids["guest"])
        else:
            await controller.ban_player(ids["room"], member_id, ids["guest"])

    assert await _link(session, ids["room"], ids["guest"]) is not None
    assert await _bans(session, ids["room"]) == []
    assert (await _fresh_room(session, ids["room"])).password == ids["old_pin"]


@pytest.mark.parametrize(("how", "error"), [("kick", CannotKickYourselfError), ("ban", CannotBanYourselfError)])
async def test_the_host_never_removes_themself(session: AsyncSession, create_user, create_room, how: str, error: type):
    """400 for a kick or a ban of the host by the host; the host keeps the seat."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)
    controller = RoomController(session)

    # Act / Assert
    with pytest.raises(error) as caught:
        if how == "kick":
            await controller.kick_player(ids["room"], ids["host"], ids["host"])
        else:
            await controller.ban_player(ids["room"], ids["host"], ids["host"])

    assert caught.value.status_code == 400
    assert await _link(session, ids["room"], ids["host"]) is not None
    assert await _bans(session, ids["room"]) == []


@pytest.mark.parametrize("how", REMOVALS)
async def test_removing_a_player_who_is_not_seated_changes_nothing(
    session: AsyncSession, create_user, create_room, how: str
):
    """No link, no removal: UserNotInRoomError, and neither a ban nor a new PIN."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    stranger = await create_user(username="stranger", email="stranger@test.com")
    room = await create_room(owner=host)
    room_id, host_id, old_pin = room.id, host.id, room.password
    controller = RoomController(session)

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        if how == "kick":
            await controller.kick_player(room_id, host_id, stranger.id)
        else:
            await controller.ban_player(room_id, host_id, stranger.id)

    assert await _bans(session, room_id) == []
    assert (await _fresh_room(session, room_id)).password == old_pin


# ========== The kick: removed, free to come back ==========


async def test_a_kick_bans_nobody_and_keeps_the_pin(session: AsyncSession, create_user, create_room):
    """The player left without quitting: no RoomBan, and the code and PIN stay what they were."""
    # Prepare / Act
    ids = await _kicked_room(session, create_user, create_room)

    # Assert
    assert await _bans(session, ids["room"]) == []
    assert (await _fresh_room(session, ids["room"])).password == ids["old_pin"]
    link = await RoomController(session).get_share_link(ids["room"], ids["host"])
    assert link.password == ids["old_pin"]


async def test_a_kicked_player_comes_back_with_the_same_code_and_pin(session: AsyncSession, create_user, create_room):
    """The share link they hold still opens the room: a seat again, connected."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act
    room = await RoomController(session).join_room(
        RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"]
    )

    # Assert
    assert room.id == ids["room"]
    link = await _link(session, ids["room"], ids["guest"])
    assert link is not None
    assert link.connected is True


async def test_a_kicked_player_may_come_back_as_a_spectator(session: AsyncSession, create_user, create_room):
    """Watching is no door a kick closed either."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act
    await RoomController(session).join_room_as_spectator(ids["room"], ids["guest"], ids["old_pin"])

    # Assert
    link = await _link(session, ids["room"], ids["guest"])
    assert link is not None
    assert link.is_spectator is True


async def test_the_host_lists_no_ban_after_a_kick(session: AsyncSession, create_user, create_room):
    """The host's list of banned players is for bans: a kick does not appear in it."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act
    bans = await RoomController(session).list_bans(ids["room"], ids["host"])

    # Assert
    assert bans == []


# ========== The ban: removed, kept out until lifted ==========


async def test_a_ban_records_who_banned_and_rotates_the_pin(session: AsyncSession, create_user, create_room):
    """One ban row naming who banned, the link gone, and a new 4-digit PIN; the answer is the ban."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)

    # Act
    view = await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    assert (view.user_id, view.username) == (ids["guest"], "guest")
    assert view.banned_at is not None
    bans = await _bans(session, ids["room"])
    assert [(ban.user_id, ban.banned_by) for ban in bans] == [(ids["guest"], ids["host"])]
    assert await _link(session, ids["room"], ids["guest"]) is None
    room = await _fresh_room(session, ids["room"])
    assert room.password != ids["old_pin"]
    assert len(room.password) == 4
    assert room.password.isdigit()


async def test_the_room_state_and_the_share_link_carry_the_new_pin(session: AsyncSession, create_user, create_room):
    """What the host's lobby shows (room_state) and what it shares (share link) is the new PIN."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    controller = RoomController(session)

    # Act
    state = await controller.get_room_state(ids["room"], ids["host"], update_heartbeat=False)
    link = await controller.get_share_link(ids["room"], ids["host"])

    # Assert
    new_pin = (await _fresh_room(session, ids["room"])).password
    assert state.password == new_pin
    assert link.password == new_pin
    assert new_pin != ids["old_pin"]
    assert all(player.user_id != str(ids["guest"]) for player in state.players)


@pytest.mark.parametrize("pin", ["old", "new"])
async def test_a_banned_player_cannot_rejoin_with_any_pin(session: AsyncSession, create_user, create_room, pin: str):
    """The ban is checked before the PIN: the old one and the new one both answer 403."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    supplied = ids["old_pin"] if pin == "old" else (await _fresh_room(session, ids["room"])).password

    # Act / Assert
    with pytest.raises(RoomBannedError) as caught:
        await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=supplied), ids["guest"])

    assert caught.value.status_code == 403
    assert await _link(session, ids["room"], ids["guest"]) is None


async def test_a_banned_player_cannot_come_back_as_a_spectator(session: AsyncSession, create_user, create_room):
    """Spectating is not a way around the ban."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    new_pin = (await _fresh_room(session, ids["room"])).password

    # Act / Assert
    with pytest.raises(RoomBannedError):
        await RoomController(session).join_room_as_spectator(ids["room"], ids["guest"], new_pin)

    assert await _link(session, ids["room"], ids["guest"]) is None


async def test_the_old_pin_no_longer_admits_anyone_after_a_ban(session: AsyncSession, create_user, create_room):
    """The share link the banned player holds is dead for whoever they pass it to (another account)."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    friend_of_guest = await create_user(username="friendofguest", email="fog@test.com")
    newcomer = await create_user(username="newcomer", email="newcomer@test.com")
    new_pin = (await _fresh_room(session, ids["room"])).password
    controller = RoomController(session)

    # Act / Assert
    with pytest.raises(WrongRoomPasswordError):
        await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), friend_of_guest.id)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=new_pin), newcomer.id)
    assert await _link(session, ids["room"], newcomer.id) is not None


async def test_banning_a_returning_player_twice_keeps_one_ban(session: AsyncSession, create_user, create_room):
    """The ban is idempotent on (room, user): a lifted-then-re-banned player has one row, and a new PIN."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    controller = RoomController(session)
    await controller.lift_ban(ids["room"], ids["host"], ids["guest"])
    pin = (await _fresh_room(session, ids["room"])).password
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=pin), ids["guest"])

    # Act
    await controller.ban_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]
    assert (await _fresh_room(session, ids["room"])).password != pin


async def test_a_ban_after_a_kick_and_a_return_bans_and_rotates(session: AsyncSession, create_user, create_room):
    """Kicked, back with the same PIN, then banned: the second removal is the one that keeps them out."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"])

    # Act
    await controller.ban_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]
    assert (await _fresh_room(session, ids["room"])).password != ids["old_pin"]
    with pytest.raises(RoomBannedError):
        await RoomController(session).join_room(
            RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"]
        )


# ========== Listing and lifting ==========


async def test_the_host_lists_the_bans_with_the_username(session: AsyncSession, create_user, create_room):
    """GET /rooms/{id}/bans: who, by name, and since when."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)

    # Act
    bans = await RoomController(session).list_bans(ids["room"], ids["host"])

    # Assert
    assert len(bans) == 1
    assert bans[0].user_id == ids["guest"]
    assert bans[0].username == "guest"
    assert bans[0].banned_at is not None


async def test_after_the_host_lifts_the_ban_the_new_pin_admits_the_player(
    session: AsyncSession, create_user, create_room
):
    """Lifting removes the row; the player comes back only through a fresh join, with the new PIN."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    controller = RoomController(session)
    new_pin = (await _fresh_room(session, ids["room"])).password

    # Act
    response = await controller.lift_ban(ids["room"], ids["host"], ids["guest"])

    # Assert — lifted, not re-seated, PIN unchanged
    assert response.status == "lifted"
    assert await _bans(session, ids["room"]) == []
    assert await _link(session, ids["room"], ids["guest"]) is None
    assert (await _fresh_room(session, ids["room"])).password == new_pin
    with pytest.raises(WrongRoomPasswordError):
        await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"])

    # Act — the player rejoins with the new PIN
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=new_pin), ids["guest"])

    # Assert
    link = await _link(session, ids["room"], ids["guest"])
    assert link is not None
    assert link.connected is True


@pytest.mark.parametrize("action", ["list", "lift"])
async def test_only_the_host_reads_or_lifts_the_bans(session: AsyncSession, create_user, create_room, action: str):
    """A member's GET or DELETE on the bans is a 403, and the ban stays."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    member = await create_user(username="member", email="member@test.com")
    member_id = member.id
    pin = (await _fresh_room(session, ids["room"])).password
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=pin), member_id)

    # Act / Assert
    with pytest.raises(NotRoomHostError):
        if action == "list":
            await controller.list_bans(ids["room"], member_id)
        else:
            await controller.lift_ban(ids["room"], member_id, ids["guest"])

    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]


async def test_lifting_an_absent_ban_answers_not_found(session: AsyncSession, create_user, create_room):
    """DELETE on a player who is not banned (a kicked one included): RoomBanNotFoundError (404)."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act / Assert
    with pytest.raises(RoomBanNotFoundError) as caught:
        await RoomController(session).lift_ban(ids["room"], ids["host"], ids["guest"])
    assert caught.value.status_code == 404


async def test_a_ban_holds_only_in_its_own_room(session: AsyncSession, create_user, create_room):
    """Banned from the host's room is not banned from every room."""
    # Prepare
    ids = await _banned_room(session, create_user, create_room)
    other_host = await create_user(username="otherhost", email="otherhost@test.com")
    other_room = await create_room(owner=other_host)

    # Act
    await RoomController(session).join_room(
        RoomJoin(public_room_id=other_room.public_id, password=other_room.password), ids["guest"]
    )

    # Assert
    assert await _link(session, other_room.id, ids["guest"]) is not None


# ========== A removal mid-game ==========


@pytest.mark.parametrize("how", REMOVALS)
async def test_the_player_removed_from_a_running_undercover_game_is_a_leaver(
    session: AsyncSession, setup_undercover_game, how: str
):
    """Owner rule (b): kicked or banned, the player gets neither a win nor a loss — they are in left_player_ids."""
    # Prepare
    setup = await setup_undercover_game(4)
    room_id, host_id, target_id = setup["room"].id, setup["users"][0].id, setup["users"][3].id
    started = await UndercoverGameController(session).create_and_start(room_id, host_id)

    # Act
    if how == "kick":
        await RoomController(session).kick_player(room_id, host_id, target_id)
    else:
        await RoomController(session).ban_player(room_id, host_id, target_id)

    # Assert
    session.expunge_all()
    game = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    assert game.live_state is not None
    assert str(target_id) in game.live_state.get(LEFT_PLAYER_IDS_KEY, [])
    expected_bans = [] if how == "kick" else [target_id]
    assert [ban.user_id for ban in await _bans(session, room_id)] == expected_bans
