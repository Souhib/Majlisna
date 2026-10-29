"""A quiz round the departure completes moves to results at once.

When the one player everybody was waiting on leaves, is kicked or is removed by the
grace sweep, every remaining player has already answered (MCQ) or found the word
(Word Quiz): no answer can arrive any more, and the round used to sit open until its
timer ran out. The departure path now settles it under the game lock, in the same
commit — except while the game is paused for the prayer, where the resume does.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import GRACE_PERIOD_SECONDS
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.disconnect import _remove_expired_users
from majlisna.api.controllers.quiz_rules import everyone_has_answered, settle_round_if_everyone_answered
from majlisna.api.controllers.room import RoomController
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game

QUIZ_KINDS = ["wordquiz", "mcqquiz"]
DEPARTURES = ["leave", "kick", "sweep"]


# ─── Helpers ──────────────────────────────────────────────────


@dataclass
class StartedQuiz:
    """A running 3-player quiz. Ids only: ORM rows can expire under a rollback."""

    kind: str
    controller: BaseGameController
    game_id: UUID
    room_id: UUID
    host_id: UUID
    player_ids: list[UUID]


class QuizStarter:
    def __init__(self, setups: dict, controllers: dict):
        self._setups = setups
        self._controllers = controllers

    async def start(self, kind: str, num_players: int = 3) -> StartedQuiz:
        setup = await self._setups[kind](num_players=num_players)
        controller = self._controllers[kind]
        player_ids = [user.id for user in setup["users"]]
        result = await controller.create_and_start(setup["room"].id, player_ids[0])
        return StartedQuiz(
            kind=kind,
            controller=controller,
            game_id=UUID(result.game_id),
            room_id=setup["room"].id,
            host_id=player_ids[0],
            player_ids=player_ids,
        )


@pytest_asyncio.fixture(name="quizzes")
async def get_quizzes(
    setup_wordquiz_game, setup_mcqquiz_game, wordquiz_game_controller, mcqquiz_game_controller
) -> QuizStarter:
    return QuizStarter(
        setups={"wordquiz": setup_wordquiz_game, "mcqquiz": setup_mcqquiz_game},
        controllers={"wordquiz": wordquiz_game_controller, "mcqquiz": mcqquiz_game_controller},
    )


async def _reload(session: AsyncSession, game_id: UUID) -> Game:
    """The game as stored, not the instance a controller may still hold in memory."""
    statement = select(Game).where(Game.id == game_id).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


async def _finish_the_round(started: StartedQuiz, session: AsyncSession, user_id: UUID) -> None:
    """The player is done with the open round: answered (MCQ) or found the word (Word Quiz)."""
    state = (await _reload(session, started.game_id)).live_state
    if started.kind == "wordquiz":
        await started.controller.submit_answer(started.game_id, user_id, state["current_word"]["word_en"])
    else:
        await started.controller.submit_answer(
            started.game_id, user_id, state["current_question"]["correct_answer_index"]
        )


async def _depart(
    how: str, started: StartedQuiz, session: AsyncSession, room_controller: RoomController, user_id: UUID
) -> None:
    """Make `user_id` leave the game the way `how` names."""
    if how == "leave":
        await room_controller.leave_room(started.room_id, user_id)
    elif how == "kick":
        await room_controller.kick_player(started.room_id, started.host_id, user_id)
    else:
        link = (
            await session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == started.room_id)
                .where(RoomUserLink.user_id == user_id)
            )
        ).one()
        link.connected = False
        # Naive local time, like the checker (root CLAUDE.md: RoomUserLink stays naive).
        link.disconnected_at = datetime.now() - timedelta(seconds=GRACE_PERIOD_SECONDS + 5)
        session.add(link)
        await session.commit()
        await _remove_expired_users(session)


# ─── The departure completes the round ────────────────────────


@pytest.mark.parametrize("how", DEPARTURES)
@pytest.mark.parametrize("kind", QUIZ_KINDS)
async def test_a_departure_that_completes_the_round_resolves_it_at_once(
    quizzes: QuizStarter, session: AsyncSession, room_controller: RoomController, kind: str, how: str
):
    """Two of three are done; the third goes — the round's results are out, no timer needed."""
    # Prepare
    started = await quizzes.start(kind)
    host_id, done_id, leaver_id = started.player_ids
    await _finish_the_round(started, session, host_id)
    await _finish_the_round(started, session, done_id)
    assert (await _reload(session, started.game_id)).live_state["round_phase"] == "playing"

    # Act
    await _depart(how, started, session, room_controller, leaver_id)

    # Assert — stored state, then what a remaining player reads
    game = await _reload(session, started.game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    assert game.live_state["round_phase"] == "results"
    assert {row["user_id"] for row in game.live_state["round_results"]} == {str(host_id), str(done_id)}
    assert all(row["points"] > 0 for row in game.live_state["round_results"])
    view = await started.controller.get_state(started.game_id, done_id, update_heartbeat=False)
    assert view.round_phase == "results"


@pytest.mark.parametrize("kind", QUIZ_KINDS)
async def test_a_departure_that_leaves_someone_still_playing_keeps_the_round_open(
    quizzes: QuizStarter, session: AsyncSession, room_controller: RoomController, kind: str
):
    """The leaver had answered, one of the two who stay has not: the round waits for them.

    In Word Quiz a wrong try is not "done": the player may still find the word.
    """
    # Prepare
    started = await quizzes.start(kind)
    host_id, still_playing_id, leaver_id = started.player_ids
    await _finish_the_round(started, session, host_id)
    await _finish_the_round(started, session, leaver_id)
    if kind == "wordquiz":
        await started.controller.submit_answer(started.game_id, still_playing_id, "not the word")

    # Act
    await _depart("leave", started, session, room_controller, leaver_id)

    # Assert
    game = await _reload(session, started.game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    assert game.live_state["round_phase"] == "playing"
    assert str(leaver_id) not in game.live_state["answers"]
    assert "round_results" not in game.live_state or not game.live_state["round_results"]

    # And the one still playing still closes it with their answer
    await _finish_the_round(started, session, still_playing_id)
    game = await _reload(session, started.game_id)
    assert game.live_state["round_phase"] == "results"


# ─── The prayer pause holds the round until the resume ────────


@pytest.mark.parametrize("how", ["leave", "kick"])
@pytest.mark.parametrize("kind", QUIZ_KINDS)
async def test_a_departure_during_the_pause_is_settled_by_the_resume(
    quizzes: QuizStarter, session: AsyncSession, room_controller: RoomController, kind: str, how: str
):
    """The departure is recorded during the prayer, the round stays as it was, and the
    resume moves it to results in the same commit."""
    # Prepare
    started = await quizzes.start(kind)
    host_id, done_id, leaver_id = started.player_ids
    await _finish_the_round(started, session, host_id)
    await _finish_the_round(started, session, done_id)
    await started.controller.pause_game(started.game_id, host_id)

    # Act — the departure, during the pause
    await _depart(how, started, session, room_controller, leaver_id)

    # Assert — recorded, but the round has not moved
    game = await _reload(session, started.game_id)
    assert [p["user_id"] for p in game.live_state["players"]] == [str(host_id), str(done_id)]
    assert "paused" in game.live_state
    assert game.live_state["round_phase"] == "playing"
    paused_view = await started.controller.get_state(started.game_id, done_id, update_heartbeat=False)
    assert paused_view.paused is not None
    assert paused_view.round_phase == "playing"

    # Act — the prayer is over
    await started.controller.resume_game(started.game_id, host_id)

    # Assert — the resume settled it
    game = await _reload(session, started.game_id)
    assert "paused" not in game.live_state
    assert game.live_state["round_phase"] == "results"
    assert {row["user_id"] for row in game.live_state["round_results"]} == {str(host_id), str(done_id)}


@pytest.mark.parametrize("kind", QUIZ_KINDS)
async def test_the_resume_leaves_an_unfinished_round_open(
    quizzes: QuizStarter, session: AsyncSession, room_controller: RoomController, kind: str
):
    """Settling at the resume applies the same rule: someone still owes an answer, so it stays open."""
    # Prepare
    started = await quizzes.start(kind)
    host_id, still_playing_id, leaver_id = started.player_ids
    await _finish_the_round(started, session, host_id)
    await started.controller.pause_game(started.game_id, host_id)
    await _depart("leave", started, session, room_controller, leaver_id)

    # Act
    await started.controller.resume_game(started.game_id, host_id)

    # Assert
    game = await _reload(session, started.game_id)
    assert game.live_state["round_phase"] == "playing"
    assert str(still_playing_id) not in game.live_state["answers"]


# ─── The rule itself ──────────────────────────────────────────


def test_nobody_left_is_not_everyone_answered():
    """An empty table is cancelled by the departure path, never sent to results."""
    state = {"players": [], "answers": {}, "round_phase": "playing"}

    assert everyone_has_answered(state) is False
    assert settle_round_if_everyone_answered(state, GameType.MCQ_QUIZ) is False
    assert state["round_phase"] == "playing"


def test_only_an_open_round_is_settled():
    """A round already in results is left alone (its results are not rebuilt)."""
    state = {
        "players": [{"user_id": "a", "username": "a", "total_score": 1}],
        "answers": {"a": {"correct": True, "points": 1, "choice_index": 0, "answer_time_ms": 10}},
        "round_phase": "results",
        "round_results": ["kept as is"],
    }

    assert settle_round_if_everyone_answered(state, GameType.MCQ_QUIZ) is False
    assert state["round_results"] == ["kept as is"]
