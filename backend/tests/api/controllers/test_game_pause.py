"""The prayer pause (وقفة الصلاة): pause / resume across all four games.

When the adhan comes mid-game the host pauses it; nothing is lost and no clock runs
until the host resumes. Each test below is parametrised over the four games where the
rule is shared, and written per game where the clock it protects is game-specific
(the Word Quiz hint ladder, the MCQ speed bonus).
"""

import asyncio
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    GRACE_PERIOD_SECONDS,
    PAUSED_GAME_GRACE_PERIOD_SECONDS,
    PRAYER_PAUSE_MAX_SECONDS,
)
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.codenames_helpers import CodenamesRole
from majlisna.api.controllers.disconnect import (
    _handle_codenames_disconnect,
    _remove_expired_users,
    _still_expired,
)
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.game import GamePauseReason, GameStatus
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.common import PauseGameResponse, ResumeGameResponse, TimerExpiredAction
from majlisna.api.schemas.error import (
    BaseError,
    GameAlreadyPausedError,
    GameNotFoundError,
    GameNotPausedError,
    GamePausedError,
    OnlyHostCanPauseError,
    SpectatorCannotPauseError,
)
from majlisna.api.schemas.undercover import SubmitDescriptionResponse

GAME_KINDS = ["undercover", "codenames", "wordquiz", "mcqquiz"]
QUIZ_KINDS = {"wordquiz", "mcqquiz"}
DEFAULT_PLAYERS = {"undercover": 3, "codenames": 4, "wordquiz": 2, "mcqquiz": 2}
CONTROLLER_CLASSES = {
    "undercover": UndercoverGameController,
    "codenames": CodenamesGameController,
    "wordquiz": WordQuizGameController,
    "mcqquiz": McqQuizGameController,
}
# What `timer-expired` answers once the clock has actually run out, per game.
TIMER_ACTIONS = {
    "undercover": "skip_to_voting",
    "codenames": "auto_end_turn",
    "wordquiz": "results",
    "mcqquiz": "results",
}


# ─── Helpers ──────────────────────────────────────────────────


@dataclass
class StartedGame:
    """A running game. Ids only: ORM rows can expire under a rollback."""

    kind: str
    controller: BaseGameController
    game_id: UUID
    room_id: UUID
    host_id: UUID
    player_ids: list[UUID]


class GameStarter:
    """Starts a game of any of the four kinds with the shared conftest factories."""

    def __init__(self, setups: dict, controllers: dict):
        self._setups = setups
        self._controllers = controllers

    async def start(self, kind: str, num_players: int | None = None) -> StartedGame:
        count = num_players or DEFAULT_PLAYERS[kind]
        setup = await (self._setups[kind](num_players=count) if kind in QUIZ_KINDS else self._setups[kind](count))
        controller = self._controllers[kind]
        room_id = setup["room"].id
        player_ids = [user.id for user in setup["users"]]
        result = await controller.create_and_start(room_id, player_ids[0])
        return StartedGame(
            kind=kind,
            controller=controller,
            game_id=UUID(result.game_id),
            room_id=room_id,
            host_id=player_ids[0],
            player_ids=player_ids,
        )


@pytest_asyncio.fixture(name="games")
async def get_games(
    setup_undercover_game,
    setup_codenames_game,
    setup_wordquiz_game,
    setup_mcqquiz_game,
    undercover_game_controller,
    codenames_game_controller,
    wordquiz_game_controller,
    mcqquiz_game_controller,
) -> GameStarter:
    return GameStarter(
        setups={
            "undercover": setup_undercover_game,
            "codenames": setup_codenames_game,
            "wordquiz": setup_wordquiz_game,
            "mcqquiz": setup_mcqquiz_game,
        },
        controllers={
            "undercover": undercover_game_controller,
            "codenames": codenames_game_controller,
            "wordquiz": wordquiz_game_controller,
            "mcqquiz": mcqquiz_game_controller,
        },
    )


async def _reload(session: AsyncSession, game_id: UUID) -> Game:
    """The game as stored, not the instance a controller may still hold in memory."""
    statement = select(Game).where(Game.id == game_id).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


