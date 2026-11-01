"""Tests for WordQuiz game controller."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DEFAULT_WORD_QUIZ_MAX_HINTS,
    DEFAULT_WORD_QUIZ_ROUNDS,
    WINNER_IDS_KEY,
    WORDQUIZ_MAX_ATTEMPTS_PER_ROUND,
    WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY,
)
from majlisna.api.controllers.game_cancel import cancel_running_game
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.common import TimerExpiredAction
from majlisna.api.schemas.error import (
    AlreadyAnsweredError,
    AnswerAttemptsExhaustedError,
    EmptyAnswerError,
    GameAlreadyOverError,
    NotAGameParticipantError,
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

    # Verify DB state
    game = await _get_game(session, result.game_id)
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[0].id))
    assert player["total_score"] == answer_result.points_earned
    assert str(users[0].id) in game.live_state["answers"]


@pytest.mark.asyncio
async def test_submit_wrong_answer(wordquiz_game_controller, setup_wordquiz_game, session):
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

    # Verify DB state — wrong answer doesn't lock player out (can retry)
    game = await _get_game(session, result.game_id)
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[0].id))
    assert player["total_score"] == 0


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

    # Verify DB state
    game = await _get_game(session, result.game_id)
    assert str(users[0].id) in game.live_state["answers"]


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

    # Verify DB state
    game = await _get_game(session, result.game_id)
    assert str(users[0].id) in game.live_state["answers"]


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
async def test_timer_expired_non_host_allowed(wordquiz_game_controller, setup_wordquiz_game, session):
    """Any player can trigger timer expiration — not just host."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    await _expire_the_round(session, result.game_id)  # 0 is untimed, not "already expired"

    # Act — non-host triggers timer expiration
    timer_result = await wordquiz_game_controller.handle_timer_expired(UUID(result.game_id), users[1].id)

    # Assert — should succeed
    assert timer_result.action == "results"

    # Verify DB state
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"


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
async def test_advance_non_host_marks_ready(wordquiz_game_controller, setup_wordquiz_game, session):
    """A non-host marks themselves ready; the round waits for the rest."""
    # Prepare — 3 players so one ready mark is not yet the whole quorum
    setup = await setup_wordquiz_game(num_players=3, num_words=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]
    for user in users:
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), user.id, correct_word)

    # Act — one of the two non-hosts marks ready
    advance_result = await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)

    # Assert — not advanced, just marked ready. `total_players` reports what
    # readiness is measured against: everyone but the host.
    assert advance_result.advanced is False
    assert advance_result.ready_count == 1
    assert advance_result.total_players == 2
    assert str(users[1].id) in advance_result.ready_players
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"  # Still in results


@pytest.mark.asyncio
async def test_advance_all_ready_advances_round_without_the_host(
    wordquiz_game_controller, setup_wordquiz_game, session
):
    """ "Everyone is ready" must be reachable — it never was.

    The host advances by pressing next and is never added to ``ready_players``, so
    requiring ``len(ready_players) == len(players)`` could not be satisfied while
    the host was also a player, i.e. in every normal game. The documented feature
    collapsed to "only the host can advance", and an absent host stalled the quiz
    with nothing to rescue it — the results phase has no timeout.
    """
    # Prepare — 3 players: users[0] hosts, users[1] and users[2] do not
    setup = await setup_wordquiz_game(num_players=3, num_words=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]
    for user in users:
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), user.id, correct_word)

    # Act — both non-hosts mark ready; the host does nothing at all
    first = await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[1].id)
    second = await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[2].id)

    # Assert
    assert first.advanced is False
    assert second.advanced is True
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"
    assert game.live_state["ready_players"] == []


