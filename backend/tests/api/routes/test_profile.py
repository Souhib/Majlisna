"""Route-level tests for profile endpoints (/api/v1/profiles)."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.profile import ProfileController
from majlisna.api.models.table import User
from majlisna.api.schemas.profile import PublicProfile
from majlisna.dependencies import get_current_user, get_profile_controller

BASE_URL = "/api/v1/profiles"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


def _mock_profile(user_id: str, username: str = "testplayer") -> PublicProfile:
    return PublicProfile(
        user_id=user_id,
        username=username,
        bio="Salam alaikum",
        total_games_played=10,
        favorite_game="undercover",
        undercover_games_played=5,
        codenames_games_played=3,
        wordquiz_games_played=2,
    )


# ========== GET /profiles/users/{user_id} ==========


def test_get_public_profile_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /profiles/users/{user_id} returns 200 with PublicProfile, to a signed-in caller."""
    # Arrange
    user_id = uuid4()
    mock_controller = Mock(spec=ProfileController)
    mock_controller.get_public_profile = AsyncMock(return_value=_mock_profile(str(user_id)))
    test_app.dependency_overrides[get_profile_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_current_user] = _mock_user

    try:
        # Act
        response = client.get(f"{BASE_URL}/users/{user_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["username"] == "testplayer"
        assert data["bio"] == "Salam alaikum"
        assert data["total_games_played"] == 10
        assert data["favorite_game"] == "undercover"
        mock_controller.get_public_profile.assert_awaited_once_with(user_id)
    finally:
        test_app.dependency_overrides.clear()


def test_get_public_profile_invalid_uuid(test_app: FastAPI, client: TestClient) -> None:
    """GET /profiles/users/{user_id} with invalid UUID returns 422."""
    # Arrange
    mock_controller = Mock(spec=ProfileController)
    test_app.dependency_overrides[get_profile_controller] = lambda: mock_controller
    test_app.dependency_overrides[get_current_user] = _mock_user

    try:
        # Act
        response = client.get(f"{BASE_URL}/users/not-a-uuid")

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


def test_get_public_profile_requires_sign_in(test_app: FastAPI, client: TestClient) -> None:
    """A player's profile (username, bio, games played) is read by signed-in players only
    (owner decision, 8 November 2026): without a token, 401 and nothing read."""
    # Arrange
    mock_controller = Mock(spec=ProfileController)
    mock_controller.get_public_profile = AsyncMock(return_value=_mock_profile(str(uuid4())))
    test_app.dependency_overrides[get_profile_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/users/{uuid4()}")

        # Assert
        assert response.status_code == 401
        mock_controller.get_public_profile.assert_not_awaited()
    finally:
        test_app.dependency_overrides.clear()


# ========== PATCH /profiles/me ==========


def test_update_my_profile_success(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /profiles/me returns 200 with updated PublicProfile."""
    # Arrange
    user = _mock_user()
    mock_controller = Mock(spec=ProfileController)
    mock_controller.update_bio = AsyncMock(return_value=None)
    mock_controller.get_public_profile = AsyncMock(return_value=_mock_profile(str(user.id)))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_profile_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(
            f"{BASE_URL}/me",
            json={"bio": "New bio"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user.id)
        assert data["username"] == "testplayer"
        mock_controller.update_bio.assert_awaited_once_with(user.id, "New bio")
        mock_controller.get_public_profile.assert_awaited_once_with(user.id)
    finally:
        test_app.dependency_overrides.clear()


def test_update_my_profile_null_bio(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /profiles/me with null bio returns 200."""
    # Arrange
    user = _mock_user()
    mock_controller = Mock(spec=ProfileController)
    mock_controller.update_bio = AsyncMock(return_value=None)
    mock_controller.get_public_profile = AsyncMock(
        return_value=PublicProfile(
            user_id=str(user.id),
            username="testplayer",
            bio=None,
            total_games_played=0,
            favorite_game=None,
            undercover_games_played=0,
            codenames_games_played=0,
            wordquiz_games_played=0,
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_profile_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(f"{BASE_URL}/me", json={"bio": None})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["bio"] is None
        mock_controller.update_bio.assert_awaited_once_with(user.id, None)
    finally:
        test_app.dependency_overrides.clear()


def test_update_my_profile_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """PATCH /profiles/me without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=ProfileController)
    test_app.dependency_overrides[get_profile_controller] = lambda: mock_controller

    try:
        # Act
        response = client.patch(f"{BASE_URL}/me", json={"bio": "test"})

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()
