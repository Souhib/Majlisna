"""Tests for the NotebookController — the Kunnash (كُنّاش) of words kept from finished games."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.notebook import NotebookController
from majlisna.api.models.codenames import CodenamesWord, CodenamesWordPack
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.notebook import NotebookEntry, NotebookGameType
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.undercover import Word
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.error import (
    GameNotFoundError,
    GameStillInProgressError,
    InvalidNotebookCursorError,
    NotAGameParticipantError,
    NotebookEntryNotFoundError,
    NotebookGameTypeNotSupportedError,
    TermNotInGameError,
)
from majlisna.api.schemas.notebook import KeepWordRequest
from majlisna.api.utils.cursor import encode_cursor

# ─── Content ──────────────────────────────────────────────────

SABR_HINT = {"en": "Patience in hardship", "fr": "Patience dans l'épreuve", "ar": "الصبر على الشدائد"}
UNDERCOVER_SCRIPTS: dict[str, tuple[str, str | None]] = {"Sabr": ("صبر", "صَبْر"), "Shukr": ("شكر", None)}

# 25 board words; two of them carry Arabic forms, one without a certain vocalisation.
BOARD_WORDS = ["Uhud", "Thawr", *[f"Kalima{i:02d}" for i in range(23)]]
BOARD_SCRIPTS: dict[str, tuple[str, str | None]] = {"Uhud": ("أحد", "أُحُد"), "Thawr": ("ثور", None)}


def encode_cursor_naive_example() -> str:
    """A well-formed cursor whose instant is naive — never one the server hands out."""
    return encode_cursor(datetime(2026, 1, 1), uuid4())  # naive on purpose


def _undercover_state(civilian: str = "Sabr", undercover: str = "Shukr") -> dict:
    return {"players": [], "civilian_word": civilian, "undercover_word": undercover, "winner": "civilians"}


def _codenames_state(words: list[str] = BOARD_WORDS) -> dict:
    return {
        "players": [],
        "board": [{"word": word, "card_type": "neutral", "revealed": False} for word in words],
        "winner": "red",
    }


def _quiz_state(quiz_words: list[QuizWord]) -> dict:
    return {"players": [], "used_word_ids": [str(word.id) for word in quiz_words], "winner": "keeper"}


async def _entries(session: AsyncSession, user_id) -> list[NotebookEntry]:
    """Re-fetch a user's notebook rows straight from the database."""
    return list((await session.exec(select(NotebookEntry).where(NotebookEntry.user_id == user_id))).all())


# ─── Fixtures ─────────────────────────────────────────────────


@pytest_asyncio.fixture(name="player")
async def get_player(create_user) -> User:
    """The player keeping words; owner (and so participant) of every game below."""
    return await create_user(username="keeper", email="keeper@test.com")


@pytest_asyncio.fixture(name="room")
async def get_room(player: User, create_room) -> Room:
    return await create_room(owner=player)


@pytest_asyncio.fixture(name="make_game")
async def get_make_game(session: AsyncSession, game_controller: GameController, room: Room):
    """Factory: a game in the player's room, in the given status, with the given live_state.

    ``create_game`` links every room member to the game, so the player is a participant.
    """

    async def _make_game(game_type: GameType, live_state: dict, status: GameStatus = GameStatus.FINISHED) -> Game:
        game = await game_controller.create_game(GameCreate(room_id=room.id, type=game_type, number_of_players=1))
        game.live_state = live_state
        game.game_status = status
        session.add(game)
        await session.commit()
        return game

    return _make_game


@pytest_asyncio.fixture(name="undercover_content")
async def get_undercover_content(session: AsyncSession, create_term_scripts) -> None:
    """Word rows for Sabr (multilingual hint), Shukr (no hint: description only) and Hajj."""
    session.add(
        Word(word="Sabr", category="virtue", short_description="Patience", long_description="Long sabr", hint=SABR_HINT)
    )
    session.add(Word(word="Shukr", category="virtue", short_description="Thanks", long_description="Gratitude to God"))
    session.add(Word(word="Hajj", category="pillar", short_description="Pilgrimage", long_description="The pilgrimage"))
    await session.commit()
    await create_term_scripts(UNDERCOVER_SCRIPTS)


@pytest_asyncio.fixture(name="codenames_content")
async def get_codenames_content(session: AsyncSession, create_term_scripts) -> None:
    """A pack holding the 25 board words, each with an en/fr hint."""
    pack = CodenamesWordPack(name="Notebook Pack")
    session.add(pack)
    await session.commit()
    for i, word in enumerate(BOARD_WORDS):
        session.add(CodenamesWord(word=word, word_pack_id=pack.id, hint={"en": f"Meaning {i}", "fr": f"Sens {i}"}))
    await session.commit()
    await create_term_scripts(BOARD_SCRIPTS)


