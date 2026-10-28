"""The Codenames seed: cards that carry a Name of Allah are retired, also from a database that has them."""

from uuid import uuid4

from sqlmodel import select

from majlisna.api.models.codenames import CodenamesWord, CodenamesWordPack
from scripts.seed_data.codenames_data import CODENAMES_WORD_PACKS, RETIRED_CODENAMES_WORDS, seed_codenames_words


def test_no_retired_card_is_dealt_by_the_seed_data():
    """No pack lists a retired card (Ar-Rahman, Bismillah, …): nothing may pass over a sacred name."""
    seeded = {w["word"] for words in CODENAMES_WORD_PACKS.values() for w in words}
    assert seeded.isdisjoint(RETIRED_CODENAMES_WORDS)


async def test_seed_removes_retired_cards_from_an_existing_database(session):
    """The seed is how content reaches a server, so it also takes the retired cards out."""
    # Arrange: a database seeded before the retirement still holds "Rahman"
    pack = CodenamesWordPack(id=uuid4(), name="Quran & Surahs", description="old", is_active=True)
    session.add(pack)
    await session.flush()
    session.add(CodenamesWord(id=uuid4(), word="Rahman", word_pack_id=pack.id, hint={"en": "old"}))
    await session.commit()

    # Act
    await seed_codenames_words(session)

    # Assert
    words = set((await session.exec(select(CodenamesWord.word))).all())
    assert words.isdisjoint(RETIRED_CODENAMES_WORDS)
    assert "Fatiha" in words
