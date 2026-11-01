"""Tests for the RiddleController: the samar riddles shown while a table waits.

A riddle is rung 1 of a random QuizWord and its answer. It is a pastime, never a
spoiler: it is never today's word of the day (nor a recent one), never an answer of the
room's running quiz, and there is none at all while another game is played (Kalimat
draws its words one round at a time, so a riddle could be a later round's word).
"""

from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from freezegun import freeze_time
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import ROOM_RIDDLE_HINT_RUNG
from majlisna.api.controllers.riddle import RiddleController
from majlisna.api.models.daily_word import DailyWord
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.error import NoQuizWordsAvailableError, RiddleNotDuringGameError, RoomMembersOnlyError
from majlisna.api.schemas.wordquiz import WordQuizCategory

# Noon in Makkah: no test straddles the turn of the day.
NOW = "2026-11-10T09:00:00Z"
TODAY = date(2026, 11, 10)
DRAWS = 25  # enough random draws that a leak would show


def _ladder(name: str) -> dict:
    return {
        str(rung): {"en": f"{name} hint {rung}", "fr": f"{name} indice {rung}", "ar": f"{name} تلميح {rung}"}
        for rung in range(1, 7)
    }


@pytest.fixture(autouse=True)
def _frozen_clock():
    with freeze_time(NOW):
        yield


@pytest_asyncio.fixture(name="riddle_controller")
async def get_riddle_controller(session: AsyncSession) -> RiddleController:
    return RiddleController(session)


@pytest_asyncio.fixture(name="host")
async def get_host(create_user) -> User:
    return await create_user(username="host", email="host@test.com")


@pytest_asyncio.fixture(name="room")
async def get_room(host: User, create_room) -> Room:
    """A room whose host is seated (create_room seats its owner)."""
    return await create_room(owner=host)


@pytest_asyncio.fixture(name="make_word")
async def get_make_word(create_quiz_word):
    async def _make(
        word_en: str, word_ar: str | None = None, *, accepted: dict | None = None, category: str = "Prophets"
    ) -> QuizWord:
        return await create_quiz_word(
            word_en=word_en,
            word_ar=word_ar,
            word_fr=f"{word_en} (fr)",
            accepted_answers=accepted,
            category=category,
            hints=_ladder(word_en),
        )

    return _make


async def _seat(
    session: AsyncSession, room: Room, user: User, *, spectator: bool = False, connected: bool = True
) -> None:
    link = (
        await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room.id, RoomUserLink.user_id == user.id))
    ).first()
    if link is None:
        link = RoomUserLink(room_id=room.id, user_id=user.id, last_seen_at=datetime.now())
    link.is_spectator = spectator
    link.connected = connected
    session.add(link)
    await session.commit()


async def _daily(session: AsyncSession, day: date, word: QuizWord) -> None:
    session.add(DailyWord(day=day, quiz_word_id=word.id))
    await session.commit()


async def _running_game(
    session: AsyncSession, room: Room, game_type: GameType, live_state: dict, status=GameStatus.IN_PROGRESS
) -> Game:
    game = Game(room_id=room.id, number_of_players=2, type=game_type, game_status=status, live_state=live_state)
    session.add(game)
    await session.commit()
    room.active_game_id = game.id
    session.add(room)
    await session.commit()
    return game


async def _draw_many(riddle_controller: RiddleController, room: Room, user: User, lang: str = "en") -> set[str]:
    return {
        (await riddle_controller.get_room_riddle(room.id, user.id, lang=lang)).answer.word_display for _ in range(DRAWS)
    }


# ─── What a riddle is ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_member_gets_rung_one_and_its_answer_in_their_language(
    riddle_controller, room, host, make_word, session
):
    # Prepare
    word = await make_word("Ibrahim", "إبراهيم")
    await _daily(session, TODAY, await make_word("Badr", category="Places"))

    # Act
    riddle = await riddle_controller.get_room_riddle(room.id, host.id, lang="fr")

    # Assert
    assert ROOM_RIDDLE_HINT_RUNG == 1
    assert riddle.id == word.id
    assert riddle.hint == "Ibrahim indice 1"
    assert riddle.category == WordQuizCategory.PROPHETS
    assert riddle.answer.word_display == "Ibrahim (fr)"
    assert riddle.answer.word_ar == "إبراهيم"


