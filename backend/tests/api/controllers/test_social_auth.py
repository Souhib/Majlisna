"""Tests for Google social authentication."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from jose import jwt
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import AUTH_PROVIDER_EMAIL, AUTH_PROVIDER_GOOGLE
from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.shared import get_password_hash, verify_password
from majlisna.api.controllers.token_auth import authenticate_access_token
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.table import User
from majlisna.api.models.user import UserCreate
from majlisna.api.schemas.error import InvalidCredentialsError, SessionRevokedError
from majlisna.api.schemas.social_auth import SocialTokenPayload
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.settings import Settings


@pytest.fixture
def social_auth_service(test_settings: Settings) -> SocialAuthService:
    """Create a SocialAuthService for testing."""
    return SocialAuthService(test_settings)


@pytest.fixture
def google_token_payload() -> SocialTokenPayload:
    """Sample Google token payload."""
    return SocialTokenPayload(
        sub="google_sub_123456",
        email="socialuser@gmail.com",
        email_verified=True,
        first_name="John",
        last_name="Doe",
        picture="https://lh3.googleusercontent.com/photo.jpg",
    )


# ========== Google Social Login ==========


@pytest.mark.asyncio
async def test_google_new_user_created(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,
    google_token_payload: SocialTokenPayload,
):
    """New user is created when Google account is not linked."""
    # Prepare
    social_auth_service.verify_google_access_token = AsyncMock(return_value=google_token_payload)

    # Act
    result = await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token="fake_google_access_token",
    )

    # Assert
    assert result.is_new_user is True
    assert result.access_token
    assert result.refresh_token
    assert result.token_type == "bearer"
    assert result.expires_in > 0
    assert result.user.username == "john_doe"
    assert result.user.email == "socialuser@gmail.com"

    # Verify user in DB
    stmt = select(User).where(User.email_address == "socialuser@gmail.com")
    db_result = await session.exec(stmt)
    user = db_result.one()

    assert user.google_sub == "google_sub_123456"
    assert user.auth_provider == AUTH_PROVIDER_GOOGLE
    assert user.email_verified is True
    assert user.profile_picture_url == "https://lh3.googleusercontent.com/photo.jpg"


@pytest.mark.asyncio
async def test_google_returning_user(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,
    google_token_payload: SocialTokenPayload,
):
    """Returning Google user logs in without creating a new account."""
    # Prepare — create user with google_sub
    hashed = get_password_hash("sentinel")
    user = User(
        username="existing_google",
        email_address="socialuser@gmail.com",
        password=hashed,
        google_sub="google_sub_123456",
        auth_provider=AUTH_PROVIDER_GOOGLE,
        email_verified=True,
    )
    session.add(user)
    await session.commit()

    social_auth_service.verify_google_access_token = AsyncMock(return_value=google_token_payload)

    # Act
    result = await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token="fake_google_access_token",
    )

    # Assert
    assert result.is_new_user is False
    assert result.access_token
    assert result.user.username == "existing_google"


@pytest.mark.asyncio
async def test_google_links_existing_email(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,
    google_token_payload: SocialTokenPayload,
):
    """Existing email user gets Google sub linked."""
    # Prepare — create email user with same email as Google payload
    hashed = get_password_hash("mypassword")
    user = User(
        username="emailuser",
        email_address="socialuser@gmail.com",
        password=hashed,
        auth_provider=AUTH_PROVIDER_EMAIL,
        email_verified=True,
    )
    session.add(user)
    await session.commit()

    social_auth_service.verify_google_access_token = AsyncMock(return_value=google_token_payload)

    # Act
    result = await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token="fake_google_access_token",
    )

    # Assert
    assert result.is_new_user is False

    # Verify google_sub was linked
    stmt = select(User).where(User.email_address == "socialuser@gmail.com")
    db_result = await session.exec(stmt)
    linked_user = db_result.one()
    assert linked_user.google_sub == "google_sub_123456"


@pytest.mark.asyncio
async def test_google_invalid_token(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
):
    """Invalid Google token raises InvalidCredentialsError."""
    # Prepare
    social_auth_service.verify_google_access_token = AsyncMock(side_effect=InvalidCredentialsError())

    # Act & Assert
    with pytest.raises(InvalidCredentialsError):
        await auth_controller.social_login(
            social_auth_service=social_auth_service,
            access_token="invalid_token",
        )


@pytest.mark.asyncio
async def test_social_user_cannot_login_with_password(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,  # noqa: ARG001
    google_token_payload: SocialTokenPayload,
):
    """A user created via social login cannot authenticate with password."""
    # Prepare — create user via social login
    social_auth_service.verify_google_access_token = AsyncMock(return_value=google_token_payload)
    await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token="fake_token",
    )

    # Act & Assert — try password login
    with pytest.raises(InvalidCredentialsError):
        await auth_controller.login("socialuser@gmail.com", "anypassword")


@pytest.mark.asyncio
async def test_username_generated_from_google_name(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
):
    """Username is generated from Google first/last name."""
    # Prepare
    payload = SocialTokenPayload(
        sub="google_name_test",
        email="nametest@gmail.com",
        email_verified=True,
        first_name="Ahmad",
        last_name="Khan",
    )
    social_auth_service.verify_google_access_token = AsyncMock(return_value=payload)

    # Act
    result = await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token="fake_token",
    )

    # Assert
    assert result.user.username == "ahmad_khan"


@pytest.mark.asyncio
async def test_username_fallback_to_email_prefix(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
):
    """Username falls back to email prefix when no name is provided."""
    # Prepare
    payload = SocialTokenPayload(
        sub="google_noname_test",
        email="noname.user@gmail.com",
        email_verified=True,
    )
    social_auth_service.verify_google_access_token = AsyncMock(return_value=payload)

    # Act
    result = await auth_controller.social_login(
        social_auth_service=social_auth_service,
        access_token="fake_token",
    )

    # Assert — dots are stripped by the regex, so "noname.user" becomes "nonameuser"
    assert result.user.username == "nonameuser"


# ========== SEC F02: Google links only into a verified account ==========


async def test_google_sign_in_takes_back_an_unverified_account_registered_for_the_address(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,
):
    """Port of test_f02_google_login_links_into_unverified_account_whose_password_still_works, inverted.

    Someone registered an address they do not own (registration needs no verification).
    The mailbox's real owner then signs in with Google, whose verified email proves
    ownership: the account is reset to them. The squatter's password and every token
    they hold stop working.
    """
    # Prepare
    squatter_password = "Squat-Passw0rd!"
    squatted = await auth_controller.register(
        UserCreate(username="first_registrant", email_address="owner.mailbox@example.com", password=squatter_password)
    )
    assert squatted.email_verified is False
    squatted_id = squatted.id
    squatter = await auth_controller.login("owner.mailbox@example.com", squatter_password)
    social_auth_service.verify_google_access_token = AsyncMock(
        return_value=SocialTokenPayload(
            sub="google-sub-owner", email="owner.mailbox@example.com", email_verified=True, first_name="Real"
        )
    )

    # Act
    result = await auth_controller.social_login(social_auth_service=social_auth_service, access_token="google-token")

    # Assert — the owner is in, as the same account
    assert result.is_new_user is False
    assert result.user.id == str(squatted_id)
    session.expire_all()
    linked = (await session.exec(select(User).where(User.id == squatted_id))).one()
    assert linked.google_sub == "google-sub-owner"
    assert linked.auth_provider == AUTH_PROVIDER_GOOGLE
    assert linked.email_verified is True
    # the squatter's password no longer opens it
    with pytest.raises(InvalidCredentialsError):
        await auth_controller.login("owner.mailbox@example.com", squatter_password)
    assert not verify_password(squatter_password, linked.password)
    # nor do the squatter's earlier tokens
    with pytest.raises(SessionRevokedError):
        await authenticate_access_token(session, auth_controller.settings, squatter.access_token)
    with pytest.raises(SessionRevokedError):
        await auth_controller.refresh_session(squatter.refresh_token)
    sessions = (await session.exec(select(AuthSession).where(AuthSession.user_id == squatted_id))).all()
    live = [row for row in sessions if row.revoked_at is None]
    assert [str(row.id) for row in live] == [jwt.get_unverified_claims(result.access_token)["sid"]]
    # the owner's own tokens work
    owner = await authenticate_access_token(session, auth_controller.settings, result.access_token)
    assert owner.id == squatted_id


async def test_google_sign_in_links_a_verified_account_and_keeps_its_password_and_sessions(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,
):
    """A verified account proved the mailbox already: link, and leave everything else alone."""
    # Prepare
    user = User(
        username="verified_owner",
        email_address="verified.owner@example.com",
        password=get_password_hash("mypassword"),
        auth_provider=AUTH_PROVIDER_EMAIL,
        email_verified=True,
    )
    session.add(user)
    await session.commit()
    user_id = user.id
    earlier = await auth_controller.login("verified.owner@example.com", "mypassword")
    social_auth_service.verify_google_access_token = AsyncMock(
        return_value=SocialTokenPayload(
            sub="google-sub-verified", email="verified.owner@example.com", email_verified=True
        )
    )

    # Act
    result = await auth_controller.social_login(social_auth_service=social_auth_service, access_token="google-token")

    # Assert
    assert result.user.id == str(user_id)
    session.expire_all()
    linked = (await session.exec(select(User).where(User.id == user_id))).one()
    assert linked.google_sub == "google-sub-verified"
    assert linked.auth_provider == AUTH_PROVIDER_EMAIL
    assert (await auth_controller.login("verified.owner@example.com", "mypassword")).user.id == str(user_id)
    still = await authenticate_access_token(session, auth_controller.settings, earlier.access_token)
    assert still.id == user_id
    assert jwt.get_unverified_claims(earlier.access_token)["sid"]


async def test_google_sign_in_opens_a_session(
    auth_controller: AuthController,
    social_auth_service: SocialAuthService,
    session: AsyncSession,
    google_token_payload: SocialTokenPayload,
):
    """Social login mints a session pair like the password login does (SEC F01)."""
    # Prepare
    social_auth_service.verify_google_access_token = AsyncMock(return_value=google_token_payload)

    # Act
    result = await auth_controller.social_login(social_auth_service=social_auth_service, access_token="google-token")

    # Assert
    sid = jwt.get_unverified_claims(result.access_token)["sid"]
    assert jwt.get_unverified_claims(result.refresh_token)["sid"] == sid
    stored = (await session.exec(select(AuthSession).where(AuthSession.id == UUID(sid)))).one()
    assert str(stored.user_id) == result.user.id
