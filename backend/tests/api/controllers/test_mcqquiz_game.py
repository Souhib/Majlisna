"""Tests for MCQ Quiz game controller."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import WINNER_IDS_KEY
from majlisna.api.controllers.game_cancel import cancel_running_game
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.common import TimerExpiredAction
from majlisna.api.schemas.error import (
    AlreadyAnsweredError,
    GameAlreadyOverError,
    InvalidChoiceIndexError,
    NoMcqQuestionsAvailableError,
    NotAGameParticipantError,
    RoundNotPlayingError,
    SpectatorCannotAnswerError,
)


async def _start_game(controller: McqQuizGameController, room_id, user_id):
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


async def _reload(session: AsyncSession, game_id_str: str) -> Game:
    """The game as stored, not the instance a controller may still hold in memory."""
    statement = select(Game).where(Game.id == UUID(game_id_str)).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


async def _expire_the_round(session: AsyncSession, game_id_str: str, seconds_ago: int = 120) -> None:
    """Move the round's anchor back so its (positive) duration has really elapsed."""
    game = await _reload(session, game_id_str)
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()


# === Game Creation ===


@pytest.mark.asyncio
async def test_create_and_start_1_player(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """MCQ Quiz supports 1 player — game starts successfully."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert len(state["players"]) == 1
    assert state["round_phase"] == "playing"
    assert state["current_round"] == 1
    assert state["current_question"] is not None
    assert "choices" in state["current_question"]
    assert "correct_answer_index" in state["current_question"]


@pytest.mark.asyncio
async def test_create_and_start_multiple_players(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Multiple players start correctly with proper live_state structure."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=3)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert len(state["players"]) == 3
    assert state["total_rounds"] == 10
    assert state["round_phase"] == "playing"
    assert state["game_over"] is False
    assert state["winner"] is None
    assert state["answers"] == {}
    assert len(state["question_ids"]) > 0


# === Answer Submission ===


@pytest.mark.asyncio
async def test_submit_correct_answer(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Correct answer earns 1-3 points (1 base + up to 2 time bonus)."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]

    # Act
    answer_result = await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)

    # Assert — fast answer should earn 1-3 points (base 1 + time bonus up to 2)
    assert answer_result.correct is True
    assert 1 <= answer_result.points_earned <= 3

    # Verify DB state
    game = await _get_game(session, result.game_id)
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[0].id))
    assert player["total_score"] == answer_result.points_earned
    assert str(users[0].id) in game.live_state["answers"]


@pytest.mark.asyncio
async def test_submit_wrong_answer(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Wrong answer earns 0 points."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]
    wrong_index = (correct_index + 1) % 4

    # Act
    answer_result = await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, wrong_index)

    # Assert
    assert answer_result.correct is False
    assert answer_result.points_earned == 0

    # Verify DB state
    game = await _get_game(session, result.game_id)
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[0].id))
    assert player["total_score"] == 0
    assert str(users[0].id) in game.live_state["answers"]


@pytest.mark.asyncio
async def test_cannot_answer_twice(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Cannot answer twice — AlreadyAnsweredError raised."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]

    # Act — first answer
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)

    # Assert — second answer rejected
    with pytest.raises(AlreadyAnsweredError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)


@pytest.mark.asyncio
async def test_invalid_choice_index(mcqquiz_game_controller, setup_mcqquiz_game):
    """Invalid choice index (out of 0-3) raises error."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(InvalidChoiceIndexError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 5)

    with pytest.raises(InvalidChoiceIndexError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, -1)


@pytest.mark.asyncio
async def test_all_players_answered_auto_results(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """When all players answer, round_phase transitions to 'results'."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"
    assert len(game.live_state["round_results"]) == 2


# === Timer ===


@pytest.mark.asyncio
async def test_timer_expired_non_host_allowed(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Any player can trigger timer expiration — not just host."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    await _expire_the_round(session, result.game_id)  # 0 is untimed, not "already expired"

    # Act — non-host triggers timer expiration
    timer_result = await mcqquiz_game_controller.handle_timer_expired(UUID(result.game_id), users[1].id)

    # Assert — should succeed
    assert timer_result.action == "results"

    # Verify DB state
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"


# === Round Advancement ===


@pytest.mark.asyncio
async def test_advance_to_next_round(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """After results, host can advance to next round."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2, num_questions=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Answer to transition to results
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Act
    await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"
    assert game.live_state["answers"] == {}


@pytest.mark.asyncio
async def test_advance_non_host_marks_ready(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """A non-host marks themselves ready; the round waits for the rest."""
    # Prepare — 3 players so one ready mark is not yet the whole quorum
    setup = await setup_mcqquiz_game(num_players=3, num_questions=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    for i, user in enumerate(users):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), user.id, i % 4)

    # Act — one of the two non-hosts marks ready
    advance_result = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)

    # Assert — not advanced, just marked ready. `total_players` reports what
    # readiness is measured against: everyone but the host.
    assert advance_result.advanced is False
    assert advance_result.ready_count == 1
    assert advance_result.total_players == 2
    assert str(users[1].id) in advance_result.ready_players
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"  # Still in results


@pytest.mark.asyncio
async def test_advance_all_ready_advances_round_without_the_host(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """ "Everyone is ready" must be reachable — it never was.

    The host advances by pressing next and is never added to ``ready_players``, so
    requiring ``len(ready_players) == len(players)`` could not be satisfied while
    the host was also a player, i.e. in every normal game. The documented feature
    collapsed to "only the host can advance", and an absent host stalled the quiz
    with nothing to rescue it — the results phase has no timeout.
    """
    # Prepare — 3 players: users[0] hosts, users[1] and users[2] do not
    setup = await setup_mcqquiz_game(num_players=3, num_questions=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    for i, user in enumerate(users):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), user.id, i % 4)

    # Act — both non-hosts mark ready; the host does nothing at all
    first = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)
    second = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[2].id)

    # Assert
    assert first.advanced is False
    assert second.advanced is True
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"
    assert game.live_state["ready_players"] == []


