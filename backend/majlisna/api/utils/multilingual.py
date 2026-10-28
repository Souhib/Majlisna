"""Resolving the multilingual ``{en, ar, fr}`` JSON values stored on game content.

Hints, explanations and word descriptions are stored as one dict per value. This is
the single fallback chain every reader uses — the game controllers through
``BaseGameController._resolve_multilingual`` and the notebook directly — so a value
reads the same wherever it is shown.
"""

from majlisna.api.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def resolve_multilingual(data: dict | None, lang: str) -> str | None:
    """Resolve a multilingual dict to one string: the exact ``lang``, then ``en``, then any value."""
    if not data or not isinstance(data, dict):
        return None
    return data.get(lang) or data.get("en") or next(iter(data.values()), None)


def normalize_lang(value: object) -> str:
    """A client-supplied language code as one of ``SUPPORTED_LANGUAGES``, else the default.

    Used where the value does not come through a typed FastAPI parameter — the
    Socket.IO handshake and ``join_game`` payload are free-form dicts.
    """
    if isinstance(value, str) and value in SUPPORTED_LANGUAGES:
        return value
    return DEFAULT_LANGUAGE