@pytest.mark.asyncio
async def test_host_advances_the_round_on_their_own(wordquiz_game_controller, setup_wordquiz_game, session):
    """The host override still bypasses readiness entirely."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=3, num_words=5)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]
    for user in users:
        await wordquiz_game_controller.submit_answer(UUID(result.game_id), user.id, correct_word)

    # Act — nobody has marked ready
    advance_result = await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    assert advance_result.advanced is True
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_round"] == 2


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
    # A solo game is played, never won (owner rule (a)): no winner label.
    assert game.live_state["winner"] is None
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


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

    # Verify DB state
    game = await _get_game(session, result.game_id)
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[0].id))
    assert player["total_score"] == 6


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


@pytest.mark.asyncio
async def test_check_answer_al_prefix_flexible():
    """_check_answer matches with or without the 'Al' prefix."""
    word = {
        "word_en": "Al-Bukhari",
        "word_ar": "البخاري",
        "word_fr": "Al-Bukhari",
        "accepted_answers": {"en": ["Al-Bukhari", "Bukhari"]},
    }

    # With prefix
    assert WordQuizGameController._check_answer("Al-Bukhari", word) is True
    assert WordQuizGameController._check_answer("Al Bukhari", word) is True
    # Without prefix — should still match via _strip_article
    assert WordQuizGameController._check_answer("Bukhari", word) is True
    assert WordQuizGameController._check_answer("bukhari", word) is True

    # Test another word where user types "Al" but the answer doesn't have it
    word2 = {
        "word_en": "Makkah",
        "word_ar": "مكة",
        "word_fr": "La Mecque",
        "accepted_answers": {"en": ["Makkah", "Mecca"]},
    }
    assert WordQuizGameController._check_answer("Makkah", word2) is True
    assert WordQuizGameController._check_answer("Mecca", word2) is True


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


# === Timer Expiration ===


@pytest.mark.asyncio
async def test_timer_expired_transitions_to_results(wordquiz_game_controller, setup_wordquiz_game, session):
    """Timer expiration should transition from playing to results phase."""
    # Prepare — a round whose clock has really run out
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    await _expire_the_round(session, result.game_id)  # 0 is untimed, not "already expired"

    # Act
    timer_result = await wordquiz_game_controller.handle_timer_expired(UUID(result.game_id), users[0].id)

    # Assert
    assert timer_result.action == "results"
    game = await _get_game(session, result.game_id)
    assert game.live_state["round_phase"] == "results"


# === Points at Different Hints ===


@pytest.mark.asyncio
async def test_points_at_hint_2(wordquiz_game_controller, setup_wordquiz_game, session):
    """Answering at hint 2 gives 5 points (max_hints(6) - hint(2) + 1)."""
    # Prepare — set hint_interval to 0 so all hints reveal instantly,
    # but we need elapsed to land on hint 2. hint_interval=1 means hint = floor(elapsed/1)+1.
    # We manipulate round_started_at to simulate elapsed time.
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    # Manipulate round_started_at to simulate 1 * hint_interval elapsed (hint 2)
    hint_interval = game.live_state.get("hint_interval_seconds", 10)
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=hint_interval)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Assert
    assert answer_result.hint_number == 2
    assert answer_result.points_earned == 5


@pytest.mark.asyncio
async def test_points_at_hint_3(wordquiz_game_controller, setup_wordquiz_game, session):
    """Answering at hint 3 gives 4 points (max_hints(6) - hint(3) + 1)."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    hint_interval = game.live_state.get("hint_interval_seconds", 10)
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=hint_interval * 2)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Assert
    assert answer_result.hint_number == 3
    assert answer_result.points_earned == 4


