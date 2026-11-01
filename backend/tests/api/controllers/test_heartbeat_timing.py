"""Freezegun-based timing tests for heartbeat and disconnect checker."""

from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlmodel import select

from majlisna.api.constants import GRACE_PERIOD_SECONDS, HEARTBEAT_STALE_SECONDS
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.disconnect import (
    HeartbeatResult,
    _mark_stale_users,
    _remove_expired_users,
    mark_user_disconnected,
    presence_listener,
    update_heartbeat,
)
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.undercover import UndercoverRole

# ─── Helpers ──────────────────────────────────────────────────


async def _create_user(session, username="testuser", email="test@test.com"):
    user = User(username=username, email_address=email, password=get_password_hash("pass123"))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _create_room(session, owner, public_id="ABCDE"):
    room = Room(
        public_id=public_id,
        owner_id=owner.id,
        status="online",
        password="1234",
        type=RoomType.ACTIVE,
    )
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return room


async def _create_link(
    session, room_id, user_id, connected=True, last_seen_at=None, disconnected_at=None, joined_at=None
):
    link = RoomUserLink(
        room_id=room_id,
        user_id=user_id,
        connected=connected,
        last_seen_at=last_seen_at or datetime.now(),
    )
    if disconnected_at is not None:
        link.disconnected_at = disconnected_at
    if joined_at is not None:
        link.joined_at = joined_at
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def _create_undercover_game(session, room, players_data):
    """Create a game with undercover live_state."""
    game = Game(
        room_id=room.id,
        type=GameType.UNDERCOVER,
        number_of_players=len(players_data),
        game_status=GameStatus.IN_PROGRESS,
        live_state={
            "civilian_word": "mosque",
            "undercover_word": "church",
            "players": players_data,
            "eliminated_players": [],
            "turns": [
                {"votes": {}, "words": {}, "description_order": [], "current_describer_index": 0, "phase": "describing"}
            ],
        },
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)

    room.active_game_id = game.id
    session.add(room)
    await session.commit()

    return game


async def _create_wordquiz_game(session, room, players_data):
    """Create a game with word quiz live_state."""
    game = Game(
        room_id=room.id,
        type=GameType.WORD_QUIZ,
        number_of_players=len(players_data),
        game_status=GameStatus.IN_PROGRESS,
        live_state={
            "players": players_data,
            "current_round": 1,
            "total_rounds": 5,
            "answers": {},
            "game_over": False,
        },
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)

    room.active_game_id = game.id
    session.add(room)
    await session.commit()

    return game


# ========== Heartbeat Timing Tests ==========


@pytest.mark.asyncio
@freeze_time("2026-01-01 12:00:00")
async def test_stale_threshold_exact_boundary(session):
    """User with last_seen_at exactly at the stale threshold is NOT stale (< not <=).
    User with last_seen_at 1 second before the threshold IS stale.
    """
    # Prepare
    user_at_boundary = await _create_user(session, "boundary", "boundary@test.com")
    user_past_boundary = await _create_user(session, "past", "past@test.com")
    room = await _create_room(session, user_at_boundary)

    # Exactly HEARTBEAT_STALE_SECONDS ago — threshold time itself
    # The code checks `last_seen_at < stale_threshold`, so equal means NOT stale
    threshold_time = datetime(2026, 1, 1, 12, 0, 0) - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
    await _create_link(session, room.id, user_at_boundary.id, connected=True, last_seen_at=threshold_time)

    # 1 second before threshold — strictly less than → IS stale
    past_time = threshold_time - timedelta(seconds=1)
    await _create_link(session, room.id, user_past_boundary.id, connected=True, last_seen_at=past_time)

    # Act
    affected = await _mark_stale_users(session)

    # Assert — boundary user should NOT be stale (equal to threshold, not less than)
    boundary_link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == room.id)
            .where(RoomUserLink.user_id == user_at_boundary.id)
        )
    ).first()
    assert boundary_link.connected is True

    # Assert — past-boundary user should be stale
    past_link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == room.id)
            .where(RoomUserLink.user_id == user_past_boundary.id)
        )
    ).first()
    assert past_link.connected is False
    assert str(room.id) in affected