async def _reload_link(session: AsyncSession, room_id: UUID, user_id: UUID) -> RoomUserLink | None:
    statement = (
        select(RoomUserLink)
        .where(RoomUserLink.room_id == room_id)
        .where(RoomUserLink.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return (await session.exec(statement)).first()


async def _save_state(session: AsyncSession, game: Game, state: dict) -> None:
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()


async def _read_state(started: StartedGame, user_id: UUID):
    """The game state as `user_id` would fetch it (board for Codenames)."""
    if isinstance(started.controller, CodenamesGameController):
        return await started.controller.get_board(started.game_id, user_id, update_heartbeat=False)
    return await started.controller.get_state(started.game_id, user_id, update_heartbeat=False)


def _anchor_key(kind: str) -> str:
    return "round_started_at" if kind in QUIZ_KINDS else "timer_started_at"


def _set_round_timer(state: dict, kind: str, seconds: int, started_ago: float) -> None:
    """Give the current turn/round a `seconds` timer that started `started_ago` seconds ago."""
    if kind == "undercover":
        state["timer_config"]["description_seconds"] = seconds
    elif kind == "codenames":
        state["timer_config"]["clue_seconds"] = seconds
    else:
        state["turn_duration_seconds"] = seconds
    state[_anchor_key(kind)] = (datetime.now(UTC) - timedelta(seconds=started_ago)).isoformat()


def _age_anchor(state: dict, kind: str, seconds: float) -> None:
    """Let `seconds` of (unpaused) time pass on the game's clock."""
    key = _anchor_key(kind)
    state[key] = (datetime.fromisoformat(state[key]) - timedelta(seconds=seconds)).isoformat()


async def _backdate_pause(session: AsyncSession, game_id: UUID, seconds: float) -> None:
    """Pretend the game was paused `seconds` ago."""
    game = await _reload(session, game_id)
    state = copy.deepcopy(game.live_state)
    state["paused"]["at"] = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()
    await _save_state(session, game, state)


def _codenames_player(state: dict, role: str) -> UUID:
    """A player of the team to move with the given role."""
    player = next(p for p in state["players"] if p["team"] == state["current_team"] and p["role"] == role)
    return UUID(player["user_id"])


async def _add_spectator(session: AsyncSession, create_user, room_id: UUID, name: str) -> UUID:
    spectator = await create_user(username=name, email=f"{name}@test.com")
    session.add(RoomUserLink(room_id=room_id, user_id=spectator.id, connected=True, is_spectator=True))
    await session.commit()
    return spectator.id


async def _set_owner(session: AsyncSession, room_id: UUID, owner_id: UUID) -> None:
    room = (await session.exec(select(Room).where(Room.id == room_id))).one()
    room.owner_id = owner_id
    session.add(room)
    await session.commit()


async def _disconnect(session: AsyncSession, room_id: UUID, user_id: UUID, seconds_ago: float) -> None:
    """Mark a member disconnected `seconds_ago` (naive local time, like the checker)."""
    link = await _reload_link(session, room_id, user_id)
    assert link is not None
    link.connected = False
    link.disconnected_at = datetime.now() - timedelta(seconds=seconds_ago)
    session.add(link)
    await session.commit()


class Moves:
    """One call per mutation entry point, with arguments that would be legal (or at
    least plausible) right now — so the only thing that can stop it is the pause."""

    @staticmethod
    async def describe(started: StartedGame, state: dict):
        turn = state["turns"][-1]
        describer = UUID(turn["description_order"][turn["current_describer_index"]])
        return await started.controller.submit_description(started.game_id, describer, "Patience")

    @staticmethod
    async def vote(started: StartedGame, state: dict):  # noqa: ARG004
        return await started.controller.submit_vote(started.game_id, started.host_id, started.player_ids[1])

    @staticmethod
    async def mr_white_guess(started: StartedGame, state: dict):  # noqa: ARG004
        return await started.controller.submit_mr_white_guess(started.game_id, started.host_id, "mosque")

    @staticmethod
    async def undercover_next_round(started: StartedGame, state: dict):  # noqa: ARG004
        return await started.controller.start_next_round(started.game_id, started.room_id, started.host_id)

    @staticmethod
    async def clue(started: StartedGame, state: dict):
        spymaster = _codenames_player(state, CodenamesRole.SPYMASTER.value)
        return await started.controller.give_clue(started.game_id, spymaster, "Patience", 1)

    @staticmethod
    async def guess(started: StartedGame, state: dict):
        operative = _codenames_player(state, CodenamesRole.OPERATIVE.value)
        return await started.controller.guess_card(started.game_id, operative, 0)

    @staticmethod
    async def end_turn(started: StartedGame, state: dict):
        operative = _codenames_player(state, CodenamesRole.OPERATIVE.value)
        return await started.controller.end_turn(started.game_id, operative)

    @staticmethod
    async def wordquiz_answer(started: StartedGame, state: dict):
        return await started.controller.submit_answer(
            started.game_id, started.host_id, state["current_word"]["word_en"]
        )

    @staticmethod
    async def mcq_answer(started: StartedGame, state: dict):
        correct_index = state["current_question"]["correct_answer_index"]
        return await started.controller.submit_answer(started.game_id, started.host_id, correct_index)

    @staticmethod
    async def quiz_next_round(started: StartedGame, state: dict):  # noqa: ARG004
        return await started.controller.advance_to_next_round(started.game_id, started.host_id)


async def _make_move(started: StartedGame, state: dict, move: str):
    return await getattr(Moves, move)(started, state)


# ─── Pause ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_host_pauses_the_game_for_the_prayer(games: GameStarter, session: AsyncSession, kind: str):
    """The host's pause is stored in live_state and shown to every player."""
    # Prepare
    started = await games.start(kind)
    before = datetime.now(UTC)

    # Act
    result = await started.controller.pause_game(started.game_id, started.host_id)

    # Assert — the response
    assert isinstance(result, PauseGameResponse)
    assert result.game_id == str(started.game_id)
    assert result.paused.by_user_id == str(started.host_id)
    assert result.paused.by_username
    assert result.paused.reason == GamePauseReason.SALAH
    assert result.paused.since.tzinfo is not None
    assert before <= result.paused.since <= datetime.now(UTC)

    # Assert — the database
    game = await _reload(session, started.game_id)
    record = game.live_state["paused"]
    assert record["by"] == str(started.host_id)
    assert record["reason"] == "salah"
    assert datetime.fromisoformat(record["at"]) == result.paused.since
    assert game.game_status == GameStatus.IN_PROGRESS

    # Assert — every player's state carries it
    view = await _read_state(started, started.player_ids[1])
    assert view.paused is not None
    assert view.paused.by_user_id == str(started.host_id)
    assert view.paused.since == result.paused.since


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_a_running_game_reads_as_not_paused(games: GameStarter, kind: str):
    """`paused` is null on a game nobody paused."""
    # Prepare
    started = await games.start(kind)

    # Act
    view = await _read_state(started, started.host_id)

    # Assert
    assert view.paused is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_only_the_host_can_pause(games: GameStarter, session: AsyncSession, kind: str):
    """A player who is not the host gets 403 and the game keeps running."""
    # Prepare
    started = await games.start(kind)

    # Act / Assert
    with pytest.raises(OnlyHostCanPauseError) as exc_info:
        await started.controller.pause_game(started.game_id, started.player_ids[1])
    assert exc_info.value.status_code == 403

    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_a_spectator_cannot_pause(games: GameStarter, session: AsyncSession, create_user, kind: str):
    """A spectator is rejected — even one who became the host."""
    # Prepare
    started = await games.start(kind)
    spectator_id = await _add_spectator(session, create_user, started.room_id, f"watcher_{kind}")

    # Act / Assert — a plain spectator is not the host
    with pytest.raises(OnlyHostCanPauseError):
        await started.controller.pause_game(started.game_id, spectator_id)

    # Act / Assert — a spectator holding the host role is still only watching
    await _set_owner(session, started.room_id, spectator_id)
    with pytest.raises(SpectatorCannotPauseError) as exc_info:
        await started.controller.pause_game(started.game_id, spectator_id)
    assert exc_info.value.status_code == 403

    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_pausing_a_paused_game_is_a_conflict(games: GameStarter, session: AsyncSession, kind: str):
    """A second pause answers 409 and leaves the first one untouched."""
    # Prepare
    started = await games.start(kind)
    first = await started.controller.pause_game(started.game_id, started.host_id)

    # Act / Assert
    with pytest.raises(GameAlreadyPausedError) as exc_info:
        await started.controller.pause_game(started.game_id, started.host_id)
    assert exc_info.value.status_code == 409

    game = await _reload(session, started.game_id)
    assert datetime.fromisoformat(game.live_state["paused"]["at"]) == first.paused.since


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_a_game_that_is_over_cannot_be_paused(games: GameStarter, session: AsyncSession, kind: str):
    """Only a game IN_PROGRESS can be paused."""
    # Prepare
    started = await games.start(kind)
    game = await _reload(session, started.game_id)
    game.game_status = GameStatus.FINISHED
    session.add(game)
    await session.commit()

    # Act / Assert
    with pytest.raises(BaseError) as exc_info:
        await started.controller.pause_game(started.game_id, started.host_id)
    assert exc_info.value.status_code == 400
    # A named error, so French and Arabic players get "already over" in their language
    assert exc_info.value.error_key == "errors.api.gameAlreadyOver"

    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state


# ─── Resume ───────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_host_resumes_the_game(games: GameStarter, session: AsyncSession, kind: str):
    """Resuming clears the pause and reports how long it lasted."""
    # Prepare
    started = await games.start(kind)
    await started.controller.pause_game(started.game_id, started.host_id)
    await _backdate_pause(session, started.game_id, 90)

    # Act
    result = await started.controller.resume_game(started.game_id, started.host_id)

    # Assert
    assert isinstance(result, ResumeGameResponse)
    assert result.game_id == str(started.game_id)
    assert 89 <= result.paused_seconds <= 92
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state
    assert game.game_status == GameStatus.IN_PROGRESS
    view = await _read_state(started, started.player_ids[1])
    assert view.paused is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_resuming_a_running_game_is_a_conflict(games: GameStarter, session: AsyncSession, kind: str):
    """Resume without a pause answers 409 and moves no clock."""
    # Prepare
    started = await games.start(kind)
    before = copy.deepcopy((await _reload(session, started.game_id)).live_state)

    # Act / Assert
    with pytest.raises(GameNotPausedError) as exc_info:
        await started.controller.resume_game(started.game_id, started.host_id)
    assert exc_info.value.status_code == 409

    game = await _reload(session, started.game_id)
    assert game.live_state == before


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_only_the_host_can_resume(games: GameStarter, session: AsyncSession, kind: str):
    """A player who is not the host gets 403 and the game stays paused."""
    # Prepare
    started = await games.start(kind)
    await started.controller.pause_game(started.game_id, started.host_id)

    # Act / Assert
    with pytest.raises(OnlyHostCanPauseError):
        await started.controller.resume_game(started.game_id, started.player_ids[1])

    game = await _reload(session, started.game_id)
    assert "paused" in game.live_state


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_a_spectator_who_became_host_can_resume(
    games: GameStarter, session: AsyncSession, create_user, kind: str
):
    """Host transfer falls back to a spectator when no player is connected — that host
    must be able to resume, or the game would stay paused for good."""
    # Prepare
    started = await games.start(kind)
    spectator_id = await _add_spectator(session, create_user, started.room_id, f"heir_{kind}")
    await started.controller.pause_game(started.game_id, started.host_id)
    await _set_owner(session, started.room_id, spectator_id)

    # Act
    await started.controller.resume_game(started.game_id, spectator_id)

    # Assert
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state


# ─── While paused, nothing moves ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "move"),
    [
        ("undercover", "describe"),
        ("undercover", "vote"),
        ("undercover", "mr_white_guess"),
        ("undercover", "undercover_next_round"),
        ("codenames", "clue"),
        ("codenames", "guess"),
        ("codenames", "end_turn"),
        ("wordquiz", "wordquiz_answer"),
        ("wordquiz", "quiz_next_round"),
        ("mcqquiz", "mcq_answer"),
        ("mcqquiz", "quiz_next_round"),
    ],
)
async def test_every_move_is_rejected_while_paused(games: GameStarter, session: AsyncSession, kind: str, move: str):
    """Every mutation answers GamePausedError (409) and changes nothing."""
    # Prepare
    started = await games.start(kind)
    await started.controller.pause_game(started.game_id, started.host_id)
    before = copy.deepcopy((await _reload(session, started.game_id)).live_state)

    # Act / Assert
    with pytest.raises(GamePausedError) as exc_info:
        await _make_move(started, before, move)
    assert exc_info.value.status_code == 409

    game = await _reload(session, started.game_id)
    assert game.live_state == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "move"),
    [("undercover", "describe"), ("codenames", "clue"), ("wordquiz", "wordquiz_answer"), ("mcqquiz", "mcq_answer")],
)
async def test_the_same_move_is_accepted_after_resume(games: GameStarter, session: AsyncSession, kind: str, move: str):
    """The pause was the only thing in the way: once resumed, the move goes through."""
    # Prepare
    started = await games.start(kind)
    await started.controller.pause_game(started.game_id, started.host_id)
    await started.controller.resume_game(started.game_id, started.host_id)
    state = copy.deepcopy((await _reload(session, started.game_id)).live_state)

    # Act
    await _make_move(started, state, move)

    # Assert
    game = await _reload(session, started.game_id)
    assert game.live_state != state


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["undercover", "codenames", "wordquiz"])
async def test_hint_views_are_still_recorded_while_paused(games: GameStarter, session: AsyncSession, kind: str):
    """Looking up a hint changes nothing a player competes on, so it stays open."""
    # Prepare
    started = await games.start(kind)
    await started.controller.pause_game(started.game_id, started.host_id)

    # Act
    if kind == "wordquiz":
        result = await started.controller.record_hint_view(started.game_id, started.host_id)
    else:
        result = await started.controller.record_hint_view(started.game_id, started.host_id, "mosque")

    # Assert
    assert result.recorded is True
    game = await _reload(session, started.game_id)
    assert game.live_state["hint_usage"][str(started.host_id)]
    assert "paused" in game.live_state


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_timer_expired_does_nothing_while_paused(games: GameStarter, session: AsyncSession, kind: str):
    """Clients fire timer-expired from their own clocks: answered with a status, never acted on.

    The timer here has run out on any clock, so without the pause the call would act.
    """
    # Prepare
    started = await games.start(kind)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    _set_round_timer(state, kind, seconds=5, started_ago=3600)
    await _save_state(session, game, state)
    await started.controller.pause_game(started.game_id, started.host_id)
    before = copy.deepcopy((await _reload(session, started.game_id)).live_state)

    # Act
    result = await started.controller.handle_timer_expired(started.game_id, started.player_ids[1])

    # Assert
    assert result.action == TimerExpiredAction.PAUSED
    game = await _reload(session, started.game_id)
    assert game.live_state == before
    assert game.game_status == GameStatus.IN_PROGRESS


