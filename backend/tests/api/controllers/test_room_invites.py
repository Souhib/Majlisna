"""A friend's invite is stored on the server and opens the room without the PIN.

The invite used to be a socket push that carried the room's code AND PIN (invites were
not stored), and a ban rotates the PIN: an invite sent before it opened a join that was
refused. ``invite_friend_to_room`` now stores a ``RoomInvite`` — one live invite per
(room, invitee), re-inviting refreshes it, it lasts ``ROOM_INVITE_LIFETIME_MINUTES`` —
and the push names it by id, never with the PIN. ``accept_invite`` seats the invitee
through the join path when the invite is theirs and live, the room is live, they are not
banned from it and not seated elsewhere; the seat consumes the invite. Account deletion
and closing the room purge the invites (no foreign key declares ON DELETE).

Kick and ban (owner decision, 2 November 2026): a kicked player keeps the invites they
sent and the ones sent to them, and may be invited back; a ban deletes both kinds for
that room, and no member may invite the banned player (``InviteeBannedError``, 403) until
the host lifts it.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import ROOM_INVITE_LIFETIME_MINUTES
from majlisna.api.controllers import room as room_controller_module
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.user import UserController
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomJoin, RoomType
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.room_invite import RoomInvite
from majlisna.api.models.table import Room, User
from majlisna.api.schemas.error import (
    InviteeBannedError,
    InviterNotInRoomError,
    RoomBannedError,
    RoomInviteExpiredError,
    RoomInviteNotFoundError,
    RoomNotFoundError,
    UserAlreadyInRoomError,
)
from majlisna.api.utils.game_state import as_utc

PASSWORD = "password123"  # create_user's default


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _make_friends(session: AsyncSession, first: UUID, second: UUID) -> None:
    friends = FriendController(session)
    request = await friends.send_request(first, second)
    await friends.accept_request(request.id, second)


async def _invites(session: AsyncSession) -> list[RoomInvite]:
    session.expunge_all()
    return list((await session.exec(select(RoomInvite).order_by(RoomInvite.created_at))).all())  # ty: ignore[invalid-argument-type]


async def _link(session: AsyncSession, room_id: UUID, user_id: UUID) -> RoomUserLink | None:
    session.expunge_all()
    return (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
        )
    ).first()


async def _fresh_room(session: AsyncSession, room_id: UUID) -> Room:
    session.expunge_all()
    return (await session.exec(select(Room).where(Room.id == room_id))).one()


async def _set_expiry(session: AsyncSession, invite_id: UUID, expires_at: datetime) -> None:
    invite = (await session.exec(select(RoomInvite).where(RoomInvite.id == invite_id))).one()
    invite.expires_at = expires_at
    session.add(invite)
    await session.commit()


async def _host_and_friend(session: AsyncSession, create_user, create_room) -> dict:
    """A host in a new room's lobby and a friend of theirs who is not seated anywhere."""
    host = await create_user(username="host", email="host@test.com")
    friend = await create_user(username="friend", email="friend@test.com")
    room = await create_room(owner=host)
    await _make_friends(session, host.id, friend.id)
    return {"host": host.id, "friend": friend.id, "room": room.id, "code": room.public_id, "pin": room.password}


# ─── Inviting ─────────────────────────────────────────────────────────────────


async def test_an_invite_is_stored_and_what_the_friend_receives_never_carries_the_pin(
    session: AsyncSession, create_user, create_room
):
    """The row names the room, who invited and who is invited; the view names the room's
    code and the inviter, expires ROOM_INVITE_LIFETIME_MINUTES from now, and has no PIN."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    before = datetime.now(UTC)

    # Act
    response = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Assert
    lifetime = timedelta(minutes=ROOM_INVITE_LIFETIME_MINUTES)
    invite = response.invite
    assert (invite.room_id, invite.public_id, invite.invited_by) == (ids["room"], ids["code"], "host")
    assert before + lifetime <= invite.expires_at <= datetime.now(UTC) + lifetime
    assert "password" not in invite.model_dump()
    assert ids["pin"] not in invite.model_dump_json()
    stored = await _invites(session)
    assert [(row.id, row.room_id, row.inviter_id, row.invitee_id) for row in stored] == [
        (invite.id, ids["room"], ids["host"], ids["friend"])
    ]
    assert as_utc(stored[0].expires_at) == invite.expires_at


async def test_inviting_again_refreshes_the_one_live_invite(session: AsyncSession, create_user, create_room):
    """Another member's invite to the same friend is the same invite, made new: one row,
    the same id (a strip already on the friend's screen still opens it), the latest
    inviter, a full lifetime again."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    guest = await create_user(username="guest", email="guest@test.com")
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), guest.id)
    await _make_friends(session, guest.id, ids["friend"])
    first = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    await _set_expiry(session, first.invite.id, datetime.now(UTC) + timedelta(minutes=1))

    # Act
    again = await RoomController(session).invite_friend_to_room(ids["room"], guest.id, ids["friend"])

    # Assert
    assert again.invite.id == first.invite.id
    assert again.invite.invited_by == "guest"
    stored = await _invites(session)
    assert [(row.id, row.inviter_id) for row in stored] == [(first.invite.id, guest.id)]
    remaining = as_utc(stored[0].expires_at) - datetime.now(UTC)
    assert remaining > timedelta(minutes=ROOM_INVITE_LIFETIME_MINUTES - 1)


