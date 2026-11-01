"""BDP-03 / SEC F08: a timer-expired call that changes nothing broadcasts nothing.

Every page fires ``POST /{game}/games/{id}/timer-expired`` from its own clock, and the
four routes awaited ``notify_game_changed`` whatever the answer. So at each round
boundary a table of N players produced N calls, one of which did the work, and N
broadcasts of ``game_updated`` (+ ``room_state``) — N² pushes and as many refetches
(storm.py: 10 clients, 100 ``game_updated``, 100 state GETs for one change).

These run the real routes, controllers and test database, one session per request as
in production; the Socket.IO server is the only fake, and every emit is recorded so
the tests can count what each client of the table would have received.
"""

import asyncio
from collections import Counter
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import Game, User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.undercover import StartNextRoundResponse
from majlisna.dependencies import get_current_user, get_engine, get_undercover_game_controller

# A timer that has plainly not run out, and one that plainly has (both well clear of
# TIMER_EXPIRATION_TOLERANCE_SECONDS).
TIMED_PHASE_SECONDS = 30
EXPIRED_BY = timedelta(seconds=TIMED_PHASE_SECONDS + 30)


class _HeaderAuthenticator:
    """A stand-in for get_current_user: the user named by the header, recorded on the
    request exactly as the real dependency records it (the rate-limit key reads it)."""

    def __init__(self, users: dict[str, User]):
        self.users = users

    def __call__(self, request: Request) -> User:
        user = self.users[request.headers["X-Test-User"]]
        request.state.user_id = str(user.id)
        return user


@dataclass
class Table:
    """One started game: who sits at it and what the broadcasts reached."""

    game: str
    game_id: str
    room_id: str
    user_ids: list[str]
    emits: AsyncMock = field(repr=False)

    def received(self, event: str) -> list[int]:
        """How many ``event`` pushes each player received.

        Every player's socket is in ``room:{room_id}`` and its own
        ``member:{room_id}:{user_id}`` (joined at connect; the room state is addressed to
        the latter, review R2) and in ``game:{game_id}`` (join_game). One emit addressed
        to several rooms reaches a client once (python-socketio merges the recipients),
        which is exactly what notify_game_changed relies on.
        """
        counts = []
        for user_id in self.user_ids:
            rooms = {f"game:{self.game_id}", f"room:{self.room_id}", f"member:{self.room_id}:{user_id}"}
            received = 0
            for call in self.emits.await_args_list:
                if call.args[0] != event:
                    continue
                to = call.kwargs.get("to")
                targets = {to} if isinstance(to, str) else set(to or [])
                if targets & rooms:
                    received += 1
            counts.append(received)
        return counts


@pytest_asyncio.fixture(name="http")
async def get_http(test_app: FastAPI, engine: AsyncEngine) -> AsyncGenerator[tuple[httpx.AsyncClient, dict]]:
    """The real app on the test database, a fresh session per request (as get_session
    gives in production, so concurrent calls really are concurrent transactions)."""
    users: dict[str, User] = {}

    async def _test_engine() -> AsyncEngine:
        return engine

    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator(users)
    test_app.dependency_overrides[get_engine] = _test_engine
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client, users
    limiter.reset()
    test_app.dependency_overrides.clear()


@pytest.fixture(name="emits")
def get_emits(engine: AsyncEngine):
    """Record every Socket.IO emit; the notify lookups read the test database.

    ``fetch_room_state`` reads it too: the room state is addressed to the members it lists
    (``notify.member_channel``, review R2), so what it carries decides who it reaches.
    """
    with (
        patch("majlisna.api.ws.notify.sio") as sio,
        patch("majlisna.api.ws.notify.get_engine", new=AsyncMock(return_value=engine)),
        patch("majlisna.api.ws.state.get_engine", new=AsyncMock(return_value=engine)),
    ):
        sio.emit = AsyncMock()
        yield sio.emit


async def _reload(session: AsyncSession, game_id: str) -> Game:
    statement = select(Game).where(Game.id == UUID(game_id)).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


def _set_undercover_clock(state: dict, started_at: datetime) -> None:
    state["timer_config"] = {"description_seconds": TIMED_PHASE_SECONDS, "voting_seconds": TIMED_PHASE_SECONDS}
    state["timer_started_at"] = started_at.isoformat()


def _set_codenames_clock(state: dict, started_at: datetime) -> None:
    state["timer_config"] = {"clue_seconds": TIMED_PHASE_SECONDS, "guess_seconds": TIMED_PHASE_SECONDS}
    state["timer_started_at"] = started_at.isoformat()


def _set_quiz_clock(state: dict, started_at: datetime) -> None:
    state["turn_duration_seconds"] = TIMED_PHASE_SECONDS
    state["round_started_at"] = started_at.isoformat()


