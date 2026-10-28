"""Route-level tests for MCQ Quiz game action endpoints (/api/v1/mcqquiz/games)."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.models.table import User
from majlisna.api.schemas.common import AdvanceRoundResponse, GameStartResponse, TimerExpiredResponse
from majlisna.api.schemas.mcqquiz import McqQuizGameState, McqSubmitAnswerResponse
from majlisna.dependencies import get_current_user, get_mcqquiz_game_controller

BASE_URL = "/api/v1/mcqquiz"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


def _mock_game_state(game_id: str, room_id: str) -> McqQuizGameState:
    return McqQuizGameState(
        game_id=game_id,
        room_id=room_id,
        is_host=True,
        current_round=1,
        total_rounds=10,
        round_phase="playing",
        question="What is the first pillar of Islam?",
        choices=["Salah", "Shahada", "Zakat", "Hajj"],
        turn_duration_seconds=15,
        players=[],
        my_answered=False,
        my_points=0,
        round_results=[],
        leaderboard=[],
        game_over=False,
    )


# ========== POST /mcqquiz/games/{room_id}/start ==========


@patch("majlisna.api.routes.mcqquiz.notify_game_changed", new_callable=AsyncMock)
@patch("majlisna.api.routes.mcqquiz.notify_room_changed", new_callable=AsyncMock)
@patch("majlisna.api.routes.mcqquiz.auto_join_game_room", new_callable=AsyncMock)
def test_start_game_success(
    mock_auto_join: AsyncMock,
    mock_notify_room: AsyncMock,
    mock_notify_game: AsyncMock,
    test_app: FastAPI,
    client: TestClient,
) -> None:
    """Starting an MCQ quiz game returns 201 with game_id and room_id."""
    # Arrange
    room_id = uuid4()
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    mock_controller.create_and_start = AsyncMock(
        return_value=GameStartResponse(game_id=str(game_id), room_id=str(room_id))
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{room_id}/start")

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["game_id"] == str(game_id)
        assert data["room_id"] == str(room_id)
        mock_controller.create_and_start.assert_awaited_once_with(room_id, user.id)
        mock_auto_join.assert_awaited_once()
        mock_notify_room.assert_awaited_once()
        mock_notify_game.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()


def test_start_game_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Starting a game without auth returns 401."""
    # Arrange
    room_id = uuid4()
    mock_controller = Mock(spec=McqQuizGameController)
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{room_id}/start")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /mcqquiz/games/{game_id}/state ==========


def test_get_state_success(test_app: FastAPI, client: TestClient) -> None:
    """Getting MCQ quiz state returns 200 with full state."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    mock_controller.get_state = AsyncMock(return_value=_mock_game_state(str(game_id), str(room_id)))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/state")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == str(game_id)
        assert data["round_phase"] == "playing"
        assert len(data["choices"]) == 4
        mock_controller.get_state.assert_awaited_once_with(game_id, user.id, lang="en")
    finally:
        test_app.dependency_overrides.clear()


def test_get_state_with_lang(test_app: FastAPI, client: TestClient) -> None:
    """Getting state with lang query param passes it to the controller."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    mock_controller.get_state = AsyncMock(return_value=_mock_game_state(str(game_id), str(room_id)))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/state?lang=ar")

        # Assert
        assert response.status_code == 200
        mock_controller.get_state.assert_awaited_once_with(game_id, user.id, lang="ar")
    finally:
        test_app.dependency_overrides.clear()


def test_get_state_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Getting state without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=McqQuizGameController)
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/state")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /mcqquiz/games/{game_id}/answer ==========


@patch("majlisna.api.routes.mcqquiz.notify_game_changed", new_callable=AsyncMock)
def test_submit_answer_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """Submitting an answer returns 200 with result."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    mock_controller.submit_answer = AsyncMock(return_value=McqSubmitAnswerResponse(correct=True, points_earned=1))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/answer",
            json={"choice_index": 1},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["correct"] is True
        assert data["points_earned"] == 1
        mock_controller.submit_answer.assert_awaited_once_with(game_id, user.id, 1)
        mock_notify.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()


def test_submit_answer_missing_body(test_app: FastAPI, client: TestClient) -> None:
    """Submitting without choice_index returns 422."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/answer", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /mcqquiz/games/{game_id}/timer-expired ==========


@patch("majlisna.api.routes.mcqquiz.notify_game_changed", new_callable=AsyncMock)
def test_timer_expired_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """Timer expired returns 200 with action."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    mock_controller.handle_timer_expired = AsyncMock(
        return_value=TimerExpiredResponse(game_id=str(game_id), action="results")
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/timer-expired")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "results"
        mock_controller.handle_timer_expired.assert_awaited_once_with(game_id, user.id)
        mock_notify.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /mcqquiz/games/{game_id}/next-round ==========


@patch("majlisna.api.routes.mcqquiz.notify_game_changed", new_callable=AsyncMock)
def test_next_round_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """Advancing to next round returns 200 with game_id and room_id."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=McqQuizGameController)
    mock_controller.advance_to_next_round = AsyncMock(
        return_value=AdvanceRoundResponse(game_id=str(game_id), room_id=str(room_id), advanced=True)
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/next-round")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == str(game_id)
        mock_controller.advance_to_next_round.assert_awaited_once_with(game_id, user.id)
        mock_notify.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()