@pytest.mark.asyncio
async def test_host_advances_the_round_on_their_own(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """The host override still bypasses readiness entirely."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=3, num_questions=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    for i, user in enumerate(users):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), user.id, i % 4)

    # Act — nobody has marked ready
    advance_result = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    assert advance_result.advanced is True
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2


@pytest.mark.asyncio
async def test_game_over_after_final_round(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Game ends after all rounds are played."""
    # Prepare — 1 round game
    setup = await setup_mcqquiz_game(num_players=1, num_questions=3)
    room, users = setup["room"], setup["users"]
    room.settings = {"mcq_quiz_rounds": 1}
    session.add(room)
    await session.commit()

    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]

    # Answer to go to results
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)

    # Act — advance (should end game since total_rounds=1)
    await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["game_over"] is True
    assert game.live_state["round_phase"] == "game_over"
    # A solo game is played, never won (owner rule (a)): no winner label.
    assert game.live_state["winner"] is None
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


# === Spectator ===


@pytest.mark.asyncio
async def test_spectator_cannot_answer(mcqquiz_game_controller, setup_mcqquiz_game, session, create_user):
    """Spectator cannot submit answers."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]

    # Create spectator
    spectator = await create_user(username="mcq_spectator", email="mcq_spec@test.com")
    link = RoomUserLink(
        room_id=room.id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(link)
    await session.commit()

    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(SpectatorCannotAnswerError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), spectator.id, 0)


# === Get State ===


@pytest.mark.asyncio
async def test_get_state_hides_correct_answer_during_playing(mcqquiz_game_controller, setup_mcqquiz_game):
    """During playing phase, correct_answer_index is not visible."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act
    state = await mcqquiz_game_controller.get_state(UUID(result.game_id), users[0].id)

    # Assert
    assert state.correct_answer_index is None
    assert state.explanation is None
    assert state.round_results == []
    assert len(state.choices) == 4
    assert state.question != ""