@pytest_asyncio.fixture(name="quiz_words")
async def get_quiz_words(session: AsyncSession, create_quiz_word) -> list[QuizWord]:
    """Ibrahim (with an explanation) and Musa (without one: the last hint stands in)."""
    ibrahim = await create_quiz_word(word_en="Ibrahim", word_ar="إبراهيم", word_fr="Abraham")
    ibrahim.explanation = {"en": "Father of the prophets", "fr": "Père des prophètes", "ar": "أبو الأنبياء"}
    session.add(ibrahim)
    await session.commit()
    musa = await create_quiz_word(word_en="Musa", word_ar="موسى", word_fr="Moïse")
    return [ibrahim, musa]


# ─── keep_game_words ──────────────────────────────────────────


@pytest.mark.usefixtures("undercover_content")
async def test_keep_undercover_game_keeps_both_words(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """The civilian and the undercover word are kept, resolved, and stored with their source game."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state())

    # Act
    result = await notebook_controller.keep_game_words(game.id, player.id, lang="fr")

    # Assert
    assert (result.added, result.already_kept) == (2, 0)
    assert [entry.word for entry in result.entries] == ["Sabr", "Shukr"]
    sabr, shukr = result.entries
    assert (sabr.word_ar, sabr.word_ar_vocalized, sabr.hint) == ("صبر", "صَبْر", SABR_HINT["fr"])
    assert (shukr.word_ar, shukr.word_ar_vocalized, shukr.hint) == ("شكر", None, "Gratitude to God")
    assert all(entry.game_type == NotebookGameType.UNDERCOVER for entry in result.entries)
    assert all(entry.source_game_id == game.id for entry in result.entries)
    assert all(entry.kept_at.tzinfo is not None for entry in result.entries)
    rows = await _entries(session, player.id)
    assert sorted(row.term for row in rows) == ["Sabr", "Shukr"]
    assert {row.id for row in rows} == {entry.id for entry in result.entries}
    assert all(row.source_game_id == game.id and row.game_type == NotebookGameType.UNDERCOVER for row in rows)


@pytest.mark.usefixtures("undercover_content")
async def test_keep_is_idempotent(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """Keeping the same game twice adds nothing the second time and raises nothing."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state())
    first = await notebook_controller.keep_game_words(game.id, player.id)

    # Act
    second = await notebook_controller.keep_game_words(game.id, player.id)

    # Assert
    assert (second.added, second.already_kept) == (0, 2)
    assert [entry.id for entry in second.entries] == [entry.id for entry in first.entries]
    assert len(await _entries(session, player.id)) == 2


@pytest.mark.usefixtures("codenames_content")
async def test_keep_codenames_game_keeps_all_25_board_words(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """Every board word is kept, revealed or not — the game is over."""
    # Prepare
    game = await make_game(GameType.CODENAMES, _codenames_state())

    # Act
    result = await notebook_controller.keep_game_words(game.id, player.id, lang="fr")

    # Assert
    assert (result.added, result.already_kept) == (25, 0)
    assert [entry.word for entry in result.entries] == BOARD_WORDS
    by_term = {entry.word: entry for entry in result.entries}
    assert (by_term["Uhud"].word_ar, by_term["Uhud"].word_ar_vocalized) == ("أحد", "أُحُد")
    assert (by_term["Thawr"].word_ar, by_term["Thawr"].word_ar_vocalized) == ("ثور", None)
    assert (by_term["Kalima00"].word_ar, by_term["Kalima00"].hint) == (None, "Sens 2")
    rows = await _entries(session, player.id)
    assert sorted(row.term for row in rows) == sorted(BOARD_WORDS)
    assert all(row.game_type == NotebookGameType.CODENAMES for row in rows)


async def test_keep_word_quiz_game_keeps_every_round_word(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game, quiz_words
):
    """Each round's word is kept by its word_en; its own Arabic and explanation resolve."""
    # Prepare
    game = await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words))

    # Act
    result = await notebook_controller.keep_game_words(game.id, player.id, lang="fr")

    # Assert
    assert (result.added, result.already_kept) == (2, 0)
    ibrahim, musa = result.entries
    assert (ibrahim.word, ibrahim.word_ar, ibrahim.word_ar_vocalized, ibrahim.hint) == (
        "Ibrahim",
        "إبراهيم",
        None,
        "Père des prophètes",
    )
    # No explanation: the most specific rung of the hint ladder stands in.
    assert (musa.word, musa.word_ar, musa.hint) == ("Musa", "موسى", "Indice 6")
    rows = await _entries(session, player.id)
    assert sorted(row.term for row in rows) == ["Ibrahim", "Musa"]
    assert all(row.game_type == NotebookGameType.WORD_QUIZ for row in rows)