@pytest.mark.asyncio
async def test_points_at_hint_6(wordquiz_game_controller, setup_wordquiz_game, session):
    """Answering at hint 6 gives 1 point (max_hints(6) - hint(6) + 1)."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]

    hint_interval = game.live_state.get("hint_interval_seconds", 10)
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=hint_interval * 5)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    answer_result = await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)

    # Assert
    assert answer_result.hint_number == 6
    assert answer_result.points_earned == 1


# === Normalization — Arabic ===


@pytest.mark.asyncio
async def test_normalize_answer_arabic_diacritics():
    """Arabic diacritics (fathah, kasrah, dammah, sukun, shadda, tanwin) are stripped."""
    normalize = WordQuizGameController._normalize_answer

    # fathah (U+064E), kasrah (U+0650), dammah (U+064F)
    assert normalize("مُحَمَّد") == "محمد"
    # sukun (U+0652)
    assert normalize("قُرْآن") == "قرآن"
    # tanwin: fathatan (U+064B), kasratan (U+064D), dammatan (U+064C)
    assert normalize("كِتَابًا") == "كتابا"


# === Normalization — Latin ===


@pytest.mark.asyncio
async def test_normalize_answer_latin_diacritics():
    """Latin diacritics are stripped (e.g., e with acute, u with umlaut)."""
    normalize = WordQuizGameController._normalize_answer

    assert normalize("café") == "cafe"
    assert normalize("über") == "uber"
    assert normalize("naïve") == "naive"
    assert normalize("résumé") == "resume"
    assert normalize("Zürich") == "zurich"


# === Check Answer — Arabic Variant ===


@pytest.mark.asyncio
async def test_check_answer_arabic_variant():
    """_check_answer matches with Arabic accepted_answers."""
    word = {
        "word_en": "Quran",
        "word_ar": "القرآن",
        "word_fr": "Coran",
        "accepted_answers": {
            "en": ["Quran", "Qur'an"],
            "ar": ["القرآن", "قرآن", "القران"],
        },
    }

    # Direct Arabic match
    assert WordQuizGameController._check_answer("القرآن", word) is True
    # Without alef-lam prefix via accepted_answers
    assert WordQuizGameController._check_answer("قرآن", word) is True
    # Without hamza on alef
    assert WordQuizGameController._check_answer("القران", word) is True
    # English variant
    assert WordQuizGameController._check_answer("Qur'an", word) is True
    # Wrong answer
    assert WordQuizGameController._check_answer("الكتاب", word) is False


# === Advance Final Round Ends Game ===


@pytest.mark.asyncio
async def test_advance_final_round_ends_game(wordquiz_game_controller, setup_wordquiz_game, session):
    """Advancing past the last round should end the game."""
    # Prepare — 2 round game
    setup = await setup_wordquiz_game(num_players=1, num_words=5)
    room, users = setup["room"], setup["users"]
    room.settings = {"word_quiz_rounds": 2}
    session.add(room)
    await session.commit()

    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Round 1 — answer and advance
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Round 2 — answer and advance (should end game)
    game = await _get_game(session, result.game_id)
    correct_word = game.live_state["current_word"]["word_en"]
    await wordquiz_game_controller.submit_answer(UUID(result.game_id), users[0].id, correct_word)
    await wordquiz_game_controller.advance_to_next_round(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["game_over"] is True
    assert game.live_state["round_phase"] == "game_over"
    # A solo game is played, never won (owner rule (a)): no winner label.
    assert game.live_state["winner"] is None
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


# === Calculate Hints Revealed ===


@pytest.mark.asyncio
async def test_calculate_hints_revealed_time_based():
    """_calculate_hints_revealed returns correct count based on elapsed time."""
    calc = WordQuizGameController._calculate_hints_revealed

    # 0 seconds elapsed, hint_interval=10 → 1 hint
    state = {
        "round_phase": "playing",
        "round_started_at": datetime.now(UTC).isoformat(),
        "hint_interval_seconds": 10,
        "hints_revealed": 1,
    }
    assert calc(state) == 1

    # 15 seconds elapsed, hint_interval=10 → floor(15/10)+1 = 2
    state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=15)).isoformat()
    assert calc(state) == 2

    # 55 seconds elapsed, hint_interval=10 → floor(55/10)+1 = 6 (max)
    state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=55)).isoformat()
    assert calc(state) == 6

    # 100 seconds elapsed → still capped at 6
    state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=100)).isoformat()
    assert calc(state) == 6

    # Non-playing phase returns current hints_revealed
    state["round_phase"] = "results"
    state["hints_revealed"] = 3
    assert calc(state) == 3


# === Get State Spectator ===


@pytest.mark.asyncio
async def test_get_state_spectator(wordquiz_game_controller, setup_wordquiz_game, session, create_user):
    """Spectator should get state with is_spectator=True and my_answered=False."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]

    spectator = await create_user(username="wq_spectator", email="wq_spec@test.com")
    link = RoomUserLink(
        room_id=room.id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(link)
    await session.commit()

    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Act
    state = await wordquiz_game_controller.get_state(UUID(result.game_id), spectator.id)

    # Assert
    assert state.is_spectator is True
    assert state.my_answered is False
    assert state.my_points == 0
    assert state.round_phase == "playing"


# ========== The hint ladder is released one rung at a time ==========


@pytest.mark.asyncio
async def test_state_only_carries_the_hints_released_so_far(wordquiz_game_controller, setup_wordquiz_game):
    """Shipping the whole ladder at round start was a straight scoring exploit.

    A correct answer pays ``max_hints - hint_number + 1``, where ``hint_number``
    comes from elapsed *server* time. With all six hints in the very first
    response, reading the network tab showed the most specific one at t=0 and paid
    full marks, while honest players waited out the interval for one point less
    each rung.
    """
    # Prepare — a fresh round, one hint interval into it at most
    setup = await setup_wordquiz_game(2)
    result = await _start_game(wordquiz_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)

    # Act
    state = await wordquiz_game_controller.get_state(game_uuid, setup["users"][1].id)

    # Assert — exactly the revealed prefix, and the ladder length reported separately
    assert state.hints_revealed == 1
    assert len(state.hints) == 1
    assert state.max_hints == DEFAULT_WORD_QUIZ_MAX_HINTS


@pytest.mark.asyncio
async def test_hints_appear_as_the_round_clock_advances(wordquiz_game_controller, setup_wordquiz_game, session):
    """The rungs already earned are still served — the cap tracks server time, not a constant."""
    # Prepare — push the round start back past three hint intervals
    setup = await setup_wordquiz_game(2)
    result = await _start_game(wordquiz_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    interval = game.live_state["hint_interval_seconds"]
    state_dict = game.live_state
    state_dict["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=interval * 2 + 1)).isoformat()
    game.live_state = state_dict
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    state = await wordquiz_game_controller.get_state(UUID(result.game_id), setup["users"][1].id)

    # Assert
    assert state.hints_revealed == 3
    assert len(state.hints) == 3


# === The round's results: category, what each player typed, never before the reveal ===


@pytest.mark.asyncio
async def test_state_carries_the_words_category_key(wordquiz_game_controller, setup_wordquiz_game, session):
    """The header's theme ("a prophet") comes from the stored category as a stable key."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)

    # Act
    view = await wordquiz_game_controller.get_state(UUID(result.game_id), users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["category"] == "Prophets"
    assert view.category == "prophets"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("Places", "places"), ("Islamic History", "islamic_history"), ("Poetry", None), (None, None)],
)
def test_category_key_maps_the_seeded_labels_and_nothing_else(stored: str | None, expected: str | None):
    """An admin-made category outside the seeded set reads as null rather than as raw English."""
    # Act / Assert
    assert WordQuizGameController._category_key(stored) == expected


@pytest.mark.asyncio
async def test_typed_answers_appear_only_once_the_round_resolves(
    wordquiz_game_controller, setup_wordquiz_game, session
):
    """What each player typed (and at which hint) is in the round's results, and nowhere before."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=3)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    answer = game.live_state["current_word"]["word_en"]

    # Act — player 0 misses once then finds it; player 1 only misses; player 2 types nothing
    await wordquiz_game_controller.submit_answer(game_id, users[0].id, "  Nuh ")  # none of the dealt words
    await wordquiz_game_controller.submit_answer(game_id, users[0].id, f" {answer.lower()} ")
    await wordquiz_game_controller.submit_answer(game_id, users[1].id, "Yunus")  # none of the dealt words
    while_open = await wordquiz_game_controller.get_state(game_id, users[1].id)
    game = await _get_game(session, result.game_id)
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    await wordquiz_game_controller.handle_timer_expired(game_id, users[0].id)
    revealed = await wordquiz_game_controller.get_state(game_id, users[2].id)

    # Assert — nothing typed is in the open round's payload
    assert while_open.round_results == []
    assert while_open.correct_answer is None
    assert answer.lower() not in while_open.model_dump_json().lower()
    # — and the reveal names it all
    assert revealed.round_phase == "results"
    rows = {r.user_id: r for r in revealed.round_results}
    finder = rows[str(users[0].id)]
    assert (finder.typed_answer, finder.attempts, finder.answered_at_hint) == (answer.lower(), 2, 1)
    misser = rows[str(users[1].id)]
    assert (misser.typed_answer, misser.attempts, misser.answered_at_hint, misser.points) == ("Yunus", 1, None, 0)
    silent = rows[str(users[2].id)]
    assert (silent.typed_answer, silent.attempts) == (None, 0)
    stored = await _get_game(session, result.game_id)
    assert stored.live_state["attempts"][str(users[1].id)]["last_text"] == "Yunus"


@pytest.mark.asyncio
async def test_next_round_clears_the_typed_answers(wordquiz_game_controller, setup_wordquiz_game, session):
    """A new word starts with no attempts and its own category."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    await wordquiz_game_controller.submit_answer(game_id, users[0].id, game.live_state["current_word"]["word_en"])

    # Act
    await wordquiz_game_controller.advance_to_next_round(game_id, users[0].id)

    # Assert
    stored = await _get_game(session, result.game_id)
    assert stored.live_state["current_round"] == 2
    assert stored.live_state["attempts"] == {}
    assert stored.live_state["category"] == "Prophets"


@pytest.mark.asyncio
async def test_state_carries_the_colophon_once_over(wordquiz_game_controller, setup_wordquiz_game, session):
    """At game over: the starting host's name and the UTC start and end."""
    # Prepare — a one-round game
    setup = await setup_wordquiz_game(num_players=1)
    room, users = setup["room"], setup["users"]
    room.settings = {**(room.settings or {}), "word_quiz_rounds": 1}
    session.add(room)
    await session.commit()
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    game_id = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    await wordquiz_game_controller.submit_answer(game_id, users[0].id, game.live_state["current_word"]["word_en"])

    # Act
    await wordquiz_game_controller.advance_to_next_round(game_id, users[0].id)
    over = await wordquiz_game_controller.get_state(game_id, users[0].id)

    # Assert
    assert over.game_over is True
    assert over.host_username == users[0].username
    assert over.started_at is not None and over.ended_at is not None
    assert over.started_at.utcoffset() is not None and over.ended_at.utcoffset() is not None
    assert over.ended_at >= over.started_at
    stored = await _get_game(session, result.game_id)
    assert stored.end_time is not None


# === WP-10: a wrong try costs a rung, five tries a round (owner rule (e), BR-10, SEC F15) ===


async def _reload(session: AsyncSession, game_id_str: str) -> Game:
    """The game as stored, not the instance a controller may still hold in memory."""
    statement = select(Game).where(Game.id == UUID(game_id_str)).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


async def _start_one_round(controller, setup_wordquiz_game, session, num_players: int = 2):
    """A one-round Kalimat, started by the first player (the host)."""
    setup = await setup_wordquiz_game(num_players=num_players)
    room, users = setup["room"], setup["users"]
    room.settings = {**(room.settings or {}), "word_quiz_rounds": 1}
    session.add(room)
    await session.commit()
    result = await _start_game(controller, room.id, users[0].id)
    game = await _get_game(session, result.game_id)
    return room, users, result.game_id, game.live_state["current_word"]["word_en"]


async def _expire_the_round(session: AsyncSession, game_id_str: str, seconds_ago: int = 120) -> None:
    """Move the round's anchor back so its (positive) duration has really elapsed."""
    game = await _reload(session, game_id_str)
    game.live_state["round_started_at"] = (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()


@pytest.mark.asyncio
async def test_a_wrong_try_costs_a_rung_and_counts_down_the_tries(
    wordquiz_game_controller, setup_wordquiz_game, session
):
    """Four wrong tries, then the word at hint 1: four rungs lower, and the tries count down 5, 4, 3, 2, 1."""
    # Prepare
    _, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    gid = UUID(game_id)
    seen = [(await wordquiz_game_controller.get_state(gid, users[1].id)).my_attempts_left]

    # Act — four names of the theme that are not the word, then the word, all at hint 1
    for guess in ("guess one", "guess two", "guess three", "guess four"):
        miss = await wordquiz_game_controller.submit_answer(gid, users[1].id, guess)
        assert miss.correct is False
        seen.append((await wordquiz_game_controller.get_state(gid, users[1].id)).my_attempts_left)
    found = await wordquiz_game_controller.submit_answer(gid, users[1].id, word)
    after = await wordquiz_game_controller.get_state(gid, users[1].id)

    # Assert — the response, the stored score, and the caller's view
    assert seen == [5, 4, 3, 2, 1]
    assert found.correct is True
    assert found.hint_number == 1
    rung = min(DEFAULT_WORD_QUIZ_MAX_HINTS, 1 + 4 * WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY)
    assert found.points_earned == DEFAULT_WORD_QUIZ_MAX_HINTS - rung + 1
    assert found.points_earned < DEFAULT_WORD_QUIZ_MAX_HINTS
    assert after.my_attempts_left is None
    game = await _reload(session, game_id)
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[1].id))
    assert player["total_score"] == found.points_earned
    assert game.live_state["answers"][str(users[1].id)]["points"] == found.points_earned
    assert game.live_state["attempts"][str(users[1].id)]["count"] == 5


@pytest.mark.asyncio
async def test_rungs_lost_are_the_callers_own(wordquiz_game_controller, setup_wordquiz_game, session):
    """`my_rungs_lost` counts the caller's wrong tries this round, nobody else's."""
    # Prepare
    _, users, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    gid = UUID(game_id)

    # Act
    await wordquiz_game_controller.submit_answer(gid, users[1].id, "not it")
    await wordquiz_game_controller.submit_answer(gid, users[1].id, "still not it")
    missed = await wordquiz_game_controller.get_state(gid, users[1].id)
    untouched = await wordquiz_game_controller.get_state(gid, users[0].id)

    # Assert
    assert missed.my_rungs_lost == 2 * WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY
    assert missed.my_attempts_left == WORDQUIZ_MAX_ATTEMPTS_PER_ROUND - 2
    assert untouched.my_rungs_lost == 0
    assert untouched.my_attempts_left == WORDQUIZ_MAX_ATTEMPTS_PER_ROUND


@pytest.mark.asyncio
async def test_past_the_cap_the_next_try_is_refused(wordquiz_game_controller, setup_wordquiz_game, session):
    """Walking the theme's list no longer pays: after five tries the round refuses the sixth, the word included."""
    # Prepare — the probe's walk: ten candidates, the right one last
    setup = await setup_wordquiz_game(num_players=2, num_words=10)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    gid = UUID(result.game_id)
    word = (await _get_game(session, result.game_id)).live_state["current_word"]["word_en"]
    candidates = [w.word_en for w in setup["quiz_words"] if w.word_en != word] + [word]
    for guess in candidates[:WORDQUIZ_MAX_ATTEMPTS_PER_ROUND]:
        assert (await wordquiz_game_controller.submit_answer(gid, users[1].id, guess)).correct is False

    # Act / Assert — the next try, even the word itself
    with pytest.raises(AnswerAttemptsExhaustedError) as exc_info:
        await wordquiz_game_controller.submit_answer(gid, users[1].id, word)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_params == {"max": WORDQUIZ_MAX_ATTEMPTS_PER_ROUND}

    # Assert — nothing was scored or counted by the refused try
    game = await _reload(session, result.game_id)
    assert str(users[1].id) not in game.live_state["answers"]
    assert game.live_state["attempts"][str(users[1].id)]["count"] == WORDQUIZ_MAX_ATTEMPTS_PER_ROUND
    player = next(p for p in game.live_state["players"] if p["user_id"] == str(users[1].id))
    assert player["total_score"] == 0
    view = await wordquiz_game_controller.get_state(gid, users[1].id)
    assert view.my_attempts_left == 0


@pytest.mark.asyncio
async def test_a_player_out_of_tries_is_done_with_the_round(wordquiz_game_controller, setup_wordquiz_game, session):
    """One player found the word, the other used every try: nobody is left to answer, so the round resolves."""
    # Prepare
    _, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    gid = UUID(game_id)
    await wordquiz_game_controller.submit_answer(gid, users[0].id, word)

    # Act
    for i in range(WORDQUIZ_MAX_ATTEMPTS_PER_ROUND):
        await wordquiz_game_controller.submit_answer(gid, users[1].id, f"wrong {i}")

    # Assert
    game = await _reload(session, game_id)
    assert game.live_state["round_phase"] == "results"
    rows = {r["user_id"]: r for r in game.live_state["round_results"]}
    assert rows[str(users[1].id)]["attempts"] == WORDQUIZ_MAX_ATTEMPTS_PER_ROUND
    assert rows[str(users[1].id)]["points"] == 0


@pytest.mark.asyncio
async def test_a_spectator_has_no_tries(wordquiz_game_controller, setup_wordquiz_game, session, create_user):
    """A spectator never answers, so their state carries no tries left."""
    # Prepare
    room, users, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    spectator = await create_user(username="wqwatcher", email="wqwatcher@test.com")
    session.add(RoomUserLink(room_id=room.id, user_id=spectator.id, connected=True, is_spectator=True))
    await session.commit()

    # Act
    view = await wordquiz_game_controller.get_state(UUID(game_id), spectator.id)
    player_view = await wordquiz_game_controller.get_state(UUID(game_id), users[1].id)

    # Assert
    assert view.is_spectator is True
    assert view.my_attempts_left is None
    assert player_view.my_attempts_left == WORDQUIZ_MAX_ATTEMPTS_PER_ROUND


# === WP-10: who wins a quiz (owner rule (a), BR-11, PD-10) ===


@pytest.mark.asyncio
async def test_a_tie_names_no_single_winner_and_both_share_the_win(
    wordquiz_game_controller, setup_wordquiz_game, session
):
    """6-6: no winner label, both in winner_ids, both credited with the win."""
    # Prepare
    _, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    gid = UUID(game_id)
    for user in users:
        assert (await wordquiz_game_controller.submit_answer(gid, user.id, word)).points_earned == 6

    # Act
    await wordquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await wordquiz_game_controller.get_state(gid, users[1].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] is None
    assert sorted(game.live_state[WINNER_IDS_KEY]) == sorted(str(u.id) for u in users)
    assert over.winner is None
    assert sorted(over.winner_ids) == sorted(str(u.id) for u in users)
    stats = (await session.exec(select(UserStats).execution_options(populate_existing=True))).all()
    assert {str(s.user_id): s.total_games_won for s in stats} == {str(u.id): 1 for u in users}


@pytest.mark.asyncio
async def test_a_solo_game_has_no_winner(wordquiz_game_controller, setup_wordquiz_game, session):
    """A solo Kalimat is played, never won: no label, no winner_ids, even with 6 points."""
    # Prepare
    _, users, game_id, word = await _start_one_round(
        wordquiz_game_controller, setup_wordquiz_game, session, num_players=1
    )
    gid = UUID(game_id)
    await wordquiz_game_controller.submit_answer(gid, users[0].id, word)

    # Act
    await wordquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await wordquiz_game_controller.get_state(gid, users[0].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] is None
    assert game.live_state[WINNER_IDS_KEY] == []
    assert over.winner is None
    assert over.winner_ids == []


@pytest.mark.asyncio
async def test_a_clear_lead_names_the_winner(wordquiz_game_controller, setup_wordquiz_game, session):
    """7-3: the top scorer is the winner, by name and by id."""
    # Prepare — the round is over; the scores are set as two rounds would have left them
    _, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    gid = UUID(game_id)
    await wordquiz_game_controller.submit_answer(gid, users[0].id, word)
    await wordquiz_game_controller.submit_answer(gid, users[1].id, word)
    game = await _reload(session, game_id)
    scores = {str(users[0].id): 3, str(users[1].id): 7}
    for player in game.live_state["players"]:
        player["total_score"] = scores[player["user_id"]]
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    await wordquiz_game_controller.advance_to_next_round(gid, users[0].id)
    over = await wordquiz_game_controller.get_state(gid, users[0].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.live_state["winner"] == users[1].username
    assert game.live_state[WINNER_IDS_KEY] == [str(users[1].id)]
    assert over.winner == users[1].username
    assert over.winner_ids == [str(users[1].id)]


@pytest.mark.asyncio
async def test_winner_ids_stay_empty_until_the_game_is_over(wordquiz_game_controller, setup_wordquiz_game, session):
    """Nobody has won a game still being played."""
    # Prepare
    _, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    await wordquiz_game_controller.submit_answer(UUID(game_id), users[0].id, word)

    # Act
    view = await wordquiz_game_controller.get_state(UUID(game_id), users[0].id)

    # Assert
    assert view.game_over is False
    assert view.winner is None
    assert view.winner_ids == []


@pytest.mark.asyncio
async def test_finishing_a_game_the_room_moved_on_from_leaves_the_room_alone(
    wordquiz_game_controller, setup_wordquiz_game, session
):
    """The finish only detaches the room from THIS game (detach_room_if_current, BR-06)."""
    # Prepare — the room already points at another game
    room, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    newer = Game(room_id=room.id, number_of_players=2, type=GameType.WORD_QUIZ, game_status=GameStatus.IN_PROGRESS)
    session.add(newer)
    await session.commit()
    newer_id = newer.id
    stored_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    stored_room.active_game_id = newer_id
    session.add(stored_room)
    await session.commit()
    await wordquiz_game_controller.submit_answer(UUID(game_id), users[0].id, word)
    await wordquiz_game_controller.submit_answer(UUID(game_id), users[1].id, word)

    # Act
    await wordquiz_game_controller.advance_to_next_round(UUID(game_id), users[0].id)

    # Assert
    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    stored_room = (
        await session.exec(select(Room).where(Room.id == room.id).execution_options(populate_existing=True))
    ).one()
    assert stored_room.active_game_id == newer_id


# === WP-10: status, timer and caller guards (BR-18, BR-17, BR-13 / SEC F08) ===


@pytest.mark.asyncio
async def test_an_answer_on_a_cancelled_game_is_refused(wordquiz_game_controller, setup_wordquiz_game, session):
    """A cancelled game no longer moves: the right word scores nothing (it used to score 6)."""
    # Prepare
    room, users, game_id, word = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    game = await _reload(session, game_id)
    stored_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    assert await cancel_running_game(session, game, stored_room) is True
    await session.commit()

    # Act / Assert
    with pytest.raises(GameAlreadyOverError):
        await wordquiz_game_controller.submit_answer(UUID(game_id), users[1].id, word)

    game = await _reload(session, game_id)
    assert game.game_status == GameStatus.CANCELLED
    assert game.live_state["answers"] == {}
    assert game.live_state.get("attempts", {}) == {}
    assert all(p["total_score"] == 0 for p in game.live_state["players"])


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", [0, -5])
async def test_a_round_without_a_positive_duration_never_expires(
    wordquiz_game_controller, setup_wordquiz_game, session, duration: int
):
    """A stored duration of 0 or less is untimed: timer-expired answers timer_not_expired."""
    # Prepare
    _, users, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    game = await _reload(session, game_id)
    game.live_state["turn_duration_seconds"] = duration
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    await _expire_the_round(session, game_id)

    # Act
    timer_result = await wordquiz_game_controller.handle_timer_expired(UUID(game_id), users[1].id)

    # Assert
    assert timer_result.action == TimerExpiredAction.TIMER_NOT_EXPIRED
    game = await _reload(session, game_id)
    assert game.live_state["round_phase"] == "playing"
    assert wordquiz_game_controller._phase_timer(game.live_state) is None


@pytest.mark.asyncio
async def test_a_stranger_cannot_fire_the_timer(wordquiz_game_controller, setup_wordquiz_game, session, create_user):
    """Only someone in the game fires its timer, even once it has really run out."""
    # Prepare
    _, _, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    await _expire_the_round(session, game_id)
    stranger = await create_user(username="wqstranger", email="wqstranger@test.com")

    # Act / Assert
    with pytest.raises(NotAGameParticipantError):
        await wordquiz_game_controller.handle_timer_expired(UUID(game_id), stranger.id)

    game = await _reload(session, game_id)
    assert game.live_state["round_phase"] == "playing"


@pytest.mark.asyncio
async def test_a_spectator_may_fire_the_timer(wordquiz_game_controller, setup_wordquiz_game, session, create_user):
    """A spectator's client runs the same clock and may report it."""
    # Prepare
    room, _, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    spectator = await create_user(username="wqtimewatch", email="wqtimewatch@test.com")
    session.add(RoomUserLink(room_id=room.id, user_id=spectator.id, connected=True, is_spectator=True))
    await session.commit()
    await _expire_the_round(session, game_id)

    # Act
    timer_result = await wordquiz_game_controller.handle_timer_expired(UUID(game_id), spectator.id)

    # Assert
    assert timer_result.action == TimerExpiredAction.RESULTS
    game = await _reload(session, game_id)
    assert game.live_state["round_phase"] == "results"


@pytest.mark.asyncio
async def test_a_stranger_cannot_record_a_hint_view(
    wordquiz_game_controller, setup_wordquiz_game, session, create_user
):
    """Review INT-05: Undercover's and Codenames' hint-viewed refuse a stranger; Kalimat's let
    anyone with the game id write into its ``hint_usage`` under the game lock."""
    # Prepare
    _, _, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    stranger = await create_user(username="wqhintstranger", email="wqhintstranger@test.com")

    # Act / Assert
    with pytest.raises(NotAGameParticipantError):
        await wordquiz_game_controller.record_hint_view(UUID(game_id), stranger.id)

    game = await _reload(session, game_id)
    assert str(stranger.id) not in game.live_state.get("hint_usage", {})


@pytest.mark.asyncio
async def test_a_spectators_hint_view_is_not_recorded(
    wordquiz_game_controller, setup_wordquiz_game, session, create_user
):
    """A spectator opens the hints too, but has no game to win without them: recorded False, nothing written."""
    # Prepare
    room, _, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)
    spectator = await create_user(username="wqhintwatch", email="wqhintwatch@test.com")
    session.add(RoomUserLink(room_id=room.id, user_id=spectator.id, connected=True, is_spectator=True))
    await session.commit()

    # Act
    result = await wordquiz_game_controller.record_hint_view(UUID(game_id), spectator.id)

    # Assert
    assert result.recorded is False
    game = await _reload(session, game_id)
    assert str(spectator.id) not in game.live_state.get("hint_usage", {})


@pytest.mark.asyncio
async def test_a_players_hint_view_is_recorded_once_per_round(wordquiz_game_controller, setup_wordquiz_game, session):
    """The control: a player's views are recorded, one entry per round."""
    # Prepare
    _, users, game_id, _ = await _start_one_round(wordquiz_game_controller, setup_wordquiz_game, session)

    # Act
    first = await wordquiz_game_controller.record_hint_view(UUID(game_id), users[1].id)
    await wordquiz_game_controller.record_hint_view(UUID(game_id), users[1].id)

    # Assert
    assert first.recorded is True
    game = await _reload(session, game_id)
    assert game.live_state["hint_usage"][str(users[1].id)] == [str(game.live_state["current_round"])]


@pytest.mark.asyncio
async def test_a_hostless_room_advances_when_every_player_is_ready(
    wordquiz_game_controller, setup_wordquiz_game, session
):
    """The host deleted their account (owner_id NULL): every player is in the ready quorum (SEC F05)."""
    # Prepare — a 2-round game in results, its room without an owner
    setup = await setup_wordquiz_game(num_players=2)
    room, users = setup["room"], setup["users"]
    result = await _start_game(wordquiz_game_controller, room.id, users[0].id)
    gid = UUID(result.game_id)
    word = (await _get_game(session, result.game_id)).live_state["current_word"]["word_en"]
    for user in users:
        await wordquiz_game_controller.submit_answer(gid, user.id, word)
    stored_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    stored_room.owner_id = None
    session.add(stored_room)
    await session.commit()

    # Act
    first = await wordquiz_game_controller.advance_to_next_round(gid, users[0].id)
    second = await wordquiz_game_controller.advance_to_next_round(gid, users[1].id)

    # Assert
    assert (first.advanced, first.ready_count, first.total_players) == (False, 1, 2)
    assert second.advanced is True
    game = await _reload(session, result.game_id)
    assert game.live_state["current_round"] == 2
    assert game.live_state["round_phase"] == "playing"