@pytest.mark.asyncio
async def test_get_state_shows_results(mcqquiz_game_controller, setup_mcqquiz_game):
    """After all players answer, results are visible."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Both answer
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Act
    state = await mcqquiz_game_controller.get_state(UUID(result.game_id), users[0].id)

    # Assert
    assert state.round_phase == "results"
    assert state.correct_answer_index is not None
    assert len(state.round_results) == 2


@pytest.mark.asyncio
async def test_answer_during_results_rejected(mcqquiz_game_controller, setup_mcqquiz_game):
    """Cannot submit answer after round has ended."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Both answer → results
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Act / Assert
    with pytest.raises(RoundNotPlayingError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 2)


# === Timer Expiration ===


@pytest.mark.asyncio
async def test_timer_expired_transitions_to_results(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Timer expiration should transition from playing to results phase."""
    # Prepare — a round whose clock has really run out
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    await _expire_the_round(session, result.game_id)  # 0 is untimed, not "already expired"

    # Act
    timer_result = await mcqquiz_game_controller.handle_timer_expired(UUID(result.game_id), users[0].id)

    # Assert
    assert timer_result.action == "results"
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"


# === Choice Index Boundaries ===


@pytest.mark.asyncio
async def test_submit_choice_index_boundary_valid(mcqquiz_game_controller, setup_mcqquiz_game, session):  # noqa: ARG001
    """choice_index=3 (last valid index) should be accepted."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act — submit choice_index=3 (last valid)
    answer_result = await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 3)

    # Assert — should not raise, answer is accepted (may or may not be correct)
    assert 0 <= answer_result.points_earned <= 3

    # Verify DB state
    game = await _get_game(session, result.game_id)
    assert str(users[0].id) in game.live_state["answers"]


@pytest.mark.asyncio
async def test_submit_choice_index_4_invalid(mcqquiz_game_controller, setup_mcqquiz_game):
    """choice_index=4 should be rejected."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(InvalidChoiceIndexError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 4)


@pytest.mark.asyncio
async def test_submit_choice_index_negative_invalid(mcqquiz_game_controller, setup_mcqquiz_game):
    """choice_index=-1 should be rejected."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(InvalidChoiceIndexError):
        await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, -1)


# === Final Round Ends Game ===


