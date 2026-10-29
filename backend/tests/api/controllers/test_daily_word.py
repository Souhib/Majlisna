"""Tests for the DailyWordController — the word of the day (Kalimat al-yawm, كلمة اليوم)."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import DAILY_WORD_GUESSES_KEPT, DAILY_WORD_NO_REPEAT_DAYS
from majlisna.api.controllers import daily_word as daily_word_module
from majlisna.api.controllers.daily_word import DailyWordController
from majlisna.api.controllers.user import UserController
from majlisna.api.models.daily_word import DailyWord, DailyWordPlay
from majlisna.api.models.notebook import NotebookEntry, NotebookGameType
from majlisna.api.models.table import User
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.daily_word import DailyWordStatus
from majlisna.api.schemas.error import (
    DailyWordAlreadyFinishedError,
    DailyWordNoMoreHintsError,
    DailyWordNotFinishedError,
    DailyWordNotTodayError,
    EmptyAnswerError,
    NoQuizWordsAvailableError,
)
from majlisna.api.schemas.wordquiz import WordQuizCategory

# Noon in Makkah on day #13 — far from midnight, so a test never straddles the turn.
NOW = "2026-11-10T09:00:00Z"
TODAY = date(2026, 11, 10)

HADITH_HINTS = {
    str(rung): {"en": f"Hint {rung}", "fr": f"Indice {rung}", "ar": f"تلميح {rung}"} for rung in range(1, 7)
}


# ─── Fixtures ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _frozen_clock():
    """Every test runs at noon in Makkah on TODAY unless it moves the clock itself."""
    with freeze_time(NOW):
        yield


@pytest_asyncio.fixture(name="daily_controller")
async def get_daily_controller(session: AsyncSession) -> DailyWordController:
    return DailyWordController(session)


@pytest_asyncio.fixture(name="player")
async def get_player(create_user) -> User:
    return await create_user(username="seeker", email="seeker@test.com")


@pytest_asyncio.fixture(name="quiz_word")
async def get_quiz_word(create_quiz_word) -> QuizWord:
    """The only QuizWord, so it is today's word."""
    return await create_quiz_word(
        word_en="Hudaybiyyah",
        word_ar="الحديبية",
        word_fr="Houdaybiya",
        accepted_answers={"en": ["Hudaybiya"], "ar": ["صلح الحديبية"], "fr": ["Hudaybiya"]},
        category="Islamic History",
        hints=HADITH_HINTS,
    )


async def _plays(session: AsyncSession, user_id: UUID) -> list[DailyWordPlay]:
    """Re-fetch a player's plays straight from the database."""
    statement = select(DailyWordPlay).where(DailyWordPlay.user_id == user_id)
    return list((await session.exec(statement.execution_options(populate_existing=True))).all())


async def _daily_words(session: AsyncSession) -> list[DailyWord]:
    statement = select(DailyWord).order_by(col(DailyWord.day))
    return list((await session.exec(statement.execution_options(populate_existing=True))).all())


async def _record_solved_days(session: AsyncSession, user: User, word: QuizWord, offsets: list[int]) -> None:
    """Past days the player solved (and those days' word rows), ``offset`` days before TODAY."""
    for offset in offsets:
        day = TODAY - timedelta(days=offset)
        session.add(DailyWord(day=day, quiz_word_id=word.id))
        session.add(DailyWordPlay(user_id=user.id, day=day, solved_at=datetime.now(UTC), score=6))
    await session.commit()


# ─── The day and its word ─────────────────────────────────────


