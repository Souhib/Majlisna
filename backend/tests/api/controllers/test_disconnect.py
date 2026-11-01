"""Tests for disconnect handler functions."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    GRACE_PERIOD_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    LEFT_PLAYER_IDS_KEY,
    LOBBY_GRACE_PERIOD_SECONDS,
    PAUSE_STATE_KEY,
    PAUSED_GAME_GRACE_PERIOD_SECONDS,
)
from majlisna.api.controllers.codenames_helpers import CodenamesGameStatus, CodenamesRole, CodenamesTeam
from majlisna.api.controllers.disconnect import (
    _handle_codenames_disconnect,
    _handle_permanent_disconnect,
    _handle_undercover_disconnect,
    _handle_wordquiz_disconnect,
    _mark_stale_users,
    _remove_expired_users,
    _remove_member,
    away_seconds_left,
    disconnect_checker_loop,
    mark_user_disconnected,
    member_grace_seconds,
    update_heartbeat,
)
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.undercover import UndercoverRole

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
    """No crash, and the link is removed, when the link has no room to resolve.

    A room cannot disappear from under a live link: the foreign key forbids it, and
    deleting the Room through the ORM deletes its links with it (which is what this
    test used to do, so the handler then deleted an already-deleted row and
    SQLAlchemy warned "expected to delete 1 row(s); 0 were matched"). The reachable
    case is an orphan link with no room id, which `_remove_expired_users` sends here.
    """
    # Prepare — a link that points at no room
    user = await _create_user(session)
    link = await _create_link(session, None, user.id)
    link_id = link.id

    # Act — should not raise
    await _handle_permanent_disconnect(session, link)

    # Assert
    remaining = (await session.exec(select(RoomUserLink).where(RoomUserLink.id == link_id))).first()
    assert remaining is None


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
    """Below 3 alive players with a win condition -> game finished (win awarded before cancel check)."""
    # Prepare — 3 players, disconnect a civilian -> 2 alive (1 UC >= 1 CIV) -> undercovers win
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

    # Assert — win condition met (UC >= CIV), so game finishes instead of cancelling
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED


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
async def test_wq_disconnect_drops_the_players_typed_tries(session):
    """A departed player's typed tries leave with them; the others' stay for the round's results."""
    # Prepare
    users = [await _create_user(session, f"p{i}", f"p{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    players_data = [{"user_id": str(u.id), "username": u.username, "score": 0} for u in users]
    game = await _create_wordquiz_game(session, room, players_data)
    game.live_state["attempts"] = {
        str(users[1].id): {"count": 2, "last_text": "Musa", "last_hint": 2},
        str(users[2].id): {"count": 1, "last_text": "Nuh", "last_hint": 1},
    }
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    await _handle_wordquiz_disconnect(session, game, str(users[1].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert list(game.live_state["attempts"]) == [str(users[2].id)]


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
    """Full chain: disconnect during 3-player undercover game finishes it (win condition met)."""
    # Prepare — exactly 3 players (2 civ, 1 UC), disconnect a civilian -> 1 UC >= 1 CIV -> UC wins
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

    # Assert — win condition met (UC >= CIV), so game finishes
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED

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


@pytest.mark.asyncio
async def test_disconnect_transfers_ownership_to_a_player_not_a_spectator(session):
    """Host transfer prefers an actual player over a spectator.

    `remaining` includes spectators, and handing the room to `remaining[0]` blindly
    could make one of them host — while the host is who starts games, changes
    settings and kicks players, and `_prepare_game_start` excludes spectators from
    the roster entirely.
    """
    # Prepare — the spectator's link is created first, so remaining[0] is the
    # spectator unless the handler filters.
    owner = await _create_user(session, "owner_spec", "owner_spec@test.com")
    spectator = await _create_user(session, "watcher", "watcher@test.com")
    player = await _create_user(session, "player", "player@test.com")
    room = await _create_room(session, owner)
    owner_link = await _create_link(session, room.id, owner.id)
    spectator_link = await _create_link(session, room.id, spectator.id)
    spectator_link.is_spectator = True
    session.add(spectator_link)
    await session.commit()
    await _create_link(session, room.id, player.id)

    # Act
    await _handle_permanent_disconnect(session, owner_link)

    # Assert
    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.owner_id == player.id


@pytest.mark.asyncio
async def test_disconnect_transfers_ownership_to_a_spectator_as_last_resort(session):
    """With nobody but spectators left, one of them has to take the room."""
    # Prepare
    owner = await _create_user(session, "owner_only", "owner_only@test.com")
    spectator = await _create_user(session, "lone_watcher", "lone_watcher@test.com")
    room = await _create_room(session, owner)
    owner_link = await _create_link(session, room.id, owner.id)
    spectator_link = await _create_link(session, room.id, spectator.id)
    spectator_link.is_spectator = True
    session.add(spectator_link)
    await session.commit()

    # Act
    await _handle_permanent_disconnect(session, owner_link)

    # Assert
    room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert room.owner_id == spectator.id
    assert room.type == RoomType.ACTIVE


@pytest.mark.asyncio
async def test_uc_disconnect_records_stats_for_every_player(session):
    """A game that ends because someone dropped must still count for the players.

    The handlers flipped the game to FINISHED and wrote the winner but never ran the
    stat/achievement flow, so these games counted for nobody: not in totals, not in
    win streaks, not towards a badge. Ending by disconnect is a common path — a
    player closing their tab decides plenty of games.
    """
    # Prepare — 3 players; dropping a civilian leaves 1 UC vs 1 CIV, so undercovers win
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

    # Act — a civilian drops
    await _handle_undercover_disconnect(session, game, str(users[2].id), room)

    # Assert — the game ended, and every player who stayed has a stats row reflecting it
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == "undercovers"

    for user in users[:2]:
        stats = (await session.exec(select(UserStats).where(UserStats.user_id == user.id))).first()
        assert stats is not None, f"no stats recorded for {user.username}"
        assert stats.total_games_played == 1
        assert stats.undercover_games_played == 1
    # The one who left gets neither a win nor a loss (owner rule (b)): the game is not theirs
    leaver_stats = (await session.exec(select(UserStats).where(UserStats.user_id == users[2].id))).first()
    assert leaver_stats is None

    undercover_stats = (await session.exec(select(UserStats).where(UserStats.user_id == users[1].id))).first()
    civilian_stats = (await session.exec(select(UserStats).where(UserStats.user_id == users[0].id))).first()
    assert undercover_stats.total_games_won == 1
    assert civilian_stats.total_games_won == 0


@pytest.mark.asyncio
async def test_codenames_disconnect_records_stats_for_the_winning_team(session):
    """Same guarantee on the Codenames disconnect path."""
    # Prepare — the 4-player minimum; the red spymaster dropping hands blue the win
    users = [await _create_user(session, f"c{i}", f"c{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    seats = [
        (CodenamesTeam.RED, CodenamesRole.SPYMASTER),
        (CodenamesTeam.RED, CodenamesRole.OPERATIVE),
        (CodenamesTeam.BLUE, CodenamesRole.SPYMASTER),
        (CodenamesTeam.BLUE, CodenamesRole.OPERATIVE),
    ]
    players_data = [
        {"user_id": str(u.id), "username": u.username, "team": team.value, "role": role.value}
        for u, (team, role) in zip(users, seats, strict=True)
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Act — the red spymaster drops
    await _handle_codenames_disconnect(session, game, str(users[0].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == CodenamesTeam.BLUE.value

    # The blue players win, the red operative who stayed loses, and the one who
    # dropped is credited nothing (owner rule (b)).
    for winner in users[2:]:
        winner_stats = (await session.exec(select(UserStats).where(UserStats.user_id == winner.id))).one()
        assert winner_stats.codenames_games_played == 1
        assert winner_stats.total_games_won == 1
    loser_stats = (await session.exec(select(UserStats).where(UserStats.user_id == users[1].id))).one()
    assert loser_stats.codenames_games_played == 1
    assert loser_stats.total_games_won == 0
    assert (await session.exec(select(UserStats).where(UserStats.user_id == users[0].id))).first() is None


# ========== A drop-out must never wedge the round it was blocking ==========
#
# All four cases below used to leave a live game with no legal move left. None of
# them were rescued by the timer: `description_timer` / `voting_timer` both default
# to 0, which means "no time limit", so `handle_timer_expired` answers
# `timer_not_expired` forever. The room's only escape was the host cancelling the
# game through a rematch. See undercover_rules.repair_turn_after_dropout.


def _uc_players(users, roles):
    return [
        {
            "user_id": str(u.id),
            "username": u.username,
            "role": role,
            "is_alive": True,
            "is_mayor": i == 0,
        }
        for i, (u, role) in enumerate(zip(users, roles, strict=True))
    ]


@pytest.mark.asyncio
async def test_dropout_of_the_last_outstanding_voter_resolves_the_round(session):
    """A tally that becomes complete by subtraction must still be counted.

    `all_voted` is only ever evaluated inside `submit_vote`. When the one player
    everybody was waiting on left instead of voting, every remaining alive player
    had already voted and no further vote could arrive — so the round sat complete
    and uncounted, permanently.
    """
    # Prepare — 5 players; everyone but p3 has voted, and p3 is about to drop
    users = [await _create_user(session, f"v{i}", f"v{i}@test.com") for i in range(5)]
    room = await _create_room(session, users[0])
    roles = [UndercoverRole.CIVILIAN.value] * 4 + [UndercoverRole.UNDERCOVER.value]
    players_data = _uc_players(users, roles)
    game = await _create_undercover_game(session, room, players_data)

    votes = {str(users[i].id): str(users[4].id) for i in range(3)}
    votes[str(users[4].id)] = str(users[0].id)
    state = game.live_state
    state["turns"][-1] = {
        "votes": votes,
        "words": {},
        "description_order": [str(u.id) for u in users],
        "current_describer_index": 5,
        "phase": "voting",
    }
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — the only player who had not voted leaves
    await _handle_undercover_disconnect(session, game, str(users[3].id), room)

    # Assert — the round resolved on the votes that were in, exactly once
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    turn = game.live_state["turns"][-1]
    assert turn["resolved"] is True
    voted_out = [e for e in game.live_state["eliminated_players"] if e["round"] == 1]
    assert len(voted_out) == 1
    assert voted_out[0]["user_id"] == str(users[4].id)


@pytest.mark.asyncio
async def test_dropout_of_the_current_describer_hands_the_turn_on(session):
    """`submit_description` only accepts the player at `current_describer_index`.

    With that index pointing at someone who has left, nobody could describe and the
    phase could never reach voting.
    """
    # Prepare — 4 players, it is p1's turn to describe
    users = [await _create_user(session, f"d{i}", f"d{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    roles = [UndercoverRole.CIVILIAN.value] * 3 + [UndercoverRole.UNDERCOVER.value]
    game = await _create_undercover_game(session, room, _uc_players(users, roles))

    state = game.live_state
    state["turns"][-1] = {
        "votes": {},
        "words": {str(users[0].id): "dome"},
        "description_order": [str(u.id) for u in users],
        "current_describer_index": 1,
        "phase": "describing",
    }
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — the player everyone is waiting on leaves
    await _handle_undercover_disconnect(session, game, str(users[1].id), room)

    # Assert — the turn passes to the next describer, still in the describing phase
    turn = (await session.exec(select(Game).where(Game.id == game.id))).first().live_state["turns"][-1]
    assert turn["phase"] == "describing"
    assert turn["description_order"][turn["current_describer_index"]] == str(users[2].id)
    # The order keeps every entry: it is also what renders the descriptions already
    # given, and p0's word is evidence the table still votes on.
    assert turn["description_order"] == [str(u.id) for u in users]
    assert turn["words"][str(users[0].id)] == "dome"


@pytest.mark.asyncio
async def test_dropout_of_the_last_describer_opens_the_vote(session):
    """When the departure leaves nobody left to describe, the round moves to voting."""
    # Prepare — 4 players, only the last one still owes a description. The undercover
    # is p1, so p3 leaving does not decide the game on its own.
    users = [await _create_user(session, f"l{i}", f"l{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    roles = [
        UndercoverRole.CIVILIAN.value,
        UndercoverRole.UNDERCOVER.value,
        UndercoverRole.CIVILIAN.value,
        UndercoverRole.CIVILIAN.value,
    ]
    game = await _create_undercover_game(session, room, _uc_players(users, roles))

    state = game.live_state
    state["turns"][-1] = {
        "votes": {},
        "words": {str(u.id): "dome" for u in users[:3]},
        "description_order": [str(u.id) for u in users],
        "current_describer_index": 3,
        "phase": "describing",
    }
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    await _handle_undercover_disconnect(session, game, str(users[3].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.game_status == GameStatus.IN_PROGRESS
    assert game.live_state["turns"][-1]["phase"] == "voting"


@pytest.mark.asyncio
async def test_dropout_of_the_mr_white_guesser_leaves_a_playable_phase(session):
    """Losing the guesser must not leave the turn stuck on `mr_white_guessing`.

    Guessing 403s once nobody matches `mr_white_guesser`, and voting and describing
    both reject the phase — the same wedge the guess *timeout* already fixed.
    """
    # Prepare — 5 players, Mr. White eliminated and owing a guess
    users = [await _create_user(session, f"w{i}", f"w{i}@test.com") for i in range(5)]
    room = await _create_room(session, users[0])
    roles = [
        UndercoverRole.CIVILIAN.value,
        UndercoverRole.CIVILIAN.value,
        UndercoverRole.CIVILIAN.value,
        UndercoverRole.UNDERCOVER.value,
        UndercoverRole.MR_WHITE.value,
    ]
    players_data = _uc_players(users, roles)
    players_data[4]["is_alive"] = False
    game = await _create_undercover_game(session, room, players_data)

    state = game.live_state
    state["mr_white_guesser"] = str(users[4].id)
    state["turns"][-1]["phase"] = "mr_white_guessing"
    state["turns"][-1]["resolved"] = True
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — the eliminated Mr. White closes their tab instead of guessing
    await _handle_undercover_disconnect(session, game, str(users[4].id), room)

    # Assert — the phase is one the game can leave, and no guesser is owed
    state = (await session.exec(select(Game).where(Game.id == game.id))).first().live_state
    assert "mr_white_guesser" not in state
    assert state["turns"][-1]["phase"] == "voting"


@pytest.mark.asyncio
async def test_cn_disconnect_of_the_only_spymaster_ends_the_game(session):
    """A team with operatives but no spymaster can never receive a clue.

    `give_clue` requires a spymaster on the team to move, so `guess_card` answers
    NoClueGivenError forever and the side can only ever pass its turn — and the
    Codenames timers default to 0, so nothing switches the turn either.
    """
    # Prepare — the 4-player minimum: 1 spymaster + 1 operative per side
    users = [await _create_user(session, f"s{i}", f"s{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {"user_id": str(users[0].id), "username": "s0", "team": "red", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[1].id), "username": "s1", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[2].id), "username": "s2", "team": "blue", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[3].id), "username": "s3", "team": "blue", "role": CodenamesRole.OPERATIVE.value},
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Act — blue loses its spymaster while still holding an operative
    await _handle_codenames_disconnect(session, game, str(users[2].id), room)

    # Assert — red wins rather than the game sitting unplayable
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
    assert game.live_state["winner"] == CodenamesTeam.RED.value
    assert game.game_status == GameStatus.FINISHED


@pytest.mark.asyncio
async def test_cn_disconnect_of_the_only_operative_ends_the_game(session):
    """A team with a spymaster but no operative cannot guess and cannot end its turn."""
    # Prepare
    users = [await _create_user(session, f"o{i}", f"o{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    players_data = [
        {"user_id": str(users[0].id), "username": "o0", "team": "red", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[1].id), "username": "o1", "team": "red", "role": CodenamesRole.OPERATIVE.value},
        {"user_id": str(users[2].id), "username": "o2", "team": "blue", "role": CodenamesRole.SPYMASTER.value},
        {"user_id": str(users[3].id), "username": "o3", "team": "blue", "role": CodenamesRole.OPERATIVE.value},
    ]
    game = await _create_codenames_game(session, room, players_data)

    # Act — red loses its only operative
    await _handle_codenames_disconnect(session, game, str(users[1].id), room)

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id))).first()
    assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
    assert game.live_state["winner"] == CodenamesTeam.BLUE.value
    assert game.game_status == GameStatus.FINISHED


# ========== The away countdown shown in the lobby (pure) ==========

_NOW = datetime(2026, 10, 28, 12, 0, 0)  # naive, like every RoomUserLink timestamp


@pytest.mark.parametrize(
    ("connected", "seconds_ago", "grace", "expected"),
    [
        (True, None, 600, None),  # present: no countdown
        (False, None, 600, None),  # away without a timestamp is never swept, so no countdown
        (False, 0, 600, 600),  # just left: the whole grace ("away · 10:00")
        (False, 2.2, 600, 598),  # rounded up: 597.8 reads 598 ("away · 9:58")
        (False, 600, 600, 0),  # due
        (False, 900, 180, 0),  # long past due: never negative
        (False, -30, 180, 180),  # an anchor after `now` never reads more than the grace
    ],
)
def test_away_seconds_left(connected: bool, seconds_ago: float | None, grace: int, expected: int | None):
    """Whole seconds before the sweep removes an away member — null while they are present."""
    # Prepare
    link = RoomUserLink(
        connected=connected,
        disconnected_at=_NOW - timedelta(seconds=seconds_ago) if seconds_ago is not None else None,
    )

    # Act
    left = away_seconds_left(link, grace, _NOW)

    # Assert
    assert left == expected


def test_member_grace_matches_the_sweep():
    """The lobby, a running game and a paused game each get the grace the sweep applies."""
    # Prepare
    lobby = Room(owner_id=None, public_id="AAAAA", password="1234", type=RoomType.ACTIVE)
    running_game = Game(
        number_of_players=3, type=GameType.UNDERCOVER, game_status=GameStatus.IN_PROGRESS, live_state={}
    )
    paused_game = Game(
        number_of_players=3,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.IN_PROGRESS,
        live_state={"paused": {"by": "u", "by_username": "u", "at": "2026-10-28T12:00:00+00:00", "reason": "salah"}},
    )
    in_game = Room(
        owner_id=None, public_id="BBBBB", password="1234", type=RoomType.ACTIVE, active_game_id=running_game.id
    )
    in_paused = Room(
        owner_id=None, public_id="CCCCC", password="1234", type=RoomType.ACTIVE, active_game_id=paused_game.id
    )

    # Act / Assert
    assert member_grace_seconds(lobby, None) == LOBBY_GRACE_PERIOD_SECONDS
    assert member_grace_seconds(in_game, running_game) == GRACE_PERIOD_SECONDS
    assert member_grace_seconds(in_paused, paused_game) == PAUSED_GAME_GRACE_PERIOD_SECONDS


# ========== WP-04: every departure is a leaver (owner rule (b)) ==========
#
# A player who leaves before the end gets neither a win nor a loss, in all four
# games: each `_handle_*_disconnect` records them with `mark_player_left` as soon as
# it finds them, before any end-of-game write, and `game_end_stats.scorable_players`
# then skips them. The Undercover handler kept the drop-out in `players` (dead), so
# a civilian who walked out of a game the civilians later won was credited the win.


async def _create_mcqquiz_game(session, room, players_data):
    """Create a game with MCQ live_state, its question open."""
    game = Game(
        room_id=room.id,
        type=GameType.MCQ_QUIZ,
        number_of_players=len(players_data),
        game_status=GameStatus.IN_PROGRESS,
        live_state={
            "players": players_data,
            "current_round": 1,
            "total_rounds": 5,
            "round_phase": "playing",
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


async def _leaver_undercover(session, room, users):
    roles = [UndercoverRole.CIVILIAN.value] * len(users)
    roles[1] = UndercoverRole.UNDERCOVER.value
    return await _create_undercover_game(session, room, _uc_players(users, roles))


async def _leaver_codenames(session, room, users):
    teams = ["red", "red", "red", "blue", "blue", "blue"]
    roles = [CodenamesRole.SPYMASTER.value, CodenamesRole.OPERATIVE.value, CodenamesRole.OPERATIVE.value] * 2
    players = [
        {"user_id": str(u.id), "username": u.username, "team": team, "role": role}
        for u, team, role in zip(users, teams, roles, strict=True)
    ]
    return await _create_codenames_game(session, room, players)


async def _leaver_wordquiz(session, room, users):
    return await _create_wordquiz_game(
        session, room, [{"user_id": str(u.id), "username": u.username, "score": 0} for u in users]
    )


async def _leaver_mcqquiz(session, room, users):
    return await _create_mcqquiz_game(
        session, room, [{"user_id": str(u.id), "username": u.username, "total_score": 0} for u in users]
    )


@pytest.mark.parametrize(
    "build_game",
    [_leaver_undercover, _leaver_codenames, _leaver_wordquiz, _leaver_mcqquiz],
    ids=["undercover", "codenames", "word_quiz", "mcq_quiz"],
)
@pytest.mark.asyncio
async def test_every_departure_marks_the_player_as_a_leaver(session, engine, build_game):
    """In all four games, a departure appends the user to live_state['left_player_ids']."""
    # Prepare — six players seated; the third one leaves (a red operative in Codenames)
    users = [await _create_user(session, f"lv{i}", f"lv{i}@test.com") for i in range(6)]
    room = await _create_room(session, users[0])
    links = [await _create_link(session, room.id, u.id) for u in users]
    game = await build_game(session, room, users)

    # Act
    await _handle_permanent_disconnect(session, links[2])

    # Assert — read back as committed, in a session of its own
    async with AsyncSession(engine, expire_on_commit=False) as fresh:
        stored = (await fresh.exec(select(Game).where(Game.id == game.id))).one()
    assert stored.live_state[LEFT_PLAYER_IDS_KEY] == [str(users[2].id)]
    assert stored.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_an_undercover_drop_out_never_shares_the_win_of_their_side(session):
    """A civilian walks out; the civilians later win: the leaver's stats do not move."""
    # Prepare — users[1] is the undercover, the other three civilians
    users = [await _create_user(session, f"dw{i}", f"dw{i}@test.com") for i in range(4)]
    room = await _create_room(session, users[0])
    links = [await _create_link(session, room.id, u.id) for u in users]
    roles = [UndercoverRole.CIVILIAN.value] * 4
    roles[1] = UndercoverRole.UNDERCOVER.value
    game = await _create_undercover_game(session, room, _uc_players(users, roles))

    # Act — a civilian leaves, then the undercover does: the civilians win
    await _handle_permanent_disconnect(session, links[2])
    await _handle_permanent_disconnect(session, links[1])

    # Assert
    game = (await session.exec(select(Game).where(Game.id == game.id).execution_options(populate_existing=True))).one()
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == "civilians"
    leaver_stats = (await session.exec(select(UserStats).where(UserStats.user_id == users[2].id))).first()
    assert leaver_stats is None, "the civilian who walked out is credited nothing"
    for stayed in (users[0], users[3]):
        stats = (await session.exec(select(UserStats).where(UserStats.user_id == stayed.id))).one()
        assert stats.total_games_won == 1


# ========== WP-04 / BR-05: a room that lets go of its game ends it ==========


async def _fresh(session, model, pk):
    return (await session.exec(select(model).where(model.id == pk).execution_options(populate_existing=True))).one()


async def _start_undercover(session, setup_undercover_game, num_players: int):
    """A started Undercover game without Mr. White; returns (setup, game_id)."""
    setup = await setup_undercover_game(num_players)
    room = await _fresh(session, Room, setup["room"].id)
    room.settings = {**(room.settings or {}), "enable_mr_white": False}
    flag_modified(room, "settings")
    session.add(room)
    await session.commit()
    started = await UndercoverGameController(session).create_and_start(setup["room"].id, setup["users"][0].id)
    return setup, UUID(started.game_id)


async def _everyone_away_but(session, room_id, present_user_id, *, seconds_ago: float = 0):
    links = (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()
    for link in links:
        if present_user_id is not None and link.user_id == present_user_id:
            continue
        link.connected = False
        link.disconnected_at = datetime.now() - timedelta(seconds=seconds_ago)
        session.add(link)
    await session.commit()


@pytest.mark.asyncio
async def test_the_last_connected_member_leaving_cancels_the_running_game(session, setup_undercover_game):
    """Every other phone is away; the one connected player leaves: the game is CANCELLED, not orphaned.

    The room was deactivated and unlinked from a game left IN_PROGRESS for ever: later
    removals skipped it (no active game), it read "In progress" in every history, and
    its words could never be kept or summarised.
    """
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 6)
    room_id = setup["room"].id
    game = await _fresh(session, Game, game_id)
    leaver = next(p for p in game.live_state["players"] if p["role"] == "civilian")
    # Every other phone away for longer than the grace: nobody is coming back.
    await _everyone_away_but(session, room_id, UUID(leaver["user_id"]), seconds_ago=GRACE_PERIOD_SECONDS + 30)

    # Act
    await RoomController(session).leave_room(room_id, UUID(leaver["user_id"]))

    # Assert
    room = await _fresh(session, Room, room_id)
    game = await _fresh(session, Game, game_id)
    assert room.type == RoomType.INACTIVE
    assert room.active_game_id is None
    assert game.game_status == GameStatus.CANCELLED
    assert game.end_time is not None
    cancelled_at = game.end_time

    # Act — the grace sweep removes everyone else later on
    links = (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()
    for link in links:
        link.disconnected_at = datetime.now() - timedelta(seconds=LOBBY_GRACE_PERIOD_SECONDS + 100)
        session.add(link)
    await session.commit()
    await _remove_expired_users(session)

    # Assert — still cancelled, once
    assert not (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()
    game = await _fresh(session, Game, game_id)
    assert game.game_status == GameStatus.CANCELLED
    assert game.end_time == cancelled_at


@pytest.mark.asyncio
async def test_a_prayer_pause_outlasted_by_every_phone_cancels_the_game(session, setup_undercover_game):
    """The host pauses for the prayer, every phone sleeps 46 min: CANCELLED, not left running and paused."""
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 4)
    room_id = setup["room"].id
    await UndercoverGameController(session).pause_game(game_id, setup["users"][0].id)
    await _everyone_away_but(session, room_id, None, seconds_ago=PAUSED_GAME_GRACE_PERIOD_SECONDS + 60)

    # Act
    await _remove_expired_users(session)

    # Assert
    game = await _fresh(session, Game, game_id)
    room = await _fresh(session, Room, room_id)
    assert game.game_status == GameStatus.CANCELLED
    assert game.end_time is not None
    assert PAUSE_STATE_KEY not in game.live_state
    assert room.type == RoomType.INACTIVE
    assert room.active_game_id is None
    assert not (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()


async def _assert_cancelled_for_everyone(session, game_id, room_id, leaver_id: str) -> None:
    """CANCELLED with no winner, the leaver marked, the room let go, and no player credited."""
    game = await _fresh(session, Game, game_id)
    room = await _fresh(session, Room, room_id)
    assert game.game_status == GameStatus.CANCELLED
    assert game.end_time is not None
    assert game.live_state.get("winner") is None
    assert leaver_id in game.live_state[LEFT_PLAYER_IDS_KEY]
    assert room.type == RoomType.INACTIVE
    assert room.active_game_id is None
    for player in game.live_state["players"]:
        stats = (await session.exec(select(UserStats).where(UserStats.user_id == UUID(player["user_id"])))).first()
        assert stats is None or stats.total_games_played == 0, player["username"]


@pytest.mark.asyncio
async def test_a_departure_that_leaves_nobody_connected_cancels_the_game_instead_of_deciding_it(
    session, setup_undercover_game
):
    """The undercover is the last phone still connected and leaves: CANCELLED, not a civilians' win.

    The departure used to be played into the game first: it decided it, and the three
    civilians — every one of them away — were credited a win for a game none of them
    saw end. Only then was the room found empty and deactivated.
    """
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 4)
    room_id = setup["room"].id
    game = await _fresh(session, Game, game_id)
    undercover = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value)
    await _everyone_away_but(session, room_id, UUID(undercover["user_id"]), seconds_ago=GRACE_PERIOD_SECONDS + 30)

    # Act
    await RoomController(session).leave_room(room_id, UUID(undercover["user_id"]))

    # Assert
    await _assert_cancelled_for_everyone(session, game_id, room_id, undercover["user_id"])


@pytest.mark.asyncio
async def test_a_paused_game_whose_undercover_is_swept_first_is_cancelled(session, setup_undercover_game):
    """Every phone asleep through the prayer; the undercover's grace runs out first: CANCELLED.

    Which link the sweep removed first decided the result: the undercover's made it a
    civilians' win credited to sleeping phones, anyone else's a cancellation.
    """
    # Prepare — every phone past the paused grace, the undercover's the longest
    setup, game_id = await _start_undercover(session, setup_undercover_game, 4)
    room_id = setup["room"].id
    await UndercoverGameController(session).pause_game(game_id, setup["users"][0].id)
    game = await _fresh(session, Game, game_id)
    undercover = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value)
    await _everyone_away_but(session, room_id, None, seconds_ago=PAUSED_GAME_GRACE_PERIOD_SECONDS + 30)
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == room_id)
            .where(RoomUserLink.user_id == UUID(undercover["user_id"]))
        )
    ).one()
    link.disconnected_at = datetime.now() - timedelta(seconds=PAUSED_GAME_GRACE_PERIOD_SECONDS + 60)
    session.add(link)
    await session.commit()

    # Act — the sweep's own removal of the undercover's seat, first: the sweep's row order
    # is the database's (PostgreSQL gives no order), so the test names the first removal
    await _remove_member(session, link, only_if_expired=True)
    await _remove_expired_users(session)

    # Assert
    await _assert_cancelled_for_everyone(session, game_id, room_id, undercover["user_id"])
    assert PAUSE_STATE_KEY not in (await _fresh(session, Game, game_id)).live_state
    assert not await _seats(session, room_id)


async def _seats(session, room_id) -> list[RoomUserLink]:
    return list(
        (
            await session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == room_id).execution_options(populate_existing=True)
            )
        ).all()
    )


async def _age_link(session, room_id, user_id: str, seconds_ago: float) -> None:
    link = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == UUID(user_id))
        )
    ).one()
    link.connected = False
    link.disconnected_at = datetime.now() - timedelta(seconds=seconds_ago)
    session.add(link)
    await session.commit()


@pytest.mark.asyncio
async def test_a_sweep_while_the_others_are_only_briefly_away_plays_the_departure(session, setup_undercover_game):
    """One phone past its grace, the four others locked for 25 s: the departure is played, the game goes on.

    A room used to count as empty when nobody was CONNECTED, so a sweep during the
    in-person discussion (phones lock, heartbeats go stale after 20 s) cancelled the
    game for four players still seated and inside their 180 s grace.
    """
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 5)
    room_id = setup["room"].id
    game = await _fresh(session, Game, game_id)
    gone = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value)
    await _everyone_away_but(session, room_id, None, seconds_ago=25)
    await _age_link(session, room_id, gone["user_id"], GRACE_PERIOD_SECONDS + 10)

    # Act
    await _remove_expired_users(session)

    # Assert
    game = await _fresh(session, Game, game_id)
    room = await _fresh(session, Room, room_id)
    assert len(await _seats(session, room_id)) == 4
    assert room.type == RoomType.ACTIVE
    assert room.active_game_id == game_id
    assert game.game_status == GameStatus.IN_PROGRESS
    assert gone["user_id"] in game.live_state[LEFT_PLAYER_IDS_KEY]
    leaver = next(p for p in game.live_state["players"] if p["user_id"] == gone["user_id"])
    assert leaver["is_alive"] is False


@pytest.mark.asyncio
async def test_a_paused_game_outlasted_by_one_phone_only_plays_that_departure(session, setup_undercover_game):
    """During the prayer one phone outlasts the 45 min, the others are 10 min in: nobody else's game is cancelled."""
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 5)
    room_id = setup["room"].id
    await UndercoverGameController(session).pause_game(game_id, setup["users"][0].id)
    game = await _fresh(session, Game, game_id)
    gone = next(
        p
        for p in game.live_state["players"]
        if p["role"] == UndercoverRole.CIVILIAN.value and p["user_id"] != str(setup["users"][0].id)
    )
    await _everyone_away_but(session, room_id, None, seconds_ago=600)
    await _age_link(session, room_id, gone["user_id"], PAUSED_GAME_GRACE_PERIOD_SECONDS + 60)

    # Act
    await _remove_expired_users(session)

    # Assert
    game = await _fresh(session, Game, game_id)
    room = await _fresh(session, Room, room_id)
    assert len(await _seats(session, room_id)) == 4
    assert room.type == RoomType.ACTIVE
    assert game.game_status == GameStatus.IN_PROGRESS
    assert PAUSE_STATE_KEY in game.live_state
    assert gone["user_id"] in game.live_state[LEFT_PLAYER_IDS_KEY]


@pytest.mark.asyncio
async def test_the_last_connected_member_leaving_while_the_others_are_within_grace_keeps_the_room(
    session, setup_undercover_game
):
    """A voluntary leave by the only phone awake: the room stays live for the seats still inside their grace."""
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 5)
    room_id = setup["room"].id
    game = await _fresh(session, Game, game_id)
    leaver = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value)
    await _everyone_away_but(session, room_id, UUID(leaver["user_id"]), seconds_ago=30)

    # Act
    await RoomController(session).leave_room(room_id, UUID(leaver["user_id"]))

    # Assert
    room = await _fresh(session, Room, room_id)
    game = await _fresh(session, Game, game_id)
    assert room.type == RoomType.ACTIVE
    assert room.active_game_id == game_id
    assert game.game_status == GameStatus.IN_PROGRESS
    assert leaver["user_id"] in game.live_state[LEFT_PLAYER_IDS_KEY]


