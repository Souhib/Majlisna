"""Route-level tests for the stats endpoints (/api/v1/stats)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.achievement import AchievementController
from ipg.api.controllers.stats import StatsController
from ipg.api.models.stats import UserStats
from ipg.api.schemas.stats import AchievementWithProgress, LeaderboardEntry
from ipg.dependencies import get_achievement_controller, get_stats_controller


class TestUserStats:
    """Tests for the GET /api/v1/stats/users/{user_id}/stats endpoint."""

    def test_get_user_stats_success(self, test_app: FastAPI, client: TestClient):
        """Fetching user stats returns 200 and all UserStats fields."""
        # Arrange
        stats_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_controller = Mock(spec=StatsController)
        mock_controller.get_or_create_user_stats = AsyncMock(
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

        mock_controller.get_or_create_user_stats.assert_awaited_once_with(user_id)

        test_app.dependency_overrides.clear()


class TestUserAchievements:
    """Tests for the GET /api/v1/stats/users/{user_id}/achievements endpoint."""

    def test_get_user_achievements_success(self, test_app: FastAPI, client: TestClient):
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

    def test_get_user_achievements_empty(self, test_app: FastAPI, client: TestClient):
        """Fetching achievements for a user with none returns 200 and an empty list."""
        # Arrange
        user_id = uuid.uuid4()
        mock_controller = Mock(spec=AchievementController)
        mock_controller.get_user_achievements = AsyncMock(return_value=[])
        test_app.dependency_overrides[get_achievement_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/stats/users/{user_id}/achievements")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

        mock_controller.get_user_achievements.assert_awaited_once_with(user_id)

        test_app.dependency_overrides.clear()


class TestLeaderboard:
    """Tests for the GET /api/v1/stats/leaderboard endpoint."""

    def test_get_leaderboard_success(self, test_app: FastAPI, client: TestClient):
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

    def test_get_leaderboard_with_params(self, test_app: FastAPI, client: TestClient):
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
