"""Route-level tests for challenge endpoints (/api/v1/challenges)."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.models.table import User
from majlisna.api.schemas.challenge import ActiveChallenge
from majlisna.dependencies import get_challenge_controller, get_current_user, get_settings
from majlisna.settings import Settings

BASE_URL = "/api/v1/challenges"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== GET /challenges/active ==========


def test_get_active_challenges_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /challenges/active returns 200 and a list of ActiveChallenge."""
    # Arrange
    user = _mock_user()
    challenge_id = uuid4()
    mock_controller = Mock(spec=ChallengeController)
    mock_controller.get_active_challenges = AsyncMock(
        return_value=[
            ActiveChallenge(
                id=challenge_id,
                code="play_3_undercover",
                description="Play 3 undercover games",
                challenge_type="daily",
                target_count=3,
                game_type="undercover",
                condition="games_played",
                role=None,
                progress=1,
                completed=False,
                assigned_at="2026-03-23T00:00:00",
                expires_at="2026-03-24T00:00:00",
            )
        ]
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_challenge_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/active")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(challenge_id)
        assert data[0]["code"] == "play_3_undercover"
        assert data[0]["challenge_type"] == "daily"
        assert data[0]["progress"] == 1
        assert data[0]["completed"] is False
        mock_controller.get_active_challenges.assert_awaited_once_with(user.id)
    finally:
        test_app.dependency_overrides.clear()


def test_get_active_challenges_empty(test_app: FastAPI, client: TestClient) -> None:
    """GET /challenges/active returns 200 and empty list when no challenges."""
    # Arrange
    user = _mock_user()
    mock_controller = Mock(spec=ChallengeController)
    mock_controller.get_active_challenges = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_challenge_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/active")

        # Assert
        assert response.status_code == 200
        assert response.json() == []
    finally:
        test_app.dependency_overrides.clear()


def test_get_active_challenges_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """GET /challenges/active without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=ChallengeController)
    test_app.dependency_overrides[get_challenge_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/active")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /challenges/seed ==========


def _settings_with_admin(address: str) -> Settings:
    return Settings(database_url="sqlite+aiosqlite:///:memory:", admin_emails=address)


def test_seed_challenges_success(test_app: FastAPI, client: TestClient) -> None:
    """POST /challenges/seed by a verified administrator returns 204."""
    # Arrange
    admin = _mock_user()
    admin.email_verified = True
    mock_controller = Mock(spec=ChallengeController)
    mock_controller.seed_challenges = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_current_user] = lambda: admin
    test_app.dependency_overrides[get_settings] = lambda: _settings_with_admin(admin.email_address)
    test_app.dependency_overrides[get_challenge_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/seed")

        # Assert
        assert response.status_code == 204
        mock_controller.seed_challenges.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()


def test_seed_challenges_by_a_player_is_forbidden(test_app: FastAPI, client: TestClient) -> None:
    """SEC F15: any signed-in player could run the seed; it is an admin operation."""
    # Arrange
    player = _mock_user()
    player.email_verified = True
    mock_controller = Mock(spec=ChallengeController)
    mock_controller.seed_challenges = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_current_user] = lambda: player
    test_app.dependency_overrides[get_settings] = lambda: _settings_with_admin("someone-else@test.com")
    test_app.dependency_overrides[get_challenge_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/seed")

        # Assert
        assert response.status_code == 403
        assert response.json()["error_key"] == "errors.api.forbidden"
        mock_controller.seed_challenges.assert_not_awaited()
    finally:
        test_app.dependency_overrides.clear()


def test_seed_challenges_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """POST /challenges/seed without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=ChallengeController)
    test_app.dependency_overrides[get_challenge_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/seed")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()
