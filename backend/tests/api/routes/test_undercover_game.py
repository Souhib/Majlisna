"""Route-level tests for undercover game action endpoints (/api/v1/undercover/games)."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.models.error import GameNotFoundError
from ipg.api.models.table import User
from ipg.dependencies import get_current_user, get_undercover_game_controller

BASE_URL = "/api/v1/undercover"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== POST /undercover/games/{room_id}/start ==========


class TestStartUndercoverGame:
    """Tests for POST /undercover/games/{room_id}/start."""

    def test_start_game_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting an undercover game returns 201 with game_id and room_id."""
        # Arrange
        room_id = uuid4()
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.create_and_start = AsyncMock(return_value={"game_id": str(game_id), "room_id": str(room_id)})
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(f"{BASE_URL}/games/{room_id}/start")

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["game_id"] == str(game_id)
            assert data["room_id"] == str(room_id)
            mock_controller.create_and_start.assert_awaited_once_with(room_id, user.id)
        finally:
            test_app.dependency_overrides.clear()

    def test_start_game_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting a game without auth returns 401."""
        # Arrange
        room_id = uuid4()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(f"{BASE_URL}/games/{room_id}/start")

            # Assert
            assert response.status_code == 401
        finally:
            test_app.dependency_overrides.clear()


# ========== GET /undercover/games/{game_id}/state ==========


class TestGetUndercoverState:
    """Tests for GET /undercover/games/{game_id}/state."""

    def test_get_state_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Getting game state returns 200 with full state."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        state_response = {
            "game_id": str(game_id),
            "room_id": str(uuid4()),
            "is_host": True,
            "my_role": "civilian",
            "my_word": "prayer",
            "is_alive": True,
            "players": [
                {"user_id": str(user.id), "username": "testplayer", "is_alive": True, "is_mayor": False},
            ],
            "eliminated_players": [],
            "turn_number": 1,
            "votes": {},
            "has_voted": False,
            "winner": None,
            "turn_phase": "describing",
            "description_order": [],
            "current_describer_index": 0,
            "descriptions": {},
        }
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.get_state = AsyncMock(return_value=state_response)
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.get(f"{BASE_URL}/games/{game_id}/state")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["game_id"] == str(game_id)
            assert data["my_role"] == "civilian"
            assert data["is_alive"] is True
            assert data["turn_phase"] == "describing"
            mock_controller.get_state.assert_awaited_once_with(game_id, user.id, sid=None)
        finally:
            test_app.dependency_overrides.clear()

    def test_get_state_with_sid(self, test_app: FastAPI, client: TestClient) -> None:
        """Getting state with sid query param passes it to the controller."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.get_state = AsyncMock(return_value={"game_id": str(game_id)})
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.get(f"{BASE_URL}/games/{game_id}/state?sid=new-sid-456")

            # Assert
            assert response.status_code == 200
            mock_controller.get_state.assert_awaited_once_with(game_id, user.id, sid="new-sid-456")
        finally:
            test_app.dependency_overrides.clear()

    def test_get_state_game_not_found(self, test_app: FastAPI, client: TestClient) -> None:
        """Getting state for a nonexistent game returns 404."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.get_state = AsyncMock(side_effect=GameNotFoundError(game_id=game_id))
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.get(f"{BASE_URL}/games/{game_id}/state")

            # Assert
            assert response.status_code == 404
            data = response.json()
            assert data["error"] == "GameNotFoundError"
        finally:
            test_app.dependency_overrides.clear()

    def test_get_state_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
        """Getting state without auth returns 401."""
        # Arrange
        game_id = uuid4()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.get(f"{BASE_URL}/games/{game_id}/state")

            # Assert
            assert response.status_code == 401
        finally:
            test_app.dependency_overrides.clear()


# ========== POST /undercover/games/{game_id}/describe ==========


class TestSubmitDescription:
    """Tests for POST /undercover/games/{game_id}/describe."""

    def test_submit_description_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Submitting a description returns 200 with result."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.submit_description = AsyncMock(
            return_value={"game_id": str(game_id), "all_described": False, "word": "building"}
        )
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/describe",
                json={"word": "building"},
            )

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["word"] == "building"
            assert data["all_described"] is False
            mock_controller.submit_description.assert_awaited_once_with(game_id, user.id, "building")
        finally:
            test_app.dependency_overrides.clear()

    def test_submit_description_missing_word(self, test_app: FastAPI, client: TestClient) -> None:
        """Submitting without word returns 422."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(f"{BASE_URL}/games/{game_id}/describe", json={})

            # Assert
            assert response.status_code == 422
        finally:
            test_app.dependency_overrides.clear()

    def test_submit_description_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
        """Submitting a description without auth returns 401."""
        # Arrange
        game_id = uuid4()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/describe",
                json={"word": "building"},
            )

            # Assert
            assert response.status_code == 401
        finally:
            test_app.dependency_overrides.clear()


