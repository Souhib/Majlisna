"""Ban after removal (owner request, 3 November 2026).

A host who pressed Remove (a kick) and then decided "we don't want them back" could not
ban: a ban needed a seat (``UserNotInRoomError``, 404), and the removed player had none
until they sat down again. The kick now leaves a record (``RoomRemoval``: the room, the
player, the host, when), the host lists the removed players (``list_removals``: neither
banned nor seated again, newest first), and the ban takes a seated player OR one with a
removal record. For the latter: the ``RoomBan``, the invites and the new PIN exactly as for
a seated player, the record deleted, and no departure (there is no seat to take).

The record goes when the player sits down again (a join with the code and PIN, an invite,
a spectator's seat), when they are banned, with the room and with the account. Anyone else
(never seated, or gone by themselves) still answers ``UserNotInRoomError``.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import utc_instant
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.user import UserController
from majlisna.api.models.game import GameStatus
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomJoin, RoomType
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.room_invite import RoomInvite
from majlisna.api.models.room_removal import RoomRemoval
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.error import NotRoomHostError, RoomBannedError, UserNotInRoomError

# How long a request is left waiting on a row lock before the other side commits.
LOCK_WAIT_SECONDS = 0.6


# ─── Helpers ──────────────────────────────────────────────────────────────────


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


async def _removals(session: AsyncSession, room_id: UUID) -> list[RoomRemoval]:
    session.expunge_all()
    return list((await session.exec(select(RoomRemoval).where(RoomRemoval.room_id == room_id))).all())


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


async def _kicked_room(session: AsyncSession, create_user, create_room) -> dict:
    """The guest seated, then removed by the host (Remove)."""
    ids = await _seated_room(session, create_user, create_room)
    await RoomController(session).kick_player(ids["room"], ids["host"], ids["guest"])
    return ids


async def _seat_with_the_old_pin(session: AsyncSession, ids: dict, user_id: UUID) -> None:
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), user_id)


# ─── The kick leaves a record ─────────────────────────────────────────────────


async def test_a_kick_records_who_was_removed_and_by_whom(session: AsyncSession, create_user, create_room):
    """One record per kick: the room, the player, the host, and when (UTC)."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)
    before = datetime.now(UTC)

    # Act
    await RoomController(session).kick_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    records = await _removals(session, ids["room"])
    assert [(r.user_id, r.removed_by) for r in records] == [(ids["guest"], ids["host"])]
    assert utc_instant(records[0].updated_at) >= before - timedelta(seconds=1)


async def test_the_host_lists_the_removed_players_newest_first_with_their_name(
    session: AsyncSession, create_user, create_room
):
    """GET /rooms/{id}/removals: who, by name, since when (aware UTC), the latest removal first."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)
    second = await create_user(username="second", email="second@test.com")
    second_id = second.id
    await _seat_with_the_old_pin(session, ids, second_id)
    controller = RoomController(session)
    await controller.kick_player(ids["room"], ids["host"], ids["guest"])
    await controller.kick_player(ids["room"], ids["host"], second_id)

    # Act
    removed = await RoomController(session).list_removals(ids["room"], ids["host"])

    # Assert
    assert [(view.user_id, view.username) for view in removed] == [(second_id, "second"), (ids["guest"], "guest")]
    assert all(view.removed_at.tzinfo is not None for view in removed)
    assert removed[0].removed_at >= removed[1].removed_at


async def test_a_kick_refreshes_a_record_left_behind_rather_than_doubling_it(
    session: AsyncSession, create_user, create_room
):
    """One record per (room, player): a record a race left behind is refreshed by the next kick
    (the latest host, the latest time), never a second row nor an IntegrityError."""
    # Prepare: the guest is seated, and an old record of theirs is still there
    ids = await _seated_room(session, create_user, create_room)
    stale = datetime.now(UTC) - timedelta(hours=1)
    session.add(
        RoomRemoval(room_id=ids["room"], user_id=ids["guest"], removed_by=None, created_at=stale, updated_at=stale)
    )
    await session.commit()

    # Act
    await RoomController(session).kick_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    records = await _removals(session, ids["room"])
    assert [(r.user_id, r.removed_by) for r in records] == [(ids["guest"], ids["host"])]
    assert utc_instant(records[0].updated_at) > stale + timedelta(minutes=59)


@pytest.mark.parametrize("door", ["join", "invite", "spectate"])
async def test_a_removed_player_who_sits_down_again_leaves_the_list(
    session: AsyncSession, create_user, create_room, door: str
):
    """A join with the code and PIN, an invite or a spectator's seat: the record goes with it."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    controller = RoomController(session)

    # Act
    if door == "join":
        await _seat_with_the_old_pin(session, ids, ids["guest"])
    elif door == "invite":
        friends = FriendController(session)
        request = await friends.send_request(ids["host"], ids["guest"])
        await friends.accept_request(request.id, ids["guest"])
        sent = await controller.invite_friend_to_room(ids["room"], ids["host"], ids["guest"])
        await RoomController(session).accept_invite(sent.invite.id, ids["guest"])
    else:
        await controller.join_room_as_spectator(ids["room"], ids["guest"], ids["old_pin"])

    # Assert
    assert await _link(session, ids["room"], ids["guest"]) is not None
    assert await _removals(session, ids["room"]) == []
    assert await RoomController(session).list_removals(ids["room"], ids["host"]) == []