async def test_keep_mcq_game_is_refused(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """An MCQ round is a question, not a word: a clear 400, nothing stored."""
    # Prepare
    game = await make_game(GameType.MCQ_QUIZ, {"players": [], "winner": "keeper"})

    # Act / Assert
    with pytest.raises(NotebookGameTypeNotSupportedError) as error:
        await notebook_controller.keep_game_words(game.id, player.id)
    assert error.value.status_code == 400
    assert await _entries(session, player.id) == []


@pytest.mark.usefixtures("undercover_content")
async def test_keep_in_progress_game_is_refused(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """While the game runs its words are the secret: same 403 as the summary."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state(), status=GameStatus.IN_PROGRESS)

    # Act / Assert
    with pytest.raises(GameStillInProgressError):
        await notebook_controller.keep_game_words(game.id, player.id)
    assert await _entries(session, player.id) == []


@pytest.mark.usefixtures("undercover_content")
async def test_keep_by_non_participant_is_refused(
    notebook_controller: NotebookController, session: AsyncSession, make_game, create_user
):
    """Someone who did not play the game cannot keep (and so read) its words."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state())
    outsider = await create_user(username="outsider", email="outsider@test.com")

    # Act / Assert
    with pytest.raises(NotAGameParticipantError):
        await notebook_controller.keep_game_words(game.id, outsider.id)
    assert await _entries(session, outsider.id) == []


async def test_keep_non_participant_learns_nothing_about_an_mcq_game(
    notebook_controller: NotebookController, make_game, create_user
):
    """The participation gate runs before the game-type check: a stranger gets 403, not 400."""
    # Prepare
    game = await make_game(GameType.MCQ_QUIZ, {"players": []})
    outsider = await create_user(username="outsider", email="outsider@test.com")

    # Act / Assert
    with pytest.raises(NotAGameParticipantError):
        await notebook_controller.keep_game_words(game.id, outsider.id)


async def test_keep_unknown_game_is_not_found(notebook_controller: NotebookController, player: User):
    """A game id that does not exist answers 404."""
    # Act / Assert
    with pytest.raises(GameNotFoundError):
        await notebook_controller.keep_game_words(uuid4(), player.id)


@pytest.mark.usefixtures("undercover_content")
async def test_keep_cancelled_game_passes_the_summary_gates(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """The gates are exactly the summary's: anything not IN_PROGRESS is over."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state(), status=GameStatus.CANCELLED)

    # Act
    result = await notebook_controller.keep_game_words(game.id, player.id)

    # Assert
    assert result.added == 2
    assert len(await _entries(session, player.id)) == 2


@pytest.mark.usefixtures("undercover_content")
async def test_rekeeping_a_word_from_another_game_keeps_the_first_source(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """One entry per (user, game type, term): a later game's copy of a word is "already kept"."""
    # Prepare
    first_game = await make_game(GameType.UNDERCOVER, _undercover_state("Sabr", "Shukr"))
    second_game = await make_game(GameType.UNDERCOVER, _undercover_state("Hajj", "Sabr"))
    await notebook_controller.keep_game_words(first_game.id, player.id)

    # Act
    result = await notebook_controller.keep_game_words(second_game.id, player.id)

    # Assert
    assert (result.added, result.already_kept) == (1, 1)
    rows = {row.term: row for row in await _entries(session, player.id)}
    assert sorted(rows) == ["Hajj", "Sabr", "Shukr"]
    assert rows["Sabr"].source_game_id == first_game.id
    assert rows["Hajj"].source_game_id == second_game.id


@pytest.mark.usefixtures("undercover_content")
async def test_same_term_in_two_games_types_is_two_entries(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """The constraint includes the game type: Sabr from Undercover and from Codenames are distinct lines."""
    # Prepare
    undercover = await make_game(GameType.UNDERCOVER, _undercover_state())
    codenames = await make_game(GameType.CODENAMES, _codenames_state(["Sabr", *BOARD_WORDS[1:]]))
    await notebook_controller.keep_game_words(undercover.id, player.id)

    # Act
    result = await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=codenames.id, word="Sabr"))

    # Assert
    assert result.added == 1
    rows = [row for row in await _entries(session, player.id) if row.term == "Sabr"]
    assert sorted(row.game_type.value for row in rows) == ["codenames", "undercover"]


@pytest.mark.postgres
@pytest.mark.usefixtures("undercover_content")
async def test_concurrent_keeps_insert_each_word_once(
    engine: AsyncEngine, session: AsyncSession, player: User, make_game
):
    """Keeps racing (double tap, several tabs) neither collide nor duplicate: ON CONFLICT DO NOTHING."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state())

    # Act — one session per task, as production gives one per request
    results = await asyncio.gather(*(_keep_in_own_session(engine, game.id, player.id) for _ in range(4)))

    # Assert
    assert sum(result.added for result in results) == 2
    assert all(result.added + result.already_kept == 2 for result in results)
    assert sorted(row.term for row in await _entries(session, player.id)) == ["Sabr", "Shukr"]


async def _keep_in_own_session(engine: AsyncEngine, game_id, user_id):
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await NotebookController(own_session).keep_game_words(game_id, user_id)


# ─── keep_word ────────────────────────────────────────────────


@pytest.mark.usefixtures("codenames_content")
async def test_keep_word_keeps_one_word(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """A single board word is kept, alone, resolved."""
    # Prepare
    game = await make_game(GameType.CODENAMES, _codenames_state())

    # Act
    result = await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="Uhud"), lang="en")

    # Assert
    assert (result.added, result.already_kept) == (1, 0)
    [entry] = result.entries
    assert (entry.word, entry.word_ar, entry.word_ar_vocalized, entry.hint) == ("Uhud", "أحد", "أُحُد", "Meaning 0")
    rows = await _entries(session, player.id)
    assert [(row.term, row.source_game_id) for row in rows] == [("Uhud", game.id)]


@pytest.mark.usefixtures("undercover_content")
async def test_keep_word_twice_is_idempotent(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """The second keep of the same word reports it as already kept; one row, surrounding spaces ignored."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state())
    await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="Sabr"))

    # Act
    result = await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word=" Sabr "))

    # Assert
    assert (result.added, result.already_kept) == (0, 1)
    assert [row.term for row in await _entries(session, player.id)] == ["Sabr"]


