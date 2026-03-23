"""Tests for disconnect handler functions."""

from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from ipg.api.constants import GRACE_PERIOD_SECONDS, HEARTBEAT_STALE_SECONDS
from ipg.api.controllers.codenames_helpers import CodenamesGameStatus, CodenamesRole, CodenamesTeam
from ipg.api.controllers.disconnect import (
    _handle_codenames_disconnect,
    _handle_permanent_disconnect,
    _handle_undercover_disconnect,
    _handle_wordquiz_disconnect,
    _mark_stale_users,
    _remove_expired_users,
    mark_user_disconnected,
    update_heartbeat,
)
from ipg.api.controllers.shared import get_password_hash
from ipg.api.models.game import GameStatus, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.room import RoomType
from ipg.api.models.table import Game, Room, User
from ipg.api.models.undercover import UndercoverRole

# ─── Helpers ──────────────────────────────────────────────────


async def _create_user(session, username="testuser", email="test@test.com"):
    user = User(username=username, email_address=email, password=get_password_hash("pass123"))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _create_room(session, owner):
    room = Room(
        public_id="ABCDE",
        owner_id=owner.id,
        status="online",
        password="1234",
        type=RoomType.ACTIVE,
    )
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return room


async def _create_link(session, room_id, user_id, connected=True):
    link = RoomUserLink(
        room_id=room_id,
        user_id=user_id,
        connected=connected,
        last_seen_at=datetime.now(),
    )
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


async def _create_codenames_game(session, room, players_data):
    """Create a game with codenames live_state."""
    game = Game(
        room_id=room.id,
        type=GameType.CODENAMES,
        number_of_players=len(players_data),
        game_status=GameStatus.IN_PROGRESS,
        live_state={
            "board": [{"word": f"w{i}", "card_type": "neutral", "revealed": False} for i in range(25)],
            "players": players_data,
            "current_team": CodenamesTeam.RED.value,
            "current_turn": {
                "team": CodenamesTeam.RED.value,
                "clue_word": None,
                "clue_number": 0,
                "guesses_made": 0,
                "max_guesses": 0,
            },
            "red_remaining": 9,
            "blue_remaining": 8,
            "status": CodenamesGameStatus.IN_PROGRESS.value,
            "winner": None,
        },
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)

    room.active_game_id = game.id
    session.add(room)
    await session.commit()

    return game


# ========== Permanent Disconnect Tests ==========


@pytest.mark.asyncio
async def test_disconnect_removes_link(session):
    """Permanent disconnect deletes the RoomUserLink."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id)

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert
    remaining = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert remaining is None


@pytest.mark.asyncio
async def test_disconnect_deactivates_empty_room(session):
    """Empty room after disconnect becomes INACTIVE."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id)

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert
    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.type == RoomType.INACTIVE


@pytest.mark.asyncio
async def test_disconnect_transfers_ownership(session):
    """If owner disconnects but others remain, ownership transfers."""
    # Prepare
    owner = await _create_user(session, "owner", "owner@test.com")
    other = await _create_user(session, "other", "other@test.com")
    room = await _create_room(session, owner)
    owner_link = await _create_link(session, room.id, owner.id)
    await _create_link(session, room.id, other.id)

    # Act
    await _handle_permanent_disconnect(session, owner_link)

    # Assert
    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.owner_id == other.id


@pytest.mark.asyncio
async def test_disconnect_room_not_found(session):
    """No crash when room is deleted before disconnect handler runs."""
    # Prepare — create user, room, link, then delete the room
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id)

    # Delete the room to simulate it being gone
    db_room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    await session.delete(db_room)
    await session.commit()

    # Act — should not raise
    await _handle_permanent_disconnect(session, link)


# ========== Undercover Disconnect Tests ==========


@pytest.mark.asyncio
async def test_uc_disconnect_marks_dead(session):
    """Disconnected player is marked is_alive=False."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    # Act
    await _handle_undercover_disconnect(session, game, str(users[2].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[2].id))
    assert player["is_alive"] is False


@pytest.mark.asyncio
async def test_uc_disconnect_cancels_below_3(session):
    """Below 3 alive players -> game cancelled."""
    # Prepare — 3 players, disconnect one -> 2 alive -> cancel
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    # Act
    await _handle_undercover_disconnect(session, game, str(users[2].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.CANCELLED


@pytest.mark.asyncio
async def test_uc_disconnect_checks_win_condition(session):
    """If disconnecting player triggers win, game ends."""
    # Prepare — 4 players: 1 undercover, 3 civilians. Disconnect the undercover -> civilians win
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    # Act — disconnect the undercover
    await _handle_undercover_disconnect(session, game, str(users[1].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED


@pytest.mark.asyncio
async def test_uc_disconnect_undercovers_win_when_equal(session):
    """If disconnect makes undercovers >= civilians, undercovers win."""
    # Prepare — 4 players: 2 undercover, 2 civilian. Disconnect a civilian -> 2 uc >= 1 civ
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[0]["role"] = UndercoverRole.UNDERCOVER.value
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    # Act — disconnect a civilian
    await _handle_undercover_disconnect(session, game, str(users[2].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED


@pytest.mark.asyncio
async def test_uc_disconnect_already_dead_no_re_elimination(session):
    """Already dead player disconnect does nothing."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    players_data[3]["is_alive"] = False  # Already dead
    game = await _create_undercover_game(session, room, players_data)

    # Act
    await _handle_undercover_disconnect(session, game, str(users[3].id), room)

    # Assert — no additional elimination, game still in progress
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.IN_PROGRESS