async def test_the_list_leaves_out_a_banned_or_seated_player_whatever_records_remain(
    session: AsyncSession, create_user, create_room
):
    """Records a race left behind never list a banned player, nor one at the table."""
    # Prepare: the guest is banned; a member is seated; both still have a record
    ids = await _seated_room(session, create_user, create_room)
    member = await create_user(username="member", email="member@test.com")
    member_id = member.id
    await _seat_with_the_old_pin(session, ids, member_id)
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])
    session.add_all(
        [
            RoomRemoval(room_id=ids["room"], user_id=ids["guest"], removed_by=ids["host"]),
            RoomRemoval(room_id=ids["room"], user_id=member_id, removed_by=ids["host"]),
        ]
    )
    await session.commit()

    # Act
    removed = await RoomController(session).list_removals(ids["room"], ids["host"])

    # Assert
    assert removed == []


async def test_only_the_host_lists_the_removed_players(session: AsyncSession, create_user, create_room):
    """A member asking is NotRoomHostError (403)."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    member = await create_user(username="member", email="member@test.com")
    member_id = member.id
    await _seat_with_the_old_pin(session, ids, member_id)

    # Act / Assert
    with pytest.raises(NotRoomHostError):
        await RoomController(session).list_removals(ids["room"], member_id)


# ─── The ban of a removed player ──────────────────────────────────────────────


async def test_the_host_bans_a_removed_player_who_has_no_seat(session: AsyncSession, create_user, create_room):
    """The ban (who banned), a new PIN, the record gone, and no seat taken or made; the
    player moves from the removed list to the banned one."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act
    view = await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    assert (view.user_id, view.username) == (ids["guest"], "guest")
    assert [(ban.user_id, ban.banned_by) for ban in await _bans(session, ids["room"])] == [(ids["guest"], ids["host"])]
    assert await _removals(session, ids["room"]) == []
    assert await _link(session, ids["room"], ids["guest"]) is None
    room = await _fresh_room(session, ids["room"])
    assert room.password != ids["old_pin"]
    assert len(room.password) == 4
    assert room.password.isdigit()
    controller = RoomController(session)
    assert await controller.list_removals(ids["room"], ids["host"]) == []
    assert [ban.user_id for ban in await controller.list_bans(ids["room"], ids["host"])] == [ids["guest"]]