@pytest.mark.usefixtures("undercover_content")
async def test_keep_word_not_dealt_by_the_game_is_refused(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """A real word from the content tables that this game never dealt cannot be kept from it."""
    # Prepare — Hajj exists as a Word, but this game dealt Sabr and Shukr
    game = await make_game(GameType.UNDERCOVER, _undercover_state())

    # Act / Assert
    for term in ("Hajj", "anything at all", "sabr"):
        with pytest.raises(TermNotInGameError) as error:
            await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word=term))
        assert error.value.status_code == 404
    assert await _entries(session, player.id) == []


async def test_keep_word_from_word_quiz_accepts_any_spelling_the_game_showed(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game, quiz_words
):
    """A French or Arabic UI shows `word_fr` / `word_ar` as the answer; both keep the word_en entry."""
    # Prepare
    game = await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words))

    # Act
    by_french = await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="Moïse"))
    by_arabic = await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="موسى"))

    # Assert
    assert (by_french.added, by_french.entries[0].word) == (1, "Musa")
    assert (by_arabic.added, by_arabic.already_kept, by_arabic.entries[0].word) == (0, 1, "Musa")
    assert [row.term for row in await _entries(session, player.id)] == ["Musa"]


async def test_keep_word_from_word_quiz_rejects_a_word_of_another_game(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game, quiz_words
):
    """Only the rounds' words count — not every QuizWord in the database."""
    # Prepare — the game played Ibrahim only; Musa exists but was not dealt
    game = await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words[:1]))

    # Act / Assert
    with pytest.raises(TermNotInGameError):
        await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="Musa"))
    assert await _entries(session, player.id) == []


@pytest.mark.usefixtures("undercover_content")
async def test_keep_word_applies_the_same_gates(
    notebook_controller: NotebookController,
    session: AsyncSession,
    player: User,
    make_game,
    create_user,
):
    """In progress → 403, stranger → 403, MCQ → 400; nothing is stored by any of them."""
    # Prepare
    running = await make_game(GameType.UNDERCOVER, _undercover_state(), status=GameStatus.IN_PROGRESS)
    finished = await make_game(GameType.UNDERCOVER, _undercover_state())
    mcq = await make_game(GameType.MCQ_QUIZ, {"players": []})
    outsider = await create_user(username="outsider", email="outsider@test.com")

    # Act / Assert
    with pytest.raises(GameStillInProgressError):
        await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=running.id, word="Sabr"))
    with pytest.raises(NotAGameParticipantError):
        await notebook_controller.keep_word(outsider.id, KeepWordRequest(game_id=finished.id, word="Sabr"))
    with pytest.raises(NotebookGameTypeNotSupportedError):
        await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=mcq.id, word="Sabr"))
    assert await _entries(session, player.id) == []
    assert await _entries(session, outsider.id) == []