@pytest.mark.asyncio
async def test_the_host_leaving_hands_the_room_to_a_player_within_grace_before_a_spectator(session):
    """Host transfer: a connected player, else a player inside their grace, and only then a spectator."""
    # Prepare
    host = await _create_user(session, "h", "h@test.com")
    away_player = await _create_user(session, "ap", "ap@test.com")
    watcher = await _create_user(session, "sp", "sp@test.com")
    room = await _create_room(session, host)
    host_link = await _create_link(session, room.id, host.id)
    await _create_link(session, room.id, away_player.id, connected=False)
    spectator_link = await _create_link(session, room.id, watcher.id)
    spectator_link.is_spectator = True
    session.add(spectator_link)
    await _age_link(session, room.id, str(away_player.id), 30)

    # Act
    await _handle_permanent_disconnect(session, host_link)

    # Assert
    room = await _fresh(session, Room, room.id)
    assert room.type == RoomType.ACTIVE
    assert room.owner_id == away_player.id


@pytest.mark.asyncio
async def test_a_lobby_whose_others_are_past_their_grace_is_deactivated(session):
    """The away seats that will be swept next do not keep a lobby alive."""
    # Prepare
    host = await _create_user(session, "h2", "h2@test.com")
    gone = await _create_user(session, "g2", "g2@test.com")
    room = await _create_room(session, host)
    host_link = await _create_link(session, room.id, host.id)
    await _create_link(session, room.id, gone.id, connected=False)
    await _age_link(session, room.id, str(gone.id), LOBBY_GRACE_PERIOD_SECONDS + 30)

    # Act
    await _handle_permanent_disconnect(session, host_link)

    # Assert
    room = await _fresh(session, Room, room.id)
    assert room.type == RoomType.INACTIVE


