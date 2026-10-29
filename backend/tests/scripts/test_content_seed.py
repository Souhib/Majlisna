"""--seed is how game content reaches a server: a corrected word must replace the old one, not sit beside it."""

from sqlmodel import select

from majlisna.api.models.codenames import CodenamesWord
from majlisna.api.models.undercover import Word
from majlisna.api.models.wordquiz import QuizWord
from scripts.seed_data.codenames_data import CODENAMES_WORD_PACKS, seed_codenames_words
from scripts.seed_data.undercover_data import UNDERCOVER_WORDS, seed_undercover_words
from scripts.seed_data.wordquiz_data import QUIZ_WORDS, seed_quiz_words


async def test_quiz_seed_brings_an_existing_word_back_to_the_seed_data(session):
    # Prepare: a server seeded before a correction holds the old Arabic and hints
    await seed_quiz_words(session)
    data = QUIZ_WORDS[0]
    stale = (await session.exec(select(QuizWord).where(QuizWord.word_en == data["word_en"]))).one()
    stale.word_ar = "خطأ"
    stale.hints = {"1": {"en": "old", "ar": "قديم", "fr": "ancien"}}
    stale.explanation = None
    session.add(stale)
    await session.commit()

    # Act: run twice, the second run must change nothing
    await seed_quiz_words(session)
    await seed_quiz_words(session)

    # Assert
    rows = (await session.exec(select(QuizWord))).all()
    assert len(rows) == len(QUIZ_WORDS)
    fixed = next(row for row in rows if row.word_en == data["word_en"])
    assert fixed.word_ar == data.get("word_ar")
    assert fixed.hints == data["hints"]
    assert fixed.explanation == data.get("explanation")


async def test_undercover_seed_brings_an_existing_word_back_to_the_seed_data(session):
    # Prepare
    await seed_undercover_words(session)
    data = UNDERCOVER_WORDS[0]
    stale = (await session.exec(select(Word).where(Word.word == data["word"]))).one()
    stale.hint = {"en": "old", "ar": "قديم"}
    stale.long_description = "old"
    session.add(stale)
    await session.commit()

    # Act
    await seed_undercover_words(session)
    await seed_undercover_words(session)

    # Assert
    rows = (await session.exec(select(Word))).all()
    assert len(rows) == len({w["word"] for w in UNDERCOVER_WORDS})
    fixed = next(row for row in rows if row.word == data["word"])
    assert fixed.long_description == data["long_description"]
    assert fixed.hint == data.get("hint", {"en": data["long_description"]})


async def test_codenames_seed_brings_an_existing_hint_back_to_the_seed_data(session):
    # Prepare
    await seed_codenames_words(session)
    pack_words = next(iter(CODENAMES_WORD_PACKS.values()))
    data = pack_words[0]
    stale = (await session.exec(select(CodenamesWord).where(CodenamesWord.word == data["word"]))).first()
    assert stale is not None
    stale.hint = {"en": "old", "ar": "قديم"}
    session.add(stale)
    await session.commit()

    # Act
    await seed_codenames_words(session)
    await seed_codenames_words(session)

    # Assert
    rows = (await session.exec(select(CodenamesWord).where(CodenamesWord.word == data["word"]))).all()
    assert all(row.hint is not None and row.hint.get("en") != "old" for row in rows)
    assert any(row.hint == data.get("hint") for row in rows)