async def test_issuing_an_invite_purges_every_expired_one(session: AsyncSession, create_user, create_room):
    """The table stays bounded: an expired invite, whoever's, goes with the next one issued."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    other_host = await create_user(username="otherhost", email="otherhost@test.com")
    other_friend = await create_user(username="otherfriend", email="otherfriend@test.com")
    other_room = await create_room(owner=other_host)
    await _make_friends(session, other_host.id, other_friend.id)
    stale = await RoomController(session).invite_friend_to_room(other_room.id, other_host.id, other_friend.id)
    await _set_expiry(session, stale.invite.id, datetime.now(UTC) - timedelta(seconds=1))

    # Act
    fresh = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Assert
    assert [row.id for row in await _invites(session)] == [fresh.invite.id]


# ─── Accepting ────────────────────────────────────────────────────────────────


async def test_accepting_seats_the_invitee_without_the_pin_and_consumes_the_invite(
    session: AsyncSession, create_user, create_room
):
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Act
    room = await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    # Assert
    assert room.id == ids["room"]
    assert {user.id for user in room.users} == {ids["host"], ids["friend"]}
    link = await _link(session, ids["room"], ids["friend"])
    assert link is not None
    assert link.connected is True
    assert link.is_spectator is False
    assert await _invites(session) == []


async def test_an_invite_sent_before_a_ban_still_opens_the_room(session: AsyncSession, create_user, create_room):
    """The owner's report: the PIN the invite used to carry was rotated (now by a ban), and
    the friend's join was refused. A stored invite needs no PIN."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    troll = await create_user(username="troll", email="troll@test.com")
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), troll.id)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    await RoomController(session).ban_player(ids["room"], ids["host"], troll.id)
    assert (await _fresh_room(session, ids["room"])).password != ids["pin"]

    # Act
    room = await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    # Assert
    assert room.id == ids["room"]
    assert await _link(session, ids["room"], ids["friend"]) is not None
    assert await _link(session, ids["room"], troll.id) is None


async def _troll_with_a_sent_invite(session: AsyncSession, create_user, create_room) -> dict:
    """The host's room with a seated member ("troll") who invited a friend of theirs ("crony"),
    and the host's own invite to their friend."""
    ids = await _host_and_friend(session, create_user, create_room)
    troll = await create_user(username="troll", email="troll@test.com")
    crony = await create_user(username="crony", email="crony@test.com")
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), troll.id)
    await _make_friends(session, troll.id, crony.id)
    from_troll = await controller.invite_friend_to_room(ids["room"], troll.id, crony.id)
    from_host = await controller.invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    return {
        **ids,
        "troll": troll.id,
        "crony": crony.id,
        "from_troll": from_troll.invite.id,
        "from_host": from_host.invite.id,
    }


async def test_the_invites_a_kicked_player_sent_stay(session: AsyncSession, create_user, create_room):
    """A kick is for someone who left without quitting: what they sent still stands, and
    their friend sits down with it."""
    # Prepare
    ids = await _troll_with_a_sent_invite(session, create_user, create_room)

    # Act
    await RoomController(session).kick_player(ids["room"], ids["host"], ids["troll"])

    # Assert
    assert {row.id for row in await _invites(session)} == {ids["from_troll"], ids["from_host"]}
    room = await RoomController(session).accept_invite(ids["from_troll"], ids["crony"])
    assert room.id == ids["room"]
    assert await _link(session, ids["room"], ids["crony"]) is not None