@pytest.mark.asyncio
async def test_a_regional_language_tag_reads_as_its_language(riddle_controller, room, host, make_word, session):
    # Prepare
    await make_word("Ibrahim", "إبراهيم")
    await _daily(session, TODAY, await make_word("Badr"))

    # Act
    arabic = await riddle_controller.get_room_riddle(room.id, host.id, lang="ar-SA")
    unknown = await riddle_controller.get_room_riddle(room.id, host.id, lang="de")

    # Assert: the rung AND the answer (the notebook's spelling compares the language raw)
    assert arabic.hint == "Ibrahim تلميح 1"
    assert arabic.answer.word_display == "إبراهيم"
    assert unknown.hint == "Ibrahim hint 1"
    assert unknown.answer.word_display == "Ibrahim"


@pytest.mark.asyncio
async def test_a_spectator_and_a_briefly_disconnected_member_get_one(
    riddle_controller, room, create_user, make_word, session
):
    # Prepare
    await make_word("Ibrahim")
    await _daily(session, TODAY, await make_word("Badr"))
    watcher = await create_user(username="watcher", email="watcher@test.com")
    away = await create_user(username="away", email="away@test.com")
    await _seat(session, room, watcher, spectator=True)
    await _seat(session, room, away, connected=False)

    # Act
    for_watcher = await riddle_controller.get_room_riddle(room.id, watcher.id)
    for_away = await riddle_controller.get_room_riddle(room.id, away.id)

    # Assert
    assert for_watcher.hint == for_away.hint == "Ibrahim hint 1"


@pytest.mark.asyncio
async def test_someone_outside_the_room_is_refused(riddle_controller, room, create_user, make_word):
    # Prepare
    await make_word("Ibrahim")
    stranger = await create_user(username="stranger", email="stranger@test.com")

    # Act / Assert
    with pytest.raises(RoomMembersOnlyError) as refused:
        await riddle_controller.get_room_riddle(room.id, stranger.id)
    assert refused.value.status_code == 403
    assert refused.value.error_key == "errors.api.roomMembersOnly"


# ─── Never the word of the day ────────────────────────────────


@pytest.mark.asyncio
async def test_never_todays_word_of_the_day(riddle_controller, room, host, make_word, session):
    # Prepare
    today = await make_word("Ibrahim")
    await make_word("Musa")
    await _daily(session, TODAY, today)

    # Act
    drawn = await _draw_many(riddle_controller, room, host)

    # Assert
    assert drawn == {"Musa"}


@pytest.mark.asyncio
async def test_draws_the_word_of_the_day_first_when_nobody_has_yet(riddle_controller, room, host, make_word, session):
    """The day's word is drawn lazily: a riddle asked before it would not know what to avoid."""
    # Prepare
    await make_word("Ibrahim")
    await make_word("Musa")

    # Act
    riddle = await riddle_controller.get_room_riddle(room.id, host.id)

    # Assert
    drawn = (await session.exec(select(DailyWord).where(DailyWord.day == TODAY))).one()
    assert drawn.quiz_word_id != riddle.id


@pytest.mark.asyncio
async def test_recent_words_of_the_day_are_left_out(riddle_controller, room, host, make_word, session):
    # Prepare
    await _daily(session, TODAY, await make_word("Ibrahim"))
    await _daily(session, TODAY - timedelta(days=30), await make_word("Musa"))
    await make_word("Nuh")

    # Act
    drawn = await _draw_many(riddle_controller, room, host)

    # Assert
    assert drawn == {"Nuh"}


@pytest.mark.asyncio
async def test_a_recent_word_of_the_day_serves_when_nothing_else_is_left(
    riddle_controller, room, host, make_word, session
):
    # Prepare
    await _daily(session, TODAY, await make_word("Ibrahim"))
    await _daily(session, TODAY - timedelta(days=1), await make_word("Musa"))

    # Act
    drawn = await _draw_many(riddle_controller, room, host)

    # Assert: yesterday's word is old news; today's never is
    assert drawn == {"Musa"}