@pytest.mark.asyncio
async def test_the_last_quiz_player_leaving_a_paused_game_cancels_it_unpaused(session):
    """Cancelled through game_cancel: a cancelled game is not paused, and nobody can resume it."""
    # Prepare
    user = await _create_user(session)
    room = await _create_room(session, user)
    link = await _create_link(session, room.id, user.id)
    game = await _create_wordquiz_game(session, room, [{"user_id": str(user.id), "username": "u", "score": 0}])
    game.live_state[PAUSE_STATE_KEY] = {
        "by": str(user.id),
        "by_username": "u",
        "at": datetime.now(UTC).isoformat(),
        "reason": "salah",
    }
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    await _handle_permanent_disconnect(session, link)

    # Assert
    game = await _fresh(session, Game, game.id)
    assert game.game_status == GameStatus.CANCELLED
    assert PAUSE_STATE_KEY not in game.live_state


@pytest.mark.asyncio
async def test_finishing_an_old_game_by_a_departure_keeps_the_rooms_new_game(session):
    """A finish path detaches the room only from ITS game (BR-06): an old game ending must not unlink the new one."""
    # Prepare — the room runs a new game; an old one of the same room is still IN_PROGRESS
    users = [await _create_user(session, f"og{i}", f"og{i}@test.com") for i in range(3)]
    room = await _create_room(session, users[0])
    roles = [UndercoverRole.CIVILIAN.value, UndercoverRole.UNDERCOVER.value, UndercoverRole.CIVILIAN.value]
    old_game = await _create_undercover_game(session, room, _uc_players(users, roles))
    new_game = await _create_undercover_game(session, room, _uc_players(users, roles))
    assert room.active_game_id == new_game.id

    # Act — the old game's undercover leaves it: the civilians win the OLD game
    await _handle_undercover_disconnect(session, old_game, str(users[1].id), room)

    # Assert
    old_game = await _fresh(session, Game, old_game.id)
    room = await _fresh(session, Room, room.id)
    assert old_game.game_status == GameStatus.FINISHED
    assert room.active_game_id == new_game.id


