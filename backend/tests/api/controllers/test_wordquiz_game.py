"""Tests for WordQuiz game controller."""

from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import DEFAULT_WORD_QUIZ_ROUNDS
from ipg.api.controllers.wordquiz_game import WordQuizGameController
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game
from ipg.api.schemas.error import (
    AlreadyAnsweredError,
    EmptyAnswerError,
    NotHostError,
    RoundNotPlayingError,
    SpectatorCannotAnswerError,
)


async def _start_game(controller: WordQuizGameController, room_id, user_id):
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


# === Game Creation ===


@pytest.mark.asyncio
async def test_create_and_start_1_player(wordquiz_game_controller, setup_wordquiz_game, session):
    """Word Quiz supports 1 player — game starts successfully."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert len(state["players"]) == 1
    assert state["round_phase"] == "playing"
    assert state["current_round"] == 1
    assert state["current_word"] is not None


@pytest.mark.asyncio
async def test_create_and_start_multiple_players(wordquiz_game_controller, setup_wordquiz_game, session):
    """Multiple players start correctly with proper live_state structure."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=3)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert len(state["players"]) == 3
    assert state["total_rounds"] == DEFAULT_WORD_QUIZ_ROUNDS
    assert state["hints_revealed"] == 1
    assert state["round_phase"] == "playing"
    assert state["game_over"] is False
    assert state["winner"] is None
    assert state["answers"] == {}
    assert len(state["used_word_ids"]) == 1


# === Answer Submission ===


@pytest.mark.asyncio
async def test_submit_correct_answer(wordquiz_game_controller, setup_wordquiz_game, session):
    """Correct answer awards points = max_hints - hint + 1."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Assert
    assert answer_result.correct is True
    assert answer_result.points_earned > 0


@pytest.mark.asyncio
async def test_submit_wrong_answer(wordquiz_game_controller, setup_wordquiz_game):
    """Wrong answer gives 0 points, player can retry."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(
        UUID(result.game_id), users[0].id, "TotallyWrongAnswer"
    )

    # Assert
    assert answer_result.correct is False
    assert answer_result.points_earned == 0


@pytest.mark.asyncio
async def test_submit_answer_arabic_diacritics(
    wordquiz_game_controller, setup_wordquiz_game, session, create_quiz_word
):
    """Arabic answer with diacritics matches the stripped version."""
    # Prepare — create a word with known Arabic answer
    setup = await setup_wordquiz_game(num_players=1, num_words=0)
    room, users = setup["room"], setup["users"]
    await create_quiz_word(word_en="TestArabic", word_ar="إبراهيم")
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    word_ar = game.live_state["current_word"].get("word_ar")

    if word_ar:
        # Act — submit with diacritics
        answer_result = await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, "إِبْرَاهِيم")
        # Assert — should match since diacritics are stripped
        # This test depends on the word picked; if it's "TestArabic", the Arabic is "إبراهيم"
        # and "إِبْرَاهِيم" should normalize to "إبراهيم"
        assert answer_result.correct is True


@pytest.mark.asyncio
async def test_submit_answer_case_insensitive(wordquiz_game_controller, setup_wordquiz_game, session):
    """Answer matching is case insensitive."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(
        UUID(result.game_id), users[0].id, correct_word.upper()
    )

    # Assert
    assert answer_result.correct is True


@pytest.mark.asyncio
async def test_submit_answer_whitespace(wordquiz_game_controller, setup_wordquiz_game, session):
    """Whitespace around answer is stripped before matching."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(
        UUID(result.game_id), users[0].id, f"  {correct_word}  "
    )

    # Assert
    assert answer_result.correct is True


@pytest.mark.asyncio
async def test_already_answered_rejected(wordquiz_game_controller, setup_wordquiz_game, session):
    """Cannot answer twice after a correct answer."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Act — first answer
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Assert — second answer rejected
    with pytest.raises(AlreadyAnsweredError):
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)


@pytest.mark.asyncio
async def test_empty_answer_rejected(wordquiz_game_controller, setup_wordquiz_game):
    """Empty answer is rejected."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(EmptyAnswerError):
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, "   ")


@pytest.mark.asyncio
async def test_all_players_answered_auto_results(wordquiz_game_controller, setup_wordquiz_game, session):
    """When all players answer correctly, round_phase transitions to 'results'."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Act
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, correct_word)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"
    assert len(game.live_state["round_results"]) == 2


# === Timer ===


@pytest.mark.asyncio
async def test_timer_expired_non_host_rejected(wordquiz_game_controller, setup_wordquiz_game):
    """Non-host cannot trigger timer expiration."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Act / Assert — users[1] is not host
    with pytest.raises(NotHostError):
        await wordquiz_game_controller.handle_timer_expired(UUID(result.game_id), users[1].id)


# === Round Advancement ===


@pytest.mark.asyncio
async def test_advance_to_next_round(wordquiz_game_controller, setup_wordquiz_game, session):
    """After results, host can advance to next round."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2, num_words=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Answer correctly and transition to results
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, correct_word)

    # Act
    await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"
    assert game.live_state["answers"] == {}
    assert len(game.live_state["used_word_ids"]) == 2


@pytest.mark.asyncio
async def test_advance_non_host_rejected(wordquiz_game_controller, setup_wordquiz_game, session):
    """Non-host cannot advance to next round."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, correct_word)

    # Act / Assert
    with pytest.raises(NotHostError):
        await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)