@pytest.mark.asyncio
async def test_no_riddle_when_the_only_word_is_todays(riddle_controller, room, host, make_word, session):
    # Prepare
    await _daily(session, TODAY, await make_word("Ibrahim"))

    # Act / Assert
    with pytest.raises(NoQuizWordsAvailableError):
        await riddle_controller.get_room_riddle(room.id, host.id)


# ─── Never a word of the running game ─────────────────────────


@pytest.mark.asyncio
async def test_between_quiz_questions_no_answer_of_the_game_is_a_riddle(
    riddle_controller, room, host, make_word, create_mcq_question, session
):
    """The Quiz deals all its questions at the start: every right answer of the game is
    left out (in any script, with or without the article), the wrong choices are not."""
    # Prepare
    await _daily(session, TODAY, await make_word("Badr"))
    await make_word("Yunus", "يونس")
    await make_word("Ibrahim", "إبراهيم", accepted={"en": ["Ibrahim", "Abraham"], "ar": ["إبراهيم"], "fr": ["Ibrahim"]})
    await make_word("Al-Aqsa", "الأقصى", category="Places")
    await make_word("Musa", "موسى")
    whale = await create_mcq_question(
        question_en="Which prophet was swallowed by a whale?",
        choices={
            "0": {"en": "Musa", "ar": "موسى", "fr": "Musa"},
            "1": {"en": "Jonah", "ar": "يونس", "fr": "Jonas"},
        },
        correct_answer_index=1,
    )
    kaaba = await create_mcq_question(
        question_en="Who built the Kaaba with his son?",
        choices={
            "0": {"en": "Abraham", "ar": "ابراهيم", "fr": "Abraham"},
            "1": {"en": "Nuh", "ar": "نوح", "fr": "Nuh"},
        },
        correct_answer_index=0,
    )
    mosque = await create_mcq_question(
        question_en="Which mosque was the first qibla?",
        choices={
            "0": {"en": "Aqsa", "ar": "المسجد الأقصى", "fr": "Aqsa"},
            "1": {"en": "Quba", "ar": "قباء", "fr": "Quba"},
        },
        correct_answer_index=0,
    )
    await _running_game(
        session,
        room,
        GameType.MCQ_QUIZ,
        {"question_ids": [str(whale.id), str(kaaba.id), str(mosque.id)], "current_round": 1, "round_phase": "results"},
    )

    # Act
    drawn = await _draw_many(riddle_controller, room, host)

    # Assert: Musa is only a wrong choice
    assert drawn == {"Musa"}


@pytest.mark.parametrize("game_type", [GameType.WORD_QUIZ, GameType.UNDERCOVER, GameType.CODENAMES])
@pytest.mark.asyncio
async def test_no_riddle_while_another_game_is_played(riddle_controller, room, host, make_word, session, game_type):
    """Kalimat draws its words round by round: a riddle could be a later round's word."""
    # Prepare
    await make_word("Ibrahim")
    await _running_game(session, room, game_type, {"used_word_ids": []})

    # Act / Assert
    with pytest.raises(RiddleNotDuringGameError) as refused:
        await riddle_controller.get_room_riddle(room.id, host.id)
    assert refused.value.status_code == 409
    assert refused.value.error_key == "errors.api.riddleNotDuringGame"


@pytest.mark.asyncio
async def test_a_finished_game_left_on_the_room_does_not_hold_riddles_back(
    riddle_controller, room, host, make_word, session
):
    # Prepare
    await _daily(session, TODAY, await make_word("Badr"))
    await make_word("Ibrahim")
    await _running_game(session, room, GameType.WORD_QUIZ, {}, status=GameStatus.FINISHED)

    # Act
    riddle = await riddle_controller.get_room_riddle(room.id, host.id)

    # Assert
    assert riddle.answer.word_display == "Ibrahim"
