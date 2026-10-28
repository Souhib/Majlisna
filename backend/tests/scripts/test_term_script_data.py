"""The Arabic forms seeded for every Undercover and Codenames term."""

import re

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.term_script import TermScript
from majlisna.api.utils.text_match import ARABIC_DIACRITICS
from scripts.seed_data.codenames_data import CODENAMES_WORD_PACKS
from scripts.seed_data.term_script_data import TERM_SCRIPTS, seed_term_scripts
from scripts.seed_data.undercover_data import UNDERCOVER_WORDS

LATIN_LETTER = re.compile("[A-Za-z]")
# Anything outside the Arabic block (plus the space between words) has no place in a
# card subtitle: Latin, digits, punctuation, honorific ligatures from the
# presentation-forms blocks (ﷺ is U+FDFA).
NOT_ARABIC_OR_SPACE = re.compile("[^؀-ۿ ]")
HONORIFICS = ("ﷺ", "صلى الله", "عليه السلام", "رضي الله", "رحمه الله")
# A word ending on one of these carries its vowel in the letter ("أَبُو", "ذُو", "مَا").
LONG_VOWEL_LETTERS = ("ا", "و", "ي", "ى")


def _seeded_terms() -> set[str]:
    undercover = {word["word"] for word in UNDERCOVER_WORDS}
    codenames = {word["word"] for words in CODENAMES_WORD_PACKS.values() for word in words}
    return undercover | codenames


def test_every_seeded_word_has_an_arabic_form():
    """No gaps: a word dealt in either game without a TermScript row shows no Arabic at all."""
    # Prepare
    terms = _seeded_terms()

    # Act
    missing = sorted(terms - set(TERM_SCRIPTS))

    # Assert
    assert missing == []


def test_no_arabic_form_for_a_term_that_is_not_seeded():
    """An orphan entry is either a typo in the key (so the real word has no form) or dead data."""
    # Prepare
    terms = _seeded_terms()

    # Act
    orphans = sorted(set(TERM_SCRIPTS) - terms)

    # Assert
    assert orphans == []


@pytest.mark.parametrize(("term", "forms"), sorted(TERM_SCRIPTS.items()))
def test_arabic_form_is_plain_arabic(term: str, forms: tuple[str, str | None]):
    """`ar` is Arabic script only — no Latin, no harakat, no honorific."""
    # Prepare
    ar, _ = forms

    # Act / Assert
    assert ar.strip() == ar
    assert not LATIN_LETTER.search(ar), term
    assert not NOT_ARABIC_OR_SPACE.search(ar), term
    assert not ARABIC_DIACRITICS.search(ar), term
    assert not any(honorific in ar for honorific in HONORIFICS), term


@pytest.mark.parametrize(
    ("term", "forms"), sorted((term, forms) for term, forms in TERM_SCRIPTS.items() if forms[1] is not None)
)
def test_vocalized_form_is_the_same_word(term: str, forms: tuple[str, str | None]):
    """Stripping the harakat from `ar_vocalized` gives back `ar` letter for letter.

    Catches a vocalised form that silently spells a different word (a dropped or
    swapped letter is invisible under the marks).
    """
    # Prepare
    ar, vocalized = forms
    assert vocalized is not None

    # Act
    stripped = ARABIC_DIACRITICS.sub("", vocalized)

    # Assert
    assert stripped == ar, term
    assert vocalized != ar, f"{term}: a vocalised form without harakat should be None"


@pytest.mark.parametrize(
    ("term", "vocalized"),
    sorted((term, forms[1]) for term, forms in TERM_SCRIPTS.items() if forms[1] is not None and " " in forms[1]),
)
def test_vocalized_phrase_marks_every_word_but_the_last(term: str, vocalized: str):
    """Only the last word of a vocalised name is in pause.

    A non-final word is never in pause: "لَيْلَة الْقَدْر" with a bare first word
    reads as a stop after "laylah". The construct, the "ibn" chain and the noun
    before its adjective carry their case vowel ("لَيْلَةُ الْقَدْر",
    "خَالِدُ بْنُ الْوَلِيد"); a particle keeps its sukun ("إِنْ").
    """
    # Prepare
    leading_words = vocalized.split(" ")[:-1]

    # Act
    bare = [
        word for word in leading_words if not ARABIC_DIACRITICS.match(word[-1]) and word[-1] not in LONG_VOWEL_LETTERS
    ]

    # Assert
    assert bare == [], term


async def test_seed_upserts_idempotently(session: AsyncSession):
    """--seed inserts every term once, re-running changes nothing, and a stale row is corrected."""
    # Prepare
    await seed_term_scripts(session)
    stale = (await session.exec(select(TermScript).where(TermScript.term == "Sabr"))).one()
    stale.ar = "خطأ"
    stale.ar_vocalized = None
    session.add(stale)
    await session.commit()

    # Act
    await seed_term_scripts(session)
    await seed_term_scripts(session)

    # Assert
    rows = (await session.exec(select(TermScript))).all()
    assert len(rows) == len(TERM_SCRIPTS)
    by_term = {row.term: row for row in rows}
    assert (by_term["Sabr"].ar, by_term["Sabr"].ar_vocalized) == TERM_SCRIPTS["Sabr"]
    assert all((by_term[term].ar, by_term[term].ar_vocalized) == forms for term, forms in TERM_SCRIPTS.items())