# ─── Resume moves every clock forward ─────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_a_paused_timer_resumes_with_the_time_it_had_left(games: GameStarter, session: AsyncSession, kind: str):
    """A 30 s timer paused 20 s in still has 10 s left after resume, however long the prayer.

    The timer started 40 s ago and the pause began 20 s ago: without the shift it
    reads 40 s elapsed and is expired; with it, 20 s elapsed and 10 s to go.
    """
    # Prepare
    started = await games.start(kind)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    _set_round_timer(state, kind, seconds=30, started_ago=40)
    await _save_state(session, game, state)
    anchor_before = datetime.fromisoformat(state[_anchor_key(kind)])
    await started.controller.pause_game(started.game_id, started.host_id)
    await _backdate_pause(session, started.game_id, 20)

    # Act
    resumed = await started.controller.resume_game(started.game_id, started.host_id)

    # Assert — the anchor moved by the paused duration, and only by it
    game = await _reload(session, started.game_id)
    anchor_after = datetime.fromisoformat(game.live_state[_anchor_key(kind)])
    shift = (anchor_after - anchor_before).total_seconds()
    assert 19.5 <= shift <= 21.5
    assert shift == pytest.approx(resumed.paused_seconds, abs=0.5)

    # Assert — 20 s on the clock: not expired
    result = await started.controller.handle_timer_expired(started.game_id, started.host_id)
    assert result.action == "timer_not_expired"

    # Assert — 26 s on the clock: still not expired (the 2 s tolerance starts at 28)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    _age_anchor(state, kind, 6)
    await _save_state(session, game, state)
    result = await started.controller.handle_timer_expired(started.game_id, started.host_id)
    assert result.action == "timer_not_expired"

    # Assert — 29 s on the clock: the timer runs out exactly where it would have
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    _age_anchor(state, kind, 3)
    await _save_state(session, game, state)
    result = await started.controller.handle_timer_expired(started.game_id, started.host_id)
    assert result.action == TIMER_ACTIONS[kind]


