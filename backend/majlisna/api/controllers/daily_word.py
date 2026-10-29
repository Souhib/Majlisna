from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DAILY_WORD_GUESSES_KEPT,
    DAILY_WORD_INITIAL_HINTS,
    DAILY_WORD_NO_REPEAT_DAYS,
    DAILY_WORD_PLAY_UNIQUE_COLUMNS,
    WORD_QUIZ_CATEGORY_KEYS,
)
from majlisna.api.controllers.notebook import NotebookController
from majlisna.api.models.daily_word import DailyWord, DailyWordPlay
from majlisna.api.models.notebook import NotebookGameType
from majlisna.api.models.table import User
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.daily_word import (
    DailyWordAnswer,
    DailyWordGuessResponse,
    DailyWordState,
    DailyWordStatus,
)
from majlisna.api.schemas.error import (
    DailyWordAlreadyFinishedError,
    DailyWordNoMoreHintsError,
    DailyWordNotFinishedError,
    DailyWordNotTodayError,
    EmptyAnswerError,
    NoQuizWordsAvailableError,
)
from majlisna.api.schemas.notebook import NotebookKeepResponse
from majlisna.api.schemas.wordquiz import WordQuizCategory
from majlisna.api.utils.daily_word import (
    compute_streaks,
    daily_word_number,
    ladder_length,
    makkah_day,
    next_day_starts_at,
    solved_score,
)
from majlisna.api.utils.dialect import dialect_insert
from majlisna.api.utils.multilingual import resolve_multilingual
from majlisna.api.utils.rng import rng
from majlisna.api.utils.text_match import matches_quiz_answer, normalize_answer


