"""Route-level tests for Word Quiz game action endpoints (/api/v1/wordquiz/games)."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.constants import WORDQUIZ_MAX_ATTEMPTS_PER_ROUND
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import Game, User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.common import (
    AdvanceRoundResponse,
    GameStartResponse,
    HintRecordResponse,
    TimerExpiredAction,
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


@patch("majlisna.api.routes.wordquiz.notify_timer_outcome", new_callable=AsyncMock)
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
        # Only the call that acted broadcasts (WP-11): the route hands the outcome on.
        mock_notify.assert_awaited_once_with(str(game_id), TimerExpiredAction.RESULTS)
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


# ========== Through the real controller and database (WP-10) ==========


class _HeaderAuthenticator:
    """A stand-in for get_current_user: the user named by the header, recorded on the
    request exactly as the real dependency records it."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


@pytest_asyncio.fixture(name="real_stack")
async def get_real_stack(test_app: FastAPI, session: AsyncSession) -> AsyncGenerator[tuple[httpx.AsyncClient, dict]]:
    """The real routes, controller and test database; only the token check is stood in for."""
    users: dict[str, User] = {}
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: WordQuizGameController(session)
    limiter.reset()
    with (
        patch("majlisna.api.routes.wordquiz.notify_game_changed", new_callable=AsyncMock),
        patch("majlisna.api.routes.wordquiz.notify_timer_outcome", new_callable=AsyncMock),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
            yield client, users
    limiter.reset()
    test_app.dependency_overrides.clear()


async def _reload(session: AsyncSession, game_id: str) -> Game:
    statement = select(Game).where(Game.id == UUID(game_id)).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


async def test_the_try_past_the_cap_answers_409_with_its_key(real_stack, setup_wordquiz_game, session) -> None:
    """Five wrong tries are answered; the sixth — the word itself — is a translatable 409 that scores nothing.

    Port of SEC F15's probe, where 60 wrong answers were accepted and the word still paid 6.
    """
    # Prepare
    client, users = real_stack
    setup = await setup_wordquiz_game(num_players=2)
    host, player = setup["users"]
    users.update({"host": host, "player": player})
    started = await WordQuizGameController(session).create_and_start(setup["room"].id, host.id)
    word = (await _reload(session, started.game_id)).live_state["current_word"]["word_en"]
    url = f"{BASE_URL}/games/{started.game_id}/answer"

    # Act
    misses = [
        await client.post(url, json={"answer": f"guess{i}"}, headers={"X-Test-User": "player"})
        for i in range(WORDQUIZ_MAX_ATTEMPTS_PER_ROUND)
    ]
    refused = await client.post(url, json={"answer": word}, headers={"X-Test-User": "player"})

    # Assert
    assert [(r.status_code, r.json()["correct"]) for r in misses] == [(200, False)] * WORDQUIZ_MAX_ATTEMPTS_PER_ROUND
    assert refused.status_code == 409
    body = refused.json()
    assert (body["error"], body["error_key"]) == ("AnswerAttemptsExhaustedError", "errors.api.answerAttemptsExhausted")
    assert body["error_params"] == {"max": WORDQUIZ_MAX_ATTEMPTS_PER_ROUND}
    game = await _reload(session, started.game_id)
    assert str(player.id) not in game.live_state["answers"]
    assert next(p for p in game.live_state["players"] if p["user_id"] == str(player.id))["total_score"] == 0
    state = await client.get(f"{BASE_URL}/games/{started.game_id}/state", headers={"X-Test-User": "player"})
    assert state.json()["my_attempts_left"] == 0


async def test_a_strangers_timer_call_is_refused_even_on_a_zero_second_round(
    real_stack, setup_wordquiz_game, session, create_user
) -> None:
    """Port of SEC F08: a non-member ended a 0-second round at once. Now: 403, and 0 is untimed for players too."""
    # Prepare — a round whose stored duration is 0, opened two minutes ago
    client, users = real_stack
    setup = await setup_wordquiz_game(num_players=2)
    host, player = setup["users"]
    stranger = await create_user(username="wqoutsider", email="wqoutsider@test.com")
    users.update({"player": player, "stranger": stranger})
    started = await WordQuizGameController(session).create_and_start(setup["room"].id, host.id)
    game = await _reload(session, started.game_id)
    game.live_state["turn_duration_seconds"] = 0
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    url = f"{BASE_URL}/games/{started.game_id}/timer-expired"

    # Act
    from_stranger = await client.post(url, headers={"X-Test-User": "stranger"})
    from_player = await client.post(url, headers={"X-Test-User": "player"})

    # Assert
    assert from_stranger.status_code == 403
    assert from_stranger.json()["error_key"] == "errors.api.notAGameParticipant"
    assert from_player.status_code == 200
    assert from_player.json()["action"] == "timer_not_expired"
    game = await _reload(session, started.game_id)
    assert game.live_state["round_phase"] == "playing"