# ========== Codenames Disconnect Tests ==========


@pytest.mark.asyncio
async def test_cn_disconnect_removes_player(session):
    """Disconnected player removed from game players list."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {"user_id": str(users[0].id), "username": "p0", "team": "red", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[1].id), "username": "p1", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[2].id), "username": "p2", "team": "blue", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[3].id), "username": "p3", "team": "blue", "role": CodenamesRole.OPERATIVE.value},
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Act
    await _handle_codenames_disconnect(session, game, str(users[3].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    player_ids = [p["user_id"] for p in game.live_state["players"]]
    assert str(users[3].id) not in player_ids


@pytest.mark.asyncio
async def test_cn_disconnect_empty_team_ends_game(session):
    """If a team becomes empty, remaining team wins."""
    # Prepare — blue team has only 1 player
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {"user_id": str(users[0].id), "username": "p0", "team": "red", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[1].id), "username": "p1", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[2].id), "username": "p2", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[3].id), "username": "p3", "team": "blue", "role": CodenamesRole.SPYMASTER.value},
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Act — disconnect the only blue player
    await _handle_codenames_disconnect(session, game, str(users[3].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
    assert game.live_state["winner"] == "red"
    assert game.game_status == GameStatus.FINISHED


@pytest.mark.asyncio
async def test_cn_disconnect_both_teams_have_players(session):
    """If both teams still have players, game continues."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(5)]
    room = await _create_room(session, users[0])
    players_data = [
        {"user_id": str(users[0].id), "username": "p0", "team": "red", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[1].id), "username": "p1", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[2].id), "username": "p2", "team": "blue", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[3].id), "username": "p3", "team": "blue", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[4].id), "username": "p4", "team": "blue", "role": CodenamesRole.OPERATIVE.value},
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Act — disconnect one blue operative (blue still has 2 players)
    await _handle_codenames_disconnect(session, game, str(users[4].id), room)

    # Assert — game continues
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.live_state["status"] == CodenamesGameStatus.IN_PROGRESS.value
    assert game.game_status == GameStatus.IN_PROGRESS


# ========== Word Quiz Disconnect Tests ==========


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


