"""Tests for ``controllers/game_cancel.py``: ending a running game that nothing else will end.

BR-05: deactivating a room (its last connected member leaves, or ``delete_room``) used
to detach the running game without ending it, so it stayed IN_PROGRESS forever. BR-06:
a finish path cleared ``room.active_game_id`` unconditionally, unlinking the room's NEW
game. These are the two helpers every such path calls.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import PAUSE_STATE_KEY
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.game_cancel import cancel_running_game, detach_room_if_current
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.table import Game, Room


async def _running_game(session: AsyncSession, game_controller: GameController, room: Room, *, paused: bool) -> Game:
    """An IN_PROGRESS game the room points at, optionally paused for the prayer."""
    game = await game_controller.create_game(
        GameCreate(room_id=room.id, type=GameType.UNDERCOVER, number_of_players=3, game_status=GameStatus.IN_PROGRESS)
    )
    game.live_state = {"players": [], "phase": "describing"}
    if paused:
        game.live_state[PAUSE_STATE_KEY] = {"by": str(room.owner_id), "at": datetime.now(UTC).isoformat()}
    flag_modified(game, "live_state")
    room.active_game_id = game.id
    session.add(game)
    session.add(room)
    await session.commit()
    return game


async def _reload(session: AsyncSession, game: Game, room: Room) -> tuple[Game, Room]:
    session.expunge_all()
    db_game = (await session.exec(select(Game).where(Game.id == game.id))).one()
    db_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    return db_game, db_room


@pytest.mark.asyncio
async def test_a_running_game_is_cancelled_and_its_room_detached(
    session: AsyncSession, game_controller: GameController, sample_room: Room
):
    """IN_PROGRESS -> CANCELLED, end_time set, the pause cleared, the room let go."""
    # Prepare
    game = await _running_game(session, game_controller, sample_room, paused=True)

    # Act
    cancelled = await cancel_running_game(session, game, sample_room)
    await session.commit()

    # Assert
    assert cancelled is True
    db_game, db_room = await _reload(session, game, sample_room)
    assert db_game.game_status == GameStatus.CANCELLED
    assert db_game.end_time is not None
    assert db_game.live_state is not None
    assert PAUSE_STATE_KEY not in db_game.live_state
    assert db_game.live_state["phase"] == "describing"
    assert db_room.active_game_id is None


@pytest.mark.asyncio
async def test_the_room_is_loaded_when_the_caller_does_not_pass_it(
    session: AsyncSession, game_controller: GameController, sample_room: Room
):
    """``room=None``: the helper finds the game's room itself and still detaches it."""
    # Prepare
    game = await _running_game(session, game_controller, sample_room, paused=False)

    # Act
    cancelled = await cancel_running_game(session, game)
    await session.commit()

    # Assert
    assert cancelled is True
    db_game, db_room = await _reload(session, game, sample_room)
    assert db_game.game_status == GameStatus.CANCELLED
    assert db_room.active_game_id is None


@pytest.mark.asyncio
async def test_a_room_pointing_at_another_game_is_left_alone(
    session: AsyncSession, game_controller: GameController, sample_room: Room
):
    """BR-06: cancelling an old game never unlinks the room's new one."""
    # Prepare
    old_game = await _running_game(session, game_controller, sample_room, paused=False)
    new_game = await _running_game(session, game_controller, sample_room, paused=False)
    assert sample_room.active_game_id == new_game.id

    # Act
    cancelled = await cancel_running_game(session, old_game, sample_room)
    await session.commit()

    # Assert
    assert cancelled is True
    db_old, db_room = await _reload(session, old_game, sample_room)
    assert db_old.game_status == GameStatus.CANCELLED
    assert db_room.active_game_id == new_game.id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GameStatus.FINISHED, GameStatus.CANCELLED, GameStatus.WAITING])
async def test_a_game_that_is_not_running_is_not_changed(
    session: AsyncSession, game_controller: GameController, sample_room: Room, status: GameStatus
):
    """A finished game keeps its status, its end_time and its room link."""
    # Prepare
    game = await _running_game(session, game_controller, sample_room, paused=True)
    game.game_status = status
    game.end_time = None
    session.add(game)
    await session.commit()

    # Act
    cancelled = await cancel_running_game(session, game, sample_room)
    await session.commit()

    # Assert
    assert cancelled is False
    db_game, db_room = await _reload(session, game, sample_room)
    assert db_game.game_status == status
    assert db_game.end_time is None
    assert db_game.live_state is not None
    assert PAUSE_STATE_KEY in db_game.live_state
    assert db_room.active_game_id == game.id


@pytest.mark.asyncio
async def test_detach_room_if_current_only_clears_its_own_game(
    session: AsyncSession, game_controller: GameController, sample_room: Room
):
    """The finish paths' rule: clear ``active_game_id`` only when it is THIS game."""
    # Prepare
    first = await _running_game(session, game_controller, sample_room, paused=False)
    second = await _running_game(session, game_controller, sample_room, paused=False)

    # Act
    detach_room_if_current(sample_room, first)
    after_other = sample_room.active_game_id
    detach_room_if_current(sample_room, second)

    # Assert
    assert after_other == second.id
    assert sample_room.active_game_id is None
    assert first.game_status == GameStatus.IN_PROGRESS