async def test_the_invites_a_banned_player_sent_die_with_the_ban(session: AsyncSession, create_user, create_room):
    """The ban rotates the PIN to cut off what the banned player handed out, and their
    invites are what they handed out: their friend's strip opens nothing (404), and the
    new PIN never reaches that friend through a seat. Another member's invite stands."""
    # Prepare
    ids = await _troll_with_a_sent_invite(session, create_user, create_room)

    # Act
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["troll"])

    # Assert
    assert [row.id for row in await _invites(session)] == [ids["from_host"]]
    with pytest.raises(RoomInviteNotFoundError):
        await RoomController(session).accept_invite(ids["from_troll"], ids["crony"])
    assert await _link(session, ids["room"], ids["crony"]) is None
    room = await RoomController(session).accept_invite(ids["from_host"], ids["friend"])
    assert room.id == ids["room"]


async def _away_friend_invited(session: AsyncSession, create_user, create_room) -> tuple[dict, UUID]:
    """The friend sits in the room, their phone goes away, and the host re-invites them."""
    ids = await _host_and_friend(session, create_user, create_room)
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), ids["friend"])
    link = await _link(session, ids["room"], ids["friend"])
    assert link is not None
    link.connected = False
    link.disconnected_at = datetime.now()
    session.add(link)
    await session.commit()
    sent = await controller.invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    return ids, sent.invite.id


async def test_a_kicked_player_comes_back_through_the_invite_they_hold(session: AsyncSession, create_user, create_room):
    """Removed while away, the friend keeps the invite sent to them and sits down with it."""
    # Prepare
    ids, invite_id = await _away_friend_invited(session, create_user, create_room)
    await RoomController(session).kick_player(ids["room"], ids["host"], ids["friend"])
    assert [invite.id for invite in await RoomController(session).list_invites(ids["friend"])] == [invite_id]

    # Act
    room = await RoomController(session).accept_invite(invite_id, ids["friend"])

    # Assert
    assert room.id == ids["room"]
    link = await _link(session, ids["room"], ids["friend"])
    assert link is not None
    assert link.connected is True


async def test_a_ban_deletes_the_invites_sent_to_the_banned_player(session: AsyncSession, create_user, create_room):
    """The invite to the banned player goes with the ban: never listed, and spent (404)."""
    # Prepare
    ids, invite_id = await _away_friend_invited(session, create_user, create_room)

    # Act
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["friend"])

    # Assert
    assert await _invites(session) == []
    assert await RoomController(session).list_invites(ids["friend"]) == []
    with pytest.raises(RoomInviteNotFoundError):
        await RoomController(session).accept_invite(invite_id, ids["friend"])
    assert await _link(session, ids["room"], ids["friend"]) is None


async def test_a_banned_player_cannot_use_an_invite_that_outlived_the_ban(
    session: AsyncSession, create_user, create_room
):
    """An invite stored as the ban committed (the two raced) opens no door the ban closed:
    the list leaves it out, and accepting it is a 403 roomBanned, with no seat."""
    # Prepare: banned, then an invite row that slipped in after the ban's purge
    ids, _ = await _away_friend_invited(session, create_user, create_room)
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["friend"])
    stray = RoomInvite(
        room_id=ids["room"],
        inviter_id=ids["host"],
        invitee_id=ids["friend"],
        expires_at=datetime.now(UTC) + timedelta(minutes=ROOM_INVITE_LIFETIME_MINUTES),
    )
    session.add(stray)
    await session.commit()
    stray_id = stray.id

    # Act / Assert
    assert await RoomController(session).list_invites(ids["friend"]) == []
    with pytest.raises(RoomBannedError) as caught:
        await RoomController(session).accept_invite(stray_id, ids["friend"])

    assert caught.value.status_code == 403
    assert await _link(session, ids["room"], ids["friend"]) is None


