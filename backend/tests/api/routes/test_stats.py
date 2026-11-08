"""Route-level tests for the stats endpoints (/api/v1/stats)."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.testclient import TestClient

from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.stats import AchievementWithProgress, LeaderboardEntry
from majlisna.dependencies import get_achievement_controller, get_current_user, get_session, get_stats_controller


def _signed_in() -> User:
    """The caller: a player's own figures are read by signed-in players only (owner, 8 November 2026)."""
    return User(id=uuid.uuid4(), username="reader", email_address="reader@test.com")


@pytest.mark.parametrize(
    "path",
    ["stats", "achievements", "history", "duration", f"vs/{uuid.uuid4()}"],
)
def test_a_players_figures_require_sign_in(test_app: FastAPI, client: TestClient, path: str):
    """Like the profile they fill (owner decision, 8 November 2026): without a token, 401 and
    nothing read. The leaderboard stays public (its tests below call it signed out)."""
    # Arrange
    stats = Mock(spec=StatsController)
    achievements = Mock(spec=AchievementController)
    test_app.dependency_overrides[get_stats_controller] = lambda: stats
    test_app.dependency_overrides[get_achievement_controller] = lambda: achievements

    try:
        # Act
        response = client.get(f"/api/v1/stats/users/{uuid.uuid4()}/{path}")

        # Assert
        assert response.status_code == 401
        assert stats.mock_calls == []
        assert achievements.mock_calls == []
    finally:
        test_app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────
# User Stats (GET /api/v1/stats/users/{user_id}/stats)
# ──────────────────────────────────────────────────────────────


def test_stats_get_user_stats_success(test_app: FastAPI, client: TestClient):
    """Fetching user stats returns 200 and all UserStats fields."""
    # Arrange
    stats_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    mock_controller = Mock(spec=StatsController)
    mock_controller.read_user_stats = AsyncMock(
        return_value=UserStats(
            id=stats_id,
            user_id=user_id,
            total_games_played=42,
            total_games_won=25,
            total_games_lost=17,
            undercover_games_played=20,
            undercover_games_won=12,
            codenames_games_played=22,
            codenames_games_won=13,
            times_civilian=10,
            times_undercover=6,
            times_mr_white=4,
            civilian_wins=7,
            undercover_wins=3,
            mr_white_wins=2,
            times_spymaster=11,
            times_operative=11,
            spymaster_wins=6,
            operative_wins=7,
            total_votes_cast=80,
            correct_votes=45,
            times_eliminated=8,
            times_survived=12,
            current_win_streak=3,
            longest_win_streak=7,
            current_play_streak_days=5,
            longest_play_streak_days=14,
            last_played_at=now,
            mr_white_correct_guesses=1,
            codenames_words_guessed=30,
            codenames_perfect_rounds=2,
            rooms_created=10,
            games_hosted=8,
            created_at=now,
            updated_at=now,
        )
    )
    test_app.dependency_overrides[get_stats_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_current_user] = _signed_in

    # Act
    response = client.get(f"/api/v1/stats/users/{user_id}/stats")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(stats_id)
    assert data["user_id"] == str(user_id)
    assert data["total_games_played"] == 42
    assert data["total_games_won"] == 25
    assert data["total_games_lost"] == 17
    assert data["undercover_games_played"] == 20
    assert data["undercover_games_won"] == 12
    assert data["codenames_games_played"] == 22
    assert data["codenames_games_won"] == 13
    assert data["times_civilian"] == 10
    assert data["times_undercover"] == 6
    assert data["times_mr_white"] == 4
    assert data["civilian_wins"] == 7
    assert data["undercover_wins"] == 3
    assert data["mr_white_wins"] == 2
    assert data["times_spymaster"] == 11
    assert data["times_operative"] == 11
    assert data["spymaster_wins"] == 6
    assert data["operative_wins"] == 7
    assert data["total_votes_cast"] == 80
    assert data["correct_votes"] == 45
    assert data["times_eliminated"] == 8
    assert data["times_survived"] == 12
    assert data["current_win_streak"] == 3
    assert data["longest_win_streak"] == 7
    assert data["current_play_streak_days"] == 5
    assert data["longest_play_streak_days"] == 14
    assert data["last_played_at"] is not None
    assert data["mr_white_correct_guesses"] == 1
    assert data["codenames_words_guessed"] == 30
    assert data["codenames_perfect_rounds"] == 2
    assert data["rooms_created"] == 10
    assert data["games_hosted"] == 8
    assert "created_at" in data
    assert "updated_at" in data

    mock_controller.read_user_stats.assert_awaited_once_with(user_id)

    test_app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────
