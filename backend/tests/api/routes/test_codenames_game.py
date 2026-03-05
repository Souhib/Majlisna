"""Route-level tests for codenames game action endpoints (/api/v1/codenames/games)."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.models.error import GameNotFoundError
from ipg.api.models.table import User
from ipg.dependencies import get_codenames_game_controller, get_current_user

BASE_URL = "/api/v1/codenames"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== POST /codenames/games/{room_id}/start ==========


class TestStartCodenamesGame:
    """Tests for POST /codenames/games/{room_id}/start."""

    def test_start_game_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting a codenames game returns 201 with game_id and room_id."""
        # Arrange
        room_id = uuid4()
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=CodenamesGameController)
        mock_controller.create_and_start = AsyncMock(return_value={"game_id": str(game_id), "room_id": str(room_id)})
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

    def test_start_game_with_word_packs(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting a game with word_pack_ids passes them to the controller."""
        # Arrange
        room_id = uuid4()
        game_id = uuid4()
        pack_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=CodenamesGameController)
        mock_controller.create_and_start = AsyncMock(return_value={"game_id": str(game_id), "room_id": str(room_id)})
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

    def test_start_game_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
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


class TestGetCodenamesBoard:
    """Tests for GET /codenames/games/{game_id}/board."""

    def test_get_board_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Getting the board returns 200 with full board state."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        board_response = {
            "game_id": str(game_id),
            "room_id": str(uuid4()),
            "team": "red",
            "role": "operative",
            "board": [{"word": "prayer", "revealed": False}],
            "current_team": "red",
            "red_remaining": 9,
            "blue_remaining": 8,
            "status": "in_progress",
            "current_turn": None,
            "winner": None,
            "players": [],
        }
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
            mock_controller.get_board.assert_awaited_once_with(game_id, user.id, sid=None)
        finally:
            test_app.dependency_overrides.clear()

    def test_get_board_with_sid(self, test_app: FastAPI, client: TestClient) -> None:
        """Getting the board with sid query param passes it to the controller."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=CodenamesGameController)
        mock_controller.get_board = AsyncMock(return_value={"game_id": str(game_id)})
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_codenames_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.get(f"{BASE_URL}/games/{game_id}/board?sid=test-sid-123")

            # Assert
            assert response.status_code == 200
            mock_controller.get_board.assert_awaited_once_with(game_id, user.id, sid="test-sid-123")
        finally:
            test_app.dependency_overrides.clear()

    def test_get_board_game_not_found(self, test_app: FastAPI, client: TestClient) -> None:
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

    def test_get_board_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
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


class TestGiveClue:
    """Tests for POST /codenames/games/{game_id}/clue."""

    def test_give_clue_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Giving a valid clue returns 200 with clue details."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=CodenamesGameController)
        mock_controller.give_clue = AsyncMock(
            return_value={"game_id": str(game_id), "clue_word": "prayer", "clue_number": 3}
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

    def test_give_clue_missing_fields(self, test_app: FastAPI, client: TestClient) -> None:
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

    def test_give_clue_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
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


class TestGuessCard:
    """Tests for POST /codenames/games/{game_id}/guess."""

    def test_guess_card_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Guessing a card returns 200 with the result."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=CodenamesGameController)
        mock_controller.guess_card = AsyncMock(
            return_value={
                "game_id": str(game_id),
                "card_index": 5,
                "card_type": "red",
                "result": "correct",
            }
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

    def test_guess_card_missing_index(self, test_app: FastAPI, client: TestClient) -> None:
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

    def test_guess_card_game_not_found(self, test_app: FastAPI, client: TestClient) -> None:
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


class TestEndTurn:
    """Tests for POST /codenames/games/{game_id}/end-turn."""

    def test_end_turn_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Ending a turn returns 200 with the new current team."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=CodenamesGameController)
        mock_controller.end_turn = AsyncMock(return_value={"game_id": str(game_id), "current_team": "blue"})
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

    def test_end_turn_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
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