class DailyWordController:
    """The word of the day (Kalimat al-yawm, كلمة اليوم): one QuizWord per Makkah day,
    the same for everyone, found from its hint ladder.

    The word is the secret until the caller has finished: before that, no payload —
    state, error or otherwise — names it, holds an accepted answer, or carries a rung
    the caller has not revealed. ``answer`` appears only on a solved or given-up play.

    A move (hint, guess, give-up) locks the caller's play row (``SELECT … FOR UPDATE``,
    ignored by SQLite), so a double tap or two tabs are serialised and one commit
    settles each move: a give-up racing a correct guess cannot both land.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._notebook = NotebookController(session)

    # ── Read ─────────────────────────────────────────────────────

    async def get_today(self, viewer: User | None, *, lang: str = "en") -> DailyWordState:
        """Today's word as ``viewer`` may see it; an anonymous caller sees hint 1 only.

        The first request of a Makkah day draws the day's word.
        """
        day = makkah_day()
        word = await self._get_or_draw_word(day)
        if viewer is None:
            return await self._build_state(day, word, None, None, lang)
        play = await self._find_play(viewer.id, day)
        return await self._build_state(day, word, viewer.id, play, lang)

    # ── Moves ────────────────────────────────────────────────────

    async def reveal_hint(self, user_id: UUID, *, day: date | None = None, lang: str = "en") -> DailyWordState:
        """Reveal the next rung of today's ladder (each one costs a point).

        :raises DailyWordAlreadyFinishedError: solved or given up (409).
        :raises DailyWordNoMoreHintsError: every rung is out already (409).
        """
        today, word = await self._today_for_move(day)
        play = await self._lock_play(user_id, today)
        self._ensure_open(play)
        max_hints = ladder_length(word.hints)
        if play.hints_revealed >= max_hints:
            raise DailyWordNoMoreHintsError(day=today, max_hints=max_hints)

        play.hints_revealed += 1
        self.session.add(play)
        await self.session.commit()
        return await self._build_state(today, word, user_id, play, lang)

    async def guess(
        self, user_id: UUID, answer: str, *, day: date | None = None, lang: str = "en"
    ) -> DailyWordGuessResponse:
        """Judge a guess with Kalimat's own matching, in any language or script.

        Every guess is counted and kept (the most recent ``DAILY_WORD_GUESSES_KEPT``);
        a right one solves the day with ``max_hints - hints_revealed + 1`` points.

        A wrong one opens the next rung, as a hint would, so it costs the point a hint
        costs (on the last rung there is nothing left to open, and a try is free). Were
        a wrong try free, typing every word of the theme at hint 1 — the category leaves
        17 to 53 — would beat reading the hints, for a person as for a script.

        :raises EmptyAnswerError: nothing left once normalised (400) — not counted.
        :raises DailyWordAlreadyFinishedError: solved or given up (409).
        """
        typed = answer.strip()
        if not normalize_answer(typed):
            raise EmptyAnswerError()
        today, word = await self._today_for_move(day)
        play = await self._lock_play(user_id, today)
        self._ensure_open(play)

        correct = matches_quiz_answer(
            typed, spellings=(word.word_en, word.word_ar, word.word_fr), accepted_answers=word.accepted_answers
        )
        max_hints = ladder_length(word.hints)
        play.attempts += 1
        play.last_guess = typed
        # A new list, not an in-place append: SQLAlchemy does not see a JSON mutation.
        play.guesses = [*play.guesses, typed][-DAILY_WORD_GUESSES_KEPT:]
        if correct:
            play.solved_at = datetime.now(UTC)
            play.score = solved_score(max_hints, play.hints_revealed)
        elif play.hints_revealed < max_hints:
            play.hints_revealed += 1
        self.session.add(play)
        await self.session.commit()
        return DailyWordGuessResponse(correct=correct, state=await self._build_state(today, word, user_id, play, lang))

    async def give_up(self, user_id: UUID, *, day: date | None = None, lang: str = "en") -> DailyWordState:
        """Finish today's word unsolved: 0 points, the word revealed, today's streak ended.

        :raises DailyWordAlreadyFinishedError: solved or given up (409).
        """
        today, word = await self._today_for_move(day)
        play = await self._lock_play(user_id, today)
        self._ensure_open(play)

        play.gave_up = True
        play.score = 0
        self.session.add(play)
        await self.session.commit()
        return await self._build_state(today, word, user_id, play, lang)

    async def keep(self, user_id: UUID, *, day: date | None = None, lang: str = "en") -> NotebookKeepResponse:
        """Keep a finished day's word in the caller's Kunnash. Idempotent.

        ``day`` defaults to today; a past day works too, so a page left open past
        midnight in Makkah can still keep the word it revealed.

        :raises DailyWordNotFinishedError: the caller has not solved or given up that day (409).
        """
        target = day or makkah_day()
        play = await self._find_play(user_id, target)
        word = await self._find_word(target) if play is not None and _is_finished(play) else None
        if word is None:
            raise DailyWordNotFinishedError(day=target)
        return await self._notebook.keep_daily_word(user_id, word.word_en, lang=lang)

    # ── The day's word ───────────────────────────────────────────

    async def _today_for_move(self, day: date | None) -> tuple[date, QuizWord]:
        """Today, and its word. A move names the day its page shows; another day is refused,
        or a guess typed for yesterday's word would be judged against today's."""
        today = makkah_day()
        if day is not None and day != today:
            raise DailyWordNotTodayError(day=day, today=today)
        return today, await self._get_or_draw_word(today)

    async def _get_or_draw_word(self, day: date) -> QuizWord:
        """The day's QuizWord, drawn on the first request of the day.

        ``INSERT … ON CONFLICT DO NOTHING`` on the day, then a re-read: two first
        requests racing may draw different words, but only one row is written and both
        answer it (``test_concurrent_first_requests_agree_on_the_word``, postgres).
        """
        word = await self._find_word(day)
        if word is not None:
            return word

        drawn = DailyWord(day=day, quiz_word_id=await self._draw_word_id(day))
        statement = (
            dialect_insert(self.session, DailyWord)
            .values(drawn.model_dump())
            .on_conflict_do_nothing(index_elements=[col(DailyWord.day)])
        )
        await self.session.exec(statement)
        await self.session.commit()

        word = await self._find_word(day)
        if word is None:  # the row was just written, by this request or the one it raced
            raise NoQuizWordsAvailableError()
        return word

    async def _draw_word_id(self, day: date) -> UUID:
        """A random QuizWord not drawn in the last ``DAILY_WORD_NO_REPEAT_DAYS`` (all of
        them if that leaves none), from the shared ``rng``."""
        since = day - timedelta(days=DAILY_WORD_NO_REPEAT_DAYS)
        recent = select(DailyWord.quiz_word_id).where(DailyWord.day >= since).where(DailyWord.day < day)
        fresh = (
            await self.session.exec(
                select(QuizWord.id).where(col(QuizWord.id).not_in(recent)).order_by(col(QuizWord.id))
            )
        ).all()
        candidates = fresh or (await self.session.exec(select(QuizWord.id).order_by(col(QuizWord.id)))).all()
        if not candidates:
            raise NoQuizWordsAvailableError()
        return rng.choice(list(candidates))

    async def _find_word(self, day: date) -> QuizWord | None:
        return (
            await self.session.exec(
                select(QuizWord)
                .join(DailyWord, col(DailyWord.quiz_word_id) == col(QuizWord.id))
                .where(DailyWord.day == day)
            )
        ).first()

    # ── The caller's play ────────────────────────────────────────

    async def _find_play(self, user_id: UUID, day: date) -> DailyWordPlay | None:
        return (
            await self.session.exec(
                select(DailyWordPlay).where(DailyWordPlay.user_id == user_id).where(DailyWordPlay.day == day)
            )
        ).first()

    async def _lock_play(self, user_id: UUID, day: date) -> DailyWordPlay:
        """The caller's play of ``day``, created if this is their first move, row-locked.

        ``INSERT … ON CONFLICT DO NOTHING`` rather than read-then-insert: two first moves
        would otherwise both read "no play" and the second insert would 500 on the unique
        constraint. ``populate_existing`` so the locked read wins over anything cached.
        """
        insert = (
            dialect_insert(self.session, DailyWordPlay)
            .values(DailyWordPlay(user_id=user_id, day=day).model_dump())
            .on_conflict_do_nothing(index_elements=list(DAILY_WORD_PLAY_UNIQUE_COLUMNS))
        )
        await self.session.exec(insert)
        statement = (
            select(DailyWordPlay)
            .where(DailyWordPlay.user_id == user_id)
            .where(DailyWordPlay.day == day)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.exec(statement)).one()

    @staticmethod
    def _ensure_open(play: DailyWordPlay) -> None:
        if _is_finished(play):
            raise DailyWordAlreadyFinishedError(day=play.day)

    # ── The state ────────────────────────────────────────────────

    async def _build_state(
        self, day: date, word: QuizWord, user_id: UUID | None, play: DailyWordPlay | None, lang: str
    ) -> DailyWordState:
        """What the caller may see. ``play`` None: not started (or anonymous) — hint 1 only."""
        max_hints = ladder_length(word.hints)
        revealed = min(play.hints_revealed if play is not None else DAILY_WORD_INITIAL_HINTS, max_hints)
        finished = play is not None and _is_finished(play)
        streak, best_streak = await self._streaks(user_id, day) if user_id is not None else (None, None)
        answer = await self._answer(user_id, word, lang) if finished and user_id is not None else None
        return DailyWordState(
            day=day,
            number=daily_word_number(day),
            category=_category_key(word.category),
            max_hints=max_hints,
            hints=_resolve_hints(word.hints, revealed, lang),
            hints_revealed=revealed,
            status=_status(play),
            attempts=play.attempts if play is not None else 0,
            guesses=list(play.guesses) if play is not None else [],
            score=play.score if play is not None else None,
            streak=streak,
            best_streak=best_streak,
            solvers_today=await self._count_solvers(day),
            next_day_at=next_day_starts_at(day),
            answer=answer,
        )

    async def _streaks(self, user_id: UUID, today: date) -> tuple[int, int]:
        """(streak, best streak) from ONE query over the caller's plays."""
        rows = (
            await self.session.exec(
                select(col(DailyWordPlay.day), col(DailyWordPlay.solved_at), col(DailyWordPlay.gave_up)).where(
                    DailyWordPlay.user_id == user_id
                )
            )
        ).all()
        solved_days = [day for day, solved_at, _ in rows if solved_at is not None]
        gave_up_today = any(day == today and gave_up for day, _, gave_up in rows)
        return compute_streaks(solved_days, today=today, gave_up_today=gave_up_today)

    async def _count_solvers(self, day: date) -> int:
        return (
            await self.session.exec(
                select(func.count())
                .select_from(DailyWordPlay)
                .where(DailyWordPlay.day == day)
                .where(col(DailyWordPlay.solved_at).is_not(None))
            )
        ).one()

    async def _answer(self, user_id: UUID, word: QuizWord, lang: str) -> DailyWordAnswer:
        """The word as the notebook shows a Word Quiz word, and whether the caller kept it."""
        forms = await self._notebook.get_word_forms(NotebookGameType.DAILY_WORD, word.word_en, lang=lang)
        entry = await self._notebook.find_entry(user_id, NotebookGameType.DAILY_WORD, word.word_en)
        return DailyWordAnswer(
            word_display=forms.word_display,
            word_ar=forms.word_ar,
            word_ar_vocalized=forms.word_ar_vocalized,
            explanation=forms.hint,
            kept=entry is not None,
            entry_id=entry.id if entry is not None else None,
        )


def _is_finished(play: DailyWordPlay) -> bool:
    return play.solved_at is not None or play.gave_up


def _status(play: DailyWordPlay | None) -> DailyWordStatus:
    if play is None:
        return DailyWordStatus.NOT_STARTED
    if play.solved_at is not None:
        return DailyWordStatus.SOLVED
    if play.gave_up:
        return DailyWordStatus.GAVE_UP
    return DailyWordStatus.PLAYING


def _resolve_hints(hints: dict, revealed: int, lang: str) -> list[str]:
    """The first ``revealed`` rungs in ``lang`` — never one more."""
    resolved = (resolve_multilingual(hints.get(str(rung)), lang) for rung in range(1, revealed + 1))
    return [text for text in resolved if text]


def _category_key(category: str) -> WordQuizCategory | None:
    """The stored ``QuizWord.category`` label as its stable key, like Kalimat's state."""
    key = WORD_QUIZ_CATEGORY_KEYS.get(category)
    return WordQuizCategory(key) if key else None
