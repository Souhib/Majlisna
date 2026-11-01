"""The host-only rules of a room, and the friendship check of an invite (TQ-04).

Each of these is an authorization rule that a mutant run removed without failing a
single test: any member could kick, start a game in any of the four games, or trigger a
rematch, and anyone could invite a stranger — and the suite stayed green.
"""

from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.game import GameStatus
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomJoin
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.error import (
    CannotKickYourselfError,
    CanOnlyInviteFriendsError,
    FriendAlreadyInRoomError,
    InviterNotInRoomError,
    NotRoomHostError,
)


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


async def _make_friends(session: AsyncSession, first: UUID, second: UUID) -> None:
    friends = FriendController(session)
    request = await friends.send_request(first, second)
    await friends.accept_request(request.id, second)


# ========== Kick ==========


async def test_a_kick_by_a_non_host_is_refused_and_the_target_stays(session: AsyncSession, setup_undercover_game):
    """A player who is not the host cannot kick, and the target keeps their seat."""
    # Prepare
    setup = await setup_undercover_game(3)
    room_id = setup["room"].id
    not_host, target = setup["users"][1].id, setup["users"][2].id

    # Act / Assert
    with pytest.raises(NotRoomHostError):
        await RoomController(session).kick_player(room_id, not_host, target)

    link = await _link(session, room_id, target)
    assert link is not None
    assert link.connected is True


async def test_the_host_cannot_kick_themself(session: AsyncSession, setup_undercover_game):
    """Kicking yourself is refused, and the host keeps both the seat and the room."""
    # Prepare
    setup = await setup_undercover_game(3)
    room_id, host_id = setup["room"].id, setup["users"][0].id

    # Act / Assert
    with pytest.raises(CannotKickYourselfError):
        await RoomController(session).kick_player(room_id, host_id, host_id)

    assert await _link(session, room_id, host_id) is not None
    assert (await _fresh_room(session, room_id)).owner_id == host_id


# ========== Game start, in all four games ==========


@pytest.mark.parametrize(
    ("controller_class", "setup_fixture", "num_players"),
    [
        (UndercoverGameController, "setup_undercover_game", 3),
        (CodenamesGameController, "setup_codenames_game", 4),
        (WordQuizGameController, "setup_wordquiz_game", 2),
        (McqQuizGameController, "setup_mcqquiz_game", 2),
    ],
    ids=["undercover", "codenames", "wordquiz", "mcqquiz"],
)
async def test_a_game_start_by_a_non_host_is_refused(
    session: AsyncSession,
    setup_undercover_game,
    setup_codenames_game,
    setup_wordquiz_game,
    setup_mcqquiz_game,
    controller_class,
    setup_fixture: str,
    num_players: int,
):
    """Only the host deals a game: a member's start is a 403 and creates no game."""
    # Prepare — a room that could start (enough players, content seeded). The setups are
    # factories, so requesting all four creates nothing until one is called.
    setups = {
        "setup_undercover_game": setup_undercover_game,
        "setup_codenames_game": setup_codenames_game,
        "setup_wordquiz_game": setup_wordquiz_game,
        "setup_mcqquiz_game": setup_mcqquiz_game,
    }
    setup = await setups[setup_fixture](num_players)
    room_id, not_host = setup["room"].id, setup["users"][1].id

    # Act / Assert
    with pytest.raises(NotRoomHostError):
        await controller_class(session).create_and_start(room_id, not_host)

    assert (await _fresh_room(session, room_id)).active_game_id is None
    games = (await session.exec(select(Game).where(Game.room_id == room_id))).all()
    assert games == []


# ========== Rematch ==========


async def test_a_rematch_by_a_non_host_is_refused_and_the_game_keeps_running(
    session: AsyncSession, setup_undercover_game
):
    """A member cannot end the table's game through a rematch."""
    # Prepare
    setup = await setup_undercover_game(3)
    room_id, host_id, not_host = setup["room"].id, setup["users"][0].id, setup["users"][1].id
    started = await UndercoverGameController(session).create_and_start(room_id, host_id)
    game_id = UUID(started.game_id)

    # Act / Assert
    with pytest.raises(NotRoomHostError):
        await RoomController(session).rematch(room_id, not_host)

    assert (await _fresh_room(session, room_id)).active_game_id == game_id
    game = (await session.exec(select(Game).where(Game.id == game_id))).one()
    assert game.game_status == GameStatus.IN_PROGRESS
    assert game.end_time is None


# ========== Invite ==========


async def test_inviting_someone_who_is_not_a_friend_is_refused(session: AsyncSession, create_user, create_room):
    """An invite reaches friends only."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    stranger = await create_user(username="stranger", email="stranger@test.com")
    room = await create_room(owner=host)

    # Act / Assert
    with pytest.raises(CanOnlyInviteFriendsError):
        await RoomController(session).invite_friend_to_room(room.id, host.id, stranger.id)


async def test_an_inviter_who_is_not_in_the_room_is_refused(session: AsyncSession, create_user, create_room):
    """Even a friend cannot be invited into a room the inviter is not seated in."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    outsider = await create_user(username="outsider", email="outsider@test.com")
    friend = await create_user(username="friend", email="friend@test.com")
    room = await create_room(owner=host)
    await _make_friends(session, outsider.id, friend.id)

    # Act / Assert
    with pytest.raises(InviterNotInRoomError):
        await RoomController(session).invite_friend_to_room(room.id, outsider.id, friend.id)


async def test_inviting_a_friend_already_in_the_room_is_refused(session: AsyncSession, create_user, create_room):
    """A friend already seated gets no second invite."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    friend = await create_user(username="friend", email="friend@test.com")
    room = await create_room(owner=host)
    await _make_friends(session, host.id, friend.id)
    await RoomController(session).join_room(RoomJoin(public_room_id=room.public_id, password=room.password), friend.id)

    # Act / Assert
    with pytest.raises(FriendAlreadyInRoomError):
        await RoomController(session).invite_friend_to_room(room.id, host.id, friend.id)


async def test_inviting_a_friend_is_accepted(session: AsyncSession, create_user, create_room):
    """The happy path: the host invites a friend who is not seated yet."""
    # Prepare
    host = await create_user(username="host", email="host@test.com")
    friend = await create_user(username="friend", email="friend@test.com")
    room = await create_room(owner=host)
    await _make_friends(session, host.id, friend.id)

    # Act
    response = await RoomController(session).invite_friend_to_room(room.id, host.id, friend.id)

    # Assert
    assert response.room_id == str(room.id)
    assert response.invited_user_id == str(friend.id)