@pytest.mark.asyncio
async def test_a_timer_restarted_during_the_pause_starts_counting_at_the_resume(
    undercover_game_controller: UndercoverGameController, games: GameStarter, session: AsyncSession
):
    """A drop-out during the prayer can move a round to voting, which restarts its timer
    mid-pause. That timer has counted nothing yet: it starts at the resume, not later."""
    # Prepare
    started = await games.start("undercover")
    await started.controller.pause_game(started.game_id, started.host_id)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    state["paused"]["at"] = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    state["timer_started_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    await _save_state(session, game, state)

    # Act
    before_resume = datetime.now(UTC)
    await undercover_game_controller.resume_game(started.game_id, started.host_id)

    # Assert
    game = await _reload(session, started.game_id)
    anchor = datetime.fromisoformat(game.live_state["timer_started_at"])
    assert before_resume <= anchor <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_the_hint_ladder_stands_still_while_paused_and_after_resume(
    wordquiz_game_controller: WordQuizGameController, games: GameStarter, session: AsyncSession
):
    """A round paused 5 s in still shows its first hint — during the prayer and after it.

    The round started 35 s ago with a 10 s interval: on the wall clock that is the
    fourth rung. The pause began 30 s ago, so the game's clock reads 5 s.
    """
    # Prepare
    started = await games.start("wordquiz")
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    state["hint_interval_seconds"] = 10
    state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=35)).isoformat()
    await _save_state(session, game, state)
    await wordquiz_game_controller.pause_game(started.game_id, started.host_id)
    await _backdate_pause(session, started.game_id, 30)

    # Act — while paused
    paused_view = await wordquiz_game_controller.get_state(started.game_id, started.host_id, update_heartbeat=False)

    # Assert — frozen at the pause
    assert paused_view.hints_revealed == 1
    assert len(paused_view.hints) == 1

    # Act — after resume
    await wordquiz_game_controller.resume_game(started.game_id, started.host_id)
    resumed_view = await wordquiz_game_controller.get_state(started.game_id, started.host_id, update_heartbeat=False)
    word = (await _reload(session, started.game_id)).live_state["current_word"]["word_en"]
    answer = await wordquiz_game_controller.submit_answer(started.game_id, started.host_id, word)

    # Assert — still the first rung, and an answer now earns the first rung's score
    assert resumed_view.hints_revealed == 1
    assert answer.hint_number == 1
    assert answer.points_earned == 6
    game = await _reload(session, started.game_id)
    assert game.live_state["answers"][str(started.host_id)]["points"] == 6
    assert game.live_state["answers"][str(started.host_id)]["answer_time_ms"] < 10_000