@pytest.mark.asyncio
async def test_advance_final_round_ends_game(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Advancing past final round ends game."""
    # Prepare — 2 round game
    setup = await setup_mcqquiz_game(num_players=1, num_questions=5)
    room, users = setup["room"], setup["users"]
    room.settings = {"mcq_quiz_rounds": 2}
    session.add(room)
    await session.commit()

    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Round 1 — answer and advance
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)
    await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Round 2 — answer and advance (should end game)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)
    await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["game_over"] is True
    assert game.live_state["round_phase"] == "game_over"
    # A solo game is played, never won (owner rule (a)): no winner label.
    assert game.live_state["winner"] is None
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


# === Get State — Explanation During Results ===


@pytest.mark.asyncio
async def test_get_state_shows_explanation_during_results(mcqquiz_game_controller, setup_mcqquiz_game):
    """During results phase, explanation should be visible."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Both answer → results
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Act
    state = await mcqquiz_game_controller.get_state(UUID(result.game_id), users[0].id)

    # Assert
    assert state.round_phase == "results"
    assert state.explanation is not None
    assert state.explanation != ""
    assert state.correct_answer_index is not None


# === Score Accumulation ===


@pytest.mark.asyncio
async def test_multiple_rounds_score_accumulation(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Score should accumulate correctly across multiple rounds."""
    # Prepare — 2 round game
    setup = await setup_mcqquiz_game(num_players=1, num_questions=5)
    room, users = setup["room"], setup["users"]
    room.settings = {"mcq_quiz_rounds": 2}
    session.add(room)
    await session.commit()

    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Round 1 — answer correctly
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)

    # Check score after round 1 — fast answer gets 1-3 points
    game = await _get_game(session, result.game_id)
    score_after_r1 = game.live_state["players"][0]["total_score"]
    assert 1 <= score_after_r1 <= 3

    # Advance to round 2
    await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Round 2 — answer correctly again
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)

    # Assert — score should accumulate (each correct answer is 1-3 points)
    game = await _get_game(session, result.game_id)
    assert game.live_state["players"][0]["total_score"] > score_after_r1


# === Get State Spectator ===


@pytest.mark.asyncio
async def test_get_state_spectator(mcqquiz_game_controller, setup_mcqquiz_game, session, create_user):
    """Spectator gets state with is_spectator=True."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]

    spectator = await create_user(username="mcq_spec2", email="mcq_spec2@test.com")
    link = RoomUserLink(
        room_id=room.id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(link)
    await session.commit()

    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act
    state = await mcqquiz_game_controller.get_state(UUID(result.game_id), spectator.id)

    # Assert
    assert state.is_spectator is True
    assert state.my_answered is False
    assert state.my_points == 0
    assert state.round_phase == "playing"


# === Insufficient Questions ===


@pytest.mark.asyncio
async def test_create_insufficient_questions(mcqquiz_game_controller, setup_mcqquiz_game, session):  # noqa: ARG001
    """Creating game with not enough questions should raise error."""

    # Prepare — 0 questions available, but need 10 rounds (default)
    setup = await setup_mcqquiz_game(num_players=1, num_questions=0)
    room, users = setup["room"], setup["users"]

    # Act / Assert
    with pytest.raises(NoMcqQuestionsAvailableError):
        await _start_game(mcqquiz_game_controller, room.id, users[0].id)


# === The reveal: nothing about the open question leaks, everything survives a reload after ===


@pytest.mark.asyncio
async def test_open_question_withholds_every_players_round_points(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """While the question is open, nobody's state shows what anyone's lock-in earned.

    Points are added at lock-in, so a live `total_score` (or `current_round_points`)
    moving by 1-3 told the table who had just been right before the reveal.
    """
    # Prepare — round 2, so there is a previous score to freeze at
    setup = await setup_mcqquiz_game(num_players=3)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    for p in game.live_state["players"]:
        p["total_score"] = 5 if p["user_id"] == str(users[1].id) else 0
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    correct_index = game.live_state["current_question"]["correct_answer_index"]

    # Act — player 1 locks in the right answer, player 2 a wrong one; player 0 has not answered
    earned = await mcqquiz_game_controller.submit_answer(game_id, users[1].id, correct_index)
    await mcqquiz_game_controller.submit_answer(game_id, users[2].id, (correct_index + 1) % 4)
    views = [await mcqquiz_game_controller.get_state(game_id, u.id) for u in users]

    # Assert — the DB holds the real total, every view the pre-round one
    stored = await _get_game(session, result.game_id)
    stored_score = next(p["total_score"] for p in stored.live_state["players"] if p["user_id"] == str(users[1].id))
    assert stored_score == 5 + earned.points_earned
    for view in views:
        assert view.round_phase == "playing"
        by_id = {p.user_id: p for p in view.players}
        assert by_id[str(users[1].id)].total_score == 5
        assert all(p.current_round_points == 0 for p in view.players)
        assert [p.current_round_answered for p in view.players] == [False, True, True]
        assert {p.user_id: p.total_score for p in view.leaderboard} == {p.user_id: p.total_score for p in view.players}
        assert view.my_points == 0
        assert view.choice_tallies is None
        assert view.my_choice_index is None
        assert view.my_answer_time_ms is None
        assert view.round_results == []


@pytest.mark.asyncio
async def test_reveal_carries_tallies_choices_and_times_from_the_server(
    mcqquiz_game_controller, setup_mcqquiz_game, session
):
    """Once the round resolves the state carries the tallies, each choice, and the caller's own pick and time."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=3)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]
    wrong_index = (correct_index + 1) % 4

    # Act — everyone answers, which resolves the round
    first = await mcqquiz_game_controller.submit_answer(game_id, users[0].id, correct_index)
    await mcqquiz_game_controller.submit_answer(game_id, users[1].id, correct_index)
    await mcqquiz_game_controller.submit_answer(game_id, users[2].id, wrong_index)
    view = await mcqquiz_game_controller.get_state(game_id, users[0].id)
    other_view = await mcqquiz_game_controller.get_state(game_id, users[2].id)

    # Assert
    assert view.round_phase == "results"
    expected_tallies = [0, 0, 0, 0]
    expected_tallies[correct_index] = 2
    expected_tallies[wrong_index] = 1
    assert view.choice_tallies == expected_tallies
    assert view.my_choice_index == correct_index
    assert view.my_answer_time_ms is not None and view.my_answer_time_ms >= 0
    assert view.my_points == first.points_earned
    assert other_view.my_choice_index == wrong_index
    assert other_view.my_points == 0
    results = {r.user_id: r for r in view.round_results}
    assert results[str(users[2].id)].choice_index == wrong_index
    assert all(r.answer_time_ms is not None for r in view.round_results)
    by_id = {p.user_id: p for p in view.players}
    assert by_id[str(users[0].id)].total_score == first.points_earned
    assert by_id[str(users[0].id)].current_round_points == first.points_earned
    # The times are what the DB recorded at lock-in
    stored = await _get_game(session, result.game_id)
    assert stored.live_state["answers"][str(users[0].id)]["answer_time_ms"] == view.my_answer_time_ms


@pytest.mark.asyncio
async def test_reveal_after_a_timeout_counts_only_the_answers_given(
    mcqquiz_game_controller, setup_mcqquiz_game, session
):
    """A player who never answered has no choice and no time; the tallies count the others."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)
    await mcqquiz_game_controller.submit_answer(game_id, users[0].id, 2)
    game = await _get_game(session, result.game_id)
    game.live_state["round_started_at"] = "2000-01-01T00:00:00+00:00"
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    await mcqquiz_game_controller.handle_timer_expired(game_id, users[0].id)
    silent = await mcqquiz_game_controller.get_state(game_id, users[1].id)

    # Assert
    assert silent.round_phase == "results"
    assert silent.choice_tallies == [0, 0, 1, 0]
    assert silent.my_choice_index is None
    assert silent.my_answer_time_ms is None
    mine = next(r for r in silent.round_results if r.user_id == str(users[1].id))
    assert (mine.choice_index, mine.answer_time_ms, mine.points) == (None, None, 0)


@pytest.mark.asyncio
async def test_state_carries_the_colophon(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """The state names the starting host and the game's UTC start (and end, once over)."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)

    # Act
    running = await mcqquiz_game_controller.get_state(game_id, users[0].id)

    # Assert
    stored = await _get_game(session, result.game_id)
    assert stored.live_state["host_username"] == users[0].username
    assert running.host_username == users[0].username
    assert running.started_at is not None and running.started_at.utcoffset() is not None
    assert running.ended_at is None


# === WP-10: who wins a quiz (owner rule (a), BR-11, PD-10) ===


async def _start_one_round(controller, setup_mcqquiz_game, session, num_players: int = 2):
    """A one-question MCQ, started by the first player (the host)."""
    setup = await setup_mcqquiz_game(num_players=num_players, num_questions=3)
    room, users = setup["room"], setup["users"]
    room.settings = {**(room.settings or {}), "mcq_quiz_rounds": 1}
    session.add(room)
    await session.commit()
    result = await _start_game(controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    return room, users, result.game_id, game.live_state["current_question"]["correct_answer_index"]


async def _wins_by_user(session: AsyncSession) -> dict[str, int]:
    rows = (await session.exec(select(UserStats).execution_options(populate_existing=True))).all()
    return {str(row.user_id): row.total_games_won for row in rows}


@pytest.mark.asyncio
async def test_a_nil_nil_game_has_no_winner(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """Everybody answered wrong (0-0-0): no winner label, no winner_ids, no win for anyone."""
    # Prepare
    _, users, game_id, correct = await _start_one_round(
        mcqquiz_game_controller, setup_mcqquiz_game, session, num_players=3
    )
    gid = UUID(game_id)
    for user in users:
        await mcqquiz_game_controller.submit_answer(gid, user.id, (correct + 1) % 4)

    # Act
    await mcqquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await mcqquiz_game_controller.get_state(gid, users[2].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] is None
    assert game.live_state[WINNER_IDS_KEY] == []
    assert (over.winner, over.winner_ids) == (None, [])
    assert set((await _wins_by_user(session)).values()) == {0}


@pytest.mark.asyncio
async def test_a_solo_game_has_no_winner(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """A solo quiz answered right is still not a win."""
    # Prepare
    _, users, game_id, correct = await _start_one_round(
        mcqquiz_game_controller, setup_mcqquiz_game, session, num_players=1
    )
    gid = UUID(game_id)
    await mcqquiz_game_controller.submit_answer(gid, users[0].id, correct)

    # Act
    await mcqquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await mcqquiz_game_controller.get_state(gid, users[0].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.live_state["winner"] is None
    assert game.live_state[WINNER_IDS_KEY] == []
    assert (over.winner, over.winner_ids) == (None, [])


@pytest.mark.asyncio
async def test_a_tie_at_the_top_is_a_shared_win(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """4-4-1: no single label, both leaders in winner_ids and credited, the third is not."""
    # Prepare — the question is resolved; the scores are set as a longer game would leave them
    _, users, game_id, correct = await _start_one_round(
        mcqquiz_game_controller, setup_mcqquiz_game, session, num_players=3
    )
    gid = UUID(game_id)
    for user in users:
        await mcqquiz_game_controller.submit_answer(gid, user.id, correct)
    game = await _reload(session, game_id)
    scores = {str(users[0].id): 4, str(users[1].id): 1, str(users[2].id): 4}
    for player in game.live_state["players"]:
        player["total_score"] = scores[player["user_id"]]
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    await mcqquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await mcqquiz_game_controller.get_state(gid, users[1].id)

    # Assert
    leaders = sorted([str(users[0].id), str(users[2].id)])
    game = await _reload(session, game_id)
    assert game.live_state["winner"] is None
    assert game.live_state[WINNER_IDS_KEY] == leaders
    assert (over.winner, over.winner_ids) == (None, leaders)
    wins = await _wins_by_user(session)
    assert (wins[str(users[0].id)], wins[str(users[1].id)], wins[str(users[2].id)]) == (1, 0, 1)


@pytest.mark.asyncio
async def test_a_clear_lead_names_the_winner(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """One top scorer: named by username, alone in winner_ids."""
    # Prepare — only the second player is right
    _, users, game_id, correct = await _start_one_round(mcqquiz_game_controller, setup_mcqquiz_game, session)
    gid = UUID(game_id)
    await mcqquiz_game_controller.submit_answer(gid, users[0].id, (correct + 1) % 4)
    await mcqquiz_game_controller.submit_answer(gid, users[1].id, correct)

    # Act
    await mcqquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await mcqquiz_game_controller.get_state(gid, users[0].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.live_state["winner"] == users[1].username
    assert game.live_state[WINNER_IDS_KEY] == [str(users[1].id)]
    assert (over.winner, over.winner_ids) == (users[1].username, [str(users[1].id)])


@pytest.mark.asyncio
async def test_finishing_a_game_the_room_moved_on_from_leaves_the_room_alone(
    mcqquiz_game_controller, setup_mcqquiz_game, session
):
    """The finish only detaches the room from THIS game (detach_room_if_current, BR-06)."""
    # Prepare — the room already points at another game
    room, users, game_id, correct = await _start_one_round(mcqquiz_game_controller, setup_mcqquiz_game, session)
    newer = Game(room_id=room.id, number_of_players=2, type=GameType.MCQ_QUIZ, game_status=GameStatus.IN_PROGRESS)
    session.add(newer)
    await session.commit()
    newer_id = newer.id
    stored_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    stored_room.active_game_id = newer_id
    session.add(stored_room)
    await session.commit()
    for user in users:
        await mcqquiz_game_controller.submit_answer(UUID(game_id), user.id, correct)

    # Act
    await mcqquiz_game_controller.advance_to_next_round(UUID(game_id), users[0].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    stored_room = (
        await session.exec(select(Room).where(Room.id == room.id).execution_options(populate_existing=True))
    ).one()
    assert stored_room.active_game_id == newer_id


# === WP-10: status, timer and caller guards (BR-18, BR-17, BR-13 / SEC F08, SEC F05) ===


@pytest.mark.asyncio
async def test_an_answer_on_a_cancelled_game_is_refused(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """A cancelled game no longer moves: the right choice scores nothing."""
    # Prepare
    room, users, game_id, correct = await _start_one_round(mcqquiz_game_controller, setup_mcqquiz_game, session)
    game = await _reload(session, game_id)
    stored_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    assert await cancel_running_game(session, game, stored_room) is True
    await session.commit()

    # Act / Assert
    with pytest.raises(GameAlreadyOverError):
        await mcqquiz_game_controller.submit_answer(UUID(game_id), users[1].id, correct)

    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.CANCELLED
    assert game.live_state["answers"] == {}
    assert all(p["total_score"] == 0 for p in game.live_state["players"])


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", [0, -5])
async def test_a_round_without_a_positive_duration_never_expires(
    mcqquiz_game_controller, setup_mcqquiz_game, session, duration: int
):
    """A stored duration of 0 or less is untimed: timer-expired answers timer_not_expired."""
    # Prepare
    _, users, game_id, _ = await _start_one_round(mcqquiz_game_controller, setup_mcqquiz_game, session)
    game = await _reload(session, game_id)
    game.live_state["turn_duration_seconds"] = duration
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    await _expire_the_round(session, game_id)

    # Act
    timer_result = await mcqquiz_game_controller.handle_timer_expired(UUID(game_id), users[1].id)

    # Assert
    assert timer_result.action == TimerExpiredAction.TIMER_NOT_EXPIRED
    game = await _reload(session, game_id)
    assert game.live_state["round_phase"] == "playing"
    assert mcqquiz_game_controller._phase_timer(game.live_state) is None


@pytest.mark.asyncio
async def test_a_stranger_cannot_fire_the_timer(mcqquiz_game_controller, setup_mcqquiz_game, session, create_user):
    """Only someone in the game fires its timer, even once it has really run out."""
    # Prepare
    _, _, game_id, _ = await _start_one_round(mcqquiz_game_controller, setup_mcqquiz_game, session)
    await _expire_the_round(session, game_id)
    stranger = await create_user(username="mcqstranger", email="mcqstranger@test.com")

    # Act / Assert
    with pytest.raises(NotAGameParticipantError):
        await mcqquiz_game_controller.handle_timer_expired(UUID(game_id), stranger.id)

    game = await _reload(session, game_id)
    assert game.live_state["round_phase"] == "playing"


@pytest.mark.asyncio
async def test_a_hostless_room_advances_when_every_player_is_ready(
    mcqquiz_game_controller, setup_mcqquiz_game, session
):
    """The host deleted their account (owner_id NULL): every player is in the ready quorum (SEC F05)."""
    # Prepare — a 2-question game in results, its room without an owner
    setup = await setup_mcqquiz_game(num_players=2, num_questions=3)
    room, users = setup["room"], setup["users"]
    room.settings = {**(room.settings or {}), "mcq_quiz_rounds": 2}
    session.add(room)
    await session.commit()
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    gid = UUID(result.game_id)
    correct = (await _get_game(session, result.game_id)).live_state["current_question"]["correct_answer_index"]
    for user in users:
        await mcqquiz_game_controller.submit_answer(gid, user.id, correct)
    stored_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    stored_room.owner_id = None
    session.add(stored_room)
    await session.commit()

    # Act
    first = await mcqquiz_game_controller.advance_to_next_round(gid, users[0].id)
    second = await mcqquiz_game_controller.advance_to_next_round(gid, users[1].id)

    # Assert
    assert (first.advanced, first.ready_count, first.total_players) == (False, 1, 2)
    assert second.advanced is True
    game = await _reload(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"
