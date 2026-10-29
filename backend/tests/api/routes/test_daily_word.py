"""Route-level tests for the word of the day (/api/v1/daily-word).

Two halves: the wiring (a mocked controller behind TestClient), and the leak test,
which drives the REAL stack — routes, real JWTs, the controller and the database —
and reads every payload's raw JSON for the word.
"""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from freezegun import freeze_time
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.daily_word import DailyWordController
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.daily_word import DailyWordGuessResponse, DailyWordState, DailyWordStatus
from majlisna.api.schemas.notebook import NotebookKeepResponse
from majlisna.dependencies import (
    get_current_user,
    get_daily_word_controller,
    get_optional_current_user,
    get_session,
    get_settings,
)
from majlisna.settings import Settings

BASE_URL = "/api/v1/daily-word"
NOW = "2026-11-10T09:00:00Z"  # noon in Makkah: no test straddles the turn of the day
TODAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def _frozen_clock(test_app: FastAPI):  # noqa: ARG001 — build (and import) the app before the clock freezes
    """Every test runs at noon in Makkah. The app is built first: freezegun swaps `date`
    for a fake one, and a module importing `date` subclasses meanwhile (pydantic.v1) breaks."""
    with freeze_time(NOW):
        yield


def _mock_user(name: str = "seeker") -> User:
    return User(id=uuid4(), username=name, email_address=f"{name}@test.com", country="FRA", password="securepassword")


def _state(**overrides) -> DailyWordState:
    values = {
        "day": TODAY,
        "number": 14,
        "max_hints": 6,
        "hints": ["Hint 1"],
        "hints_revealed": 1,
        "status": DailyWordStatus.NOT_STARTED,
        "category": None,
        "attempts": 0,
        "guesses": [],
        "score": None,
        "streak": None,
        "best_streak": None,
        "solvers_today": 0,
        "next_day_at": datetime(2026, 11, 10, 21, 0, tzinfo=UTC),
        "answer": None,
    }
    return DailyWordState(**(values | overrides))


@pytest.fixture(name="user")
def get_user() -> User:
    return _mock_user()


@pytest.fixture(name="controller")
def get_controller(test_app: FastAPI, user: User):
    """A mocked DailyWordController behind an authenticated (or, for GET, optional) user."""
    controller = Mock(spec=DailyWordController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_optional_current_user] = lambda: user
    test_app.dependency_overrides[get_daily_word_controller] = lambda: controller
    limiter.reset()
    yield controller
    limiter.reset()
    test_app.dependency_overrides.clear()


# ========== Authentication ==========


@pytest.mark.parametrize(
    ("path", "body"),
    [("/hint", None), ("/guess", {"answer": "Sabr"}), ("/give-up", None), ("/keep", None)],
)
def test_moves_require_authentication(test_app: FastAPI, client: TestClient, path: str, body: dict | None) -> None:
    """Every move answers 401 without a token and never reaches the controller."""
    # Prepare
    controller = Mock(spec=DailyWordController)
    test_app.dependency_overrides[get_daily_word_controller] = lambda: controller

    try:
        # Act
        response = client.post(f"{BASE_URL}{path}", json=body)

        # Assert
        assert response.status_code == 401
        assert controller.mock_calls == []
    finally:
        test_app.dependency_overrides.clear()


# ========== Wiring ==========


def test_get_passes_the_viewer_and_the_language(client: TestClient, controller: Mock, user: User) -> None:
    """GET hands the (optional) viewer and lang to the controller and returns its state."""
    # Prepare
    controller.get_today = AsyncMock(return_value=_state(hints=["Indice 1"]))

    # Act
    response = client.get(BASE_URL, params={"lang": "fr"})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert (data["day"], data["number"], data["hints"], data["answer"]) == ("2026-11-10", 14, ["Indice 1"], None)
    assert data["next_day_at"].startswith("2026-11-10T21:00:00")
    controller.get_today.assert_awaited_once_with(user, lang="fr")


