"""Tests for the admin gate on the game-content endpoints.

`get_current_admin_user` is the only thing standing between any logged-in player and
the ability to read every undercover term pair (which reveals the opposing word) or
delete all game content. These tests pin the three properties that matter: it fails
closed, it matches addresses case-insensitively, and it refuses an unverified account.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.models.table import User
from majlisna.api.models.user import UserCreate
from majlisna.api.schemas.error import ForbiddenError, SessionRevokedError
from majlisna.api.schemas.social_auth import SocialTokenPayload
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.dependencies import get_current_admin_user, get_current_user
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


# ─── The admin gate sits behind the session check (SEC F01, F02) ─────


async def test_a_signed_out_admins_token_never_reaches_the_admin_check(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """The gate keeps failing closed: a revoked session is refused before ``admin_emails`` is read."""
    # Prepare — a verified, configured admin who then signs out
    admin = await create_user(username="admin", email="admin@example.com", password="admin12345")
    admin.email_verified = True
    session.add(admin)
    await session.commit()
    tokens = await auth_controller.login("admin@example.com", "admin12345")
    await auth_controller.logout(access_token=tokens.access_token, refresh_token=None)

    # Act / Assert
    with pytest.raises(SessionRevokedError):
        await get_current_user(Mock(cookies={}), tokens.access_token, auth_controller)


async def test_a_google_take_back_does_not_make_the_squatter_an_admin(
    auth_controller: AuthController, test_settings: Settings
):
    """Squatting the configured admin address bought nothing (unverified) — and once the owner
    signs in with Google the squatter's token is dead while the owner, now verified, passes."""
    # Prepare
    squatter = await auth_controller.register(
        UserCreate(username="squatter", email_address="Admin@Example.com", password="squat12345")
    )
    squatter_tokens = await auth_controller.login("admin@example.com", "squat12345")
    settings = _settings("admin@example.com")
    with pytest.raises(ForbiddenError):
        await get_current_admin_user(squatter, settings)
    google = SocialAuthService(test_settings)
    google.verify_google_access_token = AsyncMock(
        return_value=SocialTokenPayload(sub="g-owner", email="admin@example.com", email_verified=True)
    )

    # Act
    owner_tokens = await auth_controller.social_login(social_auth_service=google, access_token="google-token")

    # Assert
    with pytest.raises(SessionRevokedError):
        await get_current_user(Mock(cookies={}), squatter_tokens.access_token, auth_controller)
    owner = await get_current_user(Mock(cookies={}), owner_tokens.access_token, auth_controller)
    assert (await get_current_admin_user(owner, settings)).email_address == "admin@example.com"