# User Achievements (GET /api/v1/stats/users/{user_id}/achievements)
# ──────────────────────────────────────────────────────────────


def test_achievements_get_user_achievements_success(test_app: FastAPI, client: TestClient):
    """Fetching user achievements returns 200 and AchievementWithProgress objects."""
    # Arrange
    user_id = uuid.uuid4()
    mock_controller = Mock(spec=AchievementController)
    mock_controller.get_user_achievements = AsyncMock(
        return_value=[
            AchievementWithProgress(
                code="first_game",
                name="First Steps",
                description="Play your first game",
                icon="star",
                category="beginner",
                tier=1,
                threshold=1,
                progress=1,
                unlocked=True,
            ),
            AchievementWithProgress(
                code="civilian_wins_5",
                name="Good Citizen",
                description="Win 5 games as a Civilian",
                icon="shield",
                category="undercover_master",
                tier=1,
                threshold=5,
                progress=3,
                unlocked=False,
            ),
        ]
    )
    test_app.dependency_overrides[get_achievement_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_current_user] = _signed_in

    # Act
    response = client.get(f"/api/v1/stats/users/{user_id}/achievements")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["code"] == "first_game"
    assert data[0]["name"] == "First Steps"
    assert data[0]["progress"] == 1
    assert data[0]["unlocked"] is True
    assert data[0]["tier"] == 1
    assert data[0]["threshold"] == 1
    assert data[1]["code"] == "civilian_wins_5"
    assert data[1]["progress"] == 3
    assert data[1]["unlocked"] is False

    mock_controller.get_user_achievements.assert_awaited_once_with(user_id)

    test_app.dependency_overrides.clear()


def test_achievements_get_user_achievements_empty(test_app: FastAPI, client: TestClient):
    """Fetching achievements for a user with none returns 200 and an empty list."""
    # Arrange
    user_id = uuid.uuid4()
    mock_controller = Mock(spec=AchievementController)
    mock_controller.get_user_achievements = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_achievement_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_current_user] = _signed_in

    # Act
    response = client.get(f"/api/v1/stats/users/{user_id}/achievements")

    # Assert
    assert response.status_code == 200
    assert response.json() == []

    mock_controller.get_user_achievements.assert_awaited_once_with(user_id)

    test_app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────
# Leaderboard (GET /api/v1/stats/leaderboard)
# ──────────────────────────────────────────────────────────────


def test_leaderboard_get_leaderboard_success(test_app: FastAPI, client: TestClient):
    """Fetching the leaderboard with defaults returns 200 with username included."""
    # Arrange
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    mock_controller = Mock(spec=StatsController)
    mock_controller.get_leaderboard = AsyncMock(
        return_value=[
            LeaderboardEntry(
                user_id=user1_id,
                username="player_one",
                total_games_played=80,
                total_games_won=50,
                win_rate=62.5,
                current_win_streak=3,
                longest_win_streak=8,
            ),
            LeaderboardEntry(
                user_id=user2_id,
                username="player_two",
                total_games_played=60,
                total_games_won=30,
                win_rate=50.0,
                current_win_streak=1,
                longest_win_streak=5,
            ),
        ]
    )
    test_app.dependency_overrides[get_stats_controller] = lambda: mock_controller

    # Act
    response = client.get("/api/v1/stats/leaderboard")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["user_id"] == str(user1_id)
    assert data[0]["username"] == "player_one"
    assert data[0]["total_games_won"] == 50
    assert data[0]["win_rate"] == 62.5
    assert data[0]["longest_win_streak"] == 8
    assert data[1]["user_id"] == str(user2_id)
    assert data[1]["username"] == "player_two"
    assert data[1]["total_games_won"] == 30

    mock_controller.get_leaderboard.assert_awaited_once_with(stat_field="total_games_won", limit=10)

    test_app.dependency_overrides.clear()


