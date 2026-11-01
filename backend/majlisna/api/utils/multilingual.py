"""Resolving the multilingual ``{en, ar, fr}`` JSON values stored on game content.

Hints, explanations and word descriptions are stored as one dict per value. This is
the single fallback chain every reader uses — the game controllers through
``BaseGameController._resolve_multilingual`` and the notebook directly — so a value
reads the same wherever it is shown.
"""

from majlisna.api.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def resolve_multilingual(data: dict | None, lang: str) -> str | None:
    """Resolve a multilingual dict to one string: ``lang``'s own text, then ``en``, then any value.

    ``lang`` goes through ``normalize_lang`` first, so a browser's regional tag reads as its
    language: ``fr-FR`` gets the French text rather than the English fallback. Every REST
    ``?lang=`` that reaches game content comes through here.
    """
    if not data or not isinstance(data, dict):
        return None
    return data.get(normalize_lang(lang)) or data.get("en") or next(iter(data.values()), None)


def normalize_lang(value: object) -> str:
    """A client-supplied language code as one of ``SUPPORTED_LANGUAGES``, else the default.

    The language part of a BCP 47 tag, case-insensitively: ``fr-FR`` → ``fr``, ``ar-SA`` →
    ``ar``, ``fr_CA`` → ``fr``; anything unknown (``de-DE``, ``arn``, a non-string) → ``en``.
    Browsers send regional tags, and an exact-match check used to turn every one of them
    into English. Used by ``resolve_multilingual`` and by the Socket.IO handshake and
    ``join_game`` payload, which are free-form dicts.
    """
    if not isinstance(value, str):
        return DEFAULT_LANGUAGE
    language = value.strip().replace("_", "-").split("-", 1)[0].lower()
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