# ─── list_entries ─────────────────────────────────────────────


async def _add_entries(session: AsyncSession, user: User, terms: list[str]) -> list[NotebookEntry]:
    """Store Undercover entries one minute apart, oldest first."""
    base = datetime.now(UTC) - timedelta(hours=1)
    entries = [
        NotebookEntry(
            user_id=user.id, term=term, game_type=NotebookGameType.UNDERCOVER, kept_at=base + timedelta(minutes=i)
        )
        for i, term in enumerate(terms)
    ]
    session.add_all(entries)
    await session.commit()
    return entries


async def _walk(notebook_controller: NotebookController, user_id, limit: int) -> list[list[str]]:
    """Every page of a notebook, following next_cursor to the end."""
    pages: list[list[str]] = []
    cursor = None
    while True:
        page = await notebook_controller.list_entries(user_id, limit=limit, cursor=cursor)
        pages.append([entry.word for entry in page.entries])
        if page.next_cursor is None:
            return pages
        cursor = page.next_cursor


async def test_list_entries_is_newest_first_and_paginated(
    notebook_controller: NotebookController, session: AsyncSession, player: User, create_user
):
    """The cursor walks the caller's notebook newest first; total counts all of it; the
    last page has no next cursor; others' entries never appear."""
    # Prepare
    await _add_entries(session, player, ["w0", "w1", "w2", "w3", "w4"])
    other = await create_user(username="other", email="other@test.com")
    await _add_entries(session, other, ["not-mine"])

    # Act
    first = await notebook_controller.list_entries(player.id, limit=2)
    pages = await _walk(notebook_controller, player.id, limit=2)

    # Assert
    assert pages == [["w4", "w3"], ["w2", "w1"], ["w0"]]
    assert first.total == 5
    assert first.next_cursor is not None
    assert all(entry.kept_at.tzinfo is not None for entry in first.entries)


async def test_list_entries_exact_last_page_has_no_next_cursor(
    notebook_controller: NotebookController, session: AsyncSession, player: User
):
    """A page that ends exactly on the last entry says so: no empty page to fetch."""
    # Prepare
    await _add_entries(session, player, ["w0", "w1"])

    # Act
    page = await notebook_controller.list_entries(player.id, limit=2)

    # Assert
    assert [entry.word for entry in page.entries] == ["w1", "w0"]
    assert page.next_cursor is None


async def test_list_entries_a_delete_between_pages_skips_nothing(
    notebook_controller: NotebookController, session: AsyncSession, player: User
):
    """Un-keeping a word already shown (an optimistic delete) must not shift the next
    page: with an offset, w2 would have been skipped."""
    # Prepare
    await _add_entries(session, player, ["w0", "w1", "w2", "w3", "w4"])
    first = await notebook_controller.list_entries(player.id, limit=2)

    # Act
    await notebook_controller.delete_entry(player.id, first.entries[0].id)
    second = await notebook_controller.list_entries(player.id, limit=2, cursor=first.next_cursor)

    # Assert
    assert [entry.word for entry in second.entries] == ["w2", "w1"]
    assert second.total == 4
    assert sorted(row.term for row in await _entries(session, player.id)) == ["w0", "w1", "w2", "w3"]


@pytest.mark.parametrize("cursor", ["garbage", "Zm9vfGJhcg", encode_cursor_naive_example()])
async def test_list_entries_rejects_a_cursor_it_did_not_hand_out(
    notebook_controller: NotebookController, player: User, cursor: str
):
    """Anything but a cursor from a previous page is a 400, not a 500."""
    # Act / Assert
    with pytest.raises(InvalidNotebookCursorError) as error:
        await notebook_controller.list_entries(player.id, cursor=cursor)
    assert error.value.status_code == 400


@pytest.mark.usefixtures("codenames_content")
async def test_list_entries_breaks_kept_at_ties_stably(
    notebook_controller: NotebookController, player: User, make_game
):
    """A whole board shares one kept_at; pages still partition it with no overlap and no gap."""
    # Prepare
    game = await make_game(GameType.CODENAMES, _codenames_state())
    await notebook_controller.keep_game_words(game.id, player.id)

    # Act
    pages = await _walk(notebook_controller, player.id, limit=10)

    # Assert
    assert [len(page) for page in pages] == [10, 10, 5]
    words = [word for page in pages for word in page]
    assert sorted(words) == sorted(BOARD_WORDS)


