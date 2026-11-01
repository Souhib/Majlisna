"""Samar riddles (السَّمَر): what a table turns over while it waits.

The samar is the evening majlis of talk and riddles. While the lobby waits for its
quorum or its host, and between two questions of The Quiz, each member is offered the
vaguest rung of a random Kalimat word, and its answer for later. Existing content only
(PRODUCT.md): the rung and the answer are the word's own.

A riddle is a pastime, so it must never spoil a game:

- never today's word of the day — drawn first if nobody has asked for it yet, or the
  day's draw could land on the riddle just shown — nor one of the last
  ``DAILY_WORD_NO_REPEAT_DAYS`` (unless nothing else is left: those are old news);
- never a right answer of the room's running quiz: The Quiz deals all its questions at
  the start (``question_ids``), so every one is known and left out, in any script;
- no riddle at all while another game is played: Kalimat draws its words one round at a
  time (``used_word_ids`` grows as it goes), so a riddle between its rounds could be a
  LATER round's word, and Undercover and Codenames are not a waiting table.
"""

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import DAILY_WORD_NO_REPEAT_DAYS, ROOM_RIDDLE_HINT_RUNG, WORD_QUIZ_CATEGORY_KEYS
from majlisna.api.controllers.daily_word import DailyWordController
from majlisna.api.controllers.notebook import NotebookController
from majlisna.api.models.daily_word import DailyWord
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.mcqquiz import McqQuestion
from majlisna.api.models.notebook import NotebookGameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.error import NoQuizWordsAvailableError, RiddleNotDuringGameError, RoomMembersOnlyError
from majlisna.api.schemas.riddle import RoomRiddle, RoomRiddleAnswer
from majlisna.api.schemas.wordquiz import WordQuizCategory
from majlisna.api.utils.daily_word import makkah_day
from majlisna.api.utils.multilingual import normalize_lang, resolve_multilingual
from majlisna.api.utils.rng import rng
from majlisna.api.utils.text_match import (
    fold_arabic_letters,
    fold_arabic_spellings,
    normalize_answer,
    strip_arabic_article,
    strip_article,
)

# The running games a riddle may be shown beside: their every word is dealt at the start.
_GAMES_DEALT_AT_START = (GameType.MCQ_QUIZ,)


