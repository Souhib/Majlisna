from datetime import datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.game import GameController
from majlisna.api.models.game import GameType
from majlisna.api.models.table import User
from majlisna.api.schemas.game import GameHistoryEntry, GameSummary, GameSummaryPlayer
from majlisna.dependencies import get_current_user, get_game_controller

# NOTE: The /games router now exposes ONLY two authenticated read endpoints:
# GET /games/user/{user_id} (history) and GET /games/{game_id}/summary. The generic
# unauthenticated Game CRUD (create / list-all / raw get-by-id / update / end / delete)
# was removed for security — it leaked raw live_state (roles/words) and let anyone
# mutate or delete any game. Games are created/mutated via the per-game routers.


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="historyviewer",
        email_address="viewer@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== GET /games/user/{user_id} ==========


@pytest.mark.asyncio
async def test_get_games_by_user_success(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/user/{user_id} returns 200 with the user's game history."""
    # Arrange
    user = _mock_user()
    user_id = uuid4()
    game1_id = uuid4()
    game2_id = uuid4()
    start_time = datetime.now()
    end_time = datetime.now()

    mock_controller = Mock(spec=GameController)
    mock_controller.get_games_by_user = AsyncMock(
        return_value=[
            GameHistoryEntry(
                id=game1_id,
                type=GameType.UNDERCOVER,
                start_time=start_time,
                end_time=end_time,
                number_of_players=5,
            ),
            GameHistoryEntry(
                id=game2_id,
                type=GameType.CODENAMES,
                start_time=start_time,
                end_time=None,
                number_of_players=8,
            ),
        ]
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"/api/v1/games/user/{user_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(game1_id)
        assert data[0]["type"] == GameType.UNDERCOVER.value
        assert data[0]["number_of_players"] == 5
        assert data[0]["end_time"] is not None
        assert data[1]["id"] == str(game2_id)
        assert data[1]["type"] == GameType.CODENAMES.value
        assert data[1]["number_of_players"] == 8
        assert data[1]["end_time"] is None
        mock_controller.get_games_by_user.assert_awaited_once_with(user_id, limit=20)
    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_games_by_user_empty(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/user/{user_id} returns 200 and empty list for a new user."""
    # Arrange
    user = _mock_user()
    user_id = uuid4()
    mock_controller = Mock(spec=GameController)
    mock_controller.get_games_by_user = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"/api/v1/games/user/{user_id}")

        # Assert
        assert response.status_code == 200
        assert response.json() == []
        mock_controller.get_games_by_user.assert_awaited_once_with(user_id, limit=20)
    finally:
        test_app.dependency_overrides.clear()


def test_get_games_by_user_requires_auth(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/user/{user_id} without auth returns 401."""
    # Arrange
    user_id = uuid4()
    mock_controller = Mock(spec=GameController)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"/api/v1/games/user/{user_id}")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /games/{game_id}/summary ==========


@pytest.mark.asyncio
async def test_get_game_summary_success(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/{game_id}/summary returns 200 with the game summary."""
    # Arrange
    user = _mock_user()
    game_id = uuid4()
    start_time = datetime.now()
    end_time = datetime.now()

    mock_controller = Mock(spec=GameController)
    mock_controller.get_game_summary = AsyncMock(
        return_value=GameSummary(
            id=game_id,
            type=GameType.UNDERCOVER,
            start_time=start_time,
            end_time=end_time,
            number_of_players=4,
            winner="civilians",
            game_status="finished",
            players=[
                GameSummaryPlayer(user_id=str(uuid4()), username="alice", role="civilian"),
                GameSummaryPlayer(user_id=str(uuid4()), username="bob", role="undercover"),
            ],
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"/api/v1/games/{game_id}/summary")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(game_id)
        assert data["type"] == GameType.UNDERCOVER.value
        assert data["winner"] == "civilians"
        assert len(data["players"]) == 2
        assert data["players"][0]["username"] == "alice"
        mock_controller.get_game_summary.assert_awaited_once_with(game_id)
    finally:
        test_app.dependency_overrides.clear()


def test_get_game_summary_requires_auth(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/{game_id}/summary without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=GameController)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"/api/v1/games/{game_id}/summary")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()