@pytest.mark.asyncio
async def test_the_mcq_speed_bonus_ignores_the_pause(
    mcqquiz_game_controller: McqQuizGameController, games: GameStarter, session: AsyncSession
):
    """Answering 1 s into a 15 s round earns the full bonus, even across a 13 s pause.

    The round started 14 s ago: on the wall clock that is worth 1 point. The pause
    began 13 s ago, so the game's clock reads 1 s, which is worth 3.
    """
    # Prepare
    started = await games.start("mcqquiz")
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    state["turn_duration_seconds"] = 15
    state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=14)).isoformat()
    await _save_state(session, game, state)
    correct_index = state["current_question"]["correct_answer_index"]
    await mcqquiz_game_controller.pause_game(started.game_id, started.host_id)
    await _backdate_pause(session, started.game_id, 13)
    await mcqquiz_game_controller.resume_game(started.game_id, started.host_id)

    # Act
    answer = await mcqquiz_game_controller.submit_answer(started.game_id, started.host_id, correct_index)

    # Assert
    assert answer.correct is True
    assert answer.points_earned == 3
    game = await _reload(session, started.game_id)
    assert game.live_state["answers"][str(started.host_id)]["points"] == 3
    host = next(p for p in game.live_state["players"] if p["user_id"] == str(started.host_id))
    assert host["total_score"] == 3


# ─── Disconnects during the pause ─────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("paused", [True, False])
async def test_a_paused_game_keeps_a_player_whose_phone_locked(games: GameStarter, session: AsyncSession, paused: bool):
    """Past the in-game grace, a disconnected player is removed — unless the game is paused."""
    # Prepare
    started = await games.start("mcqquiz", num_players=3)
    away_id = started.player_ids[2]
    if paused:
        await started.controller.pause_game(started.game_id, started.host_id)
    await _disconnect(session, started.room_id, away_id, seconds_ago=GRACE_PERIOD_SECONDS + 60)

    # Act
    await _remove_expired_users(session)

    # Assert
    link = await _reload_link(session, started.room_id, away_id)
    game = await _reload(session, started.game_id)
    still_playing = any(p["user_id"] == str(away_id) for p in game.live_state["players"])
    assert (link is not None) is paused
    assert still_playing is paused


