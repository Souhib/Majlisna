"""Route-level tests for the notebook (Kunnash) endpoints (/api/v1/notebook)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from majlisna.api.constants import (
    NOTEBOOK_CURSOR_MAX_LENGTH,
    NOTEBOOK_PAGE_DEFAULT_LIMIT,
    NOTEBOOK_PAGE_MAX_LIMIT,
)
from majlisna.api.controllers.notebook import NotebookController
from majlisna.api.models.notebook import NotebookGameType
from majlisna.api.models.table import User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.error import (
    GameNotFoundError,
    GameStillInProgressError,
    InvalidNotebookCursorError,
    NotAGameParticipantError,
    NotebookEntryNotFoundError,
    NotebookGameTypeNotSupportedError,
    TermNotInGameError,
)
from majlisna.api.schemas.notebook import (
    KeepWordRequest,
    NotebookEntryView,
    NotebookGameWord,
    NotebookGameWords,
    NotebookKeepResponse,
    NotebookPage,
)
from majlisna.dependencies import get_current_user, get_notebook_controller

BASE_URL = "/api/v1/notebook"


def _mock_user() -> User:
    return User(
        id=uuid4(),
        username="keeper",
        email_address="keeper@test.com",
        country="FRA",
        password="securepassword",
    )


def _entry_view(word: str = "Sabr") -> NotebookEntryView:
    return NotebookEntryView(
        id=uuid4(),
        word=word,
        word_display=word,
        game_type=NotebookGameType.UNDERCOVER,
        word_ar="صبر",
        word_ar_vocalized="صَبْر",
        hint="Patience",
        source_game_id=uuid4(),
        kept_at=datetime.now(UTC),
    )


@pytest.fixture(name="user")
def get_user() -> User:
    return _mock_user()


@pytest.fixture(name="controller")
def get_controller(test_app: FastAPI, user: User):
    """A mocked NotebookController behind an authenticated user."""
    controller = Mock(spec=NotebookController)
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_notebook_controller] = lambda: controller
    yield controller
    test_app.dependency_overrides.clear()


# ========== Authentication ==========


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", f"{BASE_URL}/games/{uuid4()}", None),
        ("post", f"{BASE_URL}/games/{uuid4()}/keep", None),
        ("post", f"{BASE_URL}/entries", {"game_id": str(uuid4()), "word": "Sabr"}),
        ("get", BASE_URL, None),
        ("delete", f"{BASE_URL}/entries/{uuid4()}", None),
    ],
)
def test_notebook_endpoints_require_authentication(
    test_app: FastAPI, client: TestClient, method: str, path: str, body: dict | None
) -> None:
    """Every notebook endpoint answers 401 without a token, and never reaches the controller."""
    # Arrange
    controller = Mock(spec=NotebookController)
    test_app.dependency_overrides[get_notebook_controller] = lambda: controller

    try:
        # Act
        response = client.request(method.upper(), path, json=body)

        # Assert
        assert response.status_code == 401
        assert controller.mock_calls == []
    finally:
        test_app.dependency_overrides.clear()


# ========== GET /notebook/games/{game_id} ==========


def test_get_game_words_success(client: TestClient, controller: Mock, user: User) -> None:
    """The colophon list: every word, resolved, with what the caller has already kept."""
    # Arrange
    game_id = uuid4()
    entry_id = uuid4()
    controller.get_game_words = AsyncMock(
        return_value=NotebookGameWords(
            game_id=game_id,
            game_type=NotebookGameType.WORD_QUIZ,
            words=[
                NotebookGameWord(
                    word="Musa", word_display="Moïse", word_ar="موسى", hint="Indice 6", kept=True, entry_id=entry_id
                ),
                NotebookGameWord(word="Ibrahim", word_display="Abraham", word_ar="إبراهيم", kept=False),
            ],
        )
    )

    # Act
    response = client.get(f"{BASE_URL}/games/{game_id}", params={"lang": "fr"})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert (data["game_id"], data["game_type"]) == (str(game_id), "word_quiz")
    assert [(w["word"], w["word_display"], w["kept"], w["entry_id"]) for w in data["words"]] == [
        ("Musa", "Moïse", True, str(entry_id)),
        ("Ibrahim", "Abraham", False, None),
    ]
    assert data["words"][1]["word_ar_vocalized"] is None
    controller.get_game_words.assert_awaited_once_with(game_id, user.id, lang="fr")


@pytest.mark.parametrize(
    ("error", "status_code", "error_key"),
    [
        (GameStillInProgressError(game_id="g"), 403, "errors.api.gameStillInProgress"),
        (NotAGameParticipantError(game_id="g", user_id="u"), 403, "errors.api.notAGameParticipant"),
        (GameNotFoundError(game_id="g"), 404, "errors.api.gameNotFound"),
        (
            NotebookGameTypeNotSupportedError(game_id="g", game_type="mcq_quiz"),
            400,
            "errors.api.notebookGameTypeNotSupported",
        ),
    ],
)
def test_get_game_words_gates(
    client: TestClient, controller: Mock, error: Exception, status_code: int, error_key: str
) -> None:
    """Same gates as keeping: a running game or a stranger reveals nothing."""
    # Arrange
    controller.get_game_words = AsyncMock(side_effect=error)

    # Act
    response = client.get(f"{BASE_URL}/games/{uuid4()}")

    # Assert
    assert response.status_code == status_code
    assert response.json()["error_key"] == error_key


# ========== POST /notebook/games/{game_id}/keep ==========


def test_keep_game_words_success(client: TestClient, controller: Mock, user: User) -> None:
    """Keeping a game's words returns the counts and the resolved entries."""
    # Arrange
    game_id = uuid4()
    entries = [_entry_view("Sabr"), _entry_view("Shukr")]
    controller.keep_game_words = AsyncMock(return_value=NotebookKeepResponse(added=1, already_kept=1, entries=entries))

    # Act
    response = client.post(f"{BASE_URL}/games/{game_id}/keep", params={"lang": "fr"})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert (data["added"], data["already_kept"]) == (1, 1)
    assert [entry["word"] for entry in data["entries"]] == ["Sabr", "Shukr"]
    first = data["entries"][0]
    assert (first["word_ar"], first["word_ar_vocalized"], first["game_type"]) == ("صبر", "صَبْر", "undercover")
    assert first["word_display"] == "Sabr"
    assert first["kept_at"].endswith("Z") or first["kept_at"].endswith("+00:00")
    controller.keep_game_words.assert_awaited_once_with(game_id, user.id, lang="fr")


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (GameStillInProgressError(game_id="g"), 403),
        (NotAGameParticipantError(game_id="g", user_id="u"), 403),
        (GameNotFoundError(game_id="g"), 404),
        (NotebookGameTypeNotSupportedError(game_id="g", game_type="mcq_quiz"), 400),
    ],
)
def test_keep_game_words_gates(client: TestClient, controller: Mock, error: Exception, status_code: int) -> None:
    """The controller's gates surface as their status codes."""
    # Arrange
    controller.keep_game_words = AsyncMock(side_effect=error)

    # Act
    response = client.post(f"{BASE_URL}/games/{uuid4()}/keep")

    # Assert
    assert response.status_code == status_code