@pytest.mark.asyncio
async def test_game_over_after_all_rounds(wordquiz_game_controller, setup_wordquiz_game, session):
    """Game ends after all rounds are played."""
    # Prepare — 1 round game
    setup = await setup_wordquiz_game(num_players=1, num_words=3)
    room, users = setup["room"], setup["users"]
    room.settings = {"word_quiz_rounds": 1}
    session.add(room)
    await session.commit()

    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Answer and go to results
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Act — advance (should end game since total_rounds=1)
    await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["game_over"] is True
    assert game.live_state["round_phase"] == "game_over"
    assert game.live_state["winner"] is not None


# === Points ===


@pytest.mark.asyncio
async def test_points_at_hint_1(wordquiz_game_controller, setup_wordquiz_game, session):
    """Answering at hint 1 gives max points (6)."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Act — answer immediately (hint 1)
    answer_result = await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Assert
    assert answer_result.hint_number == 1
    assert answer_result.points_earned == 6  # max_hints(6) - hint(1) + 1


# === Normalization ===


@pytest.mark.asyncio
async def test_normalize_answer_static():
    """Static normalization works correctly."""
    normalize = WordQuizGameController._normalize_answer

    assert normalize("  Ibrahim  ") == "ibrahim"
    assert normalize("IBRAHIM") == "ibrahim"
    assert normalize("إِبْرَاهِيم") == "إبراهيم"
    assert normalize("  multiple   spaces  ") == "multiple spaces"
    assert normalize("") == ""
    # Hyphens are replaced with spaces so "Al-Aqsa" matches "Al Aqsa"
    assert normalize("Al-Aqsa") == "al aqsa"
    assert normalize("Al Aqsa") == "al aqsa"
    assert normalize("al-aqsa") == "al aqsa"
    # Latin diacritics are stripped so "Aid" matches "Aïd", "Medine" matches "Médine"
    assert normalize("Aïd") == "aid"
    assert normalize("Aid") == "aid"
    assert normalize("Médine") == "medine"
    assert normalize("Medine") == "medine"
    assert normalize("Moïse") == "moise"
    assert normalize("Noé") == "noe"


@pytest.mark.asyncio
async def test_check_answer_accepted_variants():
    """_check_answer matches against accepted_answers list."""
    word = {
        "word_en": "Ibrahim",
        "word_ar": "إبراهيم",
        "word_fr": "Ibrahim",
        "accepted_answers": {
            "en": ["Ibrahim", "Abraham"],
            "ar": ["إبراهيم", "ابراهيم"],
        },
    }

    assert WordQuizGameController._check_answer("Ibrahim", word) is True
    assert WordQuizGameController._check_answer("Abraham", word) is True
    assert WordQuizGameController._check_answer("ibrahim", word) is True
    assert WordQuizGameController._check_answer("إبراهيم", word) is True
    assert WordQuizGameController._check_answer("ابراهيم", word) is True
    assert WordQuizGameController._check_answer("WrongWord", word) is False


@pytest.mark.asyncio
async def test_check_answer_hyphen_insensitive():
    """_check_answer treats hyphens and spaces as equivalent."""
    word = {
        "word_en": "Al-Aqsa",
        "word_ar": "الأقصى",
        "word_fr": "Al-Aqsa",
        "accepted_answers": {
            "en": ["Al-Aqsa", "Aqsa", "Masjid Al-Aqsa"],
            "ar": ["الأقصى", "المسجد الأقصى"],
        },
    }

    assert WordQuizGameController._check_answer("Al-Aqsa", word) is True
    assert WordQuizGameController._check_answer("Al Aqsa", word) is True
    assert WordQuizGameController._check_answer("al aqsa", word) is True
    assert WordQuizGameController._check_answer("Masjid Al Aqsa", word) is True
    assert WordQuizGameController._check_answer("masjid al-aqsa", word) is True


# === Spectator ===


@pytest.mark.asyncio
async def test_spectator_cannot_answer(wordquiz_game_controller, setup_wordquiz_game, session, create_user):
    """Spectator cannot submit answers."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]

    # Create spectator
    spectator = await create_user(username="spectator", email="spec@test.com")
    link = RoomUserLink(
        room_id=room.id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(link)
    await session.commit()

    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(SpectatorCannotAnswerError):
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), spectator.id, "some answer")


# === Get State ===


@pytest.mark.asyncio
async def test_get_state_hides_answers_during_playing(wordquiz_game_controller, setup_wordquiz_game, session):
    """During playing phase, other players' answers are not visible."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Player 0 answers
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Act — get state for player 1
    state = await wordquiz_game_controller.get_state(UUID(result.game_id), users[1].id)

    # Assert — correct_answer should not be visible during playing
    assert state.correct_answer is None
    assert state.round_results == []


@pytest.mark.asyncio
async def test_get_state_shows_results(wordquiz_game_controller, setup_wordquiz_game, session):
    """After all players answer, results are visible."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Both answer
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, correct_word)

    # Act
    state = await wordquiz_game_controller.get_state(UUID(result.game_id), users[0].id)

    # Assert
    assert state.round_phase == "results"
    assert state.correct_answer is not None
    assert len(state.round_results) == 2


@pytest.mark.asyncio
async def test_answer_during_results_rejected(wordquiz_game_controller, setup_wordquiz_game, session):
    """Cannot submit answer after round has ended."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Both answer → results
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[1].id, correct_word)

    # Act / Assert — try to answer again (new user can't, round is over)
    with pytest.raises(RoundNotPlayingError):
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, "anything")
