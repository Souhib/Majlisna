"""Tests for MCQ Quiz game controller."""

from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.mcqquiz_game import McqQuizGameController
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game
from ipg.api.schemas.error import (
    AlreadyAnsweredError,
    InvalidChoiceIndexError,
    NotHostError,
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
    """Correct answer earns 1 point."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_index = game.live_state["current_question"]["correct_answer_index"]

    # Act
    answer_result = await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_index)

    # Assert
    assert answer_result.correct is True
    assert answer_result.points_earned == 1


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
async def test_timer_expired_non_host_rejected(mcqquiz_game_controller, setup_mcqquiz_game):
    """Non-host cannot trigger timer expiration."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)

    # Act / Assert — users[1] is not host
    with pytest.raises(NotHostError):
        await mcqquiz_game_controller.handle_timer_expired(UUID(result.game_id), users[1].id)


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
async def test_advance_non_host_rejected(mcqquiz_game_controller, setup_mcqquiz_game):
    """Non-host cannot advance to next round."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(mcqquiz_game_controller, room.id, users[0].id)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, 0)
    await mcqquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, 1)

    # Act / Assert
    with pytest.raises(NotHostError):
        await mcqquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)


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