@pytest.mark.parametrize("door", ["old_pin", "new_pin", "spectate"])
async def test_a_removed_player_once_banned_cannot_come_back(
    session: AsyncSession, create_user, create_room, door: str
):
    """The same door as any ban: 403 before the PIN, whichever PIN, spectating included."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])
    new_pin = (await _fresh_room(session, ids["room"])).password
    controller = RoomController(session)

    # Act / Assert
    with pytest.raises(RoomBannedError):
        if door == "spectate":
            await controller.join_room_as_spectator(ids["room"], ids["guest"], new_pin)
        else:
            pin = ids["old_pin"] if door == "old_pin" else new_pin
            await controller.join_room(RoomJoin(public_room_id=ids["code"], password=pin), ids["guest"])

    await session.rollback()
    assert await _link(session, ids["room"], ids["guest"]) is None


async def test_banning_a_removed_player_deletes_the_room_invites_they_sent_and_were_sent(
    session: AsyncSession, create_user, create_room
):
    """As for a seated player: the room's invites from and to them go, anyone else's stay."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    other = await create_user(username="other", email="other@test.com")
    other_id = other.id
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    session.add_all(
        [
            RoomInvite(room_id=ids["room"], inviter_id=ids["guest"], invitee_id=other_id, expires_at=expires_at),
            RoomInvite(room_id=ids["room"], inviter_id=ids["host"], invitee_id=ids["guest"], expires_at=expires_at),
        ]
    )
    await session.commit()
    third = await create_user(username="third", email="third@test.com")
    third_id = third.id
    session.add(RoomInvite(room_id=ids["room"], inviter_id=ids["host"], invitee_id=third_id, expires_at=expires_at))
    await session.commit()

    # Act
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    session.expunge_all()
    invites = (await session.exec(select(RoomInvite).where(RoomInvite.room_id == ids["room"]))).all()
    assert [(invite.inviter_id, invite.invitee_id) for invite in invites] == [(ids["host"], third_id)]


async def test_banning_a_removed_player_mid_game_plays_no_departure(session: AsyncSession, setup_undercover_game):
    """They left the game when they were removed (a leaver); the ban changes nothing in it."""
    # Prepare
    setup = await setup_undercover_game(5)
    room_id, host_id, target_id = setup["room"].id, setup["users"][0].id, setup["users"][4].id
    started = await UndercoverGameController(session).create_and_start(room_id, host_id)
    await RoomController(session).kick_player(room_id, host_id, target_id)
    session.expunge_all()
    game_before = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    state_before, status_before = game_before.live_state, game_before.game_status
    seats_before = (await session.exec(select(RoomUserLink.user_id).where(RoomUserLink.room_id == room_id))).all()

    # Act
    await RoomController(session).ban_player(room_id, host_id, target_id)

    # Assert
    session.expunge_all()
    game_after = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    assert game_after.live_state == state_before
    assert game_after.game_status == status_before
    seats_after = (await session.exec(select(RoomUserLink.user_id).where(RoomUserLink.room_id == room_id))).all()
    assert sorted(seats_after) == sorted(seats_before)
    assert [ban.user_id for ban in await _bans(session, room_id)] == [target_id]


async def test_a_player_who_left_by_themselves_cannot_be_banned(session: AsyncSession, create_user, create_room):
    """No seat and no removal: UserNotInRoomError, no ban, the same PIN."""
    # Prepare
    ids = await _seated_room(session, create_user, create_room)
    await RoomController(session).leave_room(ids["room"], ids["guest"])

    # Act / Assert
    with pytest.raises(UserNotInRoomError):
        await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])

    await session.rollback()
    assert await _bans(session, ids["room"]) == []
    assert (await _fresh_room(session, ids["room"])).password == ids["old_pin"]


