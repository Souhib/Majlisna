"""Answer normalisation shared by every game that compares typed text.

The Word Quiz answer check and the Undercover Mr. White guess both decide whether
what a player typed "is" a term. They used to carry two different normalisers —
the Mr. White one stripped every combining mark, the Word Quiz one only diacritics
— so the same input could be right in one game and wrong in the other.
"""

import re
import unicodedata
from collections.abc import Iterable

# Arabic harakat, tanween, shadda, sukun, dagger alef and Quranic annotation marks.
ARABIC_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")

# Letters that the same word is routinely typed with either way. Hamza carriers
# and the bare alef are the commonest (most keyboards make "ا" the easy key),
# then taa marbuta / haa and alef maqsura / yaa at the end of a word. Tatweel is
# purely decorative.
_ARABIC_LETTER_FOLDS = str.maketrans(
    {
        "أ": "ا",  # أ → ا
        "إ": "ا",  # إ → ا
        "آ": "ا",  # آ → ا
        "ٱ": "ا",  # ٱ → ا
        "ؤ": "و",  # ؤ → و
        "ئ": "ي",  # ئ → ي
        "ى": "ي",  # ى → ي
        "ة": "ه",  # ة → ه
        "ـ": None,  # tatweel
    }
)

_ARABIC_IBN = "ابن"  # ابن
_ARABIC_IBN_SHORT = "بن"  # بن
_ARABIC_DOUBLE_WAW = "وو"  # وو
_ARABIC_WAW = "و"  # و

_LATIN_ARTICLE = "al "
_ARABIC_ARTICLE = "ال"  # ال
# Only strip "ال" when at least two letters remain, so a two-letter word that
# merely starts with those letters is never reduced to a single character.
_ARABIC_ARTICLE_MIN_LENGTH = len(_ARABIC_ARTICLE) + 2


def normalize_answer(answer: str) -> str:
    """Normalise an answer: strip diacritics, lowercase, collapse whitespace, hyphens → spaces."""
    text = answer.strip()
    text = ARABIC_DIACRITICS.sub("", text)
    # NFD decomposition splits accented Latin chars: ï → i + combining diaeresis, é → e + combining acute
    text = unicodedata.normalize("NFD", text)
    # Strip only Latin combining diacritical marks (U+0300–U+036F), preserving Arabic combining chars
    text = re.sub(r"[̀-ͯ]", "", text)
    # NFC recompose remaining characters (Arabic: alef + hamza → alef-with-hamza)
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    # Remove hyphens so "Al-Aqsa" matches "Al Aqsa" and vice versa
    text = text.replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def strip_article(text: str) -> str:
    """Strip the transliterated article prefix 'al ' for fuzzy matching."""
    if text.startswith(_LATIN_ARTICLE):
        return text[len(_LATIN_ARTICLE) :]
    return text


def answers_match(a: str, b: str) -> bool:
    """Compare two normalised answers, also trying without the 'al ' prefix."""
    if a == b:
        return True
    return strip_article(a) == strip_article(b)


def matches_quiz_answer(answer: str, *, spellings: Iterable[str | None], accepted_answers: object) -> bool:
    """Whether ``answer`` finds a Word Quiz word — THE Kalimat rule, also the word of the day's.

    ``spellings`` are the word's own ``word_en`` / ``word_ar`` / ``word_fr``;
    ``accepted_answers`` its ``{lang: [variant, …]}`` JSON, every language accepted
    whatever the player's UI. Diacritics, Latin accents, case, hyphens and the "al "
    article are ignored (``normalize_answer`` + ``answers_match``).
    """
    normalized = normalize_answer(answer)
    if not normalized:
        return False
    variants: list[object] = list(spellings)
    if isinstance(accepted_answers, dict):
        for lang_answers in accepted_answers.values():
            if isinstance(lang_answers, list):
                variants.extend(lang_answers)
    return any(
        isinstance(variant, str) and variant and answers_match(normalize_answer(variant), normalized)
        for variant in variants
    )


def fold_arabic_letters(text: str) -> str:
    """Fold Arabic letter variants that are commonly typed interchangeably."""
    return text.translate(_ARABIC_LETTER_FOLDS)


def strip_arabic_article(text: str) -> str:
    """Strip a leading definite article "ال" ("الصبر" → "صبر")."""
    if len(text) >= _ARABIC_ARTICLE_MIN_LENGTH and text.startswith(_ARABIC_ARTICLE):
        return text[len(_ARABIC_ARTICLE) :]
    return text


def fold_arabic_spellings(text: str) -> str:
    """Fold whole-word spelling variants: "ابن" → "بن" and "وو" → "و".

    Between two names "ابن" drops its alef ("خالد بن الوليد"), yet most people
    type it in full; and the Qur'anic "داود" is very often typed "داوود". Both
    sides of a comparison are folded, so this only ever widens a match.
    """
    words = [_ARABIC_IBN_SHORT if word == _ARABIC_IBN else word for word in text.split(" ")]
    return " ".join(words).replace(_ARABIC_DOUBLE_WAW, _ARABIC_WAW)


def _canonical(text: str) -> str:
    return fold_arabic_spellings(fold_arabic_letters(normalize_answer(text)))


def matches_any(answer: str, accepted_forms: Iterable[str | None]) -> bool:
    """Whether ``answer`` names the same term as any of ``accepted_forms``.

    Latin and Arabic in one pass: diacritics and Latin accents are ignored, Arabic
    letter variants are folded (أ/إ/آ → ا, ة → ه, ى → ي, …), and the article is
    optional in either script ("al-Aqsa" = "Aqsa", "الصبر" = "صبر").
    """
    candidate = _canonical(answer)
    if not candidate:
        return False
    for form in accepted_forms:
        if not form:
            continue
        accepted = _canonical(form)
        if not accepted:
            continue
        if answers_match(candidate, accepted) or strip_arabic_article(candidate) == strip_arabic_article(accepted):
            return True
    return False
