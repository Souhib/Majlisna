"""A kick is a ban for the room's lifetime, and it rotates the PIN (owner rule (c)).

BR-20 / SEC F04: ``kick_player`` only deleted the ``RoomUserLink``, so the kicked
player was back in the lobby a second later with the same code and PIN — the host's
only way to be rid of a troll was to open a new room. A kick now records a ``RoomBan``
(join and spectate answer ``RoomBannedError``, 403), rotates the room PIN (so the
share link the troll holds stops working for anyone they pass it to), and the host
can list and lift the bans. Lifting does not re-seat the player and does not restore
the old PIN.
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
    NotRoomHostError,
    RoomBannedError,
    RoomBanNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)


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


async def _kicked_room(session: AsyncSession, create_user, create_room) -> dict:
    """A room whose host kicked a guest: ids, code and the PIN from BEFORE the kick."""
    host = await create_user(username="host", email="host@test.com")
    guest = await create_user(username="guest", email="guest@test.com")
    room = await create_room(owner=host)
    ids = {"host": host.id, "guest": guest.id, "room": room.id, "code": room.public_id, "old_pin": room.password}
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"])
    await controller.kick_player(ids["room"], ids["host"], ids["guest"])
    return ids


# ========== The kick ==========


async def test_a_kick_bans_the_player_and_rotates_the_pin(session: AsyncSession, create_user, create_room):
    """One ban row naming who banned, the link gone, and a new 4-digit PIN."""
    # Prepare / Act
    ids = await _kicked_room(session, create_user, create_room)

    # Assert
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
    ids = await _kicked_room(session, create_user, create_room)
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
    ids = await _kicked_room(session, create_user, create_room)
    supplied = ids["old_pin"] if pin == "old" else (await _fresh_room(session, ids["room"])).password

    # Act / Assert
    with pytest.raises(RoomBannedError):
        await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=supplied), ids["guest"])

    assert await _link(session, ids["room"], ids["guest"]) is None


async def test_a_banned_player_cannot_come_back_as_a_spectator(session: AsyncSession, create_user, create_room):
    """Spectating is not a way around the ban."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    new_pin = (await _fresh_room(session, ids["room"])).password

    # Act / Assert
    with pytest.raises(RoomBannedError):
        await RoomController(session).join_room_as_spectator(ids["room"], ids["guest"], new_pin)

    assert await _link(session, ids["room"], ids["guest"]) is None


async def test_the_old_pin_no_longer_admits_anyone(session: AsyncSession, create_user, create_room):
    """The share link the kicked player holds is dead for whoever they pass it to."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    friend_of_guest = await create_user(username="friendofguest", email="fog@test.com")
    newcomer = await create_user(username="newcomer", email="newcomer@test.com")
    new_pin = (await _fresh_room(session, ids["room"])).password
    controller = RoomController(session)

    # Act / Assert
    with pytest.raises(WrongRoomPasswordError):
        await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), friend_of_guest.id)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=new_pin), newcomer.id)
    assert await _link(session, ids["room"], newcomer.id) is not None


async def test_kicking_a_player_who_is_not_seated_bans_nobody(session: AsyncSession, create_user, create_room):
    """No link, no kick: UserNotInRoomError, and neither a ban nor a new PIN."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    stranger = await create_user(username="stranger", email="stranger@test.com")
    room = await create_room(owner=host)
    room_id, host_id, old_pin = room.id, host.id, room.password

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        await RoomController(session).kick_player(room_id, host_id, stranger.id)

    assert await _bans(session, room_id) == []
    assert (await _fresh_room(session, room_id)).password == old_pin


async def test_kicking_a_returning_player_twice_keeps_one_ban(session: AsyncSession, create_user, create_room):
    """The ban is idempotent on (room, user): a lifted-then-re-kicked player has one row."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    controller = RoomController(session)
    await controller.lift_ban(ids["room"], ids["host"], ids["guest"])
    pin = (await _fresh_room(session, ids["room"])).password
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=pin), ids["guest"])

    # Act
    await controller.kick_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]
    assert (await _fresh_room(session, ids["room"])).password != pin


# ========== Listing and lifting ==========


async def test_the_host_lists_the_bans_with_the_username(session: AsyncSession, create_user, create_room):
    """GET /rooms/{id}/bans: who, by name, and since when."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

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
    ids = await _kicked_room(session, create_user, create_room)
    controller = RoomController(session)
    new_pin = (await _fresh_room(session, ids["room"])).password

    # Act
    response = await controller.lift_ban(ids["room"], ids["host"], ids["guest"])

    # Assert — lifted, not re-seated, PIN unchanged
    assert response.status == "lifted"
    assert await _bans(session, ids["room"]) == []
    assert await _link(session, ids["room"], ids["guest"]) is None
    assert (await _fresh_room(session, ids["room"])).password == new_pin

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
    ids = await _kicked_room(session, create_user, create_room)
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
    """DELETE on a player who is not banned: RoomBanNotFoundError (404)."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    other = await create_user(username="other", email="other@test.com")
    room = await create_room(owner=host)

    # Act / Assert
    with pytest.raises(RoomBanNotFoundError) as caught:
        await RoomController(session).lift_ban(room.id, host.id, other.id)
    assert caught.value.status_code == 404


async def test_a_ban_holds_only_in_its_own_room(session: AsyncSession, create_user, create_room):
    """Banned from the host's room is not banned from every room."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    other_host = await create_user(username="otherhost", email="otherhost@test.com")
    other_room = await create_room(owner=other_host)

    # Act
    await RoomController(session).join_room(
        RoomJoin(public_room_id=other_room.public_id, password=other_room.password), ids["guest"]
    )

    # Assert
    assert await _link(session, other_room.id, ids["guest"]) is not None


# ========== A kick mid-game ==========


async def test_the_player_kicked_from_a_running_undercover_game_is_a_leaver(
    session: AsyncSession, setup_undercover_game
):
    """Owner rule (b): a kicked player gets neither a win nor a loss — they are in left_player_ids."""
    # Prepare
    setup = await setup_undercover_game(4)
    room_id, host_id, target_id = setup["room"].id, setup["users"][0].id, setup["users"][3].id
    started = await UndercoverGameController(session).create_and_start(room_id, host_id)

    # Act
    await RoomController(session).kick_player(room_id, host_id, target_id)

    # Assert
    session.expunge_all()
    game = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    assert game.live_state is not None
    assert str(target_id) in game.live_state.get(LEFT_PLAYER_IDS_KEY, [])
    assert [ban.user_id for ban in await _bans(session, room_id)] == [target_id]