async def test_a_removed_player_back_at_the_table_is_banned_from_their_seat(
    session: AsyncSession, create_user, create_room
):
    """Removed, back, then banned: the seat goes (the ordinary ban), and no record is left."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    await _seat_with_the_old_pin(session, ids, ids["guest"])

    # Act
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["guest"])

    # Assert
    assert await _link(session, ids["room"], ids["guest"]) is None
    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]
    assert await _removals(session, ids["room"]) == []


async def test_a_seat_is_refused_when_a_ban_committed_after_the_door_checked(
    session: AsyncSession, create_user, create_room
):
    """The seat asks again once the record is gone: a ban committed between the join's
    first check and its seat (the ban of a removed player racing their return) refuses it."""
    # Prepare: the ban lands after the door's check, before the seat
    ids = await _kicked_room(session, create_user, create_room)
    await session.exec(delete(RoomRemoval).where(col(RoomRemoval.room_id) == ids["room"]))
    session.add(RoomBan(room_id=ids["room"], user_id=ids["guest"], banned_by=ids["host"]))
    await session.commit()

    # Act / Assert
    with pytest.raises(RoomBannedError):
        await RoomController(session)._take_seat(ids["room"], ids["guest"])

    await session.rollback()
    assert await _link(session, ids["room"], ids["guest"]) is None


# ─── The record goes with the room and with the account ──────────────────────


async def test_closing_the_room_deletes_its_removals(session: AsyncSession, create_user, create_room):
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act
    await RoomController(session).delete_room(ids["room"], ids["host"])

    # Assert
    assert await _removals(session, ids["room"]) == []


async def test_deleting_the_removed_players_account_deletes_their_record(
    session: AsyncSession, create_user, create_room
):
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act
    await UserController(session).delete_user(ids["guest"])

    # Assert
    assert await _removals(session, ids["room"]) == []


async def test_deleting_the_hosts_account_keeps_the_records_they_made_without_their_name(
    session: AsyncSession, create_user, create_room
):
    """Like ``RoomBan.banned_by``: the record stays (the next host may still ban), ``removed_by`` nulled."""
    # Prepare: a member stays, so the room outlives its host
    ids = await _kicked_room(session, create_user, create_room)
    member = await create_user(username="member", email="member@test.com")
    member_id = member.id
    await _seat_with_the_old_pin(session, ids, member_id)

    # Act
    await UserController(session).delete_user(ids["host"])

    # Assert
    assert [(r.user_id, r.removed_by) for r in await _removals(session, ids["room"])] == [(ids["guest"], None)]


# ─── Races (PostgreSQL row locks) ─────────────────────────────────────────────


async def _join_in_its_own_request(engine: AsyncEngine, ids: dict) -> Room:
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await RoomController(own_session).join_room(
            RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"]
        )


async def _ban_in_its_own_request(engine: AsyncEngine, ids: dict):
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await RoomController(own_session).ban_player(ids["room"], ids["host"], ids["guest"])


@pytest.mark.postgres
async def test_a_return_waiting_behind_the_ban_of_the_removed_player_is_refused(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """The ban holds the record (deleted, uncommitted) while the player rejoins with the old
    PIN: the join passed its door's ban check, waits on the record, and once the ban commits
    the seat sees it — 403, no seat."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act — the ban's statements, uncommitted, then the join
    async with AsyncSession(engine, expire_on_commit=False) as ban_session:
        await ban_session.exec(
            delete(RoomRemoval)
            .where(col(RoomRemoval.room_id) == ids["room"])
            .where(col(RoomRemoval.user_id) == ids["guest"])
        )
        ban_session.add(RoomBan(room_id=ids["room"], user_id=ids["guest"], banned_by=ids["host"]))
        await ban_session.flush()
        join = asyncio.create_task(_join_in_its_own_request(engine, ids))
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not join.done(), "the join must be waiting on the removal record"
        await ban_session.commit()
    results = await asyncio.gather(join, return_exceptions=True)

    # Assert
    assert isinstance(results[0], RoomBannedError), results
    assert await _link(session, ids["room"], ids["guest"]) is None