@pytest.mark.asyncio
@freeze_time("2026-01-01 12:00:00")
async def test_grace_period_exact_boundary(session):
    """User with disconnected_at exactly at grace threshold is NOT removed (< not <=).
    User with disconnected_at 1 second before the threshold IS removed.
    Requires an active game on the room (lobby users are never auto-removed).
    """
    # Prepare
    user_at_boundary = await _create_user(session, "boundary", "boundary@test.com")
    user_past_boundary = await _create_user(session, "past", "past@test.com")
    room = await _create_room(session, user_at_boundary)

    # Create an active game so the room qualifies for permanent removal
    game = Game(
        room_id=room.id,
        type=GameType.UNDERCOVER,
        number_of_players=3,
        game_status=GameStatus.IN_PROGRESS,
        live_state={"players": [], "eliminated_players": [], "turns": []},
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)
    room.active_game_id = game.id
    session.add(room)
    await session.commit()

    grace_threshold_time = datetime(2026, 1, 1, 12, 0, 0) - timedelta(seconds=GRACE_PERIOD_SECONDS)

    # Exactly at grace threshold — NOT removed (< not <=)
    await _create_link(
        session,
        room.id,
        user_at_boundary.id,
        connected=False,
        disconnected_at=grace_threshold_time,
    )

    # 1 second before grace threshold — IS removed
    await _create_link(
        session,
        room.id,
        user_past_boundary.id,
        connected=False,
        disconnected_at=grace_threshold_time - timedelta(seconds=1),
    )

    # Act
    room_ids, game_ids = await _remove_expired_users(session)

    # Assert — boundary user still exists (not removed)
    boundary_link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == room.id)
            .where(RoomUserLink.user_id == user_at_boundary.id)
        )
    ).first()
    assert boundary_link is not None

    # Assert — past-boundary user removed
    past_link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == room.id)
            .where(RoomUserLink.user_id == user_past_boundary.id)
        )
    ).first()
    assert past_link is None
    assert str(room.id) in room_ids


@pytest.mark.asyncio
async def test_heartbeat_refresh_resets_stale_timer(session):
    """After update_heartbeat, the stale timer resets. A user that was stale
    should no longer be stale if heartbeat was refreshed recently.
    """
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)

    # Set last_seen_at to 25 seconds ago (stale)
    stale_time = datetime.now() - timedelta(seconds=25)
    await _create_link(session, room.id, user.id, connected=True, last_seen_at=stale_time)

    # Act — refresh heartbeat (resets last_seen_at to now)
    await update_heartbeat(session, str(user.id), str(room.id))

    # Simulate 15 more seconds passing — still under 20s threshold
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    # Manually set last_seen_at to 15 seconds ago to simulate time passing
    link.last_seen_at = datetime.now() - timedelta(seconds=15)
    session.add(link)
    await session.commit()

    # Act — run stale check
    affected = await _mark_stale_users(session)

    # Assert — not stale (15s < 20s threshold)
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is True
    assert str(room.id) not in affected


@pytest.mark.asyncio
async def test_checker_handles_concurrent_reconnect(session):
    """If a user reconnects (update_heartbeat) after being marked disconnected,
    _mark_stale_users should not re-disconnect them.
    """
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(session, room.id, user.id, connected=True, last_seen_at=datetime.now())

    # Mark user as disconnected
    await mark_user_disconnected(session, str(user.id), str(room.id))

    # Verify disconnected
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is False

    # Reconnect via heartbeat
    await update_heartbeat(session, str(user.id), str(room.id))

    # Verify reconnected
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is True
    assert link.disconnected_at is None

    # Act — run stale checker
    affected = await _mark_stale_users(session)

    # Assert — user should still be connected (heartbeat is fresh)
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is True
    assert str(room.id) not in affected


@pytest.mark.asyncio
async def test_never_heartbeat_users_stale_after_threshold(session):
    """A user who never sent a heartbeat (last_seen_at=None) but joined
    more than HEARTBEAT_STALE_SECONDS ago should be marked as disconnected.
    """
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)

    joined_time = datetime.now() - timedelta(seconds=HEARTBEAT_STALE_SECONDS + 5)
    link = RoomUserLink(
        room_id=room.id,
        user_id=user.id,
        connected=True,
        last_seen_at=None,
        joined_at=joined_time,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)

    # Act
    affected = await _mark_stale_users(session)

    # Assert — marked as disconnected
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is False
    assert link.disconnected_at is not None
    assert str(room.id) in affected