@pytest.mark.asyncio
async def test_wq_disconnect_removes_player(session):
    """Disconnected player removed from word quiz game."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    players_data = [{"user_id": str(u.id), "username": u.username, "score": 0} for u in users]
    game = await _create_wordquiz_game(session, room, players_data)

    # Act
    await _handle_wordquiz_disconnect(session, game, str(users[1].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    player_ids = [p["user_id"] for p in game.live_state["players"]]
    assert str(users[1].id) not in player_ids
    assert len(player_ids) == 2
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_wq_disconnect_removes_answer(session):
    """Disconnected player's answer is removed."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    players_data = [{"user_id": str(u.id), "username": u.username, "score": 0} for u in users]
    game = await _create_wordquiz_game(session, room, players_data)

    # Add an answer for the disconnecting player
    game.live_state["answers"] = {str(users[1].id): "some answer"}
    session.add(game)
    await session.commit()

    # Act
    await _handle_wordquiz_disconnect(session, game, str(users[1].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert str(users[1].id) not in game.live_state.get("answers", {})


@pytest.mark.asyncio
async def test_wq_disconnect_last_player_cancels(session):
    """If no players remain, game is cancelled."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(1)]
    room = await _create_room(session, users[0])
    players_data = [{"user_id": str(users[0].id), "username": users[0].username, "score": 0}]
    game = await _create_wordquiz_game(session, room, players_data)

    # Act
    await _handle_wordquiz_disconnect(session, game, str(users[0].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.CANCELLED
    assert game.live_state["game_over"] is True

    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.active_game_id is None


# ========== Full Chain: Permanent Disconnect During Active Game ==========


@pytest.mark.asyncio
async def test_permanent_disconnect_during_undercover_game(session):
    """Full chain: permanent disconnect removes player from room AND handles undercover game."""
    # Prepare — 4 players in undercover game, disconnect player 2 (civilian)
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    for u in users:
        await _create_link(session, room.id, u.id, connected=True)

    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    # Get the link for player 2
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == users[2].id)
        )
    ).first()

    # Act — permanent disconnect
    await _handle_permanent_disconnect(session, link)

    # Assert — link removed
    remaining_link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == users[2].id)
        )
    ).first()
    assert remaining_link is None

    # Assert — player marked dead in game state
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[2].id))
    assert player["is_alive"] is False

    # Assert — game still in progress (3 alive players remain)
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_permanent_disconnect_during_undercover_cancels_below_3(session):
    """Full chain: disconnect during 3-player undercover game cancels it (only 2 left)."""
    # Prepare — exactly 3 players
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    for u in users:
        await _create_link(session, room.id, u.id, connected=True)

    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == users[2].id)
        )
    ).first()

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert — game cancelled
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.CANCELLED

    # Assert — room's active_game_id cleared
    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.active_game_id is None


@pytest.mark.asyncio
async def test_permanent_disconnect_during_codenames_game(session):
    """Full chain: disconnect removes player from codenames game, ends if team empty."""
    # Prepare — 4 players, blue has only 1 player
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    for u in users:
        await _create_link(session, room.id, u.id, connected=True)

    players_data = [
        {"user_id": str(users[0].id), "username": "p0", "team": "red", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[1].id), "username": "p1", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[2].id), "username": "p2", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[3].id), "username": "p3", "team": "blue", "role": CodenamesRole.SPYMASTER.value},
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Disconnect the only blue player
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == users[3].id)
        )
    ).first()

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert — game finished, red wins
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == "red"

    # Assert — room's active_game_id cleared
    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.active_game_id is None


@pytest.mark.asyncio
async def test_permanent_disconnect_during_wordquiz_game(session):
    """Full chain: disconnect removes player from word quiz game."""
    # Prepare — 3 players
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    for u in users:
        await _create_link(session, room.id, u.id, connected=True)

    players_data = [{"user_id": str(u.id), "username": u.username, "score": 0} for u in users]
    game = await _create_wordquiz_game(session, room, players_data)

    # Disconnect player 1
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == users[1].id)
        )
    ).first()

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert — player removed from game, game continues
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    player_ids = [p["user_id"] for p in game.live_state["players"]]
    assert str(users[1].id) not in player_ids
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_permanent_disconnect_last_player_during_wordquiz_cancels(session):
    """Full chain: last player disconnect during word quiz cancels game and deactivates room."""
    # Prepare — 1 player
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(session, room.id, user.id, connected=True)

    players_data = [{"user_id": str(user.id), "username": user.username, "score": 0}]
    game = await _create_wordquiz_game(session, room, players_data)

    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert — game cancelled, room inactive
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.CANCELLED
    assert game.live_state["game_over"] is True

    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.type == RoomType.INACTIVE
    assert room.active_game_id is None


@pytest.mark.asyncio
async def test_permanent_disconnect_during_finished_game_no_game_handler(session):
    """Permanent disconnect during a finished game does NOT call game handlers."""
    # Prepare — game is FINISHED, not IN_PROGRESS
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    for u in users:
        await _create_link(session, room.id, u.id, connected=True)

    players_data = [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": UndercoverRole.CIVILIAN.value,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, u in enumerate(users)
    ]
    players_data[1]["role"] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, players_data)

    # Mark game as finished
    game.game_status = GameStatus.FINISHED
    session.add(game)
    await session.commit()

    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == users[2].id)
        )
    ).first()

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert — player is NOT marked dead (game handler was not called)
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[2].id))
    assert player["is_alive"] is True


# ========== Mark Stale Users Tests ==========


@pytest.mark.asyncio
async def test_mark_stale_users_marks_stale(session):
    """Users with heartbeat older than threshold are marked disconnected."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=True)

    # Set last_seen_at to way past the threshold
    link.last_seen_at = datetime.now() - timedelta(seconds=HEARTBEAT_STALE_SECONDS + 10)
    session.add(link)
    await session.commit()

    # Act
    affected_rooms = await _mark_stale_users(session)

    # Assert
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is False
    assert link.disconnected_at is not None
    assert str(room.id) in affected_rooms


@pytest.mark.asyncio
async def test_mark_stale_users_ignores_fresh(session):
    """Users with recent heartbeat are not marked stale."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=True)

    # Set last_seen_at to very recent
    link.last_seen_at = datetime.now()
    session.add(link)
    await session.commit()

    # Act
    affected_rooms = await _mark_stale_users(session)

    # Assert
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is True
    assert link.disconnected_at is None
    assert len(affected_rooms) == 0


@pytest.mark.asyncio
async def test_mark_stale_users_handles_null_last_seen(session):
    """Users with connected=True but last_seen_at=NULL and stale joined_at are marked disconnected."""
    # Prepare — user joined but never sent a heartbeat (Socket.IO never connected)
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=True)

    # Set last_seen_at to None and joined_at to well past stale threshold
    link.last_seen_at = None
    link.joined_at = datetime.now() - timedelta(seconds=HEARTBEAT_STALE_SECONDS + 10)
    session.add(link)
    await session.commit()

    # Act
    affected_rooms = await _mark_stale_users(session)

    # Assert
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is False
    assert link.disconnected_at is not None
    assert str(room.id) in affected_rooms


@pytest.mark.asyncio
async def test_mark_stale_users_ignores_recent_null_last_seen(session):
    """Users with connected=True, last_seen_at=NULL, but recent joined_at are NOT marked stale."""
    # Prepare — user just joined, Socket.IO hasn't connected yet
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=True)

    # Set last_seen_at to None but joined_at to very recent
    link.last_seen_at = None
    link.joined_at = datetime.now()
    session.add(link)
    await session.commit()

    # Act
    affected_rooms = await _mark_stale_users(session)

    # Assert
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is True
    assert link.disconnected_at is None
    assert len(affected_rooms) == 0


# ========== Remove Expired Users Tests ==========


@pytest.mark.asyncio
async def test_remove_expired_users(session):
    """Users past grace period are permanently removed when room has an active game."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)

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

    link = await _create_link(session, room.id, user.id, connected=False)

    # Set disconnected_at past the grace period
    link.disconnected_at = datetime.now() - timedelta(seconds=GRACE_PERIOD_SECONDS + 10)
    session.add(link)
    await session.commit()

    # Act
    affected_rooms, _affected_games = await _remove_expired_users(session)

    # Assert — link should be deleted
    remaining = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert remaining is None
    assert str(room.id) in affected_rooms


@pytest.mark.asyncio
async def test_remove_expired_skips_lobby_users(session):
    """Users in rooms without an active game (lobby) are NOT removed even past grace period."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=False)

    # Set disconnected_at well past the grace period
    link.disconnected_at = datetime.now() - timedelta(seconds=GRACE_PERIOD_SECONDS + 100)
    session.add(link)
    await session.commit()

    # Act
    affected_rooms, _affected_games = await _remove_expired_users(session)

    # Assert — link should still exist (lobby users are never auto-removed)
    remaining = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert remaining is not None
    assert len(affected_rooms) == 0


@pytest.mark.asyncio
async def test_remove_expired_ignores_within_grace(session):
    """Users within grace period are NOT removed."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=False)

    # Set disconnected_at within the grace period
    link.disconnected_at = datetime.now() - timedelta(seconds=GRACE_PERIOD_SECONDS - 10)
    session.add(link)
    await session.commit()

    # Act
    affected_rooms, _affected_games = await _remove_expired_users(session)

    # Assert — link should still exist
    remaining = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert remaining is not None
    assert len(affected_rooms) == 0


# ========== Mark User Disconnected Tests ==========


@pytest.mark.asyncio
async def test_mark_user_disconnected(session):
    """mark_user_disconnected sets connected=False and disconnected_at."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    await _create_link(session, room.id, user.id, connected=True)

    # Act
    await mark_user_disconnected(session, str(user.id), str(room.id))

    # Assert
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is False
    assert link.disconnected_at is not None


@pytest.mark.asyncio
async def test_mark_user_disconnected_already_disconnected(session):
    """mark_user_disconnected is a no-op if user is already disconnected."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=False)
    original_disconnected_at = datetime.now() - timedelta(seconds=30)
    link.disconnected_at = original_disconnected_at
    session.add(link)
    await session.commit()

    # Act
    await mark_user_disconnected(session, str(user.id), str(room.id))

    # Assert — no change since the query filters on connected=True
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is False


# ========== Update Heartbeat Tests ==========


@pytest.mark.asyncio
async def test_update_heartbeat(session):
    """update_heartbeat sets connected=True and refreshes last_seen_at."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id, connected=False)
    old_disconnect = datetime.now() - timedelta(seconds=30)
    link.disconnected_at = old_disconnect
    link.last_seen_at = datetime.now() - timedelta(seconds=60)
    session.add(link)
    await session.commit()

    # Act
    await update_heartbeat(session, str(user.id), str(room.id))

    # Assert
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
        )
    ).first()
    assert link.connected is True
    assert link.disconnected_at is None
    assert link.last_seen_at is not None
    assert (datetime.now() - link.last_seen_at).total_seconds() < 5


@pytest.mark.asyncio
async def test_update_heartbeat_nonexistent_link(session):
    """update_heartbeat is a no-op if no link exists."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    # No link created

    # Act — should not raise
    await update_heartbeat(session, str(user.id), str(room.id))