@pytest.mark.postgres
async def test_a_ban_waiting_behind_the_removed_players_return_bans_their_new_seat(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """The player sits down again (record deleted, seat inserted, uncommitted) while the host
    bans from the removed list: the ban waits on the record, finds it gone, and bans the seat
    the return committed — the seat goes, the PIN changes."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)

    # Act — the seat's statements, uncommitted, then the ban
    async with AsyncSession(engine, expire_on_commit=False) as join_session:
        await join_session.exec(
            delete(RoomRemoval)
            .where(col(RoomRemoval.room_id) == ids["room"])
            .where(col(RoomRemoval.user_id) == ids["guest"])
        )
        join_session.add(RoomUserLink(room_id=ids["room"], user_id=ids["guest"], last_seen_at=datetime.now()))
        await join_session.flush()
        ban = asyncio.create_task(_ban_in_its_own_request(engine, ids))
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not ban.done(), "the ban must be waiting on the removal record"
        await join_session.commit()
    view = await ban

    # Assert
    assert view.user_id == ids["guest"]
    assert await _link(session, ids["room"], ids["guest"]) is None
    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]
    assert (await _fresh_room(session, ids["room"])).password != ids["old_pin"]


async def _invite_the_removed_player(session: AsyncSession, ids: dict) -> UUID:
    """A stored invite from the host to the removed guest (a kick leaves invites, and members may send new ones)."""
    invite = RoomInvite(
        room_id=ids["room"],
        inviter_id=ids["host"],
        invitee_id=ids["guest"],
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    session.add(invite)
    await session.commit()
    return invite.id


async def _assert_banned_from_the_seat_they_took(session: AsyncSession, ids: dict) -> None:
    """The return won, then the ban took that seat: banned, no seat, a new PIN, nothing left behind."""
    assert await _link(session, ids["room"], ids["guest"]) is None
    assert [ban.user_id for ban in await _bans(session, ids["room"])] == [ids["guest"]]
    assert await _removals(session, ids["room"]) == []
    assert (await session.exec(select(RoomInvite).where(RoomInvite.room_id == ids["room"]))).all() == []
    assert (await _fresh_room(session, ids["room"])).password != ids["old_pin"]


@pytest.mark.postgres
async def test_an_invite_accepted_while_the_host_bans_the_removed_player_bans_the_new_seat(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """``accept_invite`` locks its invite first (``FOR UPDATE``), then its seat deletes the
    removal record; the ban deletes that invite and the record. Taken in opposite orders the
    two waited on each other, and PostgreSQL's deadlock detector killed one of them (a 500).
    The ban takes the invites before the record, as the seat does: it waits on the accept,
    whose seat it then bans."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    invite_id = await _invite_the_removed_player(session, ids)

    # Act — the accept's first statement (its invite, locked), the ban, then the accept itself
    async with AsyncSession(engine, expire_on_commit=False) as accept_session:
        await accept_session.exec(select(RoomInvite).where(RoomInvite.id == invite_id).with_for_update())
        ban = asyncio.create_task(_ban_in_its_own_request(engine, ids))
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not ban.done(), "the ban must be waiting on the invite the accept holds"
        seated = await RoomController(accept_session).accept_invite(invite_id, ids["guest"])
    view = await ban

    # Assert
    # the accept succeeded (its own read of the room races the ban, which resumes at its commit)
    assert seated.id == ids["room"]
    assert view.user_id == ids["guest"]
    await _assert_banned_from_the_seat_they_took(session, ids)


@pytest.mark.postgres
async def test_a_return_with_the_pin_by_a_player_holding_an_invite_and_their_ban_bans_the_new_seat(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room, monkeypatch: pytest.MonkeyPatch
):
    """The removed player rejoins with the code and PIN while an invite of theirs is still
    stored, and the host bans them meanwhile. The seat spends the invite and deletes the
    record; the ban deletes both too. The seat takes them in the ban's order (the invites,
    then the record), so the ban waits on the whole seat and bans it, instead of each holding
    what the other waits for. The seat is held, mid-way, right after it ended the record."""
    # Prepare
    ids = await _kicked_room(session, create_user, create_room)
    await _invite_the_removed_player(session, ids)
    removal_ended, resume = asyncio.Event(), asyncio.Event()

    async def join_paused_after_the_record() -> Room:
        async with AsyncSession(engine, expire_on_commit=False) as own_session:
            controller = RoomController(own_session)
            end_removal = controller._end_removal

            async def paused(room_id: UUID, user_id: UUID) -> None:
                await end_removal(room_id, user_id)
                removal_ended.set()
                await resume.wait()

            monkeypatch.setattr(controller, "_end_removal", paused)
            return await controller.join_room(
                RoomJoin(public_room_id=ids["code"], password=ids["old_pin"]), ids["guest"]
            )

    # Act
    join = asyncio.create_task(join_paused_after_the_record())
    await asyncio.wait_for(removal_ended.wait(), timeout=10)
    ban = asyncio.create_task(_ban_in_its_own_request(engine, ids))
    await asyncio.sleep(LOCK_WAIT_SECONDS)
    assert not ban.done(), "the ban must be waiting on the seat"
    resume.set()
    joined, view = await asyncio.gather(join, ban, return_exceptions=True)

    # Assert
    assert not isinstance(joined, BaseException), joined
    assert not isinstance(view, BaseException), view
    assert view.user_id == ids["guest"]
    await _assert_banned_from_the_seat_they_took(session, ids)


async def _ban_paused_after_the_record(
    engine: AsyncEngine,
    ids: dict,
    monkeypatch: pytest.MonkeyPatch,
    record_taken: asyncio.Event,
    resume: asyncio.Event,
):
    """The host bans the removed player in a request of its own, held right after it took the
    removal record (``_take_removal``: the row deleted, locked, uncommitted)."""
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        controller = RoomController(own_session)
        take_removal = controller._take_removal

        async def paused(room_id: UUID, user_id: UUID) -> bool:
            removed = await take_removal(room_id, user_id)
            record_taken.set()
            await resume.wait()
            return removed

        monkeypatch.setattr(controller, "_take_removal", paused)
        return await controller.ban_player(ids["room"], ids["host"], ids["guest"])


@pytest.mark.postgres
async def test_closing_the_room_mid_game_while_the_host_bans_a_removed_player_fails_neither(
    session: AsyncSession, engine: AsyncEngine, setup_undercover_game, monkeypatch: pytest.MonkeyPatch
):
    """The host bans a removed player and closes the room at once, a game in progress. The close
    cancels the game, which writes the room row, then deletes the room's removal records; the ban
    holds that record and writes the room row (the new PIN) at its commit. Each held what the
    other waited for, and PostgreSQL killed one (a 500; review of 7 November 2026). The ban now
    takes the room lock first, as the close does: the close waits for the ban, then closes."""
    # Prepare: seven players, a game in progress, a civilian removed (the game goes on without them)
    setup = await setup_undercover_game(7)
    room_id, host_id = setup["room"].id, setup["users"][0].id
    started = await UndercoverGameController(session).create_and_start(room_id, host_id)
    session.expunge_all()
    players = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one().live_state["players"]
    guest_id = UUID(next(p["user_id"] for p in players if p["role"] == "civilian" and p["user_id"] != str(host_id)))
    await RoomController(session).kick_player(room_id, host_id, guest_id)
    session.expunge_all()
    game_status = (await session.exec(select(Game.game_status).where(Game.id == UUID(started.game_id)))).one()
    assert game_status == GameStatus.IN_PROGRESS
    old_pin = (await _fresh_room(session, room_id)).password
    ids = {"room": room_id, "host": host_id, "guest": guest_id}
    record_taken, resume = asyncio.Event(), asyncio.Event()

    async def close_in_its_own_request() -> None:
        async with AsyncSession(engine, expire_on_commit=False) as own_session:
            await RoomController(own_session).delete_room(room_id, host_id)

    # Act
    ban = asyncio.create_task(_ban_paused_after_the_record(engine, ids, monkeypatch, record_taken, resume))
    await asyncio.wait_for(record_taken.wait(), timeout=10)
    close = asyncio.create_task(close_in_its_own_request())
    await asyncio.sleep(LOCK_WAIT_SECONDS)
    assert not close.done(), "the close must be waiting on the ban"
    resume.set()
    view, closed = await asyncio.gather(ban, close, return_exceptions=True)

    # Assert: the ban, then the close, both committed
    assert not isinstance(view, BaseException), view
    assert not isinstance(closed, BaseException), closed
    assert view.user_id == guest_id
    assert [ban.user_id for ban in await _bans(session, room_id)] == [guest_id]
    assert await _removals(session, room_id) == []
    room = await _fresh_room(session, room_id)
    assert room.type == RoomType.INACTIVE
    assert room.active_game_id is None
    assert room.password != old_pin
    game = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    assert game.game_status == GameStatus.CANCELLED


@pytest.mark.postgres
async def test_the_hosts_account_deleted_while_they_ban_a_removed_player_fails_neither(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room, monkeypatch: pytest.MonkeyPatch
):
    """The host, alone at the table, bans the player they removed and deletes their account at
    once. The account's purge orphans the room it owns (an UPDATE of the room row), then nulls
    ``removed_by`` on that record; the ban holds the record and writes the room row (the new
    PIN) at its commit. Each held what the other waited for, and PostgreSQL killed one (a 500;
    review of 7 November 2026). The purge now takes the room lock of every room it orphans,
    the one the ban takes first: it waits for the ban, then purges."""
    # Prepare: the guest removed, the host alone in the room
    ids = await _kicked_room(session, create_user, create_room)
    record_taken, resume = asyncio.Event(), asyncio.Event()

    async def delete_account_in_its_own_request() -> None:
        async with AsyncSession(engine, expire_on_commit=False) as own_session:
            await UserController(own_session).delete_user(ids["host"])

    # Act
    ban = asyncio.create_task(_ban_paused_after_the_record(engine, ids, monkeypatch, record_taken, resume))
    await asyncio.wait_for(record_taken.wait(), timeout=10)
    deletion = asyncio.create_task(delete_account_in_its_own_request())
    await asyncio.sleep(LOCK_WAIT_SECONDS)
    assert not deletion.done(), "the account's purge must be waiting on the ban"
    resume.set()
    view, deleted = await asyncio.gather(ban, deletion, return_exceptions=True)

    # Assert: the ban, then the deletion, both committed; the ban stays, without the host's name
    assert not isinstance(view, BaseException), view
    assert not isinstance(deleted, BaseException), deleted
    assert [(ban.user_id, ban.banned_by) for ban in await _bans(session, ids["room"])] == [(ids["guest"], None)]
    assert await _removals(session, ids["room"]) == []
    room = await _fresh_room(session, ids["room"])
    assert room.owner_id is None
    assert room.type == RoomType.INACTIVE


@pytest.mark.postgres
async def test_a_ban_waiting_behind_the_hosts_account_deletion_is_refused(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room, monkeypatch: pytest.MonkeyPatch
):
    """The other way round: the purge holds the room lock when the ban arrives. The ban read the
    room before the purge committed (the host still its owner), waits on the lock, then reads
    the room again: ownerless, ``NotRoomHostError`` (403), and no ban naming a deleted account
    (which the foreign key would refuse with a 500)."""
    # Prepare: the guest removed, the host alone in the room
    ids = await _kicked_room(session, create_user, create_room)
    purged, resume = asyncio.Event(), asyncio.Event()

    async def delete_account_paused_after_the_purge() -> None:
        async with AsyncSession(engine, expire_on_commit=False) as own_session:
            controller = UserController(own_session)
            purge = controller._purge_user_references

            async def paused(user_id: UUID) -> None:
                await purge(user_id)
                purged.set()
                await resume.wait()

            monkeypatch.setattr(controller, "_purge_user_references", paused)
            await controller.delete_user(ids["host"])

    # Act
    deletion = asyncio.create_task(delete_account_paused_after_the_purge())
    await asyncio.wait_for(purged.wait(), timeout=10)
    ban = asyncio.create_task(_ban_in_its_own_request(engine, ids))
    await asyncio.sleep(LOCK_WAIT_SECONDS)
    assert not ban.done(), "the ban must be waiting on the room lock"
    resume.set()
    deleted, view = await asyncio.gather(deletion, ban, return_exceptions=True)

    # Assert
    assert not isinstance(deleted, BaseException), deleted
    assert isinstance(view, NotRoomHostError), view
    assert await _bans(session, ids["room"]) == []
    assert [(r.user_id, r.removed_by) for r in await _removals(session, ids["room"])] == [(ids["guest"], None)]