@pytest.mark.usefixtures("quiz_word")
async def test_the_word_changes_at_midnight_in_makkah(daily_controller: DailyWordController, session: AsyncSession):
    """23:59:59 and 00:00:00 in Makkah are two days, two numbers, two drawn rows."""
    # Prepare
    with freeze_time("2026-10-29T20:59:59Z"):
        before = await daily_controller.get_today(None)

    # Act
    with freeze_time("2026-10-29T21:00:00Z"):
        after = await daily_controller.get_today(None)

    # Assert
    assert (before.day, before.number) == (date(2026, 10, 29), 1)
    assert before.next_day_at == datetime(2026, 10, 29, 21, 0, tzinfo=UTC)
    assert (after.day, after.number) == (date(2026, 10, 30), 2)
    assert after.next_day_at == datetime(2026, 10, 30, 21, 0, tzinfo=UTC)
    assert [row.day for row in await _daily_words(session)] == [date(2026, 10, 29), date(2026, 10, 30)]


async def test_the_day_is_drawn_once_and_is_the_same_for_everyone(
    daily_controller: DailyWordController, session: AsyncSession, create_quiz_word, player: User
):
    """The first request draws the word; every later one, signed in or not, reads that row."""
    # Prepare
    for index in range(5):
        await create_quiz_word(word_en=f"Word{index}", word_ar=None, word_fr=None, hints=HADITH_HINTS)
    first = await daily_controller.get_today(None)

    # Act
    later = [await daily_controller.get_today(None), await daily_controller.get_today(player)]

    # Assert
    rows = await _daily_words(session)
    assert len(rows) == 1
    assert (rows[0].day, first.number) == (TODAY, 13)
    assert all(state.day == TODAY for state in later)
    assert all(state.hints == first.hints for state in later)


async def test_a_word_is_not_drawn_again_within_the_window(
    daily_controller: DailyWordController, session: AsyncSession, create_quiz_word, monkeypatch
):
    """A word drawn DAILY_WORD_NO_REPEAT_DAYS ago is excluded; one drawn the day before that is back."""
    # Prepare
    recent = await create_quiz_word(word_en="Recent", word_ar=None, word_fr=None)
    older = await create_quiz_word(word_en="Older", word_ar=None, word_fr=None)
    fresh = await create_quiz_word(word_en="Fresh", word_ar=None, word_fr=None)
    session.add(DailyWord(day=TODAY - timedelta(days=DAILY_WORD_NO_REPEAT_DAYS), quiz_word_id=recent.id))
    session.add(DailyWord(day=TODAY - timedelta(days=DAILY_WORD_NO_REPEAT_DAYS + 1), quiz_word_id=older.id))
    await session.commit()
    offered: list[list[UUID]] = []

    def _first(candidates: list[UUID]) -> UUID:
        offered.append(list(candidates))
        return candidates[0]

    monkeypatch.setattr(daily_word_module.rng, "choice", _first)

    # Act
    await daily_controller.get_today(None)

    # Assert
    assert len(offered) == 1
    assert set(offered[0]) == {older.id, fresh.id}
    today = next(row for row in await _daily_words(session) if row.day == TODAY)
    assert today.quiz_word_id in {older.id, fresh.id}


async def test_every_word_is_offered_when_the_window_leaves_none(
    daily_controller: DailyWordController, session: AsyncSession, create_quiz_word, monkeypatch
):
    """With every word drawn in the window, the draw falls back to all of them."""
    # Prepare
    words = [await create_quiz_word(word_en=f"Word{index}", word_ar=None, word_fr=None) for index in range(2)]
    for offset, word in enumerate(words, start=1):
        session.add(DailyWord(day=TODAY - timedelta(days=offset), quiz_word_id=word.id))
    await session.commit()
    offered: list[list[UUID]] = []
    monkeypatch.setattr(daily_word_module.rng, "choice", lambda candidates: offered.append(candidates) or candidates[0])

    # Act
    state = await daily_controller.get_today(None)

    # Assert
    assert set(offered[0]) == {word.id for word in words}
    assert state.day == TODAY


async def test_no_quiz_words_is_a_named_error(daily_controller: DailyWordController):
    """An empty content table cannot draw a word."""
    # Act / Assert
    with pytest.raises(NoQuizWordsAvailableError):
        await daily_controller.get_today(None)