@pytest.mark.asyncio
async def test_the_paused_grace_is_finite_and_the_new_host_resumes(games: GameStarter, session: AsyncSession):
    """A host who never comes back is removed after the paused grace; ownership moves to a
    player, the game is still paused (no auto-resume), and the new host resumes it."""
    # Prepare
    started = await games.start("mcqquiz", num_players=3)
    await started.controller.pause_game(started.game_id, started.host_id)
    await _disconnect(session, started.room_id, started.host_id, seconds_ago=PAUSED_GAME_GRACE_PERIOD_SECONDS + 60)

    # Act
    await _remove_expired_users(session)

    # Assert — the old host is gone and a remaining player holds the room
    assert await _reload_link(session, started.room_id, started.host_id) is None
    room = (
        await session.exec(select(Room).where(Room.id == started.room_id).execution_options(populate_existing=True))
    ).one()
    assert room.owner_id in started.player_ids[1:]
    new_host_id = room.owner_id
    game = await _reload(session, started.game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    assert "paused" in game.live_state

    # Act / Assert — the old host can no longer resume, the new one can
    with pytest.raises(OnlyHostCanPauseError):
        await started.controller.resume_game(started.game_id, started.host_id)
    await started.controller.resume_game(started.game_id, new_host_id)
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state


@pytest.mark.asyncio
async def test_the_host_leaving_during_the_pause_hands_resume_to_the_new_host(
    games: GameStarter, session: AsyncSession, room_controller
):
    """Leaving voluntarily transfers ownership like any departure; the game stays paused."""
    # Prepare
    started = await games.start("wordquiz", num_players=2)
    await started.controller.pause_game(started.game_id, started.host_id)

    # Act
    await room_controller.leave_room(started.room_id, started.host_id)

    # Assert — still paused, now held by the remaining player
    remaining_id = started.player_ids[1]
    view = await _read_state(started, remaining_id)
    assert view.paused is not None
    assert view.is_host is True
    await started.controller.resume_game(started.game_id, remaining_id)
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_resume_gives_a_disconnected_player_back_the_grace_they_had_left(
    games: GameStarter, session: AsyncSession
):
    """No clock runs while paused, the disconnect grace included.

    The pause lasted 10 min. One player dropped 60 s before it, another during it.
    Without the shift both would be past the 180 s grace the moment the game resumed;
    with it, the first has 120 s left and the second the full 180 s.
    """
    # Prepare
    started = await games.start("mcqquiz", num_players=3)
    before_pause_id, during_pause_id = started.player_ids[1], started.player_ids[2]
    await started.controller.pause_game(started.game_id, started.host_id)
    await _backdate_pause(session, started.game_id, 600)
    await _disconnect(session, started.room_id, before_pause_id, seconds_ago=660)
    await _disconnect(session, started.room_id, during_pause_id, seconds_ago=300)

    # Act
    await started.controller.resume_game(started.game_id, started.host_id)
    await _remove_expired_users(session)

    # Assert — the grace already used before the pause is kept, the pause adds none
    now = datetime.now()
    before_link = await _reload_link(session, started.room_id, before_pause_id)
    during_link = await _reload_link(session, started.room_id, during_pause_id)
    assert before_link is not None
    assert during_link is not None
    assert before_link.disconnected_at is not None
    assert during_link.disconnected_at is not None
    assert 58 <= (now - before_link.disconnected_at).total_seconds() <= 63
    assert 0 <= (now - during_link.disconnected_at).total_seconds() <= 3
    host_link = await _reload_link(session, started.room_id, started.host_id)
    assert host_link is not None
    assert host_link.connected is True
    assert host_link.disconnected_at is None


@pytest.mark.asyncio
async def test_a_game_decided_by_a_drop_out_during_the_pause_is_over_not_paused(
    codenames_game_controller: CodenamesGameController, games: GameStarter, session: AsyncSession
):
    """The end-of-game flow is untouched: a departure that decides the game still ends it,
    and a finished game never reads as paused nor can be resumed."""
    # Prepare — 4 players: losing a spymaster cripples that team
    started = await games.start("codenames")
    await codenames_game_controller.pause_game(started.game_id, started.host_id)
    game = await _reload(session, started.game_id)
    spymaster = next(p for p in game.live_state["players"] if p["role"] == CodenamesRole.SPYMASTER.value)
    room = (await session.exec(select(Room).where(Room.id == started.room_id))).one()

    # Act
    await _handle_codenames_disconnect(session, game, spymaster["user_id"], room)

    # Assert
    game = await _reload(session, started.game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] is not None
    viewer_id = next(uid for uid in started.player_ids if str(uid) != spymaster["user_id"])
    view = await codenames_game_controller.get_board(started.game_id, viewer_id, update_heartbeat=False)
    assert view.paused is None
    with pytest.raises(BaseError) as exc_info:
        await codenames_game_controller.resume_game(started.game_id, started.host_id)
    assert exc_info.value.status_code == 400


# ─── What a paused screen shows ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_the_paused_view_freezes_the_countdown_on_the_server(
    games: GameStarter, session: AsyncSession, kind: str
):
    """A 30 s timer paused 20 s in reads 10 s left — however long the prayer lasts.

    The server computes it, so a client never derives a countdown from its own clock.
    """
    # Prepare — the timer started 40 s ago, the pause 20 s ago
    started = await games.start(kind)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    _set_round_timer(state, kind, seconds=30, started_ago=40)
    await _save_state(session, game, state)
    await started.controller.pause_game(started.game_id, started.host_id)
    await _backdate_pause(session, started.game_id, 20)

    # Act
    view = await _read_state(started, started.player_ids[1])

    # Assert
    assert view.paused is not None
    assert view.paused.remaining_seconds == pytest.approx(10, abs=1)
    assert view.paused.paused_for_seconds == pytest.approx(20, abs=1)
    assert view.paused.anyone_can_resume_at == view.paused.since + timedelta(seconds=PRAYER_PAUSE_MAX_SECONDS)
    game = await _reload(session, started.game_id)
    assert datetime.fromisoformat(game.live_state["paused"]["at"]) == view.paused.since


@pytest.mark.asyncio
async def test_a_timer_restarted_during_the_pause_shows_its_whole_duration(games: GameStarter, session: AsyncSession):
    """An anchor later than the pause (a drop-out restarted the round's timer mid-prayer)
    has counted nothing: the frozen countdown is the full duration, never more."""
    # Prepare
    started = await games.start("undercover")
    await started.controller.pause_game(started.game_id, started.host_id)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    state["timer_config"]["description_seconds"] = 30
    state["paused"]["at"] = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    state["timer_started_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    await _save_state(session, game, state)

    # Act
    view = await _read_state(started, started.host_id)

    # Assert
    assert view.paused is not None
    assert view.paused.remaining_seconds == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["undercover", "codenames"])
async def test_an_untimed_phase_has_no_frozen_countdown(games: GameStarter, kind: str):
    """Undercover and Codenames timers default to 0 (no limit): nothing to freeze."""
    # Prepare
    started = await games.start(kind)

    # Act
    result = await started.controller.pause_game(started.game_id, started.host_id)
    view = await _read_state(started, started.host_id)

    # Assert
    assert result.paused.remaining_seconds is None
    assert view.paused is not None
    assert view.paused.remaining_seconds is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_can_pause_and_can_resume_follow_the_servers_rule(
    games: GameStarter, session: AsyncSession, create_user, kind: str
):
    """The state says exactly when pause / resume would succeed for the caller."""
    # Prepare
    started = await games.start(kind)
    other = started.player_ids[1]
    spectator_id = await _add_spectator(session, create_user, started.room_id, f"onlooker_{kind}")

    # Act / Assert — running: only the host may pause, nobody may resume
    host_view = await _read_state(started, started.host_id)
    other_view = await _read_state(started, other)
    assert (host_view.can_pause, host_view.can_resume) == (True, False)
    assert (other_view.can_pause, other_view.can_resume) == (False, False)

    # Act / Assert — paused: only the host may resume, nobody may pause again
    await started.controller.pause_game(started.game_id, started.host_id)
    host_view = await _read_state(started, started.host_id)
    other_view = await _read_state(started, other)
    assert (host_view.can_pause, host_view.can_resume) == (False, True)
    assert (other_view.can_pause, other_view.can_resume) == (False, False)

    # Act / Assert — a spectator holding the host role may resume, never pause
    await _set_owner(session, started.room_id, spectator_id)
    spectator_view = await _read_state(started, spectator_id)
    assert (spectator_view.can_pause, spectator_view.can_resume) == (False, True)