def test_keep_game_words_invalid_game_id(client: TestClient, controller: Mock) -> None:
    """A malformed game id is rejected before the controller."""
    # Arrange
    controller.keep_game_words = AsyncMock()

    # Act
    response = client.post(f"{BASE_URL}/games/not-a-uuid/keep")

    # Assert
    assert response.status_code == 422
    controller.keep_game_words.assert_not_awaited()


# ========== POST /notebook/entries ==========


def test_keep_word_success(client: TestClient, controller: Mock, user: User) -> None:
    """Keeping one word passes the validated body through."""
    # Arrange
    game_id = uuid4()
    controller.keep_word = AsyncMock(
        return_value=NotebookKeepResponse(added=1, already_kept=0, entries=[_entry_view("Uhud")])
    )

    # Act
    response = client.post(f"{BASE_URL}/entries", json={"game_id": str(game_id), "word": "Uhud"}, params={"lang": "ar"})

    # Assert
    assert response.status_code == 200
    assert [entry["word"] for entry in response.json()["entries"]] == ["Uhud"]
    controller.keep_word.assert_awaited_once_with(user.id, KeepWordRequest(game_id=game_id, word="Uhud"), lang="ar")


@pytest.mark.parametrize(
    "body",
    [
        {"game_id": str(uuid4()), "word": ""},
        {"game_id": str(uuid4()), "word": "x" * 101},
        {"game_id": str(uuid4())},
        {"word": "Sabr"},
        {"game_id": str(uuid4()), "term": "Sabr"},
        {"game_id": str(uuid4()), "word": "Sabr", "user_id": str(uuid4())},
    ],
)
def test_keep_word_rejects_invalid_bodies(client: TestClient, controller: Mock, body: dict) -> None:
    """Empty, over-long, missing or extra fields are 422 (BaseModel is extra="forbid")."""
    # Arrange
    controller.keep_word = AsyncMock()

    # Act
    response = client.post(f"{BASE_URL}/entries", json=body)

    # Assert
    assert response.status_code == 422
    controller.keep_word.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (TermNotInGameError(game_id="g", term="Hajj"), 404),
        (GameStillInProgressError(game_id="g"), 403),
        (NotAGameParticipantError(game_id="g", user_id="u"), 403),
        (NotebookGameTypeNotSupportedError(game_id="g", game_type="mcq_quiz"), 400),
    ],
)
def test_keep_word_gates(client: TestClient, controller: Mock, error: Exception, status_code: int) -> None:
    """A word the game never dealt is 404; the game gates are the same as for keeping a whole game."""
    # Arrange
    controller.keep_word = AsyncMock(side_effect=error)

    # Act
    response = client.post(f"{BASE_URL}/entries", json={"game_id": str(uuid4()), "word": "Hajj"})

    # Assert
    assert response.status_code == status_code