# ========== POST /undercover/games/{game_id}/vote ==========


class TestSubmitVote:
    """Tests for POST /undercover/games/{game_id}/vote."""

    def test_submit_vote_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Submitting a vote returns 200 with result."""
        # Arrange
        game_id = uuid4()
        voted_for = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.submit_vote = AsyncMock(return_value={"game_id": str(game_id), "all_voted": False})
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/vote",
                json={"voted_for": str(voted_for)},
            )

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["all_voted"] is False
            mock_controller.submit_vote.assert_awaited_once_with(game_id, user.id, voted_for)
        finally:
            test_app.dependency_overrides.clear()

    def test_submit_vote_all_voted(self, test_app: FastAPI, client: TestClient) -> None:
        """When all players have voted, response includes elimination info."""
        # Arrange
        game_id = uuid4()
        voted_for = uuid4()
        eliminated_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.submit_vote = AsyncMock(
            return_value={
                "game_id": str(game_id),
                "all_voted": True,
                "eliminated_player": str(eliminated_id),
                "winner": None,
            }
        )
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/vote",
                json={"voted_for": str(voted_for)},
            )

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["all_voted"] is True
            assert data["eliminated_player"] == str(eliminated_id)
            assert data["winner"] is None
        finally:
            test_app.dependency_overrides.clear()

    def test_submit_vote_missing_voted_for(self, test_app: FastAPI, client: TestClient) -> None:
        """Submitting without voted_for returns 422."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(f"{BASE_URL}/games/{game_id}/vote", json={})

            # Assert
            assert response.status_code == 422
        finally:
            test_app.dependency_overrides.clear()

    def test_submit_vote_invalid_uuid(self, test_app: FastAPI, client: TestClient) -> None:
        """Submitting with invalid UUID returns 422."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/vote",
                json={"voted_for": "not-a-uuid"},
            )

            # Assert
            assert response.status_code == 422
        finally:
            test_app.dependency_overrides.clear()

    def test_submit_vote_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
        """Voting without auth returns 401."""
        # Arrange
        game_id = uuid4()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/vote",
                json={"voted_for": str(uuid4())},
            )

            # Assert
            assert response.status_code == 401
        finally:
            test_app.dependency_overrides.clear()


# ========== POST /undercover/games/{game_id}/next-round ==========


class TestStartNextRound:
    """Tests for POST /undercover/games/{game_id}/next-round."""

    def test_next_round_success(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting next round returns 200 with turn info."""
        # Arrange
        game_id = uuid4()
        room_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        mock_controller.start_next_round = AsyncMock(
            return_value={
                "game_id": str(game_id),
                "turn_number": 2,
                "description_order": [
                    {"user_id": str(uuid4()), "username": "player1"},
                ],
            }
        )
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/next-round",
                json={"room_id": str(room_id)},
            )

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["turn_number"] == 2
            assert len(data["description_order"]) == 1
            mock_controller.start_next_round.assert_awaited_once_with(game_id, room_id, user.id)
        finally:
            test_app.dependency_overrides.clear()

    def test_next_round_missing_room_id(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting next round without room_id returns 422."""
        # Arrange
        game_id = uuid4()
        user = _mock_user()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(f"{BASE_URL}/games/{game_id}/next-round", json={})

            # Assert
            assert response.status_code == 422
        finally:
            test_app.dependency_overrides.clear()

    def test_next_round_unauthenticated(self, test_app: FastAPI, client: TestClient) -> None:
        """Starting next round without auth returns 401."""
        # Arrange
        game_id = uuid4()
        mock_controller = Mock(spec=UndercoverGameController)
        test_app.dependency_overrides[get_undercover_game_controller] = lambda: mock_controller

        try:
            # Act
            response = client.post(
                f"{BASE_URL}/games/{game_id}/next-round",
                json={"room_id": str(uuid4())},
            )

            # Assert
            assert response.status_code == 401
        finally:
            test_app.dependency_overrides.clear()