@pytest.mark.parametrize(
    ("path", "method", "result"),
    [
        ("/hint", "reveal_hint", _state(status=DailyWordStatus.PLAYING)),
        ("/give-up", "give_up", _state(status=DailyWordStatus.GAVE_UP, score=0)),
        ("/keep", "keep", NotebookKeepResponse(added=1, already_kept=0, entries=[])),
    ],
)
def test_moves_pass_the_user_the_day_and_the_language(
    client: TestClient, controller: Mock, user: User, path: str, method: str, result
) -> None:
    """Each move reaches its controller method with the caller, the page's day and lang."""
    # Prepare
    setattr(controller, method, AsyncMock(return_value=result))

    # Act
    response = client.post(f"{BASE_URL}{path}", params={"lang": "ar", "day": "2026-11-10"})

    # Assert
    assert response.status_code == 200
    getattr(controller, method).assert_awaited_once_with(user.id, day=TODAY, lang="ar")


def test_guess_passes_the_answer(client: TestClient, controller: Mock, user: User) -> None:
    """The typed answer, the day and lang reach the controller; the response says correct + state."""
    # Prepare
    controller.guess = AsyncMock(
        return_value=DailyWordGuessResponse(correct=False, state=_state(status=DailyWordStatus.PLAYING, attempts=1))
    )

    # Act
    response = client.post(f"{BASE_URL}/guess", json={"answer": "صبر"})

    # Assert
    assert response.status_code == 200
    assert response.json()["correct"] is False
    assert response.json()["state"]["attempts"] == 1
    controller.guess.assert_awaited_once_with(user.id, "صبر", day=None, lang="en")


@pytest.mark.parametrize("body", [{"answer": ""}, {"answer": "x" * 101}, {}])
def test_guess_validates_the_body(client: TestClient, controller: Mock, body: dict) -> None:
    """An empty or over-long answer is a 422 before the controller."""
    # Prepare
    controller.guess = AsyncMock()

    # Act
    response = client.post(f"{BASE_URL}/guess", json=body)

    # Assert
    assert response.status_code == 422
    controller.guess.assert_not_awaited()


# ========== Rate limiting ==========


class _HeaderAuthenticator:
    """A stand-in for get_current_user: the user named by the header, recorded on the
    request exactly as the real dependency records it."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


@pytest.fixture(name="per_user_client")
def get_per_user_client(test_app: FastAPI):
    users = {name: _mock_user(name) for name in ("first", "second")}
    controller = Mock(spec=DailyWordController)
    controller.guess = AsyncMock(
        return_value=DailyWordGuessResponse(correct=False, state=_state(status=DailyWordStatus.PLAYING))
    )
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_daily_word_controller] = lambda: controller
    limiter.reset()
    yield TestClient(test_app)
    limiter.reset()
    test_app.dependency_overrides.clear()


def test_guesses_are_limited_per_user_with_the_standard_envelope(per_user_client: TestClient) -> None:
    """The 31st guess in a minute is a translatable 429; another player on the same connection is unaffected."""
    # Prepare
    for _ in range(30):
        response = per_user_client.post(f"{BASE_URL}/guess", json={"answer": "Badr"}, headers={"X-Test-User": "first"})
        assert response.status_code == 200

    # Act
    limited = per_user_client.post(f"{BASE_URL}/guess", json={"answer": "Badr"}, headers={"X-Test-User": "first"})
    other = per_user_client.post(f"{BASE_URL}/guess", json={"answer": "Badr"}, headers={"X-Test-User": "second"})

    # Assert
    assert limited.status_code == 429
    data = limited.json()
    assert (data["error"], data["error_key"]) == ("RateLimitExceededError", "errors.api.rateLimitExceeded")
    assert data["details"]["limit"] == "30 per 1 minute"
    assert other.status_code == 200


# ========== The real stack ==========

SECRET_WORD = {
    "word_en": "Qalamzar",
    "word_ar": "قلمزار",
    "word_fr": "Qalamzare",
    "accepted_answers": {"en": ["Qalamzar", "Kalamzar"], "ar": ["قلم زار"], "fr": ["Kalamzare"]},
}
SECRET_EXPLANATION = {"en": "explanation-en-secret", "fr": "explication-fr-secrete", "ar": "شرح سري"}
RUNGS = {str(rung): {"en": f"rung{rung}-en", "fr": f"rung{rung}-fr", "ar": f"درجة{rung}"} for rung in range(1, 7)}
ANSWER_STRINGS = [
    SECRET_WORD["word_en"],
    SECRET_WORD["word_ar"],
    SECRET_WORD["word_fr"],
    *(variant for variants in SECRET_WORD["accepted_answers"].values() for variant in variants),
    *SECRET_EXPLANATION.values(),
]
LANGS = ("en", "fr", "ar")


def _rungs_after(revealed: int) -> list[str]:
    """Every language's text of the rungs past ``revealed``."""
    return [text for rung in range(revealed + 1, 7) for text in RUNGS[str(rung)].values()]