def test_leaderboard_get_leaderboard_with_params(test_app: FastAPI, client: TestClient):
    """Fetching the leaderboard with custom stat_field and limit returns 200."""
    # Arrange
    user_id = uuid.uuid4()
    mock_controller = Mock(spec=StatsController)
    mock_controller.get_leaderboard = AsyncMock(
        return_value=[
            LeaderboardEntry(
                user_id=user_id,
                username="streak_master",
                total_games_played=100,
                total_games_won=70,
                win_rate=70.0,
                current_win_streak=15,
                longest_win_streak=15,
            ),
        ]
    )
    test_app.dependency_overrides[get_stats_controller] = lambda: mock_controller

    # Act
    response = client.get(
        "/api/v1/stats/leaderboard",
        params={"stat_field": "longest_win_streak", "limit": 5},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user_id"] == str(user_id)
    assert data[0]["username"] == "streak_master"
    assert data[0]["longest_win_streak"] == 15

    mock_controller.get_leaderboard.assert_awaited_once_with(stat_field="longest_win_streak", limit=5)

    test_app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────
# Through the real app and the test database
# ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(name="api")
async def get_api(test_app: FastAPI, session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient]:
    """An async client on the real app, on the test database."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    test_app.dependency_overrides.clear()


async def _stats_rows(session: AsyncSession) -> int:
    return (await session.exec(select(func.count()).select_from(UserStats))).one()


async def test_a_stats_read_for_an_unknown_user_is_a_404(
    test_app: FastAPI, api: httpx.AsyncClient, session: AsyncSession
):
    """PD-11 / SEC F11: it answered 500 (an INSERT failing its foreign key, logged at
    ERROR) for any random id, on PostgreSQL and SQLite alike."""
    # Prepare
    test_app.dependency_overrides[get_current_user] = _signed_in

    # Act
    responses = [await api.get(f"/api/v1/stats/users/{uuid.uuid4()}/stats") for _ in range(3)]

    # Assert
    assert [r.status_code for r in responses] == [404, 404, 404]
    assert {r.json()["error_key"] for r in responses} == {"errors.api.userNotFound"}
    assert await _stats_rows(session) == 0


async def test_a_stats_read_writes_nothing(
    test_app: FastAPI, api: httpx.AsyncClient, session: AsyncSession, create_user
):
    """A user who has not played yet: zeros, and no row inserted by a GET."""
    # Prepare
    user = await create_user(username="neverplayed", email="neverplayed@test.com")
    test_app.dependency_overrides[get_current_user] = _signed_in

    # Act
    response = await api.get(f"/api/v1/stats/users/{user.id}/stats")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert (body["total_games_played"], body["total_games_won"], body["games_hosted"]) == (0, 0, 0)
    assert await _stats_rows(session) == 0


async def test_a_twelve_player_mcq_won_by_the_host_reads_as_a_win_everywhere(
    api: httpx.AsyncClient, test_app: FastAPI, session: AsyncSession, setup_mcqquiz_game
):
    """BDP-05, the auditor's harness2: UserStats said 1 win while the chart said 1 loss,
    the history said "no result" and head-to-head said a draw."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=12, num_questions=3)
    host, loser = setup["users"][0], setup["users"][1]
    room = (await session.exec(select(Room).where(Room.id == setup["room"].id))).one()
    room.settings = {**(room.settings or {}), "mcq_quiz_rounds": 1}
    flag_modified(room, "settings")
    session.add(room)
    await session.commit()
    # create_game links every member from Room.users, loaded so far with the owner alone.
    await session.refresh(room, attribute_names=["users"])
    controller = McqQuizGameController(session)
    started = await controller.create_and_start(room.id, host.id)
    game = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    correct = game.live_state["current_question"]["correct_answer_index"]
    for i, user in enumerate(setup["users"]):
        await controller.submit_answer(UUID(started.game_id), user.id, correct if i == 0 else (correct + 1) % 4)
    await controller.advance_to_next_round(UUID(started.game_id), host.id)
    test_app.dependency_overrides[get_current_user] = lambda: host

    # Act
    stats = (await api.get(f"/api/v1/stats/users/{host.id}/stats")).json()
    chart = (await api.get(f"/api/v1/stats/users/{host.id}/history?days=30")).json()
    host_history = (await api.get(f"/api/v1/games/user/{host.id}")).json()
    loser_history = (await api.get(f"/api/v1/games/user/{loser.id}")).json()
    versus = (await api.get(f"/api/v1/stats/users/{host.id}/vs/{loser.id}")).json()

    # Assert
    assert (stats["total_games_played"], stats["total_games_won"], stats["games_hosted"]) == (1, 1, 1)
    assert [(day["wins"], day["losses"]) for day in chart] == [(1, 0)]
    assert host_history[0]["user_won"] is True
    assert loser_history[0]["user_won"] is False
    assert (versus["user_wins"], versus["opponent_wins"], versus["draws"]) == (1, 0, 0)
