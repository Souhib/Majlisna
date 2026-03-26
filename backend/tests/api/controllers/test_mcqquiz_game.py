"""Tests for MCQ Quiz game controller."""

from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.mcqquiz_game import McqQuizGameController
from ipg.api.models.game import GameStatus
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game
from ipg.api.schemas.error import (
    AlreadyAnsweredError,
    InvalidChoiceIndexError,
    NoMcqQuestionsAvailableError,
    RoundNotPlayingError,
    SpectatorCannotAnswerError,
)


async def _start_game(controller: McqQuizGameController, room_id, user_id):
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


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
    room.settings = {"mcq_quiz_turn_duration": 0}  # 0 seconds = already expired
    session.add(room)
    await session.commit()
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

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
    """Non-host marks themselves as ready but round doesn't advance yet."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2, num_questions=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Act — non-host marks ready
    advance_result = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)

    # Assert — not advanced, just marked ready
    assert advance_result.advanced is False
    assert advance_result.ready_count == 1
    assert advance_result.total_players == 2
    assert str(users[1].id) in advance_result.ready_players
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"  # Still in results


@pytest.mark.asyncio
async def test_advance_all_ready_advances_round(mcqquiz_game_controller, setup_mcqquiz_game, session):
    """When all players mark ready, the round advances."""
    # Prepare — 3 players
    setup = await setup_mcqquiz_game(num_players=3, num_questions=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[2].id, 0)

    # Act — 2 non-host players mark ready, then host forces advance
    result1 = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)
    assert result1.advanced is False

    result2 = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[2].id)
    assert result2.advanced is False

    # Host forces advance
    result3 = await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)
    assert result3.advanced is True

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"


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
    assert game.live_state["winner"] is not None
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
    # Prepare — use a very short turn duration so timer is expired server-side
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    room.settings = {"mcq_quiz_turn_duration": 0}  # 0 seconds = already expired
    session.add(room)
    await session.commit()

    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

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
    assert game.live_state["winner"] is not None
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
