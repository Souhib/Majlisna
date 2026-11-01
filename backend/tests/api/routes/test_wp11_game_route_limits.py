"""WP-11: per-user limits on the game routes every client can call at will.

- ``POST /wordquiz/games/{id}/answer`` (BR-10, SEC F15): each try is a locked write
  plus a broadcast to the table, and nothing bounded how fast one came.
- the hint-viewed routes (SEC F07): a locked rewrite of ``live_state`` per call.
- the four timer-expired routes (SEC F08): any signed-in player could make every
  client of the table refetch, as often as they liked.

Counted per USER (``rate_limit.user_or_ip_key``): a majlis is several phones on one
home connection, so a per-IP budget would be shared by the whole table. Two players
behind one address (the test client's) prove it: the first is limited, the second is
not. The controllers are stood in for — the limit is the route's — and the Socket.IO
server is a mock.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.constants import HINT_VIEW_RATE_LIMIT, TIMER_EXPIRED_RATE_LIMIT, WORDQUIZ_ANSWER_RATE_LIMIT
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.common import HintRecordResponse, TimerExpiredAction, TimerExpiredResponse
from majlisna.api.schemas.wordquiz import SubmitAnswerResponse
from majlisna.dependencies import (
    get_codenames_game_controller,
    get_current_user,
    get_mcqquiz_game_controller,
    get_undercover_game_controller,
    get_wordquiz_game_controller,
)

GAME_ID = str(uuid4())


class _HeaderAuthenticator:
    """A stand-in for get_current_user: the user named by the header, recorded on the
    request exactly as the real dependency records it (the rate-limit key reads it)."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


@dataclass(frozen=True)
class LimitedRoute:
    path: str
    body: dict | None
    limit: str


LIMITED_ROUTES = {
    "wordquiz answer": LimitedRoute(
        f"/api/v1/wordquiz/games/{GAME_ID}/answer", {"answer": "Musa"}, WORDQUIZ_ANSWER_RATE_LIMIT
    ),
    "undercover hint-viewed": LimitedRoute(
        f"/api/v1/undercover/games/{GAME_ID}/hint-viewed", {"word": "Sabr"}, HINT_VIEW_RATE_LIMIT
    ),
    "codenames hint-viewed": LimitedRoute(
        f"/api/v1/codenames/games/{GAME_ID}/hint-viewed", {"word": "Hajj"}, HINT_VIEW_RATE_LIMIT
    ),
    "wordquiz hint-viewed": LimitedRoute(f"/api/v1/wordquiz/games/{GAME_ID}/hint-viewed", None, HINT_VIEW_RATE_LIMIT),
    "undercover timer-expired": LimitedRoute(
        f"/api/v1/undercover/games/{GAME_ID}/timer-expired", None, TIMER_EXPIRED_RATE_LIMIT
    ),
    "codenames timer-expired": LimitedRoute(
        f"/api/v1/codenames/games/{GAME_ID}/timer-expired", None, TIMER_EXPIRED_RATE_LIMIT
    ),
    "wordquiz timer-expired": LimitedRoute(
        f"/api/v1/wordquiz/games/{GAME_ID}/timer-expired", None, TIMER_EXPIRED_RATE_LIMIT
    ),
    "mcqquiz timer-expired": LimitedRoute(
        f"/api/v1/mcqquiz/games/{GAME_ID}/timer-expired", None, TIMER_EXPIRED_RATE_LIMIT
    ),
}


def _controller(spec: type) -> Mock:
    """A controller whose every limited call succeeds and changes nothing."""
    controller = Mock(spec=spec)
    timer_answer = TimerExpiredResponse(game_id=GAME_ID, action=TimerExpiredAction.TIMER_NOT_EXPIRED)
    controller.handle_timer_expired = AsyncMock(return_value=timer_answer)
    controller.record_hint_view = AsyncMock(return_value=HintRecordResponse(game_id=GAME_ID, recorded=False))
    if spec is WordQuizGameController:
        controller.submit_answer = AsyncMock(
            return_value=SubmitAnswerResponse(correct=False, points_earned=0, hint_number=1)
        )
    return controller


@pytest.fixture(name="per_user_client")
def get_per_user_client(test_app: FastAPI) -> Iterator[TestClient]:
    """Two signed-in players behind ONE address; the limiter's memory is wiped so no
    other test inherits a spent budget."""
    users = {name: User(id=uuid4(), username=name, email_address=f"{name}@test.com") for name in ("first", "second")}
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_undercover_game_controller] = lambda: _controller(UndercoverGameController)
    test_app.dependency_overrides[get_codenames_game_controller] = lambda: _controller(CodenamesGameController)
    test_app.dependency_overrides[get_wordquiz_game_controller] = lambda: _controller(WordQuizGameController)
    test_app.dependency_overrides[get_mcqquiz_game_controller] = lambda: _controller(McqQuizGameController)
    limiter.reset()
    with (
        patch("majlisna.api.ws.notify.sio") as sio,
        patch("majlisna.api.ws.notify._get_room_id_for_game", new=AsyncMock(return_value=None)),
    ):
        sio.emit = AsyncMock()
        yield TestClient(test_app)
    limiter.reset()
    test_app.dependency_overrides.clear()


def _limit_count(limit: str) -> int:
    return int(limit.split("/", maxsplit=1)[0])


@pytest.mark.parametrize("route_name", list(LIMITED_ROUTES))
def test_the_call_past_the_limit_is_a_translated_429_for_that_player_only(
    per_user_client: TestClient, route_name: str
) -> None:
    """The limit-th call within a minute still answers; the next is the standard 429
    envelope, and another player on the same connection is unaffected."""
    # Prepare
    route = LIMITED_ROUTES[route_name]
    allowed = [
        per_user_client.post(route.path, json=route.body, headers={"X-Test-User": "first"}).status_code
        for _ in range(_limit_count(route.limit))
    ]

    # Act
    limited = per_user_client.post(route.path, json=route.body, headers={"X-Test-User": "first"})
    other = per_user_client.post(route.path, json=route.body, headers={"X-Test-User": "second"})

    # Assert
    assert allowed == [200] * _limit_count(route.limit)
    assert limited.status_code == 429
    assert limited.json()["error_key"] == "errors.api.rateLimitExceeded"
    assert other.status_code == 200