GAMES: dict[str, dict[str, Any]] = {
    "undercover": {
        "setup": "setup_undercover_game",
        "players": 3,
        "controller": UndercoverGameController,
        "set_clock": _set_undercover_clock,
        "acted": "skip_to_voting",
        "phase": lambda state: state["turns"][-1]["phase"],
        "phase_after": "voting",
    },
    "codenames": {
        "setup": "setup_codenames_game",
        "players": 4,
        "controller": CodenamesGameController,
        "set_clock": _set_codenames_clock,
        "acted": "auto_end_turn",
        "phase": lambda state: state["current_team"],
        "phase_after": None,  # the other team: see _expected_phase_after
    },
    "wordquiz": {
        "setup": "setup_wordquiz_game",
        "players": 2,
        "controller": WordQuizGameController,
        "set_clock": _set_quiz_clock,
        "acted": "results",
        "phase": lambda state: state["round_phase"],
        "phase_after": "results",
    },
    "mcqquiz": {
        "setup": "setup_mcqquiz_game",
        "players": 2,
        "controller": McqQuizGameController,
        "set_clock": _set_quiz_clock,
        "acted": "results",
        "phase": lambda state: state["round_phase"],
        "phase_after": "results",
    },
}


@pytest_asyncio.fixture(name="start_table")
async def get_start_table(
    session: AsyncSession,
    http,
    emits,
    setup_undercover_game,
    setup_codenames_game,
    setup_wordquiz_game,
    setup_mcqquiz_game,
) -> Callable:
    """Factory: start a real game of ``game`` and set its clock ``started_ago`` back."""
    _, users = http
    setups = {
        "setup_undercover_game": setup_undercover_game,
        "setup_codenames_game": setup_codenames_game,
        "setup_wordquiz_game": setup_wordquiz_game,
        "setup_mcqquiz_game": setup_mcqquiz_game,
    }

    async def _start(game: str, *, started_ago: timedelta, num_players: int | None = None) -> Table:
        spec = GAMES[game]
        setup = await setups[spec["setup"]](num_players=num_players or spec["players"])
        players: list[User] = setup["users"]
        for index, player in enumerate(players):
            users[f"p{index}"] = player
        started = await spec["controller"](session).create_and_start(setup["room"].id, players[0].id)
        game_row = await _reload(session, started.game_id)
        state = game_row.live_state
        spec["set_clock"](state, datetime.now(UTC) - started_ago)
        game_row.live_state = state
        flag_modified(game_row, "live_state")
        session.add(game_row)
        await session.commit()
        return Table(
            game=game,
            game_id=started.game_id,
            room_id=str(setup["room"].id),
            user_ids=[str(p.id) for p in players],
            emits=emits,
        )

    return _start


def _expected_phase_after(game: str, before: Any) -> Any:
    if game == "codenames":
        return "blue" if before == "red" else "red"
    return GAMES[game]["phase_after"]


@pytest.mark.parametrize("game", list(GAMES))
async def test_a_call_before_the_deadline_broadcasts_nothing(game: str, http, start_table, session) -> None:
    """The server's clock says not yet: nothing changed, so no client is told to refetch."""
    # Prepare
    client, _ = http
    table: Table = await start_table(game, started_ago=timedelta(seconds=0))
    phase_before = GAMES[game]["phase"]((await _reload(session, table.game_id)).live_state)

    # Act
    response = await client.post(f"/api/v1/{game}/games/{table.game_id}/timer-expired", headers={"X-Test-User": "p1"})

    # Assert
    assert response.status_code == 200
    assert response.json()["action"] == "timer_not_expired"
    assert table.received("game_updated") == [0] * len(table.user_ids)
    assert table.received("room_state") == [0] * len(table.user_ids)
    assert GAMES[game]["phase"]((await _reload(session, table.game_id)).live_state) == phase_before


@pytest.mark.parametrize("game", list(GAMES))
async def test_a_call_after_the_deadline_broadcasts_once(game: str, http, start_table, session) -> None:
    """The call that does the work still reaches the whole table, exactly once."""
    # Prepare
    client, _ = http
    table: Table = await start_table(game, started_ago=EXPIRED_BY)
    phase_before = GAMES[game]["phase"]((await _reload(session, table.game_id)).live_state)

    # Act
    response = await client.post(f"/api/v1/{game}/games/{table.game_id}/timer-expired", headers={"X-Test-User": "p1"})

    # Assert
    assert response.status_code == 200
    assert response.json()["action"] == GAMES[game]["acted"]
    assert table.received("game_updated") == [1] * len(table.user_ids)
    assert table.received("room_state") == [1] * len(table.user_ids)
    phase_after = GAMES[game]["phase"]((await _reload(session, table.game_id)).live_state)
    assert phase_after == _expected_phase_after(game, phase_before)