def _assert_hides(response: httpx.Response, forbidden: list[str]) -> None:
    """None of ``forbidden`` is anywhere in the body, in any case."""
    payload = json.dumps(response.json(), ensure_ascii=False).casefold()
    raw = response.text.casefold()
    leaked = [text for text in forbidden if text.casefold() in payload or text.casefold() in raw]
    assert leaked == [], f"{response.request.method} {response.request.url} leaked {leaked}"


class _Stack:
    """An async client on the real app, with the test database and real JWTs."""

    def __init__(self, client: httpx.AsyncClient, auth: AuthController):
        self.client = client
        self.auth = auth

    def headers(self, user: User | None) -> dict[str, str]:
        if user is None:
            return {}
        return {"Authorization": f"Bearer {self.auth.create_access_token(str(user.id), user.email_address)}"}

    async def get(self, user: User | None, lang: str = "en") -> httpx.Response:
        return await self.client.get(BASE_URL, params={"lang": lang}, headers=self.headers(user))

    async def post(self, user: User, path: str, *, lang: str = "en", body: dict | None = None, **params):
        return await self.client.post(
            f"{BASE_URL}{path}", params={"lang": lang, **params}, json=body, headers=self.headers(user)
        )


@pytest_asyncio.fixture(name="stack")
async def get_stack(test_app: FastAPI, session: AsyncSession, test_settings: Settings) -> AsyncGenerator[_Stack]:
    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield _Stack(client, AuthController(session, test_settings))
    limiter.reset()
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture(name="secret_word")
async def get_secret_word(create_quiz_word, session: AsyncSession):
    word = await create_quiz_word(**SECRET_WORD, category="Places", hints=RUNGS)
    word.explanation = SECRET_EXPLANATION
    session.add(word)
    await session.commit()
    return word


