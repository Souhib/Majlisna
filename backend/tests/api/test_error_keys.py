"""Every error key the API can answer with has a translation in all three locales.

The client translates `error_key` (`getApiErrorMessage`) and only falls back to the
English `message` when the key is missing — so a key with no entry in
`front/src/i18n/locales/*.json` shows English in the Arabic and French UI. Before
this test, 33 of the error classes' keys (`invalidOrExpiredToken` among them) and
every bare `BaseError` (key `errors.api.base`, untranslatable because its message
varies) had none.
"""

import ast
import json
import pathlib

import pytest

import majlisna.app  # noqa: F401 — imports every controller, so every error class is defined
from majlisna.api.schemas.error import BaseError

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_ROOT = BACKEND_ROOT / "majlisna"
LOCALES_DIR = BACKEND_ROOT.parent / "front" / "src" / "i18n" / "locales"
LANGUAGES = ("en", "fr", "ar")
# Keys written literally by the app's own exception handlers (app.py, rate_limit.py).
HANDLER_KEYS = {
    "errors.api.resourceNotFound",
    "errors.api.validation",
    "errors.api.internalServer",
    "errors.api.rateLimitExceeded",
}


def _all_subclasses(cls: type) -> set[type]:
    found = set()
    for sub in cls.__subclasses__():
        found.add(sub)
        found |= _all_subclasses(sub)
    return found


def _emitted_keys() -> set[str]:
    return {sub._generate_error_key() for sub in _all_subclasses(BaseError)} | HANDLER_KEYS


def _locale_api_keys(lang: str) -> set[str]:
    data = json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    return {f"errors.api.{key}" for key in data["errors"]["api"]}


@pytest.mark.skipif(not LOCALES_DIR.is_dir(), reason="front/ is not checked out next to backend/")
@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_error_key_is_translated(lang: str) -> None:
    """Each error class's key (and each handler's) is in `errors.api` of the locale."""
    # Act
    missing = sorted(_emitted_keys() - _locale_api_keys(lang))

    # Assert
    assert missing == [], f"{lang}.json lacks {missing}"


def test_no_bare_base_error_is_raised() -> None:
    """A bare `BaseError(...)` answers `errors.api.base`, which no locale can translate: name the error."""
    # Prepare
    offenders = []

    # Act
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "BaseError":
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}")

    # Assert
    assert offenders == []
