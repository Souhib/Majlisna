"""Route-level tests for Word Quiz game action endpoints (/api/v1/wordquiz/games)."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import User
from majlisna.api.schemas.common import (
    AdvanceRoundResponse,
    GameStartResponse,
    HintRecordResponse,
    TimerExpiredResponse,
)
from majlisna.api.schemas.wordquiz import SubmitAnswerResponse, WordQuizGameState
from majlisna.dependencies import get_current_user, get_wordquiz_game_controller

BASE_URL = "/api/v1/wordquiz"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


def _mock_game_state(game_id: str, room_id: str) -> WordQuizGameState:
    return WordQuizGameState(
        game_id=game_id,
        room_id=room_id,
        is_host=True,
        current_round=1,
        total_rounds=5,
        round_phase="playing",
        hints_revealed=2,
        # A prefix of the ladder, not the ladder: the server only releases the
        # hints earned so far, and `max_hints` carries its real length.
        hints=["It is a pillar of Islam", "Performed 5 times a day"],
        max_hints=6,
        turn_duration_seconds=60,
        hint_interval_seconds=10,
        players=[],
        my_answered=False,
        my_points=0,
        round_results=[],
        leaderboard=[],
        game_over=False,
    )


# ========== POST /wordquiz/games/{room_id}/start ==========


@patch("majlisna.api.routes.wordquiz.notify_game_changed", new_callable=AsyncMock)
@patch("majlisna.api.routes.wordquiz.notify_room_changed", new_callable=AsyncMock)
@patch("majlisna.api.routes.wordquiz.auto_join_game_room", new_callable=AsyncMock)
def test_start_game_success(
    mock_auto_join: AsyncMock,
    mock_notify_room: AsyncMock,
    mock_notify_game: AsyncMock,
    test_app: FastAPI,
    client: TestClient,
) -> None:
    """Starting a word quiz game returns 201 with game_id and room_id."""
    # Arrange
    room_id = uuid4()
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.create_and_start = AsyncMock(
        return_value=GameStartResponse(game_id=str(game_id), room_id=str(room_id))
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

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
    mock_controller = Mock(spec=WordQuizGameController)
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{room_id}/start")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /wordquiz/games/{game_id}/state ==========


def test_get_state_success(test_app: FastAPI, client: TestClient) -> None:
    """Getting word quiz state returns 200 with full state."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.get_state = AsyncMock(return_value=_mock_game_state(str(game_id), str(room_id)))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/state")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == str(game_id)
        assert data["round_phase"] == "playing"
        assert data["hints_revealed"] == 2
        assert len(data["hints"]) == 2
        mock_controller.get_state.assert_awaited_once_with(game_id, user.id, lang="en")
    finally:
        test_app.dependency_overrides.clear()


def test_get_state_with_lang(test_app: FastAPI, client: TestClient) -> None:
    """Getting state with lang param passes it to the controller."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.get_state = AsyncMock(return_value=_mock_game_state(str(game_id), str(room_id)))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/state?lang=fr")

        # Assert
        assert response.status_code == 200
        mock_controller.get_state.assert_awaited_once_with(game_id, user.id, lang="fr")
    finally:
        test_app.dependency_overrides.clear()


def test_get_state_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Getting state without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=WordQuizGameController)
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/state")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /wordquiz/games/{game_id}/answer ==========


@patch("majlisna.api.routes.wordquiz.notify_game_changed", new_callable=AsyncMock)
def test_submit_answer_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """Submitting an answer returns 200 with result."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.submit_answer = AsyncMock(
        return_value=SubmitAnswerResponse(correct=True, points_earned=5, hint_number=2)
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/answer",
            json={"answer": "Salah"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["correct"] is True
        assert data["points_earned"] == 5
        assert data["hint_number"] == 2
        mock_controller.submit_answer.assert_awaited_once_with(game_id, user.id, "Salah")
        mock_notify.assert_awaited_once()
    finally:
        test_app.dependency_overrides.clear()


def test_submit_answer_missing_body(test_app: FastAPI, client: TestClient) -> None:
    """Submitting without answer returns 422."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/answer", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /wordquiz/games/{game_id}/timer-expired ==========


@patch("majlisna.api.routes.wordquiz.notify_game_changed", new_callable=AsyncMock)
def test_timer_expired_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """Timer expired returns 200 with action."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.handle_timer_expired = AsyncMock(
        return_value=TimerExpiredResponse(game_id=str(game_id), action="results")
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

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


# ========== POST /wordquiz/games/{game_id}/next-round ==========


@patch("majlisna.api.routes.wordquiz.notify_game_changed", new_callable=AsyncMock)
def test_next_round_success(mock_notify: AsyncMock, test_app: FastAPI, client: TestClient) -> None:
    """Advancing to next round returns 200 with game_id and room_id."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.advance_to_next_round = AsyncMock(
        return_value=AdvanceRoundResponse(game_id=str(game_id), room_id=str(room_id), advanced=True)
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

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


# ========== POST /wordquiz/games/{game_id}/hint-viewed ==========


def test_hint_viewed_success(test_app: FastAPI, client: TestClient) -> None:
    """Recording a hint view returns 200 with recorded=True."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=WordQuizGameController)
    mock_controller.record_hint_view = AsyncMock(return_value=HintRecordResponse(game_id=str(game_id), recorded=True))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/hint-viewed")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["recorded"] is True
        mock_controller.record_hint_view.assert_awaited_once_with(game_id, user.id)
    finally:
        test_app.dependency_overrides.clear()


def test_hint_viewed_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Recording a hint view without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=WordQuizGameController)
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/hint-viewed")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()
