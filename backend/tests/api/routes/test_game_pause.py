"""Route-level tests for the prayer pause: POST /{game}/games/{game_id}/pause and /resume."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.constants import PRAYER_PAUSE_MAX_SECONDS
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.game import GamePauseReason
from majlisna.api.models.table import User
from majlisna.api.schemas.common import GamePause, PauseGameResponse, ResumeGameResponse
from majlisna.api.schemas.error import (
    BaseError,
    GameAlreadyPausedError,
    GameNotPausedError,
    GamePausedError,
    OnlyHostCanPauseError,
    SpectatorCannotPauseError,
)
from majlisna.dependencies import (
    get_codenames_game_controller,
    get_current_user,
    get_mcqquiz_game_controller,
    get_undercover_game_controller,
    get_wordquiz_game_controller,
)

# (URL prefix, controller class, controller dependency, routes module that notifies)
GAMES = [
    ("undercover", UndercoverGameController, get_undercover_game_controller, "majlisna.api.routes.undercover"),
    ("codenames", CodenamesGameController, get_codenames_game_controller, "majlisna.api.routes.codenames"),
    ("wordquiz", WordQuizGameController, get_wordquiz_game_controller, "majlisna.api.routes.wordquiz"),
    ("mcqquiz", McqQuizGameController, get_mcqquiz_game_controller, "majlisna.api.routes.mcqquiz"),
]
GAME_IDS = [game[0] for game in GAMES]


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="host",
        email_address="host@test.com",
        country="FRA",
        password="securepassword",
    )


@pytest.mark.parametrize(("prefix", "controller_cls", "dependency", "routes_module"), GAMES, ids=GAME_IDS)
def test_pause_succeeds_and_notifies(
    test_app: FastAPI, client: TestClient, prefix, controller_cls, dependency, routes_module
) -> None:
    """Pausing returns the pause and broadcasts game_updated before responding."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    since = datetime.now(UTC)
    controller = Mock(spec=controller_cls)
    controller.pause_game = AsyncMock(
        return_value=PauseGameResponse(
            game_id=str(game_id),
            paused=GamePause(
                by_user_id=str(user.id),
                by_username=user.username,
                since=since,
                reason=GamePauseReason.SALAH,
                remaining_seconds=12.5,
                paused_for_seconds=0.0,
                anyone_can_resume_at=since + timedelta(seconds=PRAYER_PAUSE_MAX_SECONDS),
            ),
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[dependency] = lambda: controller

    try:
        with patch(f"{routes_module}.notify_game_changed", new_callable=AsyncMock) as notify:
            # Act
            response = client.post(f"/api/v1/{prefix}/games/{game_id}/pause")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == str(game_id)
        assert data["paused"]["by_user_id"] == str(user.id)
        assert data["paused"]["reason"] == "salah"
        assert datetime.fromisoformat(data["paused"]["since"]) == since
        assert data["paused"]["remaining_seconds"] == 12.5
        assert datetime.fromisoformat(data["paused"]["anyone_can_resume_at"]) == since + timedelta(
            seconds=PRAYER_PAUSE_MAX_SECONDS
        )
        controller.pause_game.assert_awaited_once_with(game_id, user.id)
        notify.assert_awaited_once_with(str(game_id))
    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.parametrize(("prefix", "controller_cls", "dependency", "routes_module"), GAMES, ids=GAME_IDS)
def test_resume_succeeds_and_notifies(
    test_app: FastAPI, client: TestClient, prefix, controller_cls, dependency, routes_module
) -> None:
    """Resuming reports the paused duration and broadcasts game_updated."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    controller = Mock(spec=controller_cls)
    controller.resume_game = AsyncMock(return_value=ResumeGameResponse(game_id=str(game_id), paused_seconds=612.5))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[dependency] = lambda: controller

    try:
        with patch(f"{routes_module}.notify_game_changed", new_callable=AsyncMock) as notify:
            # Act
            response = client.post(f"/api/v1/{prefix}/games/{game_id}/resume")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"game_id": str(game_id), "paused_seconds": 612.5}
        controller.resume_game.assert_awaited_once_with(game_id, user.id)
        notify.assert_awaited_once_with(str(game_id))
    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.parametrize("action", ["pause", "resume"])
@pytest.mark.parametrize(("prefix", "controller_cls", "dependency", "routes_module"), GAMES, ids=GAME_IDS)
def test_pause_and_resume_require_authentication(
    test_app: FastAPI,
    client: TestClient,
    prefix,
    controller_cls,
    dependency,
    routes_module,  # noqa: ARG001
    action: str,
) -> None:
    """Without a token both endpoints answer 401 and never reach the controller."""
    # Arrange
    controller = Mock(spec=controller_cls)
    test_app.dependency_overrides[dependency] = lambda: controller

    try:
        # Act
        response = client.post(f"/api/v1/{prefix}/games/{uuid4()}/{action}")

        # Assert
        assert response.status_code == 401
        assert controller.mock_calls == []
    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("action", "method", "error", "status_code"),
    [
        ("pause", "pause_game", OnlyHostCanPauseError(user_id="u", game_id="g"), 403),
        ("pause", "pause_game", SpectatorCannotPauseError(user_id="u", game_id="g"), 403),
        ("pause", "pause_game", GameAlreadyPausedError(game_id="g"), 409),
        ("pause", "pause_game", BaseError(message="over", status_code=400), 400),
        ("resume", "resume_game", OnlyHostCanPauseError(user_id="u", game_id="g"), 403),
        ("resume", "resume_game", GameNotPausedError(game_id="g"), 409),
    ],
)
@pytest.mark.parametrize(("prefix", "controller_cls", "dependency", "routes_module"), GAMES, ids=GAME_IDS)
def test_pause_and_resume_errors_map_to_their_status(
    test_app: FastAPI,
    client: TestClient,
    prefix,
    controller_cls,
    dependency,
    routes_module,
    action: str,
    method: str,
    error: BaseError,
    status_code: int,
) -> None:
    """The controller's refusals surface with their status and i18n key, and nothing is broadcast."""
    # Arrange
    controller = Mock(spec=controller_cls)
    setattr(controller, method, AsyncMock(side_effect=error))
    test_app.dependency_overrides[get_current_user] = _mock_user
    test_app.dependency_overrides[dependency] = lambda: controller

    try:
        with patch(f"{routes_module}.notify_game_changed", new_callable=AsyncMock) as notify:
            # Act
            response = client.post(f"/api/v1/{prefix}/games/{uuid4()}/{action}")

        # Assert
        assert response.status_code == status_code
        assert response.json()["error_key"] == error.error_key
        notify.assert_not_awaited()
    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("prefix", "path", "body", "controller_cls", "dependency", "method"),
    [
        (
            "undercover",
            "describe",
            {"word": "Sabr"},
            UndercoverGameController,
            get_undercover_game_controller,
            "submit_description",
        ),
        (
            "codenames",
            "clue",
            {"clue_word": "Sabr", "clue_number": 1},
            CodenamesGameController,
            get_codenames_game_controller,
            "give_clue",
        ),
        (
            "wordquiz",
            "answer",
            {"answer": "Musa"},
            WordQuizGameController,
            get_wordquiz_game_controller,
            "submit_answer",
        ),
        ("mcqquiz", "answer", {"choice_index": 0}, McqQuizGameController, get_mcqquiz_game_controller, "submit_answer"),
    ],
    ids=GAME_IDS,
)
def test_a_move_while_paused_answers_409(
    test_app: FastAPI, client: TestClient, prefix, path, body, controller_cls, dependency, method
) -> None:
    """GamePausedError reaches the client as a 409 with its own i18n key."""
    # Arrange
    controller = Mock(spec=controller_cls)
    setattr(controller, method, AsyncMock(side_effect=GamePausedError(game_id="g")))
    test_app.dependency_overrides[get_current_user] = _mock_user
    test_app.dependency_overrides[dependency] = lambda: controller

    try:
        # Act
        response = client.post(f"/api/v1/{prefix}/games/{uuid4()}/{path}", json=body)

        # Assert
        assert response.status_code == 409
        assert response.json()["error_key"] == "errors.api.gamePaused"
    finally:
        test_app.dependency_overrides.clear()