@pytest.mark.usefixtures("secret_word")
async def test_no_payload_carries_the_word_before_the_caller_finishes(stack: _Stack, create_user) -> None:
    """Every endpoint's raw JSON, in every language, before a finish: no spelling, no
    accepted answer, no explanation, no rung past the revealed ones — errors included,
    and other players finishing changes nothing. Then the finish does reveal it, which
    proves the check can see a leak."""
    # Prepare
    seeker = await create_user(username="seeker", email="seeker@test.com")
    quitter = await create_user(username="quitter", email="quitter@test.com")
    hidden_at_start = ANSWER_STRINGS + _rungs_after(1)

    # Act / Assert — looking, anonymous or signed in
    for lang in LANGS:
        _assert_hides(await stack.get(None, lang), hidden_at_start)
        _assert_hides(await stack.get(seeker, lang), hidden_at_start)

    # Refused moves while nothing is finished
    refused_keep = await stack.post(seeker, "/keep")
    assert refused_keep.status_code == 409
    _assert_hides(refused_keep, hidden_at_start)
    wrong_day = await stack.post(seeker, "/guess", body={"answer": "Qalamzar"}, day="2026-11-09")
    assert wrong_day.status_code == 409
    _assert_hides(wrong_day, hidden_at_start)

    # A wrong guess (it opens rung 2, as a hint would), then the ladder rung by rung, in each language
    wrong = await stack.post(seeker, "/guess", body={"answer": "Hudhud"}, lang="ar")
    assert (wrong.status_code, wrong.json()["correct"]) == (200, False)
    assert wrong.json()["state"]["hints_revealed"] == 2
    _assert_hides(wrong, ANSWER_STRINGS + _rungs_after(2))
    for revealed in range(3, 7):
        response = await stack.post(seeker, "/hint", lang=LANGS[revealed % 3])
        assert response.status_code == 200
        assert response.json()["hints_revealed"] == revealed
        _assert_hides(response, ANSWER_STRINGS + _rungs_after(revealed))
    no_more = await stack.post(seeker, "/hint")
    assert no_more.status_code == 409
    _assert_hides(no_more, ANSWER_STRINGS)

    # Someone else finishing reveals nothing to those who have not
    gave_up = await stack.post(quitter, "/give-up")
    assert gave_up.json()["answer"]["word_display"] == "Qalamzar"
    for lang in LANGS:
        _assert_hides(await stack.get(seeker, lang), ANSWER_STRINGS)
        _assert_hides(await stack.get(None, lang), hidden_at_start)

    # The caller's own finish reveals it
    solved = await stack.post(seeker, "/guess", body={"answer": "قلم زار"}, lang="fr")
    assert solved.json()["correct"] is True
    answer = solved.json()["state"]["answer"]
    assert (answer["word_display"], answer["word_ar"], answer["explanation"]) == (
        "Qalamzare",
        "قلمزار",
        "explication-fr-secrete",
    )


@pytest.mark.usefixtures("secret_word")
async def test_the_real_stack_serves_anonymous_and_signed_in_callers(stack: _Stack, create_user) -> None:
    """No token: the public view. A valid token: the player's own. A bad token: 401, never anonymous."""
    # Prepare
    seeker = await create_user(username="seeker", email="seeker@test.com")

    # Act
    anonymous = await stack.get(None, "ar")
    signed_in = await stack.get(seeker, "en")
    bad_token = await stack.client.get(BASE_URL, headers={"Authorization": "Bearer not-a-token"})

    # Assert
    assert anonymous.status_code == 200
    data = anonymous.json()
    assert (data["number"], data["category"], data["hints"], data["status"]) == (13, "places", ["درجة1"], "not_started")
    assert (data["streak"], data["best_streak"], data["answer"]) == (None, None, None)
    assert signed_in.json()["streak"] == 0
    assert bad_token.status_code == 401


@pytest.mark.usefixtures("secret_word")
async def test_the_real_stack_keeps_a_finished_word(stack: _Stack, create_user) -> None:
    """Give up, keep: the Kunnash entry is a daily_word one, and the state then says kept."""
    # Prepare
    seeker = await create_user(username="seeker", email="seeker@test.com")
    await stack.post(seeker, "/give-up")

    # Act
    kept = await stack.post(seeker, "/keep", lang="fr")
    again = await stack.post(seeker, "/keep", day=(TODAY - timedelta(days=0)).isoformat())

    # Assert
    assert kept.status_code == 200
    assert (kept.json()["added"], again.json()["already_kept"]) == (1, 1)
    entry = kept.json()["entries"][0]
    assert (entry["game_type"], entry["source_game_id"], entry["word_display"]) == ("daily_word", None, "Qalamzare")
    state = (await stack.get(seeker)).json()
    assert (state["answer"]["kept"], state["answer"]["entry_id"]) == (True, entry["id"])