@pytest.mark.parametrize(
    ("lang", "sabr_hint", "ibrahim_hint", "musa_hint"),
    [
        ("en", SABR_HINT["en"], "Father of the prophets", "Hint 6"),
        ("fr", SABR_HINT["fr"], "Père des prophètes", "Indice 6"),
        ("ar", SABR_HINT["ar"], "أبو الأنبياء", "تلميح 6"),
        ("de", SABR_HINT["en"], "Father of the prophets", "Hint 6"),  # unknown → English
    ],
)
@pytest.mark.usefixtures("undercover_content")
async def test_list_entries_resolves_meaning_in_the_requested_language(
    notebook_controller: NotebookController,
    player: User,
    make_game,
    quiz_words,
    lang,
    sabr_hint,
    ibrahim_hint,
    musa_hint,
):
    """Hints follow the shared fallback chain: exact language, then English, then any."""
    # Prepare
    await notebook_controller.keep_game_words((await make_game(GameType.UNDERCOVER, _undercover_state())).id, player.id)
    await notebook_controller.keep_game_words(
        (await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words))).id, player.id
    )

    # Act
    page = await notebook_controller.list_entries(player.id, lang=lang)

    # Assert
    hints = {entry.word: entry.hint for entry in page.entries}
    assert hints == {
        "Sabr": sabr_hint,
        "Shukr": "Gratitude to God",  # no multilingual hint: the description
        "Ibrahim": ibrahim_hint,
        "Musa": musa_hint,
    }


async def test_list_entries_shows_a_quiz_word_in_the_arabic_its_game_revealed(
    notebook_controller: NotebookController, player: User, make_game, quiz_words, create_term_scripts
):
    """A Word Quiz word's own `word_ar` is what its game revealed as the answer, so it
    wins over term_script (keyed by Latin spellings an Undercover or Codenames term may
    share). term_script's vocalisation is used only when it vocalises that same Arabic."""
    # Prepare — "Ibrahim" vocalises the quiz word's own Arabic; "Musa" names another word
    await create_term_scripts({"Ibrahim": ("إبراهيم", "إِبْرَاهِيم"), "Musa": ("موسي", "مُوسِي")})
    await notebook_controller.keep_game_words(
        (await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words))).id, player.id
    )

    # Act
    page = await notebook_controller.list_entries(player.id)

    # Assert
    forms = {entry.word: (entry.word_ar, entry.word_ar_vocalized) for entry in page.entries}
    assert forms == {"Ibrahim": ("إبراهيم", "إِبْرَاهِيم"), "Musa": ("موسى", None)}


@pytest.mark.parametrize(("lang", "expected"), [("en", "Musa"), ("fr", "Moïse"), ("ar", "موسى"), ("de", "Musa")])
async def test_list_entries_shows_a_quiz_word_as_its_game_spelled_it(
    notebook_controller: NotebookController, player: User, make_game, quiz_words, lang: str, expected: str
):
    """word_display is the spelling the game showed in that language; `word` stays the key."""
    # Prepare
    await notebook_controller.keep_game_words(
        (await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words))).id, player.id
    )

    # Act
    page = await notebook_controller.list_entries(player.id, lang=lang)

    # Assert
    musa = next(entry for entry in page.entries if entry.word == "Musa")
    assert musa.word_display == expected


@pytest.mark.usefixtures("undercover_content")
async def test_undercover_words_display_as_their_latin_key(
    notebook_controller: NotebookController, player: User, make_game
):
    """Undercover and Codenames show the Latin key in every language (the Arabic is its own field)."""
    # Prepare
    await notebook_controller.keep_game_words((await make_game(GameType.UNDERCOVER, _undercover_state())).id, player.id)

    # Act
    page = await notebook_controller.list_entries(player.id, lang="ar")

    # Assert
    assert {(entry.word, entry.word_display) for entry in page.entries} == {("Sabr", "Sabr"), ("Shukr", "Shukr")}


