"""Tests for the admin gate on the game-content endpoints.

`get_current_admin_user` is the only thing standing between any logged-in player and
the ability to read every undercover term pair (which reveals the opposing word) or
delete all game content. These tests pin the three properties that matter: it fails
closed, it matches addresses case-insensitively, and it refuses an unverified account.
"""

from uuid import uuid4

import pytest

from majlisna.api.models.table import User
from majlisna.api.schemas.error import ForbiddenError
from majlisna.dependencies import get_current_admin_user
from majlisna.settings import Settings


def _settings(admin_emails: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        database_url="sqlite+aiosqlite:///:memory:",
        admin_emails=admin_emails,
    )


def _user(email: str, *, verified: bool = True) -> User:
    return User(id=uuid4(), username="someone", email_address=email, password="x", email_verified=verified)


# ─── Fails closed ─────────────────────────────────────────────


async def test_no_admin_configured_denies_everyone():
    """An unset ADMIN_EMAILS means nobody is an admin.

    Content is loaded by scripts/generate_fake_data.py, so a deployment that never
    sets this loses nothing — and the alternative default (anyone) is what the audit
    was fixing.
    """
    with pytest.raises(ForbiddenError):
        await get_current_admin_user(_user("someone@example.com"), _settings(""))


async def test_non_admin_is_denied():
    """A logged-in account that is not listed gets 403."""
    with pytest.raises(ForbiddenError) as exc_info:
        await get_current_admin_user(_user("player@example.com"), _settings("admin@example.com"))
    assert exc_info.value.status_code == 403


# ─── Case-insensitive addresses ───────────────────────────────


@pytest.mark.parametrize(
    ("configured", "registered"),
    [
        ("admin@example.com", "admin@example.com"),
        ("Admin@Example.com", "admin@example.com"),
        ("admin@example.com", "ADMIN@EXAMPLE.COM"),
        ("  admin@example.com  ", "Admin@example.com"),
    ],
)
async def test_address_match_ignores_case_and_padding(configured: str, registered: str):
    """A configured address matches the account however either side is cased.

    Email domains are case-insensitive by definition and every provider treats the
    local part that way in practice. Comparing raw strings meant a configured
    `Admin@Example.com` silently denied the account registered as
    `admin@example.com` — a failure indistinguishable from a broken deploy.
    """
    admin = await get_current_admin_user(_user(registered), _settings(configured))
    assert admin.email_address == registered


async def test_one_admin_among_several_configured():
    """Membership is per-address, not all-or-nothing."""
    settings = _settings("first@example.com,second@example.com")
    assert await get_current_admin_user(_user("second@example.com"), settings)
    with pytest.raises(ForbiddenError):
        await get_current_admin_user(_user("third@example.com"), settings)


# ─── A verified account is required ───────────────────────────


async def test_unverified_admin_is_denied():
    """Naming an address in config makes that address a credential.

    Registration is open and `require_email_verification` is off by default, so if
    the configured admin had not yet registered, anyone who guessed the address (a
    project owner's email is rarely secret) could register it and inherit
    content-management rights. Requiring a verified email means squatting the
    address buys nothing without access to the mailbox.
    """
    with pytest.raises(ForbiddenError) as exc_info:
        await get_current_admin_user(
            _user("admin@example.com", verified=False),
            _settings("admin@example.com"),
        )
    assert exc_info.value.status_code == 403
    assert "verified" in exc_info.value.message


async def test_verified_listed_admin_is_allowed():
    """The one combination that passes."""
    admin = await get_current_admin_user(
        _user("admin@example.com", verified=True),
        _settings("admin@example.com"),
    )
    assert admin.email_address == "admin@example.com"


# ─── Settings parsing (the shapes a deploy actually uses) ─────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("a@b.com", ["a@b.com"]),
        ("a@b.com,c@d.com", ["a@b.com", "c@d.com"]),
        ("a@b.com , c@d.com ", ["a@b.com", "c@d.com"]),
        ('["a@b.com", "c@d.com"]', ["a@b.com", "c@d.com"]),
        (["a@b.com"], ["a@b.com"]),
    ],
)
async def test_admin_emails_parses_every_supported_shape(raw: object, expected: list[str]):
    """Comma-separated, JSON array, or an actual list — all land as list[str].

    The field is `Annotated[list[str], NoDecode]`: without NoDecode,
    pydantic-settings would try `json.loads` on the raw env value before validators
    run and a plain `a,b` string would raise SettingsError.
    """
    assert _settings(raw).admin_emails == expected
