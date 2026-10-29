"""Tests for the shared answer normalisation (Word Quiz answers, Mr. White guesses)."""

import pytest

from majlisna.api.utils.text_match import fold_arabic_letters, matches_any, matches_quiz_answer, strip_arabic_article


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("أيوب", "ايوب"),
        ("إبراهيم", "ابراهيم"),
        ("آدم", "ادم"),
        ("مؤذن", "موذن"),
        ("عائشة", "عايشه"),
        ("موسى", "موسي"),
        ("صلاة", "صلاه"),
        ("صـبـر", "صبر"),
    ],
)
def test_fold_arabic_letters(text: str, folded: str):
    """Hamza carriers, alef maqsura, taa marbuta and tatweel fold to the plain letter."""
    # Act / Assert
    assert fold_arabic_letters(text) == folded


@pytest.mark.parametrize(
    ("text", "stripped"),
    [("الصبر", "صبر"), ("الحج", "حج"), ("صبر", "صبر"), ("الم", "الم"), ("ال", "ال")],
)
def test_strip_arabic_article(text: str, stripped: str):
    """The article goes, but never down to a single letter."""
    # Act / Assert
    assert strip_arabic_article(text) == stripped


@pytest.mark.parametrize(
    ("answer", "accepted", "expected"),
    [
        # Latin: case, surrounding space, hyphens and the "al" article are ignored
        ("hajj", ["Hajj"], True),
        ("  HAJJ ", ["Hajj"], True),
        ("eid al fitr", ["Eid al-Fitr"], True),
        ("Aqsa", ["Al-Aqsa"], True),
        # Arabic: harakat, letter variants and the article are ignored
        ("صبر", ["Sabr", "صبر"], True),
        ("صَبْر", ["Sabr", "صبر"], True),
        ("الصبر", ["Sabr", "صبر"], True),
        ("ابراهيم", ["Ibrahim", "إبراهيم"], True),
        ("موسي", ["Musa", "موسى"], True),
        ("صلاه", ["Salah", "صلاة"], True),
        # Spelling variants: "ابن" typed in full, "داوود" with a doubled waw
        ("خالد ابن الوليد", ["Khalid ibn al-Walid", "خالد بن الوليد"], True),
        ("داوود", ["Dawud", "داود"], True),
        ("ابن بطوطة", ["Ibn Battuta", "ابن بطوطة"], True),
        # Wrong answers stay wrong
        ("شكر", ["Sabr", "صبر"], False),
        ("صب", ["Sabr", "صبر"], False),
        ("Sabrr", ["Sabr", "صبر"], False),
        ("", ["Sabr", "صبر"], False),
        ("   ", ["Sabr"], False),
        # A missing Arabic form is skipped, not matched
        ("صبر", ["Sabr", None], False),
    ],
)
def test_matches_any(answer: str, accepted: list[str | None], expected: bool):
    """One matcher for both scripts."""
    # Act / Assert
    assert matches_any(answer, accepted) is expected


# ─── matches_quiz_answer: the Kalimat rule, shared with the word of the day ───

HUDAYBIYYAH_SPELLINGS = ("Hudaybiyyah", "الحديبية", "Houdaybiya")
HUDAYBIYYAH_ACCEPTED = {"en": ["Hudaybiya", "Treaty of Hudaybiyyah"], "ar": ["صلح الحديبية"], "fr": ["Hudaybiya"]}


@pytest.mark.parametrize(
    "answer",
    [
        "hudaybiyyah",  # case
        "  Hudaybiyyah  ",  # surrounding space
        "Houdaybiya",  # the French spelling, whatever the UI language
        "الحديبية",  # the Arabic spelling
        "الْحُدَيْبِيَة",  # harakat are ignored
        "treaty of hudaybiyyah",  # an accepted variant
        "صلح الحديبية",  # an accepted variant in Arabic
    ],
)
def test_matches_quiz_answer_accepts_every_spelling_and_variant(answer: str):
    """The word's own three spellings and every accepted variant, in any language."""
    # Act
    found = matches_quiz_answer(answer, spellings=HUDAYBIYYAH_SPELLINGS, accepted_answers=HUDAYBIYYAH_ACCEPTED)

    # Assert
    assert found is True


@pytest.mark.parametrize("answer", ["Badr", "Hudaybi", "", "   ", "-"])
def test_matches_quiz_answer_refuses_another_word_and_nothing(answer: str):
    """Another word, a prefix, or nothing once normalised is not the word."""
    # Act
    found = matches_quiz_answer(answer, spellings=HUDAYBIYYAH_SPELLINGS, accepted_answers=HUDAYBIYYAH_ACCEPTED)

    # Assert
    assert found is False


def test_matches_quiz_answer_tolerates_missing_and_malformed_content():
    """A word with no French spelling, no accepted answers or a stray non-list still answers."""
    # Act
    by_spelling = matches_quiz_answer("Sabr", spellings=("Sabr", None, None), accepted_answers=None)
    by_variant = matches_quiz_answer("Patience", spellings=("Sabr",), accepted_answers={"en": ["Patience"], "ar": "x"})

    # Assert
    assert by_spelling is True
    assert by_variant is True