@pytest.mark.asyncio
async def test_checker_loop_multiple_rooms(session):
    """Stale users in different rooms should all be detected,
    and all affected room IDs should be returned.
    """
    # Prepare
    user1 = await _create_user(session, "user1", "u1@test.com")
    user2 = await _create_user(session, "user2", "u2@test.com")
    room1 = await _create_room(session, user1, public_id="ROOM1")
    room2 = await _create_room(session, user2, public_id="ROOM2")

    stale_time = datetime.now() - timedelta(seconds=HEARTBEAT_STALE_SECONDS + 10)
    await _create_link(session, room1.id, user1.id, connected=True, last_seen_at=stale_time)
    await _create_link(session, room2.id, user2.id, connected=True, last_seen_at=stale_time)

    # Act
    affected = await _mark_stale_users(session)

    # Assert — both room IDs in the affected set
    assert str(room1.id) in affected
    assert str(room2.id) in affected

    # Assert — both users disconnected
    for room_id, user_id in [(room1.id, user1.id), (room2.id, user2.id)]:
        link = (
            await session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
            )
        ).first()
        assert link.connected is False


@pytest.mark.asyncio
async def test_checker_loop_game_cleanup_per_game_type(session):
    """Permanent disconnect handles both undercover (marks player dead)
    and word quiz (removes player) correctly when users expire in different rooms.
    """
    # Prepare — undercover room
    uc_users = [await _create_user(session, f"uc{i}", f"uc{i}@test.com") for i in range(4)]
    uc_room = await _create_room(session, uc_users[0], public_id="UCROM")

    expired_time = datetime.now() - timedelta(seconds=GRACE_PERIOD_SECONDS + 10)

    # Create links — uc_users[0] is the one who will expire
    await _create_link(
        session,
        uc_room.id,
        uc_users[0].id,
        connected=False,
        disconnected_at=expired_time,
    )
    # Other users are connected (so room doesn't become inactive)
    for u in uc_users[1:]:
        await _create_link(session, uc_room.id, u.id, connected=True)

    uc_players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(uc_users)
    ]
    uc_players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    uc_game = await _create_undercover_game(session, uc_room, uc_players_data)

    # Prepare — word quiz room
    wq_users = [await _create_user(session, f"wq{i}", f"wq{i}@test.com") for i in range(3)]
    wq_room = await _create_room(session, wq_users[0], public_id="WQROM")

    # wq_users[0] is the one who will expire
    await _create_link(
        session,
        wq_room.id,
        wq_users[0].id,
        connected=False,
        disconnected_at=expired_time,
    )
    # Other users connected
    for u in wq_users[1:]:
        await _create_link(session, wq_room.id, u.id, connected=True)

    wq_players_data = [{"user_id": str(u.id), "username": u.username, "score": 0} for u in wq_users]
    wq_game = await _create_wordquiz_game(session, wq_room, wq_players_data)

    # Act
    room_ids, game_ids = await _remove_expired_users(session)

    # Assert — both rooms affected
    assert str(uc_room.id) in room_ids
    assert str(wq_room.id) in room_ids

    # Assert — both games affected
    assert str(uc_game.id) in game_ids
    assert str(wq_game.id) in game_ids

    # Assert — undercover game: player marked dead
    uc_game = (await session.exec(select(Game).where(Game.id == uc_game.id))).first()
    uc_player = next(p for p in uc_game.live_state["players"] if p["user_id"] == str(uc_users[0].id))
    assert uc_player["is_alive"] is False

    # Assert — word quiz game: player removed from players list
    wq_game = (await session.exec(select(Game).where(Game.id == wq_game.id))).first()
    wq_player_ids = [p["user_id"] for p in wq_game.live_state["players"]]
    assert str(wq_users[0].id) not in wq_player_ids
    assert len(wq_player_ids) == 2