# ─── A pause can never hold the table for good ────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GAME_KINDS)
async def test_after_the_cap_any_player_may_resume(games: GameStarter, session: AsyncSession, create_user, kind: str):
    """A host whose tab stays open never trips the paused grace. Past
    PRAYER_PAUSE_MAX_SECONDS the pause is no longer theirs alone: any player resumes."""
    # Prepare
    started = await games.start(kind)
    other = started.player_ids[1]
    spectator_id = await _add_spectator(session, create_user, started.room_id, f"bystander_{kind}")
    await started.controller.pause_game(started.game_id, started.host_id)

    # Act / Assert — just before the cap, still the host's call
    await _backdate_pause(session, started.game_id, PRAYER_PAUSE_MAX_SECONDS - 60)
    assert (await _read_state(started, other)).can_resume is False
    with pytest.raises(OnlyHostCanPauseError):
        await started.controller.resume_game(started.game_id, other)

    # Act / Assert — past the cap: any player of the game, but not a mere spectator
    await _backdate_pause(session, started.game_id, PRAYER_PAUSE_MAX_SECONDS + 1)
    assert (await _read_state(started, other)).can_resume is True
    assert (await _read_state(started, spectator_id)).can_resume is False
    with pytest.raises(OnlyHostCanPauseError):
        await started.controller.resume_game(started.game_id, spectator_id)
    result = await started.controller.resume_game(started.game_id, other)

    # Assert
    assert result.paused_seconds >= PRAYER_PAUSE_MAX_SECONDS
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_a_room_left_without_an_owner_can_be_resumed_by_any_player(games: GameStarter, session: AsyncSession):
    """The host deleting their account nulls Room.owner_id: nobody would ever be "the
    host" again, so any player may resume at once rather than never."""
    # Prepare
    started = await games.start("codenames")
    await started.controller.pause_game(started.game_id, started.host_id)
    room = (await session.exec(select(Room).where(Room.id == started.room_id))).one()
    room.owner_id = None
    session.add(room)
    await session.commit()
    other = started.player_ids[1]

    # Act
    view = await _read_state(started, other)
    await started.controller.resume_game(started.game_id, other)

    # Assert
    assert view.can_resume is True
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state


# ─── The game's own type decides ──────────────────────────────


@pytest.mark.asyncio
async def test_pause_and_resume_through_another_games_router_are_not_found(
    games: GameStarter, session: AsyncSession, undercover_game_controller: UndercoverGameController
):
    """A Word Quiz game reached through the Undercover router is not a game that router
    has: 404, and neither the pause nor any clock is touched."""
    # Prepare
    started = await games.start("wordquiz")

    # Act / Assert — pause
    with pytest.raises(GameNotFoundError):
        await undercover_game_controller.pause_game(started.game_id, started.host_id)
    assert "paused" not in (await _reload(session, started.game_id)).live_state

    # Act / Assert — resume
    await started.controller.pause_game(started.game_id, started.host_id)
    before = copy.deepcopy((await _reload(session, started.game_id)).live_state)
    with pytest.raises(GameNotFoundError):
        await undercover_game_controller.resume_game(started.game_id, started.host_id)
    assert (await _reload(session, started.game_id)).live_state == before


@pytest.mark.asyncio
async def test_resume_shifts_the_clocks_the_game_type_names(games: GameStarter, session: AsyncSession):
    """The anchors come from the game, not from the controller class that resumes it:
    the bare base controller (no game type of its own) still moves a Word Quiz round."""
    # Prepare — the round started 50 s ago, the pause 30 s ago
    started = await games.start("wordquiz")
    await started.controller.pause_game(started.game_id, started.host_id)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    now = datetime.now(UTC)
    state["round_started_at"] = (now - timedelta(seconds=50)).isoformat()
    state["paused"]["at"] = (now - timedelta(seconds=30)).isoformat()
    await _save_state(session, game, state)

    # Act
    await BaseGameController(session).resume_game(started.game_id, started.host_id)

    # Assert — 20 s of round time remain behind the anchor, not 50
    game = await _reload(session, started.game_id)
    anchor = datetime.fromisoformat(game.live_state["round_started_at"])
    assert (datetime.now(UTC) - anchor).total_seconds() == pytest.approx(20, abs=1.5)


# ─── The disconnect sweep ─────────────────────────────────────


@pytest.mark.asyncio
async def test_the_disconnect_sweep_reads_rooms_and_games_once(
    games: GameStarter, session: AsyncSession, count_statements
):
    """Players kept by the paused grace are swept every tick: one room and one game
    query for all of them, never two per away player."""
    # Prepare — three players away past the ordinary grace, kept because paused
    started = await games.start("mcqquiz", num_players=4)
    await started.controller.pause_game(started.game_id, started.host_id)
    for away_id in started.player_ids[1:]:
        await _disconnect(session, started.room_id, away_id, seconds_ago=GRACE_PERIOD_SECONDS + 60)
    rooms = count_statements("FROM room \n")
    game_reads = count_statements("FROM game \n")

    # Act
    await _remove_expired_users(session)

    # Assert
    assert rooms.count == 1
    assert game_reads.count == 1
    for away_id in started.player_ids[1:]:
        assert await _reload_link(session, started.room_id, away_id) is not None