def _ban_lands_while_storing(
    monkeypatch: pytest.MonkeyPatch, controller: RoomController, session: AsyncSession, ids: dict, banned: UUID
) -> None:
    """The ban commits while ``controller`` stores its invite: its ban check has passed and
    its row is in, the ban's purge saw nothing to delete (READ COMMITTED), and the ban is
    committed with the invite (the same session here, so it lands deterministically)."""
    store = controller._store_invite

    async def store_then_the_ban_lands(room_id: UUID, inviter_id: UUID, invitee_id: UUID) -> tuple[UUID, datetime]:
        stored = await store(room_id, inviter_id, invitee_id)
        session.add(RoomBan(room_id=ids["room"], user_id=banned, banned_by=ids["host"]))
        return stored

    monkeypatch.setattr(controller, "_store_invite", store_then_the_ban_lands)


async def test_an_invite_whose_invitee_was_banned_as_it_was_stored_is_taken_back(
    session: AsyncSession, create_user, create_room, monkeypatch: pytest.MonkeyPatch
):
    """The invite and the ban raced: asked again once the invite is committed, the ban
    wins. The row is deleted and the inviter told why (403 inviteeBanned), so the route
    pushes nothing to the banned friend."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    controller = RoomController(session)
    _ban_lands_while_storing(monkeypatch, controller, session, ids, banned=ids["friend"])

    # Act / Assert
    with pytest.raises(InviteeBannedError) as caught:
        await controller.invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    assert caught.value.status_code == 403
    assert await _invites(session) == []
    assert await RoomController(session).list_invites(ids["friend"]) == []


async def test_an_invite_whose_inviter_was_banned_as_it_was_stored_is_taken_back(
    session: AsyncSession, create_user, create_room, monkeypatch: pytest.MonkeyPatch
):
    """The same race from the inviter's side: a ban deletes the invites the banned player
    sent, and the one committed after its purge goes too. Their friend is sent nothing."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    troll = await create_user(username="troll", email="troll@test.com")
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), troll.id)
    await _make_friends(session, troll.id, ids["friend"])
    controller = RoomController(session)
    _ban_lands_while_storing(monkeypatch, controller, session, ids, banned=troll.id)

    # Act / Assert
    with pytest.raises(InviterNotInRoomError):
        await controller.invite_friend_to_room(ids["room"], troll.id, ids["friend"])

    assert await _invites(session) == []


async def test_invites_stored_while_the_ban_was_written_are_swept_once_it_is_committed(
    session: AsyncSession, create_user, create_room, monkeypatch: pytest.MonkeyPatch
):
    """The other order of the race: an invite to or from the player, committed after the
    ban's purge, while the ban's transaction runs. The ban sweeps them again once committed,
    so none outlives it (an unban later must not bring one back). Another member's stands."""
    # Prepare: two rows slip in after the purge (the troll's to the crony, the host's to the troll)
    ids = await _troll_with_a_sent_invite(session, create_user, create_room)
    expires_at = datetime.now(UTC) + timedelta(minutes=ROOM_INVITE_LIFETIME_MINUTES)
    departure = room_controller_module._handle_permanent_disconnect

    async def invites_slip_in_then_depart(own_session: AsyncSession, link: RoomUserLink) -> None:
        own_session.add(
            RoomInvite(room_id=ids["room"], inviter_id=ids["troll"], invitee_id=ids["crony"], expires_at=expires_at)
        )
        own_session.add(
            RoomInvite(room_id=ids["room"], inviter_id=ids["host"], invitee_id=ids["troll"], expires_at=expires_at)
        )
        await departure(own_session, link)

    monkeypatch.setattr(room_controller_module, "_handle_permanent_disconnect", invites_slip_in_then_depart)

    # Act
    await RoomController(session).ban_player(ids["room"], ids["host"], ids["troll"])

    # Assert
    assert [row.id for row in await _invites(session)] == [ids["from_host"]]


async def test_a_member_cannot_invite_a_banned_friend(session: AsyncSession, create_user, create_room):
    """403 inviteeBanned (the inviter is told why), and nothing is stored."""
    # Prepare: the friend was banned; a member who is also their friend tries to invite them
    ids = await _host_and_friend(session, create_user, create_room)
    member = await create_user(username="member", email="member@test.com")
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), ids["friend"])
    await controller.ban_player(ids["room"], ids["host"], ids["friend"])
    new_pin = (await _fresh_room(session, ids["room"])).password
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=new_pin), member.id)
    await _make_friends(session, member.id, ids["friend"])

    # Act / Assert
    for inviter in (ids["host"], member.id):
        with pytest.raises(InviteeBannedError) as caught:
            await RoomController(session).invite_friend_to_room(ids["room"], inviter, ids["friend"])
        assert caught.value.status_code == 403
        assert caught.value.error_key == "errors.api.inviteeBanned"

    assert await _invites(session) == []