@pytest.mark.usefixtures("codenames_content")
async def test_list_entries_picks_the_oldest_codenames_row_with_a_hint(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game
):
    """A word in two packs resolves to one deterministic hint, skipping rows that have none."""
    # Prepare — a newer pack holding Uhud again, with a different hint
    newer_pack = CodenamesWordPack(name="Newer Pack")
    session.add(newer_pack)
    await session.commit()
    session.add(CodenamesWord(word="Uhud", word_pack_id=newer_pack.id, hint={"en": "A later hint"}))
    await session.commit()
    game = await make_game(GameType.CODENAMES, _codenames_state())
    await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="Uhud"))

    # Act
    page = await notebook_controller.list_entries(player.id)

    # Assert
    assert [(entry.word, entry.hint) for entry in page.entries] == [("Uhud", "Meaning 0")]


@pytest.mark.usefixtures("undercover_content", "codenames_content")
async def test_list_entries_resolves_with_batched_queries(
    notebook_controller: NotebookController,
    player: User,
    make_game,
    quiz_words,
    count_statements,
):
    """29 entries over three games cost one statement per table — never one per entry."""
    # Prepare
    for game_type, state in (
        (GameType.UNDERCOVER, _undercover_state()),
        (GameType.CODENAMES, _codenames_state()),
        (GameType.WORD_QUIZ, _quiz_state(quiz_words)),
    ):
        await notebook_controller.keep_game_words((await make_game(game_type, state)).id, player.id)
    counters = {
        needle: count_statements(needle)
        for needle in ("notebook_entry", "term_script", "FROM word", "codenames_word", "quiz_word")
    }

    # Act
    page = await notebook_controller.list_entries(player.id, limit=50)

    # Assert
    assert page.total == 29
    assert len(page.entries) == 29
    assert counters["notebook_entry"].count == 2  # the count and the page
    assert counters["term_script"].count == 1
    assert counters["FROM word"].count == 1
    assert counters["codenames_word"].count == 1
    assert counters["quiz_word"].count == 1


async def test_list_entries_only_queries_the_content_tables_it_needs(
    notebook_controller: NotebookController, session: AsyncSession, player: User, count_statements
):
    """An Undercover-only page never touches the Codenames or Word Quiz tables; an empty one touches none."""
    # Prepare
    await _add_entries(session, player, ["Sabr"])
    counters = {needle: count_statements(needle) for needle in ("term_script", "codenames_word", "quiz_word")}

    # Act
    page = await notebook_controller.list_entries(player.id)
    empty = await notebook_controller.list_entries(uuid4())

    # Assert
    assert [entry.word for entry in page.entries] == ["Sabr"]
    assert (empty.total, empty.entries) == (0, [])
    assert counters["term_script"].count == 1
    assert counters["codenames_word"].count == 0
    assert counters["quiz_word"].count == 0


# ─── get_game_words ───────────────────────────────────────────


@pytest.mark.usefixtures("codenames_content")
async def test_game_words_lists_every_board_word_with_what_is_kept(
    notebook_controller: NotebookController, player: User, make_game
):
    """The colophon list, in the order the game dealt it: kept words carry their entry id."""
    # Prepare
    game = await make_game(GameType.CODENAMES, _codenames_state())
    kept = await notebook_controller.keep_word(player.id, KeepWordRequest(game_id=game.id, word="Uhud"))

    # Act
    result = await notebook_controller.get_game_words(game.id, player.id, lang="fr")

    # Assert
    assert (result.game_id, result.game_type) == (game.id, NotebookGameType.CODENAMES)
    assert [word.word for word in result.words] == BOARD_WORDS
    uhud, thawr = result.words[0], result.words[1]
    assert (uhud.kept, uhud.entry_id) == (True, kept.entries[0].id)
    assert (uhud.word_ar, uhud.word_ar_vocalized, uhud.hint) == ("أحد", "أُحُد", "Sens 0")
    assert (thawr.kept, thawr.entry_id, thawr.word_ar, thawr.word_ar_vocalized) == (False, None, "ثور", None)
    assert sum(word.kept for word in result.words) == 1


async def test_game_words_lists_a_word_quiz_games_rounds_in_the_players_language(
    notebook_controller: NotebookController, player: User, make_game, quiz_words
):
    """Word Quiz's state only ever holds the current answer; this is the whole game's list."""
    # Prepare
    game = await make_game(GameType.WORD_QUIZ, _quiz_state(quiz_words))

    # Act
    result = await notebook_controller.get_game_words(game.id, player.id, lang="fr")

    # Assert
    assert [(word.word, word.word_display, word.word_ar) for word in result.words] == [
        ("Ibrahim", "Abraham", "إبراهيم"),
        ("Musa", "Moïse", "موسى"),
    ]
    assert not any(word.kept for word in result.words)


