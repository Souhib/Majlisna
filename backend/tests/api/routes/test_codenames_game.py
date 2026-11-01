"""Route-level tests for codenames game action endpoints (/api/v1/codenames/games)."""

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.testclient import TestClient

from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.models.error import GameNotFoundError
from majlisna.api.models.table import Game, User
from majlisna.api.schemas.codenames import (
    CodenamesBoardState,
    CodenamesTurnState,
    EndTurnResponse,
    GiveClueResponse,
    GuessCardResponse,
)
from majlisna.api.schemas.common import GameStartResponse, HintRecordResponse
from majlisna.dependencies import get_codenames_game_controller, get_current_user, get_session, get_settings
from majlisna.settings import Settings

BASE_URL = "/api/v1/codenames"

# Sends one request as the given user: (user, method, url, **httpx kwargs).
ApiAs = Callable[..., Awaitable[httpx.Response]]


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== POST /codenames/games/{room_id}/start ==========


def test_start_game_success(test_app: FastAPI, client: TestClient) -> None:
    """Starting a codenames game returns 201 with game_id and room_id."""
    # Arrange
    room_id = uuid4()
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.create_and_start = AsyncMock(
        return_value=GameStartResponse(game_id=str(game_id), room_id=str(room_id))
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{room_id}/start")

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["game_id"] == str(game_id)
        assert data["room_id"] == str(room_id)
        mock_controller.create_and_start.assert_awaited_once_with(room_id, user.id, word_pack_ids=None)
    finally:
        test_app.dependency_overrides.clear()


def test_start_game_with_word_packs(test_app: FastAPI, client: TestClient) -> None:
    """Starting a game with word_pack_ids passes them to the controller."""
    # Arrange
    room_id = uuid4()
    game_id = uuid4()
    pack_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.create_and_start = AsyncMock(
        return_value=GameStartResponse(game_id=str(game_id), room_id=str(room_id))
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{room_id}/start",
            json={"word_pack_ids": [str(pack_id)]},
        )

        # Assert
        assert response.status_code == 201
        mock_controller.create_and_start.assert_awaited_once_with(room_id, user.id, word_pack_ids=[pack_id])
    finally:
        test_app.dependency_overrides.clear()


def test_start_game_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Starting a game without auth returns 401."""
    # Arrange
    room_id = uuid4()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{room_id}/start")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /codenames/games/{game_id}/board ==========


def test_board_get_success(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board returns 200 with full board state."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    board_response = CodenamesBoardState(
        game_id=str(game_id),
        room_id=str(uuid4()),
        team="red",
        role="operative",
        is_host=False,
        board=[],
        current_team="red",
        red_remaining=9,
        blue_remaining=8,
        status="in_progress",
        current_turn=CodenamesTurnState(team="red", clue_number=0, guesses_made=0, max_guesses=0, card_votes={}),
        winner=None,
        clue_history=[],
        players=[],
    )
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.get_board = AsyncMock(return_value=board_response)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == str(game_id)
        assert data["current_team"] == "red"
        assert data["red_remaining"] == 9
        assert data["blue_remaining"] == 8
        mock_controller.get_board.assert_awaited_once_with(game_id, user.id, lang="en", sid=None)
    finally:
        test_app.dependency_overrides.clear()


def test_board_with_sid(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board with sid query param passes it to the controller."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.get_board = AsyncMock(
        return_value=CodenamesBoardState(
            game_id=str(game_id),
            room_id=str(uuid4()),
            team="red",
            role="operative",
            is_host=False,
            board=[],
            current_team="red",
            red_remaining=9,
            blue_remaining=8,
            status="in_progress",
            current_turn=CodenamesTurnState(team="red", clue_number=0, guesses_made=0, max_guesses=0, card_votes={}),
            winner=None,
            clue_history=[],
            players=[],
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board?sid=test-sid-123")

        # Assert
        assert response.status_code == 200
        mock_controller.get_board.assert_awaited_once_with(game_id, user.id, lang="en", sid="test-sid-123")
    finally:
        test_app.dependency_overrides.clear()


def test_board_game_not_found(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board for a nonexistent game returns 404."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.get_board = AsyncMock(side_effect=GameNotFoundError(game_id=game_id))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "GameNotFoundError"
    finally:
        test_app.dependency_overrides.clear()


def test_board_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /codenames/games/{game_id}/clue ==========


def test_clue_success(test_app: FastAPI, client: TestClient) -> None:
    """Giving a valid clue returns 200 with clue details."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.give_clue = AsyncMock(
        return_value=GiveClueResponse(game_id=str(game_id), clue_word="prayer", clue_number=3)
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/clue",
            json={"clue_word": "prayer", "clue_number": 3},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["clue_word"] == "prayer"
        assert data["clue_number"] == 3
        mock_controller.give_clue.assert_awaited_once_with(game_id, user.id, "prayer", 3)
    finally:
        test_app.dependency_overrides.clear()


def test_clue_missing_fields(test_app: FastAPI, client: TestClient) -> None:
    """Giving a clue with missing fields returns 422."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/clue", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


def test_clue_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Giving a clue without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/clue",
            json={"clue_word": "prayer", "clue_number": 3},
        )

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /codenames/games/{game_id}/guess ==========


def test_guess_card_success(test_app: FastAPI, client: TestClient) -> None:
    """Guessing a card returns 200 with the result."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.guess_card = AsyncMock(
        return_value=GuessCardResponse(
            game_id=str(game_id),
            card_index=5,
            card_type="red",
            result="correct",
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/guess",
            json={"card_index": 5},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["card_index"] == 5
        assert data["card_type"] == "red"
        assert data["result"] == "correct"
        mock_controller.guess_card.assert_awaited_once_with(game_id, user.id, 5)
    finally:
        test_app.dependency_overrides.clear()


def test_guess_card_missing_index(test_app: FastAPI, client: TestClient) -> None:
    """Guessing without card_index returns 422."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/guess", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


def test_guess_card_game_not_found(test_app: FastAPI, client: TestClient) -> None:
    """Guessing a card in a nonexistent game returns 404."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.guess_card = AsyncMock(side_effect=GameNotFoundError(game_id=game_id))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/guess",
            json={"card_index": 0},
        )

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "GameNotFoundError"
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /codenames/games/{game_id}/end-turn ==========


def test_end_turn_success(test_app: FastAPI, client: TestClient) -> None:
    """Ending a turn returns 200 with the new current team."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.end_turn = AsyncMock(return_value=EndTurnResponse(game_id=str(game_id), current_team="blue"))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/end-turn")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["current_team"] == "blue"
        mock_controller.end_turn.assert_awaited_once_with(game_id, user.id)
    finally:
        test_app.dependency_overrides.clear()


def test_end_turn_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Ending a turn without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/end-turn")

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /codenames/games/{game_id}/hint-viewed ==========


def test_hint_viewed_success(test_app: FastAPI, client: TestClient) -> None:
    """Recording a hint view returns 200 with recorded=True."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.record_hint_view = AsyncMock(return_value=HintRecordResponse(game_id=str(game_id), recorded=True))
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/hint-viewed",
            json={"word": "Quran"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["recorded"] is True
        mock_controller.record_hint_view.assert_awaited_once_with(game_id, user.id, "Quran")
    finally:
        test_app.dependency_overrides.clear()


def test_hint_viewed_missing_word(test_app: FastAPI, client: TestClient) -> None:
    """Recording a hint view without the word field returns 422."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/games/{game_id}/hint-viewed", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


def test_hint_viewed_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """Recording a hint view without auth returns 401."""
    # Arrange
    game_id = uuid4()
    mock_controller = Mock(spec=CodenamesGameController)
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/games/{game_id}/hint-viewed",
            json={"word": "Quran"},
        )

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /codenames/games/{game_id}/board — lang parameter ==========


def test_board_with_lang_param(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board with lang query param passes it to the controller."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.get_board = AsyncMock(
        return_value=CodenamesBoardState(
            game_id=str(game_id),
            room_id=str(uuid4()),
            team="red",
            role="operative",
            is_host=False,
            board=[],
            current_team="red",
            red_remaining=9,
            blue_remaining=8,
            status="in_progress",
            current_turn=CodenamesTurnState(team="red", clue_number=0, guesses_made=0, max_guesses=0, card_votes={}),
            winner=None,
            clue_history=[],
            players=[],
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board?lang=fr")

        # Assert
        assert response.status_code == 200
        mock_controller.get_board.assert_awaited_once_with(game_id, user.id, lang="fr", sid=None)
    finally:
        test_app.dependency_overrides.clear()


def test_board_with_lang_and_sid(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board with both lang and sid passes both to the controller."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.get_board = AsyncMock(
        return_value=CodenamesBoardState(
            game_id=str(game_id),
            room_id=str(uuid4()),
            team="red",
            role="operative",
            is_host=False,
            board=[],
            current_team="red",
            red_remaining=9,
            blue_remaining=8,
            status="in_progress",
            current_turn=CodenamesTurnState(team="red", clue_number=0, guesses_made=0, max_guesses=0, card_votes={}),
            winner=None,
            clue_history=[],
            players=[],
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board?lang=ar&sid=my-sid")

        # Assert
        assert response.status_code == 200
        mock_controller.get_board.assert_awaited_once_with(game_id, user.id, lang="ar", sid="my-sid")
    finally:
        test_app.dependency_overrides.clear()


def test_board_defaults_lang_to_en(test_app: FastAPI, client: TestClient) -> None:
    """Getting the board without lang defaults to 'en'."""
    # Arrange
    game_id = uuid4()
    user = _mock_user()
    mock_controller = Mock(spec=CodenamesGameController)
    mock_controller.get_board = AsyncMock(
        return_value=CodenamesBoardState(
            game_id=str(game_id),
            room_id=str(uuid4()),
            team="red",
            role="operative",
            is_host=False,
            board=[],
            current_team="red",
            red_remaining=9,
            blue_remaining=8,
            status="in_progress",
            current_turn=CodenamesTurnState(team="red", clue_number=0, guesses_made=0, max_guesses=0, card_votes={}),
            winner=None,
            clue_history=[],
            players=[],
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/games/{game_id}/board")

        # Assert
        assert response.status_code == 200
        mock_controller.get_board.assert_awaited_once_with(game_id, user.id, lang="en", sid=None)
    finally:
        test_app.dependency_overrides.clear()


# ========== WP-09: the rules through the real stack (routes, controller, database) ==========


@pytest_asyncio.fixture(name="api")
async def get_api(test_app: FastAPI, session: AsyncSession, test_settings: Settings) -> AsyncGenerator[ApiAs]:
    """Call the real app as a given user, on the test database.

    Only the signed-in user is set by hand: the token rules have their own tests
    (test_wp00_token_type.py); these are about what the game answers.
    """

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:

        async def _as(user: User, method: str, url: str, **kwargs) -> httpx.Response:
            test_app.dependency_overrides[get_current_user] = lambda: user
            return await client.request(method, url, **kwargs)

        yield _as
    test_app.dependency_overrides.clear()


async def _started(setup_codenames_game, session: AsyncSession) -> tuple[str, dict, dict[str, User]]:
    """A 4-player game, its live_state and its users by id."""
    setup = await setup_codenames_game(4)
    started = await CodenamesGameController(session).create_and_start(setup["room"].id, setup["users"][0].id)
    game = (await session.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
    return started.game_id, game.live_state, {str(u.id): u for u in setup["users"]}


def _seat(state: dict, role: str) -> str:
    return next(p["user_id"] for p in state["players"] if p["team"] == state["current_team"] and p["role"] == role)


@pytest.mark.asyncio
async def test_a_two_word_clue_answers_the_translated_one_word_error(api: ApiAs, setup_codenames_game, session):
    """BR-14 over HTTP: 400 errors.api.clueMustBeOneWord, and the turn still has no clue."""
    # Prepare
    game_id, state, users = await _started(setup_codenames_game, session)
    spymaster = users[_seat(state, "spymaster")]

    # Act
    response = await api(
        spymaster, "POST", f"{BASE_URL}/games/{game_id}/clue", json={"clue_word": "the Sunnah", "clue_number": 1}
    )

    # Assert
    assert response.status_code == 400
    assert response.json()["error_key"] == "errors.api.clueMustBeOneWord"
    game = (
        await session.exec(select(Game).where(Game.id == UUID(game_id)).execution_options(populate_existing=True))
    ).one()
    assert game.live_state["current_turn"]["clue_word"] is None


@pytest.mark.asyncio
async def test_end_turn_before_a_clue_answers_no_clue_given(api: ApiAs, setup_codenames_game, session):
    """BR-15 over HTTP: 400 errors.api.noClueGiven, and the team keeps its turn."""
    # Prepare
    game_id, state, users = await _started(setup_codenames_game, session)
    operative = users[_seat(state, "operative")]

    # Act
    response = await api(operative, "POST", f"{BASE_URL}/games/{game_id}/end-turn")

    # Assert
    assert response.status_code == 400
    assert response.json()["error_key"] == "errors.api.noClueGiven"
    game = (
        await session.exec(select(Game).where(Game.id == UUID(game_id)).execution_options(populate_existing=True))
    ).one()
    assert game.live_state["current_team"] == state["current_team"]


@pytest.mark.asyncio
async def test_a_strangers_hint_view_and_timer_call_answer_403(api: ApiAs, setup_codenames_game, session, create_user):
    """SEC F07 / F08 over HTTP: 403 errors.api.notAGameParticipant, and nothing is written."""
    # Prepare
    game_id, state, _ = await _started(setup_codenames_game, session)
    stranger = await create_user(username="cn_route_stranger", email="cn_route_stranger@test.com")

    # Act
    hint = await api(
        stranger, "POST", f"{BASE_URL}/games/{game_id}/hint-viewed", json={"word": state["board"][0]["word"]}
    )
    timer = await api(stranger, "POST", f"{BASE_URL}/games/{game_id}/timer-expired")

    # Assert
    assert hint.status_code == 403
    assert hint.json()["error_key"] == "errors.api.notAGameParticipant"
    assert timer.status_code == 403
    assert timer.json()["error_key"] == "errors.api.notAGameParticipant"
    game = (
        await session.exec(select(Game).where(Game.id == UUID(game_id)).execution_options(populate_existing=True))
    ).one()
    assert game.live_state["hint_usage"] == {}


async def _stored_game(session: AsyncSession, game_id: str) -> Game:
    return (
        await session.exec(select(Game).where(Game.id == UUID(game_id)).execution_options(populate_existing=True))
    ).one()


@pytest.mark.asyncio
async def test_a_players_made_up_hint_words_never_grow_the_game(api: ApiAs, setup_codenames_game, session):
    """SEC F07 over HTTP, the Codenames half of the audit's test_f07: a player's distinct
    100-character words are each refused and leave live_state as it was; a card's word counts."""
    # Prepare
    game_id, state, users = await _started(setup_codenames_game, session)
    spymaster_id = _seat(state, "spymaster")
    spymaster = users[spymaster_id]
    card_word = state["board"][0]["word"]
    size_before = len(json.dumps(state, sort_keys=True))
    made_up = [f"{i:06d}" + "x" * 94 for i in range(30)]
    url = f"{BASE_URL}/games/{game_id}/hint-viewed"

    # Act
    responses = [await api(spymaster, "POST", url, json={"word": word}) for word in made_up]
    size_after = len(json.dumps((await _stored_game(session, game_id)).live_state, sort_keys=True))
    card = await api(spymaster, "POST", url, json={"word": card_word})

    # Assert
    assert [r.status_code for r in responses] == [200] * len(made_up)
    assert not any(r.json()["recorded"] for r in responses)
    assert size_after == size_before
    assert card.status_code == 200
    assert card.json()["recorded"] is True
    assert (await _stored_game(session, game_id)).live_state["hint_usage"] == {spymaster_id: [card_word]}