# ========== Rate limiting ==========


@pytest.fixture(name="per_user_client")
def get_per_user_client(test_app: FastAPI):
    """A client whose authenticated user is chosen per request (``X-Test-User``), the way
    the real ``get_current_user`` records it on ``request.state.user_id``; the limiter's
    memory is wiped afterwards so no other test inherits a spent budget."""
    users = {name: _mock_user() for name in ("first", "second")}
    controller = Mock(spec=NotebookController)
    controller.keep_word = AsyncMock(
        return_value=NotebookKeepResponse(added=1, already_kept=0, entries=[_entry_view("Uhud")])
    )
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_notebook_controller] = lambda: controller
    limiter.reset()
    yield TestClient(test_app)
    limiter.reset()
    test_app.dependency_overrides.clear()


class _HeaderAuthenticator:
    """A stand-in for get_current_user: the user named by the header, recorded on the
    request exactly as the real dependency records it."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


def test_keep_limit_is_counted_per_user_and_answers_the_standard_envelope(per_user_client: TestClient) -> None:
    """Several phones on one connection each have their own budget; the 31st keep of
    one player is a 429 the client can translate, and the other player is unaffected."""
    # Arrange
    body = {"game_id": str(uuid4()), "word": "Uhud"}
    for _ in range(30):
        assert (
            per_user_client.post(f"{BASE_URL}/entries", json=body, headers={"X-Test-User": "first"}).status_code == 200
        )

    # Act
    limited = per_user_client.post(f"{BASE_URL}/entries", json=body, headers={"X-Test-User": "first"})
    other = per_user_client.post(f"{BASE_URL}/entries", json=body, headers={"X-Test-User": "second"})

    # Assert
    assert limited.status_code == 429
    data = limited.json()
    assert data["error_key"] == "errors.api.rateLimitExceeded"
    assert data["error"] == "RateLimitExceededError"
    assert data["message"]
    assert data["details"]["limit"] == "30 per 1 minute"
    assert other.status_code == 200


# ========== GET /notebook ==========


def test_list_entries_defaults(client: TestClient, controller: Mock, user: User) -> None:
    """Without parameters: English, the default page size, from the start."""
    # Arrange
    controller.list_entries = AsyncMock(return_value=NotebookPage(entries=[_entry_view()], total=1, next_cursor="abc"))

    # Act
    response = client.get(BASE_URL)

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert (data["total"], data["next_cursor"]) == (1, "abc")
    assert [entry["word"] for entry in data["entries"]] == ["Sabr"]
    controller.list_entries.assert_awaited_once_with(user.id, lang="en", limit=NOTEBOOK_PAGE_DEFAULT_LIMIT, cursor=None)


def test_list_entries_passes_page_and_language(client: TestClient, controller: Mock, user: User) -> None:
    """lang, limit and cursor reach the controller as given; the last page has no next cursor."""
    # Arrange
    controller.list_entries = AsyncMock(return_value=NotebookPage(entries=[], total=30))

    # Act
    response = client.get(BASE_URL, params={"lang": "ar", "limit": 10, "cursor": "opaque"})

    # Assert
    assert response.status_code == 200
    assert response.json()["next_cursor"] is None
    controller.list_entries.assert_awaited_once_with(user.id, lang="ar", limit=10, cursor="opaque")


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": NOTEBOOK_PAGE_MAX_LIMIT + 1},
        {"cursor": ""},
        {"cursor": "x" * (NOTEBOOK_CURSOR_MAX_LENGTH + 1)},
    ],
)
def test_list_entries_bounds(client: TestClient, controller: Mock, params: dict) -> None:
    """The page size and the cursor are bounded (constants), so a client cannot ask for the whole table."""
    # Arrange
    controller.list_entries = AsyncMock()

    # Act
    response = client.get(BASE_URL, params=params)

    # Assert
    assert response.status_code == 422
    controller.list_entries.assert_not_awaited()


def test_list_entries_accepts_the_bounds_themselves(client: TestClient, controller: Mock, user: User) -> None:
    """The maximum page size is valid."""
    # Arrange
    controller.list_entries = AsyncMock(return_value=NotebookPage(entries=[], total=0))

    # Act
    response = client.get(BASE_URL, params={"limit": NOTEBOOK_PAGE_MAX_LIMIT})

    # Assert
    assert response.status_code == 200
    controller.list_entries.assert_awaited_once_with(user.id, lang="en", limit=NOTEBOOK_PAGE_MAX_LIMIT, cursor=None)


def test_list_entries_invalid_cursor(client: TestClient, controller: Mock) -> None:
    """A cursor the server never handed out is a 400 with its own key."""
    # Arrange
    controller.list_entries = AsyncMock(side_effect=InvalidNotebookCursorError(cursor="nope"))

    # Act
    response = client.get(BASE_URL, params={"cursor": "nope"})

    # Assert
    assert response.status_code == 400
    assert response.json()["error_key"] == "errors.api.invalidNotebookCursor"


# ========== DELETE /notebook/entries/{entry_id} ==========


def test_delete_entry_success(client: TestClient, controller: Mock, user: User) -> None:
    """Deleting one's own entry is a 204 with no body."""
    # Arrange
    entry_id = uuid4()
    controller.delete_entry = AsyncMock(return_value=None)

    # Act
    response = client.delete(f"{BASE_URL}/entries/{entry_id}")

    # Assert
    assert response.status_code == 204
    assert response.content == b""
    controller.delete_entry.assert_awaited_once_with(user.id, entry_id)


def test_delete_entry_not_found(client: TestClient, controller: Mock) -> None:
    """A missing entry — or someone else's — is a 404."""
    # Arrange
    controller.delete_entry = AsyncMock(side_effect=NotebookEntryNotFoundError(entry_id="e"))

    # Act
    response = client.delete(f"{BASE_URL}/entries/{uuid4()}")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_key"] == "errors.api.notebookEntryNotFound"