async def test_a_kicked_friend_can_be_invited_back(session: AsyncSession, create_user, create_room):
    """No ban, no closed door: the host's invite after the kick seats the friend again."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), ids["friend"])
    await controller.kick_player(ids["room"], ids["host"], ids["friend"])

    # Act
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    room = await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    # Assert
    assert room.id == ids["room"]
    assert await _link(session, ids["room"], ids["friend"]) is not None


async def test_once_the_ban_is_lifted_the_friend_can_be_invited_again(session: AsyncSession, create_user, create_room):
    """Lifting reopens every door: the invite is stored and seats the friend."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    controller = RoomController(session)
    await controller.join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), ids["friend"])
    await controller.ban_player(ids["room"], ids["host"], ids["friend"])
    await controller.lift_ban(ids["room"], ids["host"], ids["friend"])

    # Act
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    room = await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    # Assert
    assert room.id == ids["room"]
    assert await _link(session, ids["room"], ids["friend"]) is not None


async def test_someone_elses_invite_is_not_found_and_stays_theirs(session: AsyncSession, create_user, create_room):
    """Only the invitee can accept: anyone else gets 404, and the invite is untouched."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    stranger = await create_user(username="stranger", email="stranger@test.com")
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Act / Assert
    with pytest.raises(RoomInviteNotFoundError):
        await RoomController(session).accept_invite(sent.invite.id, stranger.id)

    assert await _link(session, ids["room"], stranger.id) is None
    assert [row.id for row in await _invites(session)] == [sent.invite.id]


async def test_an_unknown_invite_is_not_found(session: AsyncSession, create_user, create_room):
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)

    # Act / Assert
    with pytest.raises(RoomInviteNotFoundError):
        await RoomController(session).accept_invite(uuid4(), ids["friend"])


async def test_an_expired_invite_is_refused_and_seats_nobody(session: AsyncSession, create_user, create_room):
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    await _set_expiry(session, sent.invite.id, datetime.now(UTC) - timedelta(seconds=1))

    # Act / Assert
    with pytest.raises(RoomInviteExpiredError):
        await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    assert await _link(session, ids["room"], ids["friend"]) is None


async def test_closing_the_room_purges_its_invites(session: AsyncSession, create_user, create_room):
    """The host deletes the room: its invites go with it, and an old strip finds nothing."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Act
    await RoomController(session).delete_room(ids["room"], ids["host"])

    # Assert
    assert await _invites(session) == []
    with pytest.raises(RoomInviteNotFoundError):
        await RoomController(session).accept_invite(sent.invite.id, ids["friend"])


async def test_an_invite_to_a_room_everyone_left_is_refused(session: AsyncSession, create_user, create_room):
    """The last member leaving deactivates the room: no seat in it, whatever the invite."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    await RoomController(session).leave_room(ids["room"], ids["host"])
    assert (await _fresh_room(session, ids["room"])).type == RoomType.INACTIVE

    # Act / Assert
    with pytest.raises(RoomNotFoundError):
        await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    assert await _link(session, ids["room"], ids["friend"]) is None


async def test_a_friend_seated_elsewhere_is_told_where_and_keeps_the_invite(
    session: AsyncSession, create_user, create_room
):
    """409 naming the room they sit in (the strip offers "Leave X and join"); once they
    have left it, the same invite seats them."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    friend = (await session.exec(select(User).where(User.id == ids["friend"]))).one()
    elsewhere = await create_room(owner=friend)

    # Act / Assert: refused, told where
    with pytest.raises(UserAlreadyInRoomError) as refused:
        await RoomController(session).accept_invite(sent.invite.id, ids["friend"])
    assert refused.value.details["room_id"] == str(elsewhere.id)
    assert [row.id for row in await _invites(session)] == [sent.invite.id]
    assert await _link(session, ids["room"], ids["friend"]) is None

    # Act: leave, then the same invite
    await RoomController(session).leave_room(elsewhere.id, ids["friend"])
    room = await RoomController(session).accept_invite(sent.invite.id, ids["friend"])

    # Assert
    assert room.id == ids["room"]
    assert await _invites(session) == []