@pytest.mark.parametrize("game", ["mcqquiz", "wordquiz"])
async def test_ten_concurrent_calls_at_the_deadline_broadcast_once(game: str, http, start_table, session) -> None:
    """Port of storm.py: ten players' clocks run out together and all ten report it.

    One call moves the round to its results; the nine others find it already there
    (``not_playing``). Each client used to receive ten ``game_updated`` — and refetch
    ten times — for that one change; it now receives one.
    """
    # Prepare
    client, _ = http
    table: Table = await start_table(game, started_ago=EXPIRED_BY, num_players=10)
    url = f"/api/v1/{game}/games/{table.game_id}/timer-expired"

    # Act
    responses = await asyncio.gather(
        *(client.post(url, headers={"X-Test-User": f"p{index}"}) for index in range(len(table.user_ids)))
    )

    # Assert
    assert [r.status_code for r in responses] == [200] * 10
    assert Counter(r.json()["action"] for r in responses) == {"results": 1, "not_playing": 9}
    assert table.received("game_updated") == [1] * 10
    assert table.received("room_state") == [1] * 10
    assert (await _reload(session, table.game_id)).live_state["round_phase"] == "results"


async def test_a_paused_game_broadcasts_nothing(http, start_table, session) -> None:
    """During the prayer pause every clock answers ``paused``: no change, no broadcast."""
    # Prepare
    client, users = http
    table: Table = await start_table("mcqquiz", started_ago=EXPIRED_BY)
    await McqQuizGameController(session).pause_game(UUID(table.game_id), users["p0"].id)
    table.emits.reset_mock()

    # Act
    response = await client.post(f"/api/v1/mcqquiz/games/{table.game_id}/timer-expired", headers={"X-Test-User": "p1"})

    # Assert
    assert response.json()["action"] == "paused"
    assert table.received("game_updated") == [0] * len(table.user_ids)
    assert (await _reload(session, table.game_id)).live_state["round_phase"] == "playing"


async def test_an_undercover_round_already_resolved_broadcasts_nothing(http, start_table, session) -> None:
    """Between an elimination and the next round the vote timer reads as expired for
    the whole gap; the calls in it change nothing and must not broadcast."""
    # Prepare
    client, _ = http
    table: Table = await start_table("undercover", started_ago=EXPIRED_BY)
    game_row = await _reload(session, table.game_id)
    state = game_row.live_state
    state["turns"][-1]["phase"] = "voting"
    state["turns"][-1]["resolved"] = True
    game_row.live_state = state
    flag_modified(game_row, "live_state")
    session.add(game_row)
    await session.commit()
    alive_before = [p["user_id"] for p in state["players"] if p["is_alive"]]

    # Act
    response = await client.post(
        f"/api/v1/undercover/games/{table.game_id}/timer-expired", headers={"X-Test-User": "p1"}
    )

    # Assert
    assert response.json()["action"] == "round_already_resolved"
    assert table.received("game_updated") == [0] * len(table.user_ids)
    reloaded = (await _reload(session, table.game_id)).live_state
    assert [p["user_id"] for p in reloaded["players"] if p["is_alive"]] == alive_before


# ─── Undercover next round: both outcomes are a visible change ────────────────


@pytest_asyncio.fixture(name="next_round_stack")
async def get_next_round_stack(test_app: FastAPI) -> AsyncGenerator[tuple[httpx.AsyncClient, Mock, AsyncMock]]:
    """The real route; the controller and the notification are stood in for."""
    user = User(id=uuid4(), username="ready", email_address="ready@test.com")
    controller = Mock(spec=UndercoverGameController)
    test_app.dependency_overrides[get_current_user] = _HeaderAuthenticator({"ready": user})
    test_app.dependency_overrides[get_undercover_game_controller] = lambda: controller
    limiter.reset()
    with patch("majlisna.api.routes.undercover.notify_game_changed", new_callable=AsyncMock) as notify:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
            yield client, controller, notify
    limiter.reset()
    test_app.dependency_overrides.clear()


@pytest.mark.parametrize("advanced", [False, True])
async def test_an_undercover_next_round_call_notifies_once_either_way(next_round_stack, advanced: bool) -> None:
    """A ready mark (``advanced`` False) changes the ready count the table shows; an
    opened round changes everything. Both are broadcast, once."""
    # Prepare
    client, controller, notify = next_round_stack
    game_id = uuid4()
    controller.start_next_round = AsyncMock(
        return_value=StartNextRoundResponse(game_id=str(game_id), advanced=advanced)
    )

    # Act
    response = await client.post(
        f"/api/v1/undercover/games/{game_id}/next-round",
        json={"room_id": str(uuid4())},
        headers={"X-Test-User": "ready"},
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["advanced"] is advanced
    notify.assert_awaited_once_with(str(game_id))
