from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_
from sqlalchemy.dialects.postgresql import Insert as PostgresqlInsert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert
from sqlmodel import col, desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import DEFAULT_WORD_QUIZ_MAX_HINTS, NOTEBOOK_PAGE_DEFAULT_LIMIT, NOTEBOOK_UNIQUE_COLUMNS
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.term_script import TermScriptController
from majlisna.api.models.codenames import CodenamesWord
from majlisna.api.models.notebook import NotebookEntry, NotebookGameType
from majlisna.api.models.table import Game
from majlisna.api.models.undercover import Word
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.error import (
    InvalidNotebookCursorError,
    NotebookEntryNotFoundError,
    NotebookGameTypeNotSupportedError,
    TermNotInGameError,
)
from majlisna.api.schemas.notebook import (
    KeepWordRequest,
    NotebookContentDetails,
    NotebookEntryView,
    NotebookGameWord,
    NotebookGameWords,
    NotebookKeepResponse,
    NotebookPage,
    NotebookWordForms,
)
from majlisna.api.schemas.term_script import TermScriptForms
from majlisna.api.utils.cursor import decode_cursor, encode_cursor
from majlisna.api.utils.dialect import dialect_insert
from majlisna.api.utils.multilingual import resolve_multilingual

# A kept word, as the display resolution addresses it.
type WordKey = tuple[NotebookGameType, str]
# The types whose words are QuizWords (keyed by `word_en`): one `quiz_word` lookup
# serves them all, and they read their own `word_ar` first. A tuple, so `in` compares
# by equality (a member and its plain-string value both match; see the hash note below).
_QUIZ_WORD_TYPES = (NotebookGameType.WORD_QUIZ, NotebookGameType.DAILY_WORD)
# The types a finished Game can be kept from. Plain strings: an enum member hashes by
# its name, so `"undercover" in set(NotebookGameType)` would be False even though the
# two compare equal. The word of the day is no Game: it is kept through /daily-word.
_KEEPABLE_GAME_TYPES = frozenset(member.value for member in NotebookGameType if member != NotebookGameType.DAILY_WORD)


