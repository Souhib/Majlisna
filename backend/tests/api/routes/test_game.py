from datetime import datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import NoResultFound
from starlette.testclient import TestClient

from ipg.api.controllers.game import GameController
from ipg.api.models.error import RoomIsNotActiveError
from ipg.api.models.game import GameType
from ipg.api.models.table import Game
from ipg.api.schemas.game import GameHistoryEntry
from ipg.dependencies import get_game_controller


@pytest.mark.asyncio
async def test_create_game_success(test_app: FastAPI, client: TestClient):
    """POST /api/v1/games returns 201 with the created Game and all fields."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user_id = uuid4()
    start_time = datetime.now()

    mock_game = Game(
        id=game_id,
        room_id=room_id,
        user_id=user_id,
        start_time=start_time,
        end_time=None,
        number_of_players=4,
        type=GameType.UNDERCOVER,
        game_configurations={"key": "value"},
    )

    mock_controller = Mock(spec=GameController)
    mock_controller.create_game = AsyncMock(return_value=mock_game)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/games",
        json={
            "room_id": str(room_id),
            "number_of_players": 4,
            "type": GameType.UNDERCOVER.value,
            "game_configurations": {"key": "value"},
        },
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == str(game_id)
    assert data["room_id"] == str(room_id)
    assert data["user_id"] == str(user_id)
    assert data["start_time"] == start_time.isoformat()
    assert data["end_time"] is None
    assert data["number_of_players"] == 4
    assert data["type"] == GameType.UNDERCOVER.value
    assert data["game_configurations"] == {"key": "value"}
    mock_controller.create_game.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_game_inactive_room(test_app: FastAPI, client: TestClient):
    """POST /api/v1/games returns 403 when the room is not active."""
    # Arrange
    room_id = uuid4()

    mock_controller = Mock(spec=GameController)
    mock_controller.create_game = AsyncMock(side_effect=RoomIsNotActiveError(room_id=room_id))
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.post(
        "/api/v1/games",
        json={
            "room_id": str(room_id),
            "number_of_players": 4,
            "type": GameType.UNDERCOVER.value,
            "game_configurations": {"key": "value"},
        },
    )

    # Assert
    assert response.status_code == 403
    data = response.json()
    assert data["error"] == "RoomIsNotActiveError"
    assert data["error_key"] == "errors.api.roomIsNotActive"
    assert data["message"] == "This room is no longer active."
    assert data["details"] == {}
    mock_controller.create_game.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_all_games_success(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games returns 200 with a list of all games."""
    # Arrange
    room_id = uuid4()
    user_id = uuid4()
    start_time = datetime.now()
    end_time = datetime.now()

    mock_games = [
        Game(
            id=uuid4(),
            room_id=room_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            number_of_players=4,
            type=GameType.UNDERCOVER,
            game_configurations={"key": "value"},
        ),
        Game(
            id=uuid4(),
            room_id=room_id,
            user_id=user_id,
            start_time=start_time,
            end_time=None,
            number_of_players=6,
            type=GameType.CODENAMES,
            game_configurations={},
        ),
    ]

    mock_controller = Mock(spec=GameController)
    mock_controller.get_games = AsyncMock(return_value=mock_games)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.get("/api/v1/games")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == str(mock_games[0].id)
    assert data[0]["room_id"] == str(room_id)
    assert data[0]["user_id"] == str(user_id)
    assert data[0]["start_time"] == start_time.isoformat()
    assert data[0]["end_time"] == end_time.isoformat()
    assert data[0]["number_of_players"] == 4
    assert data[0]["type"] == GameType.UNDERCOVER.value
    assert data[0]["game_configurations"] == {"key": "value"}
    assert data[1]["id"] == str(mock_games[1].id)
    assert data[1]["number_of_players"] == 6
    assert data[1]["type"] == GameType.CODENAMES.value
    assert data[1]["end_time"] is None
    mock_controller.get_games.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_game_by_id_success(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/{game_id} returns 200 with the requested game."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user_id = uuid4()
    start_time = datetime.now()
    end_time = datetime.now()

    mock_game = Game(
        id=game_id,
        room_id=room_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        number_of_players=5,
        type=GameType.CODENAMES,
        game_configurations={"rounds": 3},
    )

    mock_controller = Mock(spec=GameController)
    mock_controller.get_game_by_id = AsyncMock(return_value=mock_game)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.get(f"/api/v1/games/{game_id}")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(game_id)
    assert data["room_id"] == str(room_id)
    assert data["user_id"] == str(user_id)
    assert data["start_time"] == start_time.isoformat()
    assert data["end_time"] == end_time.isoformat()
    assert data["number_of_players"] == 5
    assert data["type"] == GameType.CODENAMES.value
    assert data["game_configurations"] == {"rounds": 3}
    mock_controller.get_game_by_id.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_game_by_id_not_found(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/{game_id} returns 404 when the game does not exist."""
    # Arrange
    game_id = uuid4()

    mock_controller = Mock(spec=GameController)
    mock_controller.get_game_by_id = AsyncMock(side_effect=NoResultFound)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.get(f"/api/v1/games/{game_id}")

    # Assert
    assert response.status_code == 404
    data = response.json()
    assert data["error_key"] == "errors.api.resourceNotFound"
    assert data["frontend_message"] == "Couldn't find requested resource."
    mock_controller.get_game_by_id.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_game_success(test_app: FastAPI, client: TestClient):
    """PATCH /api/v1/games/{game_id} returns 200 with the updated game."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user_id = uuid4()
    start_time = datetime.now()

    mock_game = Game(
        id=game_id,
        room_id=room_id,
        user_id=user_id,
        start_time=start_time,
        end_time=None,
        number_of_players=6,
        type=GameType.CODENAMES,
        game_configurations={"key": "updated"},
    )

    mock_controller = Mock(spec=GameController)
    mock_controller.update_game = AsyncMock(return_value=mock_game)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.patch(
        f"/api/v1/games/{game_id}",
        json={
            "number_of_players": 6,
            "type": GameType.CODENAMES.value,
        },
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(game_id)
    assert data["room_id"] == str(room_id)
    assert data["user_id"] == str(user_id)
    assert data["start_time"] == start_time.isoformat()
    assert data["end_time"] is None
    assert data["number_of_players"] == 6
    assert data["type"] == GameType.CODENAMES.value
    assert data["game_configurations"] == {"key": "updated"}
    mock_controller.update_game.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_end_game_success(test_app: FastAPI, client: TestClient):
    """PATCH /api/v1/games/{game_id}/end returns 200 with end_time set."""
    # Arrange
    game_id = uuid4()
    room_id = uuid4()
    user_id = uuid4()
    start_time = datetime.now()
    end_time = datetime.now()

    mock_game = Game(
        id=game_id,
        room_id=room_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        number_of_players=4,
        type=GameType.UNDERCOVER,
        game_configurations={},
    )

    mock_controller = Mock(spec=GameController)
    mock_controller.end_game = AsyncMock(return_value=mock_game)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.patch(f"/api/v1/games/{game_id}/end")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(game_id)
    assert data["room_id"] == str(room_id)
    assert data["user_id"] == str(user_id)
    assert data["start_time"] == start_time.isoformat()
    assert data["end_time"] == end_time.isoformat()
    assert data["end_time"] is not None
    assert data["number_of_players"] == 4
    assert data["type"] == GameType.UNDERCOVER.value
    assert data["game_configurations"] == {}
    mock_controller.end_game.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_game_success(test_app: FastAPI, client: TestClient):
    """DELETE /api/v1/games/{game_id} returns 204 with no content."""
    # Arrange
    game_id = uuid4()

    mock_controller = Mock(spec=GameController)
    mock_controller.delete_game = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.delete(f"/api/v1/games/{game_id}")

    # Assert
    assert response.status_code == 204
    assert response.content == b""
    mock_controller.delete_game.assert_called_once()

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_games_by_user_success(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/user/{user_id} returns 200 with the user's game history."""
    # Arrange
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
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

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

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_games_by_user_empty(test_app: FastAPI, client: TestClient):
    """GET /api/v1/games/user/{user_id} returns 200 and empty list for new user."""
    # Arrange
    user_id = uuid4()
    mock_controller = Mock(spec=GameController)
    mock_controller.get_games_by_user = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_game_controller] = lambda: mock_controller

    # Act
    response = client.get(f"/api/v1/games/user/{user_id}")

    # Assert
    assert response.status_code == 200
    assert response.json() == []
    mock_controller.get_games_by_user.assert_awaited_once_with(user_id, limit=20)

    test_app.dependency_overrides.clear()