@pytest.mark.asyncio
async def test_the_sweep_rechecks_a_link_before_removing_it(games: GameStarter, session: AsyncSession):
    """The sweep's rows can be stale by the time it reaches one: a player who came back
    since must not be removed on the old row."""
    # Prepare — a link read as expired, then reconnected behind the session's back
    started = await games.start("mcqquiz", num_players=3)
    away_id = started.player_ids[2]
    await _disconnect(session, started.room_id, away_id, seconds_ago=GRACE_PERIOD_SECONDS + 60)
    stale = await _reload_link(session, started.room_id, away_id)
    assert stale is not None
    await session.exec(
        update(RoomUserLink)
        .where(RoomUserLink.id == stale.id)
        .values(connected=True, disconnected_at=None)
        .execution_options(synchronize_session=False)
    )
    await session.commit()

    # Act
    fresh = await _still_expired(session, stale)

    # Assert
    assert fresh is None
    link = await _reload_link(session, started.room_id, away_id)
    assert link is not None
    assert link.connected is True


# ─── Concurrency (PostgreSQL advisory locks) ──────────────────


async def _mutate(engine: AsyncEngine, kind: str, method: str, *args):
    """Run ONE controller call in its own session, like one request in production.

    Same pattern as test_concurrent_mutations._mutate: an AsyncSession must never be
    driven by several tasks at once.
    """
    async with AsyncSession(engine, expire_on_commit=False) as concurrent_session:
        controller = CONTROLLER_CLASSES[kind](concurrent_session)
        return await getattr(controller, method)(*args)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_pause_racing_a_move_leaves_a_consistent_state(
    games: GameStarter, session: AsyncSession, engine: AsyncEngine
):
    """Whichever wins the lock, the outcome is one of two clean states: the description
    went in before the pause, or it was refused because of it. Never half of each."""
    # Prepare
    started = await games.start("undercover")
    game = await _reload(session, started.game_id)
    turn = game.live_state["turns"][-1]
    describer = UUID(turn["description_order"][0])
    await session.commit()

    # Act
    pause_result, describe_result = await asyncio.gather(
        _mutate(engine, "undercover", "pause_game", started.game_id, started.host_id),
        _mutate(engine, "undercover", "submit_description", started.game_id, describer, "Patience"),
        return_exceptions=True,
    )

    # Assert — the pause always lands; the move either landed first or was refused
    assert isinstance(pause_result, PauseGameResponse)
    assert isinstance(describe_result, SubmitDescriptionResponse | GamePausedError)
    game = await _reload(session, started.game_id)
    turn = game.live_state["turns"][-1]
    assert "paused" in game.live_state
    if isinstance(describe_result, SubmitDescriptionResponse):
        assert turn["words"] == {str(describer): "Patience"}
        assert turn["current_describer_index"] == 1
    else:
        assert turn["words"] == {}
        assert turn["current_describer_index"] == 0


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_two_pauses_racing_exactly_one_wins(games: GameStarter, session: AsyncSession, engine: AsyncEngine):
    """A double tap on pause: one succeeds, the other is a 409."""
    # Prepare
    started = await games.start("codenames")
    await session.commit()

    # Act
    results = await asyncio.gather(
        _mutate(engine, "codenames", "pause_game", started.game_id, started.host_id),
        _mutate(engine, "codenames", "pause_game", started.game_id, started.host_id),
        return_exceptions=True,
    )

    # Assert
    assert sum(isinstance(r, PauseGameResponse) for r in results) == 1
    assert sum(isinstance(r, GameAlreadyPausedError) for r in results) == 1
    winner = next(r for r in results if isinstance(r, PauseGameResponse))
    game = await _reload(session, started.game_id)
    assert datetime.fromisoformat(game.live_state["paused"]["at"]) == winner.paused.since


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_two_resumes_racing_move_the_clock_once(games: GameStarter, session: AsyncSession, engine: AsyncEngine):
    """A double tap on resume shifts the timer by the pause once, not twice.

    The round must have started BEFORE the pause: an anchor set during it has counted
    nothing and is capped at the resume instant, so it would shift by far less than
    the pause (which is what this test once did — it backdated the pause to 100 s ago
    while the round had started a moment ago, i.e. "during" the pause).
    """
    # Prepare — the round started 110 s ago, the pause 100 s ago
    started = await games.start("mcqquiz")
    await started.controller.pause_game(started.game_id, started.host_id)
    game = await _reload(session, started.game_id)
    state = copy.deepcopy(game.live_state)
    now = datetime.now(UTC)
    state["round_started_at"] = (now - timedelta(seconds=110)).isoformat()
    state["paused"]["at"] = (now - timedelta(seconds=100)).isoformat()
    await _save_state(session, game, state)
    anchor_before = datetime.fromisoformat(state["round_started_at"])
    await session.commit()

    # Act
    results = await asyncio.gather(
        _mutate(engine, "mcqquiz", "resume_game", started.game_id, started.host_id),
        _mutate(engine, "mcqquiz", "resume_game", started.game_id, started.host_id),
        return_exceptions=True,
    )

    # Assert
    assert sum(isinstance(r, ResumeGameResponse) for r in results) == 1
    assert sum(isinstance(r, GameNotPausedError) for r in results) == 1
    game = await _reload(session, started.game_id)
    anchor_after = datetime.fromisoformat(game.live_state["round_started_at"])
    shift = (anchor_after - anchor_before).total_seconds()
    assert "paused" not in game.live_state
    # Once: ~100 s. Twice would be ~200 s — which the cap at the resume instant would
    # also clip to ~110 s, so the anchor must also still lie 10 s before now.
    assert 99 <= shift <= 102
    assert 9 <= (datetime.now(UTC) - anchor_after).total_seconds() <= 12
