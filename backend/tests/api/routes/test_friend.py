"""Route-level tests for friend endpoints (/api/v1/friends)."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.constants import FRIEND_REQUEST_RATE_LIMIT
from majlisna.api.controllers.friend import FriendController
from majlisna.api.models.friendship import Friendship, FriendshipStatus
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.friend import FriendEntry, FriendshipStatusEnum, FriendshipStatusResponse
from majlisna.dependencies import get_current_user, get_friend_controller

BASE_URL = "/api/v1/friends"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="testplayer",
        email_address="player@test.com",
        country="FRA",
        password="securepassword",
    )


# ========== GET /friends ==========


def test_get_friends_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /friends returns 200 and a list of FriendEntry."""
    # Arrange
    user = _mock_user()
    friend_id = uuid4()
    friendship_id = uuid4()
    mock_controller = Mock(spec=FriendController)
    mock_controller.get_friends = AsyncMock(
        return_value=[
            FriendEntry(friendship_id=friendship_id, user_id=friend_id, username="friend1", status="accepted")
        ]
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(BASE_URL)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["username"] == "friend1"
        assert data[0]["status"] == "accepted"
        mock_controller.get_friends.assert_awaited_once_with(user.id)
    finally:
        test_app.dependency_overrides.clear()


def test_get_friends_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """GET /friends without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=FriendController)
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(BASE_URL)

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /friends/pending ==========


def test_get_pending_requests_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /friends/pending returns 200 and a list of pending FriendEntry."""
    # Arrange
    user = _mock_user()
    mock_controller = Mock(spec=FriendController)
    mock_controller.get_pending_requests = AsyncMock(return_value=[])
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/pending")

        # Assert
        assert response.status_code == 200
        assert response.json() == []
        mock_controller.get_pending_requests.assert_awaited_once_with(user.id)
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /friends/status/{user_id} ==========


def test_get_friendship_status_success(test_app: FastAPI, client: TestClient) -> None:
    """GET /friends/status/{user_id} returns 200 with friendship status."""
    # Arrange
    user = _mock_user()
    other_user_id = uuid4()
    mock_controller = Mock(spec=FriendController)
    mock_controller.get_friendship_status = AsyncMock(
        return_value=FriendshipStatusResponse(status=FriendshipStatusEnum.ACCEPTED, friendship_id=str(uuid4()))
    )
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.get(f"{BASE_URL}/status/{other_user_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        mock_controller.get_friendship_status.assert_awaited_once_with(user.id, other_user_id)
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /friends/request ==========


def test_send_friend_request_success(test_app: FastAPI, client: TestClient) -> None:
    """POST /friends/request returns 201 with friendship_id and status."""
    # Arrange
    user = _mock_user()
    addressee_id = uuid4()
    friendship_id = uuid4()
    mock_controller = Mock(spec=FriendController)
    mock_friendship = Mock(spec=Friendship)
    mock_friendship.id = friendship_id
    mock_friendship.status = FriendshipStatus.PENDING
    mock_controller.send_request = AsyncMock(return_value=mock_friendship)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(
            f"{BASE_URL}/request",
            json={"addressee_id": str(addressee_id)},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["friendship_id"] == str(friendship_id)
        assert data["status"] == "pending"
        mock_controller.send_request.assert_awaited_once_with(user.id, addressee_id)
    finally:
        test_app.dependency_overrides.clear()


def test_send_friend_request_missing_body(test_app: FastAPI, client: TestClient) -> None:
    """POST /friends/request with empty body returns 422."""
    # Arrange
    user = _mock_user()
    mock_controller = Mock(spec=FriendController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/request", json={})

        # Assert
        assert response.status_code == 422
    finally:
        test_app.dependency_overrides.clear()


def test_send_friend_request_unauthenticated(test_app: FastAPI, client: TestClient) -> None:
    """POST /friends/request without auth returns 401."""
    # Arrange
    mock_controller = Mock(spec=FriendController)
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/request", json={"addressee_id": str(uuid4())})

        # Assert
        assert response.status_code == 401
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /friends/{friendship_id}/accept ==========


def test_accept_friend_request_success(test_app: FastAPI, client: TestClient) -> None:
    """POST /friends/{friendship_id}/accept returns 200 with updated status."""
    # Arrange
    user = _mock_user()
    friendship_id = uuid4()
    mock_controller = Mock(spec=FriendController)
    mock_friendship = Mock(spec=Friendship)
    mock_friendship.id = friendship_id
    mock_friendship.status = FriendshipStatus.ACCEPTED
    mock_controller.accept_request = AsyncMock(return_value=mock_friendship)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/{friendship_id}/accept")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["friendship_id"] == str(friendship_id)
        assert data["status"] == "accepted"
        mock_controller.accept_request.assert_awaited_once_with(friendship_id, user.id)
    finally:
        test_app.dependency_overrides.clear()


# ========== POST /friends/{friendship_id}/reject ==========


def test_reject_friend_request_success(test_app: FastAPI, client: TestClient) -> None:
    """POST /friends/{friendship_id}/reject returns 204."""
    # Arrange
    user = _mock_user()
    friendship_id = uuid4()
    mock_controller = Mock(spec=FriendController)
    mock_controller.reject_request = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.post(f"{BASE_URL}/{friendship_id}/reject")

        # Assert
        assert response.status_code == 204
        mock_controller.reject_request.assert_awaited_once_with(friendship_id, user.id)
    finally:
        test_app.dependency_overrides.clear()


# ========== DELETE /friends/{friendship_id} ==========


def test_remove_friend_success(test_app: FastAPI, client: TestClient) -> None:
    """DELETE /friends/{friendship_id} returns 204."""
    # Arrange
    user = _mock_user()
    friendship_id = uuid4()
    mock_controller = Mock(spec=FriendController)
    mock_controller.remove_friend = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller

    try:
        # Act
        response = client.delete(f"{BASE_URL}/{friendship_id}")

        # Assert
        assert response.status_code == 204
        mock_controller.remove_friend.assert_awaited_once_with(friendship_id, user.id)
    finally:
        test_app.dependency_overrides.clear()


# ========== WP-27, SEC F15: friend requests are limited per user ==========


class _HeaderAuthenticator:
    """get_current_user's stand-in: the user the header names, recorded on the request
    as the real dependency records it (the rate-limit key reads it)."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


def test_the_request_past_the_friend_request_limit_is_a_translated_429_for_that_user_only(
    test_app: FastAPI, client: TestClient
) -> None:
    """The 21st request in a minute by one user is refused; another user on the same
    connection is not (a majlis is several phones behind one address)."""
    # Prepare
    users = {name: User(id=uuid4(), username=name, email_address=f"{name}@test.com") for name in ("first", "second")}
    mock_controller = Mock(spec=FriendController)
    mock_controller.send_request = AsyncMock(
        side_effect=lambda requester_id, addressee_id: Friendship(
            id=uuid4(), requester_id=requester_id, addressee_id=addressee_id, status=FriendshipStatus.PENDING
        )
    )
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_friend_controller] = lambda: mock_controller
    allowed_count = int(FRIEND_REQUEST_RATE_LIMIT.split("/", maxsplit=1)[0])
    limiter.reset()

    try:
        allowed = [
            client.post(
                f"{BASE_URL}/request", json={"addressee_id": str(uuid4())}, headers={"X-Test-User": "first"}
            ).status_code
            for _ in range(allowed_count)
        ]

        # Act
        limited = client.post(
            f"{BASE_URL}/request", json={"addressee_id": str(uuid4())}, headers={"X-Test-User": "first"}
        )
        other = client.post(
            f"{BASE_URL}/request", json={"addressee_id": str(uuid4())}, headers={"X-Test-User": "second"}
        )

        # Assert
        assert allowed == [201] * allowed_count
        assert limited.status_code == 429
        assert limited.json()["error_key"] == "errors.api.rateLimitExceeded"
        assert other.status_code == 201
        assert mock_controller.send_request.await_count == allowed_count + 1
    finally:
        limiter.reset()
        test_app.dependency_overrides.clear()
