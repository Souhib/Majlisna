"""Tests for the shared answer normalisation (Word Quiz answers, Mr. White guesses)."""

import pytest

from majlisna.api.utils.text_match import fold_arabic_letters, matches_any, strip_arabic_article


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