@pytest.mark.postgres
async def test_concurrent_first_requests_agree_on_the_word(
    engine: AsyncEngine, session: AsyncSession, create_quiz_word
):
    """Four first requests of the day racing: one row is written, and all four answer it."""
    # Prepare
    for index in range(12):
        await create_quiz_word(word_en=f"Word{index}", word_ar=None, word_fr=None, hints=HADITH_HINTS)

    # Act — one session per task, as production gives one per request
    states = await asyncio.gather(*(_get_today_in_own_session(engine) for _ in range(4)))

    # Assert
    rows = await _daily_words(session)
    assert len(rows) == 1
    assert {state.day for state in states} == {TODAY}
    word = (await session.exec(select(QuizWord).where(QuizWord.id == rows[0].quiz_word_id))).one()
    assert {tuple(state.hints) for state in states} == {(word.hints["1"]["en"],)}


async def _get_today_in_own_session(engine: AsyncEngine):
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await DailyWordController(own_session).get_today(None)


@pytest.mark.postgres
@pytest.mark.usefixtures("quiz_word")
async def test_concurrent_first_moves_make_one_play(engine: AsyncEngine, session: AsyncSession, player: User):
    """A double tap on the first guess: one play row, both guesses counted, no 500."""
    # Prepare
    async with AsyncSession(engine, expire_on_commit=False) as warm_up:
        await DailyWordController(warm_up).get_today(None)

    # Act
    results = await asyncio.gather(*(_guess_in_own_session(engine, player.id, f"Wrong{index}") for index in range(2)))

    # Assert
    assert [result.correct for result in results] == [False, False]
    plays = await _plays(session, player.id)
    assert len(plays) == 1
    assert plays[0].attempts == 2
    assert sorted(plays[0].guesses) == ["Wrong0", "Wrong1"]


async def _guess_in_own_session(engine: AsyncEngine, user_id: UUID, answer: str):
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await DailyWordController(own_session).guess(user_id, answer)


# ─── What a caller sees ───────────────────────────────────────


@pytest.mark.usefixtures("quiz_word")
async def test_an_anonymous_caller_sees_the_number_the_category_and_hint_one(daily_controller: DailyWordController):
    """No streak, no answer, no play: the first rung only."""
    # Act
    state = await daily_controller.get_today(None, lang="fr")

    # Assert
    assert state.number == 13
    assert state.category == WordQuizCategory.ISLAMIC_HISTORY
    assert (state.hints, state.hints_revealed, state.max_hints) == (["Indice 1"], 1, 6)
    assert state.status == DailyWordStatus.NOT_STARTED
    assert (state.attempts, state.guesses, state.score) == (0, [], None)
    assert (state.streak, state.best_streak) == (None, None)
    assert state.answer is None


@pytest.mark.usefixtures("quiz_word")
async def test_viewing_writes_no_play(daily_controller: DailyWordController, session: AsyncSession, player: User):
    """A signed-in player who only looks has not started: hint 1, streaks, no row."""
    # Act
    state = await daily_controller.get_today(player, lang="ar")

    # Assert
    assert (state.status, state.hints) == (DailyWordStatus.NOT_STARTED, ["تلميح 1"])
    assert (state.streak, state.best_streak) == (0, 0)
    assert await _plays(session, player.id) == []


async def test_a_category_outside_the_map_reads_null(daily_controller: DailyWordController, create_quiz_word):
    """An admin-made label has no key the client can word."""
    # Prepare
    await create_quiz_word(word_en="Odd", category="Something Else")

    # Act
    state = await daily_controller.get_today(None)

    # Assert
    assert state.category is None


# ─── Hints ────────────────────────────────────────────────────