async def _run_one_tick(engine, **callbacks):
    """One tick of the checker loop: its sleep raises CancelledError, which ends it."""
    with (
        patch("majlisna.api.controllers.disconnect.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)),
        pytest.raises(asyncio.CancelledError),
    ):
        await disconnect_checker_loop(engine, **callbacks)


@pytest.mark.asyncio
async def test_the_sweep_cancels_games_already_orphaned(session, engine):
    """IN_PROGRESS games whose room is INACTIVE, or points at another game, are cancelled by the sweep.

    The orphans written before the fix are in the database already; nothing else
    reaches them, because every departure path starts from `room.active_game_id`.
    """
    # Prepare — an orphan of a deactivated room, an orphan replaced by a newer game, a healthy game
    users = [await _create_user(session, f"or{i}", f"or{i}@test.com") for i in range(3)]
    players = _uc_players(users, [UndercoverRole.CIVILIAN.value] * 3)
    dead_room = Room(public_id="DEADR", owner_id=None, status="online", password="1", type=RoomType.INACTIVE)
    busy_room = Room(public_id="BUSYR", owner_id=users[1].id, status="online", password="1", type=RoomType.ACTIVE)
    session.add_all([dead_room, busy_room])
    await session.commit()
    deactivated_orphan = await _create_undercover_game(session, dead_room, players)
    dead_room.active_game_id = None
    session.add(dead_room)
    await session.commit()
    replaced_orphan = await _create_undercover_game(session, busy_room, players)
    current = await _create_undercover_game(session, busy_room, players)
    game_updates: list[str] = []

    # Act
    await _run_one_tick(engine, on_game_changed=game_updates.append)

    # Assert
    for orphan in (deactivated_orphan, replaced_orphan):
        stored = await _fresh(session, Game, orphan.id)
        assert stored.game_status == GameStatus.CANCELLED
        assert stored.end_time is not None
        assert str(orphan.id) in game_updates
    assert (await _fresh(session, Game, current.id)).game_status == GameStatus.IN_PROGRESS
    assert (await _fresh(session, Room, busy_room.id)).active_game_id == current.id


# ========== WP-04 / BR-09: a departed operative's card vote ==========
#
# `current_turn.card_votes` kept the leaver's ballot: it filled the team's quorum
# before every remaining operative had voted, and could be the card turned. The
# departure now releases it (`codenames_helpers.release_departed_operative`), and
# when the leaver was the last operative the team was waiting on, the votes in hand
# settle the guess at once — nobody left could vote again to trigger it.


async def _codenames_seven_with_a_clue(session, card_votes_by_index: dict[int, int], *, card_type: str = "neutral"):
    """Red: spymaster + operatives 1, 2, 3; blue: spymaster + 2 operatives. Red has a clue."""
    users = [await _create_user(session, f"cv{i}", f"cv{i}@test.com") for i in range(7)]
    room = await _create_room(session, users[0])
    links = [await _create_link(session, room.id, u.id) for u in users]
    seats = [("red", CodenamesRole.SPYMASTER)] + [("red", CodenamesRole.OPERATIVE)] * 3
    seats += [("blue", CodenamesRole.SPYMASTER)] + [("blue", CodenamesRole.OPERATIVE)] * 2
    players = [
        {"user_id": str(u.id), "username": u.username, "team": team, "role": role.value}
        for u, (team, role) in zip(users, seats, strict=True)
    ]
    game = await _create_codenames_game(session, room, players)
    state = dict(game.live_state)
    state["board"][10]["card_type"] = card_type
    state["current_turn"] = {
        **state["current_turn"],
        "clue_word": "Sabr",
        "clue_number": 2,
        "max_guesses": 3,
        "card_votes": {str(users[i].id): card for i, card in card_votes_by_index.items()},
    }
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    return users, room, links, game


@pytest.mark.asyncio
async def test_a_departed_operatives_card_vote_never_counts(session):
    """Operative 1 votes card 2 and leaves; operative 2 voted 10; operative 3 has not voted: nothing turns."""
    # Prepare
    users, _room, links, game = await _codenames_seven_with_a_clue(session, {1: 2, 2: 10})

    # Act
    await _handle_permanent_disconnect(session, links[1])

    # Assert — the leaver's ballot is gone, and the quorum (2 and 3) is not complete
    game = await _fresh(session, Game, game.id)
    assert game.live_state["current_turn"]["card_votes"] == {str(users[2].id): 10}
    assert not any(card["revealed"] for card in game.live_state["board"])
    assert not game.live_state.get("reveal_log")
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_the_departure_of_the_last_missing_voter_settles_the_guess(session):
    """Operatives 2 and 3 voted card 10; operative 1, the one the team waited on, leaves: card 10 turns."""
    # Prepare
    users, _room, links, game = await _codenames_seven_with_a_clue(session, {2: 10, 3: 10})

    # Act
    await _handle_permanent_disconnect(session, links[1])

    # Assert
    game = await _fresh(session, Game, game.id)
    assert game.live_state["board"][10]["revealed"] is True
    entry = game.live_state["reveal_log"][-1]
    assert entry["card_index"] == 10
    assert entry["team"] == "red"
    assert sorted(entry["voter_ids"]) == sorted([str(users[2].id), str(users[3].id)])
    assert game.live_state["current_team"] == "blue", "a neutral card passes the turn"
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_a_departure_that_turns_the_assassin_finishes_the_game(session):
    """The settled guess is the assassin: the game ends like the guess path ends it."""
    # Prepare
    users, room, links, game = await _codenames_seven_with_a_clue(session, {2: 10, 3: 10}, card_type="assassin")

    # Act
    await _handle_permanent_disconnect(session, links[1])

    # Assert — FINISHED, blue wins, the room let go of the game, the stats are written
    game = await _fresh(session, Game, game.id)
    room = await _fresh(session, Room, room.id)
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None
    assert game.live_state["winner"] == "blue"
    assert room.active_game_id is None
    blue_spymaster = (await session.exec(select(UserStats).where(UserStats.user_id == users[4].id))).one()
    assert blue_spymaster.total_games_won == 1
    assert (await session.exec(select(UserStats).where(UserStats.user_id == users[1].id))).first() is None
