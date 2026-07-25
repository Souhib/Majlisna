"""Tests for the BaseGameController base class."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.models.error import GameNotFoundError, PlayerRemovedFromGameError
from majlisna.api.models.game import GameCreate, GameType
from majlisna.api.models.relationship import RoomUserLink

# ── Fixture ──────────────────────────────────────────────────────


@pytest.fixture(name="base_controller")
def get_base_controller(session: AsyncSession) -> BaseGameController:
    """Create a BaseGameController instance for testing."""
    return BaseGameController(session)


# ── _get_game ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_game_found(
    base_controller: BaseGameController,
    session: AsyncSession,
    sample_room,
    game_controller,
):
    """_get_game returns a Game when it exists and has live_state."""
    # Prepare
    game = await game_controller.create_game(
        GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=3)
    )
    game.live_state = {"players": []}
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    result = await base_controller._get_game(game.id)

    # Assert
    assert result.id == game.id
    assert result.live_state == {"players": []}


@pytest.mark.asyncio
async def test_get_game_not_found_raises(base_controller: BaseGameController):
    """_get_game raises GameNotFoundError for a non-existent game ID."""
    # Prepare
    fake_id = uuid4()

    # Act / Assert
    with pytest.raises(GameNotFoundError):
        await base_controller._get_game(fake_id)


# ── _check_is_host ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_is_host_true(base_controller: BaseGameController, sample_room, sample_owner):
    """_check_is_host returns True when user is the room owner."""
    # Act
    result = await base_controller._check_is_host(sample_room.id, sample_owner.id)

    # Assert
    assert result is True


@pytest.mark.asyncio
async def test_check_is_host_false(base_controller: BaseGameController, sample_room, sample_user):
    """_check_is_host returns False when user is not the room owner."""
    # Act
    result = await base_controller._check_is_host(sample_room.id, sample_user.id)

    # Assert
    assert result is False


# ── _update_heartbeat_throttled ──────────────────────────────────


@pytest.mark.asyncio
async def test_update_heartbeat_throttled_updates_stale(
    base_controller: BaseGameController,
    session: AsyncSession,
    sample_room,
    sample_owner,
):
    """_update_heartbeat_throttled updates a stale link (last_seen_at > 10s ago)."""
    # Prepare
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == sample_room.id)
            .where(RoomUserLink.user_id == sample_owner.id)
        )
    ).first()
    assert link is not None
    link.last_seen_at = datetime.now() - timedelta(seconds=20)
    link.connected = False
    session.add(link)
    await session.commit()

    # Act
    await base_controller._update_heartbeat_throttled(sample_room.id, sample_owner.id)

    # Assert
    await session.refresh(link)
    assert link.connected is True
    assert (datetime.now() - link.last_seen_at).total_seconds() < 5


@pytest.mark.asyncio
async def test_update_heartbeat_throttled_skips_recent(
    base_controller: BaseGameController,
    session: AsyncSession,
    sample_room,
    sample_owner,
):
    """_update_heartbeat_throttled skips update when last_seen_at is recent."""
    # Prepare
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == sample_room.id)
            .where(RoomUserLink.user_id == sample_owner.id)
        )
    ).first()
    assert link is not None
    recent_time = datetime.now() - timedelta(seconds=2)
    link.last_seen_at = recent_time
    link.connected = True
    link.disconnected_at = None
    session.add(link)
    await session.commit()

    # Act
    await base_controller._update_heartbeat_throttled(sample_room.id, sample_owner.id)

    # Assert
    await session.refresh(link)
    assert link.last_seen_at == recent_time


# ── _check_spectator ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_spectator_returns_true_for_spectator(
    base_controller: BaseGameController,
    session: AsyncSession,
    sample_room,
    game_controller,
    create_user,
):
    """_check_spectator returns True when user is a spectator."""
    # Prepare
    spectator = await create_user(username="spectator", email="spectator@test.com")
    link = RoomUserLink(
        room_id=sample_room.id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
        last_seen_at=datetime.now(),
    )
    session.add(link)
    await session.commit()

    game = await game_controller.create_game(
        GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=3)
    )
    game.live_state = {"players": []}
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    result = await base_controller._check_spectator(game, spectator.id, None)

    # Assert
    assert result is True


@pytest.mark.asyncio
async def test_check_spectator_raises_for_non_member(
    base_controller: BaseGameController,
    session: AsyncSession,
    sample_room,
    game_controller,
    create_user,
):
    """_check_spectator raises PlayerRemovedFromGameError when user is neither player nor spectator."""
    # Prepare
    outsider = await create_user(username="outsider", email="outsider@test.com")
    game = await game_controller.create_game(
        GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=3)
    )
    game.live_state = {"players": []}
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act / Assert
    with pytest.raises(PlayerRemovedFromGameError):
        await base_controller._check_spectator(game, outsider.id, None)


# ── _resolve_multilingual ───────────────────────────────────────


def test_resolve_multilingual_returns_lang():
    """_resolve_multilingual returns the value for the exact requested language."""
    # Prepare
    data = {"en": "English", "ar": "Arabic", "fr": "French"}

    # Act / Assert
    assert BaseGameController._resolve_multilingual(data, "ar") == "Arabic"
    assert BaseGameController._resolve_multilingual(data, "fr") == "French"
    assert BaseGameController._resolve_multilingual(data, "en") == "English"


def test_resolve_multilingual_fallback_to_en():
    """_resolve_multilingual falls back to 'en' when the requested language is missing."""
    # Prepare
    data = {"en": "English"}

    # Act
    result = BaseGameController._resolve_multilingual(data, "ar")

    # Assert
    assert result == "English"


def test_resolve_multilingual_returns_none_for_empty():
    """_resolve_multilingual returns None for None or empty dict."""
    # Act / Assert
    assert BaseGameController._resolve_multilingual(None, "en") is None
    assert BaseGameController._resolve_multilingual({}, "en") is None


# ── _scorable_players ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scorable_players_skips_deleted_accounts(base_controller: BaseGameController, create_user):
    """Players whose User row is gone are excluded from end-of-game stat writes.

    live_state["players"] is a snapshot taken at game start, so a player who
    deletes their account mid-game stays in it. Writing UserStats for that id
    fails the foreign key, and since the stats loop no longer swallows SQLAlchemy
    errors that would make the game impossible to ever finish.
    """
    # Prepare
    alive = await create_user(username="stillhere", email="alive@test.com")
    ghost_id = uuid4()
    state = {
        "players": [
            {"user_id": str(alive.id), "username": "stillhere", "role": "civilian"},
            {"user_id": str(ghost_id), "username": "deleted", "role": "undercover"},
        ]
    }

    # Act
    scorable = await base_controller._scorable_players(state)

    # Assert
    assert [p["user_id"] for p in scorable] == [str(alive.id)]


@pytest.mark.asyncio
async def test_scorable_players_empty_state(base_controller: BaseGameController):
    """A state with no players yields an empty list rather than querying."""
    # Act / Assert
    assert await base_controller._scorable_players({}) == []
    assert await base_controller._scorable_players({"players": []}) == []