# ========== BDP-04: a player who comes back is announced ==========
#
# `update_heartbeat` (every Socket.IO connect, heartbeat and join_game) flipped an away
# link back to connected and told nobody: the connect answered the room state to the
# returning socket alone, the heartbeat answered nothing. The rest of the table kept
# showing the player "away · 9:58…0:00" until an unrelated event re-broadcast the room.
# It now says what it found, so the handlers broadcast exactly when someone came back.


@pytest.mark.asyncio
async def test_update_heartbeat_says_when_an_away_player_came_back(session):
    """RESTORED for a link marked away (connected False, grace clock running)."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(
        session,
        room.id,
        user.id,
        connected=False,
        last_seen_at=datetime.now() - timedelta(seconds=60),
        disconnected_at=datetime.now() - timedelta(seconds=30),
    )

    # Act
    result = await update_heartbeat(session, str(user.id), str(room.id))

    # Assert
    assert result is HeartbeatResult.RESTORED
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).one()
    assert link.connected is True
    assert link.disconnected_at is None


@pytest.mark.asyncio
async def test_update_heartbeat_of_a_present_player_announces_nothing(session):
    """REFRESHED for a link already connected: last_seen_at moves, nobody needs telling."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(session, room.id, user.id, connected=True, last_seen_at=datetime.now() - timedelta(seconds=8))

    # Act
    result = await update_heartbeat(session, str(user.id), str(room.id))

    # Assert
    assert result is HeartbeatResult.REFRESHED


@pytest.mark.asyncio
async def test_update_heartbeat_without_a_seat_says_so(session):
    """NOT_A_MEMBER when the link is gone (kicked, left, swept): the handler refuses the socket."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)

    # Act
    result = await update_heartbeat(session, str(user.id), str(room.id))

    # Assert
    assert result is HeartbeatResult.NOT_A_MEMBER


@pytest.mark.asyncio
async def test_mark_user_disconnected_says_whether_it_flipped_the_link(session):
    """True on the first disconnect, False when the link was already away or is gone."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(session, room.id, user.id, connected=True)

    # Act
    first = await mark_user_disconnected(session, str(user.id), str(room.id))
    second = await mark_user_disconnected(session, str(user.id), str(room.id))

    # Assert
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_a_rest_heartbeat_that_restores_a_player_is_announced(session):
    """`_update_heartbeat_throttled` (a game page polling REST while its socket is down)
    tells the presence listener when it brought an away player back, and only then."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(
        session, room.id, user.id, connected=False, disconnected_at=datetime.now() - timedelta(seconds=30)
    )
    controller = BaseGameController(session)
    announced: list[str] = []

    # Act
    with presence_listener(announced.append):
        restored = await controller._update_heartbeat_throttled(room.id, user.id)
        again = await controller._update_heartbeat_throttled(room.id, user.id)

    # Assert
    assert restored is True
    assert again is False
    assert announced == [str(room.id)]
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).one()
    assert link.connected is True
    assert link.disconnected_at is None


@pytest.mark.asyncio
async def test_no_presence_listener_outside_the_checker_loop(session):
    """Without a running checker loop (tests, scripts) a restoration is simply not announced."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(
        session, room.id, user.id, connected=False, disconnected_at=datetime.now() - timedelta(seconds=30)
    )

    # Act / Assert — nothing to call, nothing raised
    assert await BaseGameController(session)._update_heartbeat_throttled(room.id, user.id) is True


@pytest.mark.asyncio
async def test_a_lobby_poll_that_restores_a_player_is_announced(session):
    """`RoomController.get_room_state` (the lobby polling REST while its socket is down)
    restores the player before the socket reconnects: it must announce it, or nobody does."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(
        session, room.id, user.id, connected=False, disconnected_at=datetime.now() - timedelta(seconds=30)
    )
    announced: list[str] = []

    # Act
    with presence_listener(announced.append):
        state = await RoomController(session).get_room_state(room.id, user.id)
        await RoomController(session).get_room_state(room.id, user.id)

    # Assert
    assert announced == [str(room.id)]
    assert next(p for p in state.players if p.user_id == str(user.id)).is_connected is True
