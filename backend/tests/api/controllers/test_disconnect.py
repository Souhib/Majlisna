"""Tests for disconnect handler functions."""

from datetime import datetime

import pytest
from sqlmodel import select

from ipg.api.controllers.codenames_helpers import CodenamesGameStatus, CodenamesRole, CodenamesTeam
from ipg.api.controllers.disconnect import (
    _handle_codenames_disconnect,
    _handle_permanent_disconnect,
    _handle_undercover_disconnect,
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


# ─── Permanent Disconnect Tests ───────────────────────────────


class TestHandlePermanentDisconnect:
    @pytest.mark.asyncio
    async def test_removes_link(self, session):
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
    async def test_deactivates_empty_room(self, session):
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
    async def test_transfers_ownership(self, session):
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
    async def test_room_not_found(self, session):
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


# ─── Undercover Disconnect Tests ──────────────────────────────


class TestHandleUndercoverDisconnect:
    @pytest.mark.asyncio
    async def test_marks_dead(self, session):
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
    async def test_cancels_below_3(self, session):
        """Below 3 alive players → game cancelled."""
        # Prepare — 3 players, disconnect one → 2 alive → cancel
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
    async def test_checks_win_condition(self, session):
        """If disconnecting player triggers win, game ends."""
        # Prepare — 4 players: 1 undercover, 3 civilians. Disconnect the undercover → civilians win
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
    async def test_undercovers_win_when_equal(self, session):
        """If disconnect makes undercovers >= civilians, undercovers win."""
        # Prepare — 4 players: 2 undercover, 2 civilian. Disconnect a civilian → 2 uc >= 1 civ
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
    async def test_already_dead_no_re_elimination(self, session):
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


# ─── Codenames Disconnect Tests ──────────────────────────────


class TestHandleCodenamesDisconnect:
    @pytest.mark.asyncio
    async def test_removes_player(self, session):
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
    async def test_empty_team_ends_game(self, session):
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
    async def test_both_teams_have_players(self, session):
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
