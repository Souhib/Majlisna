"""Route-level tests for room share link endpoint."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from majlisna.api.controllers.room import RoomController
from majlisna.api.models.table import User
from majlisna.api.schemas.room import ShareLinkResponse
from majlisna.dependencies import get_current_user, get_room_controller

BASE_URL = "/api/v1/rooms"


def test_share_link_endpoint_returns_200(test_app: FastAPI, client: TestClient) -> None:
    """GET /rooms/{room_id}/share-link returns 200 with public_id and password."""
    # Arrange
    mock_controller = Mock(spec=RoomController)
    room_id = uuid4()
    user_id = uuid4()
    mock_user = User(
        id=user_id,
        username="member",
        email_address="member@test.com",
        country="FRA",
        password="securepassword",
    )

    mock_controller.get_share_link = AsyncMock(return_value=ShareLinkResponse(public_id="ABC12", password="1234"))

    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_room_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/{room_id}/share-link")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["public_id"] == "ABC12"
        assert data["password"] == "1234"
    finally:
        test_app.dependency_overrides.clear()
