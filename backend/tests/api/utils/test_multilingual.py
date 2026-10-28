"""Tests for the shared multilingual fallback chain."""

import pytest

from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.utils.multilingual import normalize_lang, resolve_multilingual

HINT = {"en": "Patience", "fr": "Patience (fr)", "ar": "صبر"}


@pytest.mark.parametrize(
    ("data", "lang", "expected"),
    [
        (HINT, "fr", "Patience (fr)"),
        (HINT, "ar", "صبر"),
        (HINT, "de", "Patience"),  # unknown language → English
        ({"en": "Patience", "fr": ""}, "fr", "Patience"),  # empty translation → English
        ({"ar": "صبر"}, "fr", "صبر"),  # no English → any value
        (None, "en", None),
        ({}, "en", None),
    ],
)
def test_resolve_multilingual_fallback_chain(data: dict | None, lang: str, expected: str | None) -> None:
    """Exact language, then English, then the first value; nothing when there is no data."""
    # Act
    resolved = resolve_multilingual(data, lang)

    # Assert
    assert resolved == expected


def test_game_controllers_use_the_same_chain() -> None:
    """The game controllers' resolver is this one, so a hint reads the same in a game and in the notebook."""
    # Act / Assert
    for lang in ("en", "fr", "ar", "de"):
        assert BaseGameController._resolve_multilingual(HINT, lang) == resolve_multilingual(HINT, lang)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("ar", "ar"), ("fr", "fr"), ("en", "en"), ("de", "en"), ("", "en"), (None, "en"), (42, "en"), ("AR", "en")],
)
def test_normalize_lang_accepts_only_the_supported_languages(value: object, expected: str) -> None:
    """A free-form Socket.IO value becomes a supported language, never an arbitrary string."""
    # Act
    lang = normalize_lang(value)

    # Assert
    assert lang == expected