class RiddleController:
    """``GET /rooms/{room_id}/riddle``: one riddle for a member of the room (spectators
    included), resolved in ``lang``. Reads only, but for the day's lazy draw."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._notebook = NotebookController(session)

    async def get_room_riddle(self, room_id: UUID, user_id: UUID, *, lang: str = "en") -> RoomRiddle:
        """A random riddle the room's running game cannot be spoiled by.

        :raises RoomMembersOnlyError: the caller has no seat in the room (403).
        :raises RiddleNotDuringGameError: a game other than The Quiz is being played (409).
        :raises NoQuizWordsAvailableError: no word is left to ask (400).
        """
        # one of the three languages: the notebook's spelling compares it raw ("ar-SA" read as English)
        lang = normalize_lang(lang)
        await self._require_member(room_id, user_id)
        game_answers = await self._running_game_answers(room_id)
        word = await self._draw_word(game_answers)
        forms = await self._notebook.get_word_forms(NotebookGameType.WORD_QUIZ, word.word_en, lang=lang)
        return RoomRiddle(
            id=word.id,
            category=_category_key(word.category),
            hint=_first_rung(word, lang) or "",
            answer=RoomRiddleAnswer(
                word_display=forms.word_display,
                word_ar=forms.word_ar,
                word_ar_vocalized=forms.word_ar_vocalized,
            ),
        )

    async def _require_member(self, room_id: UUID, user_id: UUID) -> None:
        """A seat (or a spectator's place) by its link, like the chat: a member who is
        briefly disconnected still belongs to the table. Asked first, so a stranger
        learns nothing about the room."""
        link = (
            await self.session.exec(
                select(col(RoomUserLink.id)).where(RoomUserLink.room_id == room_id, RoomUserLink.user_id == user_id)
            )
        ).first()
        if link is None:
            raise RoomMembersOnlyError(room_id=room_id, user_id=user_id)

    async def _running_game_answers(self, room_id: UUID) -> set[str]:
        """The answer keys of the room's running quiz (none without a running game)."""
        game = (
            await self.session.exec(
                select(Game).join(Room, col(Room.active_game_id) == col(Game.id)).where(Room.id == room_id)
            )
        ).first()
        if game is None or game.game_status != GameStatus.IN_PROGRESS:
            return set()
        if game.type not in _GAMES_DEALT_AT_START:
            raise RiddleNotDuringGameError(room_id=room_id, game_type=game.type.value)
        return await self._quiz_answer_keys(game.live_state or {})

    async def _quiz_answer_keys(self, state: Mapping[str, object]) -> set[str]:
        """Every right answer The Quiz dealt (and its current question, which a fallback
        draw may have added), in every language, as matching keys."""
        raw_ids = state.get("question_ids")
        question_ids = [UUID(qid) for qid in raw_ids if isinstance(qid, str)] if isinstance(raw_ids, list) else []
        rows = (
            (
                await self.session.exec(
                    select(col(McqQuestion.choices), col(McqQuestion.correct_answer_index)).where(
                        col(McqQuestion.id).in_(question_ids)
                    )
                )
            ).all()
            if question_ids
            else []
        )
        questions: list[tuple[object, object]] = [(choices, index) for choices, index in rows]
        current = state.get("current_question")
        if isinstance(current, Mapping):
            questions.append((current.get("choices"), current.get("correct_answer_index")))

        keys: set[str] = set()
        for choices, index in questions:
            right = choices.get(str(index)) if isinstance(choices, Mapping) else None
            if isinstance(right, Mapping):
                keys |= _answer_keys(right.values())
        return keys

    async def _draw_word(self, game_answers: set[str]) -> QuizWord:
        """A random word with a first rung: never today's word of the day, nor a recent one
        unless nothing else is left, nor an answer of the running game."""
        today = makkah_day()
        await self._ensure_word_of_the_day(today)
        candidates: list[UUID] = []
        for days_left_out in (DAILY_WORD_NO_REPEAT_DAYS, 0):
            candidates = await self._candidate_ids(today - timedelta(days=days_left_out), game_answers)
            if candidates:
                break
        rng.shuffle(candidates)
        for word_id in candidates:
            word = (await self.session.exec(select(QuizWord).where(QuizWord.id == word_id))).first()
            if word is not None and _first_rung(word, "en"):
                return word
        raise NoQuizWordsAvailableError()

    async def _ensure_word_of_the_day(self, today: date) -> None:
        """The day's word is drawn by the day's first request; a riddle asked before it would
        not know which word to keep back. Draws it the way /daily-word does."""
        drawn = (await self.session.exec(select(col(DailyWord.day)).where(DailyWord.day == today))).first()
        if drawn is None:
            await DailyWordController(self.session).get_today(None)

    async def _candidate_ids(self, daily_since: date, game_answers: set[str]) -> list[UUID]:
        """The words not drawn as the word of the day since ``daily_since`` (today included),
        nor matching an answer of the running game."""
        recent = select(DailyWord.quiz_word_id).where(DailyWord.day >= daily_since)
        if not game_answers:
            ids = await self.session.exec(
                select(col(QuizWord.id)).where(col(QuizWord.id).not_in(recent)).order_by(col(QuizWord.id))
            )
            return list(ids.all())
        # Two narrow reads (sqlmodel's select types four columns at most), never the rows
        # with their ladders and explanations.
        spellings = await self.session.exec(
            select(col(QuizWord.id), col(QuizWord.word_en), col(QuizWord.word_ar), col(QuizWord.word_fr))
            .where(col(QuizWord.id).not_in(recent))
            .order_by(col(QuizWord.id))
        )
        accepted = dict((await self.session.exec(select(col(QuizWord.id), col(QuizWord.accepted_answers)))).all())
        return [
            word_id
            for word_id, word_en, word_ar, word_fr in spellings.all()
            if not _answer_keys(_spellings(word_en, word_ar, word_fr, accepted.get(word_id))) & game_answers
        ]


def _spellings(word_en: str, word_ar: str | None, word_fr: str | None, accepted: object) -> list[object]:
    """Every way a word is written: its three spellings and its accepted answers."""
    variants: list[object] = [word_en, word_ar, word_fr]
    if isinstance(accepted, Mapping):
        for answers in accepted.values():
            if isinstance(answers, list):
                variants.extend(answers)
    return variants


def _answer_keys(texts: Iterable[object]) -> set[str]:
    """Matching keys, broader than Kalimat's own match: diacritics, accents, case, hyphens,
    Arabic letter variants and the article (in either script) ignored, and each side of
    "Ibrahim / Abraham" on its own. A key shared by a word and a game's answer leaves the
    word out: a wider net here only ever skips a riddle."""
    keys: set[str] = set()
    for text in texts:
        if not isinstance(text, str):
            continue
        for part in text.split("/"):
            base = normalize_answer(part)
            if not base:
                continue
            keys.add(strip_article(base))
            keys.add(strip_arabic_article(strip_article(fold_arabic_spellings(fold_arabic_letters(base)))))
    return keys


def _first_rung(word: QuizWord, lang: str) -> str | None:
    return resolve_multilingual((word.hints or {}).get(str(ROOM_RIDDLE_HINT_RUNG)), lang)


def _category_key(category: str) -> WordQuizCategory | None:
    """The stored ``QuizWord.category`` label as its stable key, like Kalimat's state."""
    key = WORD_QUIZ_CATEGORY_KEYS.get(category)
    return WordQuizCategory(key) if key else None