class NotebookController:
    """The Kunnash (كُنّاش): each player's notebook of words kept from finished games.

    Keeping is gated exactly like ``GET /games/{id}/summary`` — through
    ``GameController.get_past_game_for_participant`` — because the words ARE the
    secret while a game runs: the game must be over and the caller must have
    played it. A single word must also be one the game actually dealt, so the
    endpoint can neither probe for nor inject arbitrary terms.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._game_controller = GameController(session)
        self._term_script_controller = TermScriptController(session)

    # ── Keep ─────────────────────────────────────────────────────

    async def keep_game_words(self, game_id: UUID, user_id: UUID, *, lang: str = "en") -> NotebookKeepResponse:
        """Keep every word of a finished game the caller took part in. Idempotent.

        Undercover: the civilian and the undercover word. Codenames: all 25 board
        words. Word Quiz: every round's word. MCQ: refused (a question is not a word).
        """
        game, game_type = await self._get_keepable_game(game_id, user_id)
        aliases = await self._get_game_aliases(game, game_type)
        terms = list(dict.fromkeys(aliases.values()))
        return await self._keep(user_id, game.id, game_type, terms, lang)

    async def keep_word(self, user_id: UUID, request: KeepWordRequest, *, lang: str = "en") -> NotebookKeepResponse:
        """Keep ONE word of a finished game the caller took part in. Idempotent.

        :raises TermNotInGameError: the game never dealt this word (404).
        """
        game, game_type = await self._get_keepable_game(request.game_id, user_id)
        aliases = await self._get_game_aliases(game, game_type)
        term = aliases.get(request.word.strip())
        if term is None:
            raise TermNotInGameError(game_id=request.game_id, term=request.word)
        return await self._keep(user_id, game.id, game_type, [term], lang)

    async def keep_daily_word(self, user_id: UUID, term: str, *, lang: str = "en") -> NotebookKeepResponse:
        """Keep a word of the day (a QuizWord's ``word_en``). Idempotent.

        No gate here: ``DailyWordController.keep`` has already checked that the caller
        finished that day — a word of the day is revealed to its player only then.
        """
        return await self._keep(user_id, None, NotebookGameType.DAILY_WORD, [term], lang)

    async def get_word_forms(self, game_type: NotebookGameType, term: str, *, lang: str = "en") -> NotebookWordForms:
        """How one word reads in ``lang`` — what the notebook would show for it."""
        forms = await self._resolve_forms([(game_type, term)], lang)
        return forms[(game_type, term)]

    async def find_entry(self, user_id: UUID, game_type: NotebookGameType, term: str) -> NotebookEntry | None:
        """The caller's entry for this word of this type, if they kept it."""
        entries = await self._kept_entries(user_id, game_type, [term])
        return entries[0] if entries else None

    async def get_game_words(self, game_id: UUID, user_id: UUID, *, lang: str = "en") -> NotebookGameWords:
        """Every word a finished game dealt, resolved, with whether the caller has kept it.

        What the game-over colophon lists: one call, whatever the game, in the order
        the game dealt them. Word Quiz needs it most — its state only ever carries the
        current round's answer — and every game needs ``kept`` / ``entry_id`` so a
        revisit shows what is already in the notebook and can un-keep it. Same gates
        as keeping: a stranger or a running game reveals nothing.
        """
        game, game_type = await self._get_keepable_game(game_id, user_id)
        aliases = await self._get_game_aliases(game, game_type)
        terms = list(dict.fromkeys(aliases.values()))
        if not terms:
            return NotebookGameWords(game_id=game.id, game_type=game_type, words=[])

        forms = await self._resolve_forms([(game_type, term) for term in terms], lang)
        kept = {entry.term: entry for entry in await self._kept_entries(user_id, game_type, terms)}
        return NotebookGameWords(
            game_id=game.id,
            game_type=game_type,
            words=[
                NotebookGameWord(
                    word=term,
                    **forms[(game_type, term)].model_dump(),
                    kept=term in kept,
                    entry_id=kept[term].id if term in kept else None,
                )
                for term in terms
            ],
        )

    async def _get_keepable_game(self, game_id: UUID, user_id: UUID) -> tuple[Game, NotebookGameType]:
        """The game, past the summary's gates, and the notebook type of its words.

        The gates run first, so a stranger learns nothing — not even the game type —
        about a game they did not play.
        """
        game = await self._game_controller.get_past_game_for_participant(game_id, user_id)
        if game.type.value not in _KEEPABLE_GAME_TYPES:
            raise NotebookGameTypeNotSupportedError(game_id=game_id, game_type=game.type.value)
        return game, NotebookGameType(game.type.value)

    async def _get_game_aliases(self, game: Game, game_type: NotebookGameType) -> dict[str, str]:
        """Every word the game dealt: each spelling a client may send → the stored term.

        Ordered as the game dealt them. Undercover and Codenames words are only
        ever shown by their Latin key (the Arabic is a separate field), so that is
        the one spelling; see ``_get_quiz_aliases`` for Word Quiz.
        """
        state = game.live_state or {}
        if game_type == NotebookGameType.WORD_QUIZ:
            return await self._get_quiz_aliases(state)
        if game_type == NotebookGameType.UNDERCOVER:
            words = [state.get("civilian_word"), state.get("undercover_word")]
        else:
            words = [card.get("word") for card in state.get("board", [])]
        return {word: word for word in words if word}

    async def _get_quiz_aliases(self, state: dict) -> dict[str, str]:
        """A Word Quiz game's words, by every spelling the game showed → ``word_en``.

        The game reveals each answer in the player's language (``correct_answer``
        is ``word_fr`` / ``word_ar`` in a French or Arabic UI), so a single keep
        accepts any of the three and stores the Latin key. ``word_en`` wins a clash.
        One query, for the words of every round (``used_word_ids``).
        """
        word_ids = [UUID(word_id) for word_id in state.get("used_word_ids", [])]
        if not word_ids:
            return {}
        rows = (await self.session.exec(select(QuizWord).where(col(QuizWord.id).in_(word_ids)))).all()
        by_id = {row.id: row for row in rows}
        played = [by_id[word_id] for word_id in word_ids if word_id in by_id]
        aliases = {word.word_en: word.word_en for word in played}
        for word in played:
            for spelling in (word.word_fr, word.word_ar):
                if spelling:
                    aliases.setdefault(spelling, word.word_en)
        return aliases

    async def _keep(
        self, user_id: UUID, source_game_id: UUID | None, game_type: NotebookGameType, terms: list[str], lang: str
    ) -> NotebookKeepResponse:
        """Insert the terms not yet kept, then return every requested entry.

        ``INSERT … ON CONFLICT DO NOTHING`` rather than read-then-insert: two
        concurrent keeps (a double tap, two tabs) both reading "not kept yet" would
        otherwise collide on the unique constraint and answer a 500. With it, each
        word is inserted once and ``RETURNING`` says exactly which call added it.
        """
        if not terms:
            return NotebookKeepResponse(added=0, already_kept=0, entries=[])

        kept_at = datetime.now(UTC)
        rows = [
            NotebookEntry(
                user_id=user_id, term=term, game_type=game_type, source_game_id=source_game_id, kept_at=kept_at
            ).model_dump()
            for term in terms
        ]
        statement = (
            self._insert_statement()
            .values(rows)
            .on_conflict_do_nothing(index_elements=list(NOTEBOOK_UNIQUE_COLUMNS))
            .returning(col(NotebookEntry.id))
        )
        added = len((await self.session.exec(statement)).scalars().all())
        await self.session.commit()

        by_term = {entry.term: entry for entry in await self._kept_entries(user_id, game_type, terms)}
        ordered = [by_term[term] for term in terms if term in by_term]
        return NotebookKeepResponse(
            added=added,
            already_kept=len(terms) - added,
            entries=await self._to_views(ordered, lang),
        )

    async def _kept_entries(
        self, user_id: UUID, game_type: NotebookGameType, terms: list[str]
    ) -> Sequence[NotebookEntry]:
        """The caller's entries for these words of one game type — one query."""
        return (
            await self.session.exec(
                select(NotebookEntry)
                .where(NotebookEntry.user_id == user_id)
                .where(NotebookEntry.game_type == game_type)
                .where(col(NotebookEntry.term).in_(terms))
            )
        ).all()

    def _insert_statement(self) -> PostgresqlInsert | SqliteInsert:
        """The dialect's INSERT, which is what carries ``on_conflict_do_nothing``."""
        return dialect_insert(self.session, NotebookEntry)

    # ── Read / delete ────────────────────────────────────────────

    async def list_entries(
        self,
        user_id: UUID,
        *,
        lang: str = "en",
        limit: int = NOTEBOOK_PAGE_DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> NotebookPage:
        """One page of the caller's notebook, newest first, resolved for display.

        Keyset-paginated on (``kept_at``, ``id``) — ``id`` breaks ties, because a whole
        Codenames board is kept in one call and shares one ``kept_at``. ``cursor`` is
        the previous page's ``next_cursor``. Unlike an offset, deleting an entry (or
        keeping one from another tab) between two pages neither skips nor repeats one.

        :raises InvalidNotebookCursorError: a cursor the server did not hand out (400).
        """
        total = (
            await self.session.exec(
                select(func.count()).select_from(NotebookEntry).where(NotebookEntry.user_id == user_id)
            )
        ).one()
        statement = select(NotebookEntry).where(NotebookEntry.user_id == user_id)
        if cursor is not None:
            statement = statement.where(self._after_cursor(cursor))
        # One row more than the page: whether it exists is whether there is a next page.
        rows = (
            await self.session.exec(
                statement.order_by(desc(NotebookEntry.kept_at), desc(NotebookEntry.id)).limit(limit + 1)
            )
        ).all()
        page = rows[:limit]
        next_cursor = encode_cursor(_aware(page[-1].kept_at), page[-1].id) if len(rows) > limit else None
        return NotebookPage(entries=await self._to_views(page, lang), total=total, next_cursor=next_cursor)

    @staticmethod
    def _after_cursor(cursor: str) -> ColumnElement[bool]:
        """The rows strictly after the cursor's, in the listing's (kept_at, id) DESC order."""
        try:
            kept_at, entry_id = decode_cursor(cursor)
        except ValueError as error:
            raise InvalidNotebookCursorError(cursor=cursor) from error
        return or_(
            col(NotebookEntry.kept_at) < kept_at,
            and_(col(NotebookEntry.kept_at) == kept_at, col(NotebookEntry.id) < entry_id),
        )

    async def delete_entry(self, user_id: UUID, entry_id: UUID) -> None:
        """Remove one of the caller's entries.

        Another user's entry answers the same 404 as a missing one, so entry ids
        cannot be probed.
        """
        entry = (
            await self.session.exec(
                select(NotebookEntry).where(NotebookEntry.id == entry_id).where(NotebookEntry.user_id == user_id)
            )
        ).first()
        if entry is None:
            raise NotebookEntryNotFoundError(entry_id=entry_id)
        await self.session.delete(entry)
        await self.session.commit()

    # ── Display resolution ───────────────────────────────────────

    async def _to_views(self, entries: Sequence[NotebookEntry], lang: str) -> list[NotebookEntryView]:
        """Resolve entries for display with batched reads, never one per entry."""
        if not entries:
            return []
        forms = await self._resolve_forms([(entry.game_type, entry.term) for entry in entries], lang)
        return [
            NotebookEntryView(
                id=entry.id,
                word=entry.term,
                game_type=entry.game_type,
                **forms[(entry.game_type, entry.term)].model_dump(),
                source_game_id=entry.source_game_id,
                kept_at=_aware(entry.kept_at),
            )
            for entry in entries
        ]

    async def _resolve_forms(self, keys: Sequence[WordKey], lang: str) -> dict[WordKey, NotebookWordForms]:
        """How each (game type, word) reads in ``lang`` — batched.

        One ``term_script`` lookup for every word, plus at most one query per content
        table (``word``, ``codenames_word``, ``quiz_word``), and only for the game
        types present.
        """
        scripts = await self._term_script_controller.get_forms(term for _, term in keys)
        details = await self._get_content_details(keys, lang)
        return {
            (game_type, term): self._forms(game_type, term, scripts.get(term), details.get((game_type, term)))
            for game_type, term in keys
        }

    async def _get_content_details(self, keys: Iterable[WordKey], lang: str) -> dict[WordKey, NotebookContentDetails]:
        """Hints (and Word Quiz's own Arabic and spellings), keyed by (game type, word).

        One query per content table: Word Quiz and word-of-the-day entries are both
        QuizWords, so they share one ``quiz_word`` lookup.
        """
        keys = list(keys)
        undercover = sorted({term for game_type, term in keys if game_type == NotebookGameType.UNDERCOVER})
        codenames = sorted({term for game_type, term in keys if game_type == NotebookGameType.CODENAMES})
        quiz = sorted({term for game_type, term in keys if game_type in _QUIZ_WORD_TYPES})
        found: dict[NotebookGameType, dict[str, NotebookContentDetails]] = {}
        if undercover:
            found[NotebookGameType.UNDERCOVER] = await self._get_undercover_details(undercover, lang)
        if codenames:
            found[NotebookGameType.CODENAMES] = await self._get_codenames_details(codenames, lang)
        if quiz:
            quiz_details = await self._get_quiz_details(quiz, lang)
            for game_type in _QUIZ_WORD_TYPES:
                found[game_type] = quiz_details

        details: dict[WordKey, NotebookContentDetails] = {}
        for game_type, term in keys:
            detail = found.get(game_type, {}).get(term)
            if detail is not None:
                details[(game_type, term)] = detail
        return details

    async def _get_undercover_details(self, terms: list[str], lang: str) -> dict[str, NotebookContentDetails]:
        """Undercover words' hints (``Word.word`` is unique). English description as a fallback."""
        rows = (await self.session.exec(select(Word).where(col(Word.word).in_(terms)))).all()
        return {
            row.word: NotebookContentDetails(hint=resolve_multilingual(row.hint, lang) or row.long_description)
            for row in rows
        }

    async def _get_codenames_details(self, terms: list[str], lang: str) -> dict[str, NotebookContentDetails]:
        """Codenames words' hints. A word can sit in several packs: the oldest row with a hint wins."""
        rows = (
            await self.session.exec(
                select(CodenamesWord)
                .where(col(CodenamesWord.word).in_(terms))
                .order_by(col(CodenamesWord.created_at), col(CodenamesWord.id))
            )
        ).all()
        details: dict[str, NotebookContentDetails] = {}
        for row in rows:
            hint = resolve_multilingual(row.hint, lang)
            if hint:
                details.setdefault(row.word, NotebookContentDetails(hint=hint))
        return details

    async def _get_quiz_details(self, terms: list[str], lang: str) -> dict[str, NotebookContentDetails]:
        """Word Quiz words: their own Arabic, their spelling in ``lang``, and the explanation
        (else the most specific hint)."""
        rows = (
            await self.session.exec(
                select(QuizWord)
                .where(col(QuizWord.word_en).in_(terms))
                .order_by(col(QuizWord.created_at), col(QuizWord.id))
            )
        ).all()
        details: dict[str, NotebookContentDetails] = {}
        for row in rows:
            last_hint = (row.hints or {}).get(str(DEFAULT_WORD_QUIZ_MAX_HINTS))
            hint = resolve_multilingual(row.explanation, lang) or resolve_multilingual(last_hint, lang)
            details.setdefault(
                row.word_en,
                NotebookContentDetails(word_ar=row.word_ar, word_display=_quiz_spelling(row, lang), hint=hint),
            )
        return details

    @staticmethod
    def _forms(
        game_type: NotebookGameType, term: str, script: TermScriptForms | None, detail: NotebookContentDetails | None
    ) -> NotebookWordForms:
        """One word for display.

        Undercover and Codenames: term_script is THE source of their Arabic. Word Quiz:
        the word's own ``word_ar`` first — it is the Arabic the game revealed as the
        answer, and term_script is keyed by Latin spellings an Undercover or Codenames
        term may share with a different meaning — term_script only as a fallback. A
        vocalised form is taken from term_script only when it vocalises that same
        Arabic, never glued onto another word's.
        """
        word_display = detail.word_display if detail and detail.word_display else term
        hint = detail.hint if detail else None
        own_ar = detail.word_ar if detail else None
        if game_type in _QUIZ_WORD_TYPES and own_ar:
            vocalized = script.ar_vocalized if script and script.ar == own_ar else None
            return NotebookWordForms(word_display=word_display, word_ar=own_ar, word_ar_vocalized=vocalized, hint=hint)
        if script:
            return NotebookWordForms(
                word_display=word_display, word_ar=script.ar, word_ar_vocalized=script.ar_vocalized, hint=hint
            )
        return NotebookWordForms(word_display=word_display, word_ar=own_ar, hint=hint)


def _aware(instant: datetime) -> datetime:
    """SQLite (dev, tests) reads a TIMESTAMP WITH TIME ZONE back naive; the value was
    written as UTC, and a naive one would read as browser-local time."""
    return instant if instant.tzinfo else instant.replace(tzinfo=UTC)


def _quiz_spelling(word: QuizWord, lang: str) -> str:
    """The spelling a Word Quiz game shows in ``lang`` — the rule of ``WordQuizGameController._get_correct_answer``."""
    if lang == "ar" and word.word_ar:
        return word.word_ar
    if lang == "fr" and word.word_fr:
        return word.word_fr
    return word.word_en