async def test_a_join_by_link_consumes_the_invite_to_that_room(session: AsyncSession, create_user, create_room):
    """Seated by the code and PIN, the friend no longer holds an invite to that room."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Act
    await RoomController(session).join_room(RoomJoin(public_room_id=ids["code"], password=ids["pin"]), ids["friend"])

    # Assert
    assert await _invites(session) == []


# ─── The invitee's live invites ───────────────────────────────────────────────


async def test_the_invitee_reads_their_live_invites_newest_first(session: AsyncSession, create_user, create_room):
    """What the app shell shows when it opens (an invite received while the page was
    closed): the caller's own invites only, not expired, to a live room, newest first.

    The expired invite and the one to a room its last member left are still in the
    table (nothing purges them until the next invite is issued): the list's own filters
    leave them out."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    second_host = await create_user(username="secondhost", email="secondhost@test.com")
    expired_host = await create_user(username="expiredhost", email="expiredhost@test.com")
    closed_host = await create_user(username="closedhost", email="closedhost@test.com")
    someone = await create_user(username="someone", email="someone@test.com")
    rooms = {}
    for host in (second_host, expired_host, closed_host):
        rooms[host.username] = await create_room(owner=host)
        await _make_friends(session, host.id, ids["friend"])
    await _make_friends(session, ids["host"], someone.id)
    controller = RoomController(session)
    expired = await controller.invite_friend_to_room(rooms["expiredhost"].id, expired_host.id, ids["friend"])
    closed = await controller.invite_friend_to_room(rooms["closedhost"].id, closed_host.id, ids["friend"])
    first = await controller.invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    second = await controller.invite_friend_to_room(rooms["secondhost"].id, second_host.id, ids["friend"])
    await controller.invite_friend_to_room(ids["room"], ids["host"], someone.id)
    await _set_expiry(session, expired.invite.id, datetime.now(UTC) - timedelta(seconds=1))
    await controller.leave_room(rooms["closedhost"].id, closed_host.id)
    assert (await _fresh_room(session, rooms["closedhost"].id)).type == RoomType.INACTIVE
    assert {expired.invite.id, closed.invite.id} <= {row.id for row in await _invites(session)}

    # Act
    invites = await RoomController(session).list_invites(ids["friend"])

    # Assert
    assert [invite.id for invite in invites] == [second.invite.id, first.invite.id]
    assert [(invite.public_id, invite.invited_by) for invite in invites] == [
        (rooms["secondhost"].public_id, "secondhost"),
        (ids["code"], "host"),
    ]
    assert all("password" not in invite.model_dump() for invite in invites)


# ─── Account deletion ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("deleted", ["inviter", "invitee"])
async def test_deleting_an_account_purges_the_invites_it_sent_or_received(
    session: AsyncSession, create_user, create_room, deleted: str
):
    """No foreign key declares ON DELETE: an invite left behind blocked the account's deletion."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])
    victim = ids["host"] if deleted == "inviter" else ids["friend"]

    # Act
    await UserController(session).delete_user_account(victim, PASSWORD)

    # Assert
    assert await _invites(session) == []
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == victim))).first() is None


# ─── Two accepts at once ──────────────────────────────────────────────────────


async def _accept(engine: AsyncEngine, invite_id: UUID, user_id: UUID) -> Room:
    """One accept in its own session, like one request (a session per asyncio task)."""
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await RoomController(own_session).accept_invite(invite_id, user_id)


@pytest.mark.postgres
async def test_two_accepts_of_one_invite_at_once_seat_the_friend_once(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """Two tabs press Join together: the invite is spent once (the row is locked), the
    other answers 404, never a 500 on the seat's unique pair."""
    # Prepare
    ids = await _host_and_friend(session, create_user, create_room)
    sent = await RoomController(session).invite_friend_to_room(ids["room"], ids["host"], ids["friend"])

    # Act
    results = await asyncio.gather(
        _accept(engine, sent.invite.id, ids["friend"]),
        _accept(engine, sent.invite.id, ids["friend"]),
        return_exceptions=True,
    )

    # Assert
    seated = [result for result in results if isinstance(result, Room)]
    refused = [result for result in results if isinstance(result, RoomInviteNotFoundError)]
    assert (len(seated), len(refused)) == (1, 1), results
    session.expunge_all()
    links = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == ids["room"]).where(RoomUserLink.user_id == ids["friend"])
        )
    ).all()
    assert len(links) == 1
    assert await _invites(session) == []
