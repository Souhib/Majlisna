"""Route-level tests for the samar riddle (GET /api/v1/rooms/{room_id}/riddle).

The wiring (a mocked controller behind TestClient), the refusals in the standard
envelope, and the per-user rate limit: a majlis is several phones on one home
connection, so the limit counts per signed-in user, never per address.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from freezegun import freeze_time
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.constants import ROOM_RIDDLE_DAILY_LIMIT, ROOM_RIDDLE_RATE_LIMIT
from majlisna.api.controllers.riddle import RiddleController
from majlisna.api.models.game import GameType
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.error import RiddleNotDuringGameError, RoomMembersOnlyError
from majlisna.api.schemas.riddle import RoomRiddle, RoomRiddleAnswer
from majlisna.api.schemas.wordquiz import WordQuizCategory
from majlisna.dependencies import get_current_user, get_riddle_controller

ROOM_ID = uuid4()
URL = f"/api/v1/rooms/{ROOM_ID}/riddle"


def _user(name: str) -> User:
    return User(id=uuid4(), username=name, email_address=f"{name}@test.com", country="FRA", password="securepassword")


def _riddle() -> RoomRiddle:
    return RoomRiddle(
        id=uuid4(),
        category=WordQuizCategory.PROPHETS,
        hint="Un grand patriarche",
        answer=RoomRiddleAnswer(word_display="Ibrahim / Abraham", word_ar="إبراهيم", word_ar_vocalized=None),
    )


class _HeaderAuthenticator:
    """get_current_user's stand-in: the user the header names, recorded on the request as
    the real dependency records it (the rate-limit key reads it)."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


@pytest.fixture(name="users")
def get_users() -> dict[str, User]:
    return {"maryam": _user("maryam"), "yusuf": _user("yusuf")}


@pytest.fixture(name="controller")
def get_controller(test_app: FastAPI, users: dict[str, User]) -> Iterator[Mock]:
    controller = Mock(spec=RiddleController)
    controller.get_room_riddle = AsyncMock(return_value=_riddle())
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_riddle_controller] = lambda: controller
    limiter.reset()
    yield controller
    limiter.reset()
    test_app.dependency_overrides.clear()


def test_a_riddle_needs_a_signed_in_caller(test_app: FastAPI, client: TestClient) -> None:
    # Prepare
    controller = Mock(spec=RiddleController)
    test_app.dependency_overrides[get_riddle_controller] = lambda: controller

    try:
        # Act
        response = client.get(URL)

        # Assert
        assert response.status_code == 401
        assert controller.mock_calls == []
    finally:
        test_app.dependency_overrides.clear()


def test_the_route_hands_the_room_the_caller_and_the_language_to_the_controller(
    client: TestClient, controller: Mock, users: dict[str, User]
) -> None:
    # Act
    response = client.get(URL, params={"lang": "fr"}, headers={"X-Test-User": "maryam"})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["hint"] == "Un grand patriarche"
    assert data["category"] == "prophets"
    assert data["answer"] == {"word_display": "Ibrahim / Abraham", "word_ar": "إبراهيم", "word_ar_vocalized": None}
    assert set(data) == {"id", "category", "hint", "answer"}
    controller.get_room_riddle.assert_awaited_once_with(ROOM_ID, users["maryam"].id, lang="fr")


def test_the_language_defaults_to_english(client: TestClient, controller: Mock, users: dict[str, User]) -> None:
    # Act
    client.get(URL, headers={"X-Test-User": "maryam"})

    # Assert
    controller.get_room_riddle.assert_awaited_once_with(ROOM_ID, users["maryam"].id, lang="en")


@pytest.mark.parametrize(
    ("error", "status", "key"),
    [
        (RoomMembersOnlyError(room_id=ROOM_ID, user_id=uuid4()), 403, "errors.api.roomMembersOnly"),
        (
            RiddleNotDuringGameError(room_id=ROOM_ID, game_type=GameType.WORD_QUIZ),
            409,
            "errors.api.riddleNotDuringGame",
        ),
    ],
)
def test_a_refusal_answers_the_standard_envelope(
    client: TestClient, controller: Mock, error: Exception, status: int, key: str
) -> None:
    # Prepare
    controller.get_room_riddle = AsyncMock(side_effect=error)

    # Act
    response = client.get(URL, headers={"X-Test-User": "maryam"})

    # Assert
    assert response.status_code == status
    assert response.json()["error_key"] == key


def test_riddles_are_limited_per_user_not_per_address(client: TestClient, controller: Mock) -> None:
    """Two players behind one address (the test client's): the first is limited, the second is not."""
    # Prepare
    allowed = int(ROOM_RIDDLE_RATE_LIMIT.split("/")[0])
    for _ in range(allowed):
        assert client.get(URL, headers={"X-Test-User": "maryam"}).status_code == 200

    # Act
    limited = client.get(URL, headers={"X-Test-User": "maryam"})
    other = client.get(URL, headers={"X-Test-User": "yusuf"})

    # Assert
    assert limited.status_code == 429
    assert limited.json()["error_key"] == "errors.api.rateLimitExceeded"
    assert other.status_code == 200
    assert controller.get_room_riddle.await_count == allowed + 1


def test_riddles_are_capped_per_day_as_well(client: TestClient, controller: Mock) -> None:
    """A script that keeps under the minute's limit still stops at the day's: a riddle and
    its answer are drawn from the words the next word of the day is drawn from, so the
    whole table must not be collected in an afternoon."""
    # Prepare
    per_minute = int(ROOM_RIDDLE_RATE_LIMIT.split("/")[0])
    per_day = int(ROOM_RIDDLE_DAILY_LIMIT.split("/")[0])
    # Frozen at the REAL now, never a fixed date: the in-memory storage expires keys from a
    # threading.Timer thread, which freezegun leaves on the real clock (it ignores
    # `threading` frames). Frozen at 2026-11-01 08:00, the day's key "expired" in that
    # thread from 2026-11-02 08:00 UTC on, and the 31st riddle was served.
    with freeze_time(datetime.now(UTC)) as frozen:
        served = 0
        while served < per_day:
            for _ in range(min(per_minute, per_day - served)):
                assert client.get(URL, headers={"X-Test-User": "maryam"}).status_code == 200
                served += 1
            frozen.tick(61)

        # Act
        limited = client.get(URL, headers={"X-Test-User": "maryam"})

    # Assert
    assert limited.status_code == 429
    assert limited.json()["error_key"] == "errors.api.rateLimitExceeded"
    assert controller.get_room_riddle.await_count == per_day