@pytest.mark.usefixtures("undercover_content")
async def test_game_words_sees_a_word_kept_from_another_game(
    notebook_controller: NotebookController, player: User, make_game
):
    """`kept` is about the notebook, not the game: Sabr kept from an earlier game is kept here too."""
    # Prepare
    earlier = await make_game(GameType.UNDERCOVER, _undercover_state("Sabr", "Hajj"))
    await notebook_controller.keep_game_words(earlier.id, player.id)
    game = await make_game(GameType.UNDERCOVER, _undercover_state("Sabr", "Shukr"))

    # Act
    result = await notebook_controller.get_game_words(game.id, player.id)

    # Assert
    assert [(word.word, word.kept) for word in result.words] == [("Sabr", True), ("Shukr", False)]


@pytest.mark.usefixtures("undercover_content")
async def test_game_words_reads_nothing_it_does_not_need(
    notebook_controller: NotebookController, player: User, make_game, count_statements
):
    """One term_script lookup, one content-table read, one notebook read — however many words."""
    # Prepare
    game = await make_game(GameType.UNDERCOVER, _undercover_state())
    counters = {needle: count_statements(needle) for needle in ("notebook_entry", "term_script", "FROM word")}

    # Act
    await notebook_controller.get_game_words(game.id, player.id)

    # Assert
    assert {needle: counter.count for needle, counter in counters.items()} == {
        "notebook_entry": 1,
        "term_script": 1,
        "FROM word": 1,
    }


@pytest.mark.usefixtures("undercover_content")
async def test_game_words_applies_the_keep_gates(
    notebook_controller: NotebookController, session: AsyncSession, player: User, make_game, create_user
):
    """In progress → 403, stranger → 403, MCQ → 400: the list is the words, the words are the secret."""
    # Prepare
    running = await make_game(GameType.UNDERCOVER, _undercover_state(), status=GameStatus.IN_PROGRESS)
    finished = await make_game(GameType.UNDERCOVER, _undercover_state())
    mcq = await make_game(GameType.MCQ_QUIZ, {"players": []})
    outsider = await create_user(username="outsider", email="outsider@test.com")

    # Act / Assert
    with pytest.raises(GameStillInProgressError):
        await notebook_controller.get_game_words(running.id, player.id)
    with pytest.raises(NotAGameParticipantError):
        await notebook_controller.get_game_words(finished.id, outsider.id)
    with pytest.raises(NotebookGameTypeNotSupportedError):
        await notebook_controller.get_game_words(mcq.id, player.id)
    assert await _entries(session, player.id) == []


@pytest.mark.usefixtures("undercover_content")
async def test_a_stranger_cannot_tell_a_running_game_from_a_finished_one(
    notebook_controller: NotebookController, make_game, create_user
):
    """Participation is checked before status: a stranger gets the same 403 either way,
    so the error key no longer says whether a game they never played is still running."""
    # Prepare
    running = await make_game(GameType.UNDERCOVER, _undercover_state(), status=GameStatus.IN_PROGRESS)
    finished = await make_game(GameType.UNDERCOVER, _undercover_state())
    outsider = await create_user(username="outsider", email="outsider@test.com")

    # Act / Assert
    for game in (running, finished):
        with pytest.raises(NotAGameParticipantError) as error:
            await notebook_controller.get_game_words(game.id, outsider.id)
        assert error.value.error_key == "errors.api.notAGameParticipant"


# ─── delete_entry ─────────────────────────────────────────────


async def test_delete_entry_removes_the_owners_entry(
    notebook_controller: NotebookController, session: AsyncSession, player: User
):
    """The owner deletes their own entry; the others stay."""
    # Prepare
    sabr, shukr = await _add_entries(session, player, ["Sabr", "Shukr"])

    # Act
    await notebook_controller.delete_entry(player.id, sabr.id)

    # Assert
    assert [row.id for row in await _entries(session, player.id)] == [shukr.id]


async def test_delete_someone_elses_entry_is_not_found(
    notebook_controller: NotebookController, session: AsyncSession, player: User, create_user
):
    """Another user's entry answers 404 — the same as a missing id — and survives."""
    # Prepare
    [entry] = await _add_entries(session, player, ["Sabr"])
    intruder = await create_user(username="intruder", email="intruder@test.com")

    # Act / Assert
    with pytest.raises(NotebookEntryNotFoundError) as error:
        await notebook_controller.delete_entry(intruder.id, entry.id)
    assert error.value.status_code == 404
    with pytest.raises(NotebookEntryNotFoundError):
        await notebook_controller.delete_entry(player.id, uuid4())
    assert [row.id for row in await _entries(session, player.id)] == [entry.id]