@pytest.mark.usefixtures("quiz_word")
async def test_a_hint_reveals_the_next_rung_and_starts_the_play(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """The first hint creates the play at rung 2; the state carries exactly that prefix."""
    # Act
    state = await daily_controller.reveal_hint(player.id, lang="en")

    # Assert
    assert (state.hints, state.hints_revealed, state.status) == (["Hint 1", "Hint 2"], 2, DailyWordStatus.PLAYING)
    plays = await _plays(session, player.id)
    assert [(play.hints_revealed, play.attempts, play.solved_at, play.gave_up) for play in plays] == [
        (2, 0, None, False)
    ]


@pytest.mark.usefixtures("quiz_word")
async def test_no_hint_past_the_last_rung(daily_controller: DailyWordController, session: AsyncSession, player: User):
    """Five hints take the ladder to six; a sixth is a named 409 and changes nothing."""
    # Prepare
    for _ in range(5):
        await daily_controller.reveal_hint(player.id)

    # Act / Assert
    with pytest.raises(DailyWordNoMoreHintsError):
        await daily_controller.reveal_hint(player.id)
    assert [play.hints_revealed for play in await _plays(session, player.id)] == [6]


# ─── Guesses and scores ───────────────────────────────────────


@pytest.mark.parametrize(("hints_taken", "score"), [(0, 6), (2, 4), (5, 1)])
@pytest.mark.usefixtures("quiz_word")
async def test_a_right_guess_solves_with_kalimats_score(
    daily_controller: DailyWordController, session: AsyncSession, player: User, hints_taken: int, score: int
):
    """max_hints - hints_revealed + 1, recorded with the moment it was found."""
    # Prepare
    for _ in range(hints_taken):
        await daily_controller.reveal_hint(player.id)

    # Act
    result = await daily_controller.guess(player.id, "  hudaybiyyah ")

    # Assert
    assert result.correct is True
    assert (result.state.status, result.state.score, result.state.attempts) == (DailyWordStatus.SOLVED, score, 1)
    assert result.state.hints_revealed == hints_taken + 1
    plays = await _plays(session, player.id)
    assert plays[0].score == score
    assert plays[0].solved_at is not None
    assert plays[0].last_guess == "hudaybiyyah"


@pytest.mark.parametrize("answer", ["صلح الحديبية", "Houdaybiya", "al-Hudaybiya", "الْحُدَيْبِيَة"])
@pytest.mark.usefixtures("quiz_word")
async def test_any_language_or_script_finds_the_word(daily_controller: DailyWordController, player: User, answer: str):
    """Kalimat's matching: every spelling and accepted variant, whatever the UI language."""
    # Act
    result = await daily_controller.guess(player.id, answer, lang="en")

    # Assert
    assert result.correct is True


@pytest.mark.usefixtures("quiz_word")
async def test_a_wrong_guess_is_counted_and_kept(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """correct=false, the try is listed, the play stays open, and the word stays hidden."""
    # Act
    result = await daily_controller.guess(player.id, "Badr")

    # Assert
    assert result.correct is False
    assert (result.state.status, result.state.attempts, result.state.guesses) == (
        DailyWordStatus.PLAYING,
        1,
        ["Badr"],
    )
    assert (result.state.score, result.state.answer) == (None, None)
    plays = await _plays(session, player.id)
    assert (plays[0].attempts, plays[0].last_guess, plays[0].solved_at) == (1, "Badr", None)


@pytest.mark.usefixtures("quiz_word")
async def test_a_wrong_guess_opens_the_next_rung_like_a_hint(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """A wrong try costs what a hint costs: the next rung opens, and the word is then worth one less.

    Were it free, typing the theme's words one by one at hint 1 would pay full marks."""
    # Act
    wrong = await daily_controller.guess(player.id, "Badr", lang="en")
    right = await daily_controller.guess(player.id, "Hudaybiyyah")

    # Assert
    assert (wrong.state.hints, wrong.state.hints_revealed) == (["Hint 1", "Hint 2"], 2)
    assert (right.state.status, right.state.score, right.state.hints_revealed) == (DailyWordStatus.SOLVED, 5, 2)
    plays = await _plays(session, player.id)
    assert (plays[0].hints_revealed, plays[0].attempts, plays[0].score) == (2, 2, 5)


@pytest.mark.usefixtures("quiz_word")
async def test_a_wrong_guess_on_the_last_rung_opens_nothing_and_still_scores_one(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """Past the last rung there is nothing to open: tries are free there, and finding it still pays 1."""
    # Prepare: five wrong tries take the ladder to its sixth rung
    for index in range(5):
        await daily_controller.guess(player.id, f"Try{index}")

    # Act
    wrong = await daily_controller.guess(player.id, "Badr")
    right = await daily_controller.guess(player.id, "Hudaybiyyah")

    # Assert
    assert (wrong.state.hints_revealed, wrong.state.max_hints, wrong.state.attempts) == (6, 6, 6)
    assert (right.state.status, right.state.score) == (DailyWordStatus.SOLVED, 1)
    assert [(play.hints_revealed, play.attempts) for play in await _plays(session, player.id)] == [(6, 7)]


@pytest.mark.usefixtures("quiz_word")
async def test_only_the_most_recent_guesses_are_kept(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """Every guess is counted; the list keeps the last DAILY_WORD_GUESSES_KEPT."""
    # Prepare
    total = DAILY_WORD_GUESSES_KEPT + 5
    for index in range(total - 1):
        await daily_controller.guess(player.id, f"Try{index}")

    # Act
    result = await daily_controller.guess(player.id, f"Try{total - 1}")

    # Assert
    assert result.state.attempts == total
    assert result.state.guesses == [f"Try{index}" for index in range(5, total)]
    assert (await _plays(session, player.id))[0].guesses == result.state.guesses


@pytest.mark.parametrize("answer", ["   ", "-"])
@pytest.mark.usefixtures("quiz_word")
async def test_an_empty_guess_is_refused_and_not_counted(
    daily_controller: DailyWordController, session: AsyncSession, player: User, answer: str
):
    """Nothing left once normalised: a 400, and no play is started."""
    # Act / Assert
    with pytest.raises(EmptyAnswerError):
        await daily_controller.guess(player.id, answer)
    assert await _plays(session, player.id) == []


@pytest.mark.usefixtures("quiz_word")
async def test_give_up_finishes_with_zero_and_reveals(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """0 points, the word in the player's language, the explanation, and no streak today."""
    # Prepare
    await daily_controller.reveal_hint(player.id)

    # Act
    state = await daily_controller.give_up(player.id, lang="fr")

    # Assert
    assert (state.status, state.score, state.streak) == (DailyWordStatus.GAVE_UP, 0, 0)
    assert state.answer is not None
    assert (state.answer.word_display, state.answer.word_ar) == ("Houdaybiya", "الحديبية")
    assert state.answer.explanation == "Indice 6"  # no explanation stored: the last rung
    assert (state.answer.kept, state.answer.entry_id) == (False, None)
    plays = await _plays(session, player.id)
    assert (plays[0].gave_up, plays[0].score, plays[0].solved_at) == (True, 0, None)


@pytest.mark.usefixtures("quiz_word")
async def test_nothing_moves_once_finished(daily_controller: DailyWordController, session: AsyncSession, player: User):
    """After a solve, a hint, a guess and a give-up are each a named 409 that writes nothing."""
    # Prepare
    await daily_controller.guess(player.id, "Hudaybiyyah")

    # Act / Assert
    with pytest.raises(DailyWordAlreadyFinishedError):
        await daily_controller.reveal_hint(player.id)
    with pytest.raises(DailyWordAlreadyFinishedError):
        await daily_controller.guess(player.id, "Badr")
    with pytest.raises(DailyWordAlreadyFinishedError):
        await daily_controller.give_up(player.id)
    plays = await _plays(session, player.id)
    assert (plays[0].attempts, plays[0].hints_revealed, plays[0].gave_up, plays[0].score) == (1, 1, False, 6)


@pytest.mark.usefixtures("quiz_word")
async def test_a_move_on_another_day_is_refused(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """A page left open past midnight in Makkah: its guess is not judged against the new word."""
    # Act / Assert
    with pytest.raises(DailyWordNotTodayError):
        await daily_controller.guess(player.id, "Hudaybiyyah", day=TODAY - timedelta(days=1))
    with pytest.raises(DailyWordNotTodayError):
        await daily_controller.reveal_hint(player.id, day=TODAY + timedelta(days=1))
    with pytest.raises(DailyWordNotTodayError):
        await daily_controller.give_up(player.id, day=TODAY - timedelta(days=1))
    assert await _plays(session, player.id) == []


@pytest.mark.usefixtures("quiz_word")
async def test_a_move_naming_today_is_accepted(daily_controller: DailyWordController, player: User):
    """The day the page shows is today: the move goes through."""
    # Act
    result = await daily_controller.guess(player.id, "Hudaybiyyah", day=TODAY)

    # Assert
    assert result.correct is True


@pytest.mark.usefixtures("quiz_word")
async def test_solvers_today_counts_who_found_it(daily_controller: DailyWordController, create_user, player: User):
    """Two solved, one gave up, one is still playing: two found it."""
    # Prepare
    others = [await create_user(username=f"other{index}", email=f"other{index}@test.com") for index in range(3)]
    await daily_controller.guess(player.id, "Hudaybiyyah")
    await daily_controller.guess(others[0].id, "Hudaybiya")
    await daily_controller.give_up(others[1].id)
    await daily_controller.guess(others[2].id, "Badr")

    # Act
    state = await daily_controller.get_today(None)

    # Assert
    assert state.solvers_today == 2
    assert state.answer is None  # others finishing reveals nothing to an anonymous caller


# ─── Streaks ──────────────────────────────────────────────────


async def test_streak_runs_to_yesterday_while_today_is_open(
    daily_controller: DailyWordController, session: AsyncSession, player: User, quiz_word: QuizWord, create_quiz_word
):
    """Solved the last two days, a gap, then three: streak 2, best 3."""
    # Prepare
    old_word = await create_quiz_word(word_en="Older", word_ar=None, word_fr=None)
    await _record_solved_days(session, player, old_word, [1, 2, 4, 5, 6])
    # Today's word is drawn from the fresh one, whatever the draw.
    session.add(DailyWord(day=TODAY, quiz_word_id=quiz_word.id))
    await session.commit()

    # Act
    state = await daily_controller.get_today(player)

    # Assert
    assert (state.streak, state.best_streak) == (2, 3)


async def test_solving_today_extends_the_streak(
    daily_controller: DailyWordController, session: AsyncSession, player: User, quiz_word: QuizWord, create_quiz_word
):
    """Yesterday and the day before, then today: streak 3, which is the best too."""
    # Prepare
    old_word = await create_quiz_word(word_en="Older", word_ar=None, word_fr=None)
    await _record_solved_days(session, player, old_word, [1, 2])
    session.add(DailyWord(day=TODAY, quiz_word_id=quiz_word.id))
    await session.commit()

    # Act
    result = await daily_controller.guess(player.id, "Hudaybiyyah")

    # Assert
    assert (result.state.streak, result.state.best_streak) == (3, 3)


async def test_giving_up_today_ends_the_streak(
    daily_controller: DailyWordController, session: AsyncSession, player: User, quiz_word: QuizWord, create_quiz_word
):
    """A give-up closes today unsolved: streak 0, the best run stays."""
    # Prepare
    old_word = await create_quiz_word(word_en="Older", word_ar=None, word_fr=None)
    await _record_solved_days(session, player, old_word, [1, 2, 3])
    session.add(DailyWord(day=TODAY, quiz_word_id=quiz_word.id))
    await session.commit()

    # Act
    state = await daily_controller.give_up(player.id)

    # Assert
    assert (state.streak, state.best_streak) == (0, 3)


@pytest.mark.usefixtures("quiz_word")
async def test_streaks_are_one_query(daily_controller: DailyWordController, player: User, count_statements):
    """The state reads the player's plays once for both streaks (plus one count for solvers)."""
    # Prepare
    await daily_controller.reveal_hint(player.id)
    counter = count_statements("FROM daily_word_play")

    # Act
    await daily_controller.get_today(player)

    # Assert — today's play, the streaks, the solvers' count
    assert counter.count == 3


# ─── Keep ─────────────────────────────────────────────────────


@pytest.mark.usefixtures("quiz_word")
async def test_keep_before_finishing_is_refused(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """Keeping would reveal the word: not before a solve or a give-up, and nothing is written."""
    # Prepare
    await daily_controller.reveal_hint(player.id)

    # Act / Assert
    with pytest.raises(DailyWordNotFinishedError):
        await daily_controller.keep(player.id)
    entries = (await session.exec(select(NotebookEntry).where(NotebookEntry.user_id == player.id))).all()
    assert entries == []


@pytest.mark.usefixtures("quiz_word")
async def test_keep_without_a_play_is_refused(daily_controller: DailyWordController, player: User):
    """A player who never played that day has nothing to keep."""
    # Act / Assert
    with pytest.raises(DailyWordNotFinishedError):
        await daily_controller.keep(player.id)


@pytest.mark.usefixtures("quiz_word")
async def test_keep_adds_the_word_to_the_kunnash_once(
    daily_controller: DailyWordController, session: AsyncSession, player: User
):
    """A daily_word entry with no source game, resolved like a Word Quiz word; keeping twice is a no-op."""
    # Prepare
    await daily_controller.guess(player.id, "Hudaybiyyah")

    # Act
    first = await daily_controller.keep(player.id, lang="ar")
    second = await daily_controller.keep(player.id, lang="ar")

    # Assert
    assert (first.added, first.already_kept, second.added, second.already_kept) == (1, 0, 0, 1)
    view = first.entries[0]
    assert (view.word, view.game_type, view.source_game_id) == ("Hudaybiyyah", NotebookGameType.DAILY_WORD, None)
    assert (view.word_display, view.word_ar) == ("الحديبية", "الحديبية")
    rows = (
        await session.exec(
            select(NotebookEntry).where(NotebookEntry.user_id == player.id).execution_options(populate_existing=True)
        )
    ).all()
    assert [(row.term, row.game_type, row.source_game_id) for row in rows] == [
        ("Hudaybiyyah", NotebookGameType.DAILY_WORD, None)
    ]
    state = await daily_controller.get_today(player)
    assert state.answer is not None
    assert (state.answer.kept, state.answer.entry_id) == (True, view.id)


@pytest.mark.usefixtures("quiz_word")
async def test_a_finished_day_can_still_be_kept_after_midnight(daily_controller: DailyWordController, player: User):
    """The page outlived the day: its word is still the player's to keep."""
    # Prepare
    await daily_controller.give_up(player.id)

    # Act
    with freeze_time("2026-11-10T21:00:01Z"):
        result = await daily_controller.keep(player.id, day=TODAY)

    # Assert
    assert result.added == 1
    assert result.entries[0].word == "Hudaybiyyah"


# ─── Account deletion ─────────────────────────────────────────


@pytest.mark.usefixtures("quiz_word")
async def test_deleting_an_account_purges_its_plays(
    daily_controller: DailyWordController, session: AsyncSession, player: User, create_user
):
    """The plays hold an FK to the user: deletion removes them, and leaves others' plays alone."""
    # Prepare
    other = await create_user(username="stays", email="stays@test.com")
    await daily_controller.guess(player.id, "Hudaybiyyah")
    await daily_controller.reveal_hint(other.id)
    player_id = player.id

    # Act
    await UserController(session).delete_user(player_id)

    # Assert
    assert await _plays(session, player_id) == []
    assert [play.hints_revealed for play in await _plays(session, other.id)] == [2]
    assert (await session.exec(select(User).where(User.id == player_id))).first() is None
