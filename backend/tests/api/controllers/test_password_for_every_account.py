"""A password for every account: "Change password" works for a Google-only account too.

A Google-only account (``auth_provider`` google) is created with a random sentinel
password its owner never saw, and ``AuthController.login`` refuses any account that is
not ``auth_provider`` email. "Change password" asked for the current password, which such
an account cannot give, so it could not set one; and a reset ("Forgot password?") stored
a password that the login then refused.

The rule now (no schema change): ``auth_provider`` email means "the account has a
password of its own" — what the login already reads it as. So:

- a change is confirmed by the account's own credential, EXACTLY one: the current password
  of an account that has one; a fresh Google access token for a Google-only account,
  verified like deletion (the sign-in's audience check, and the token's ``sub`` is the
  account's ``google_sub``). The other kind is a named 403;
- setting a password (the change, or a reset) makes the account ``auth_provider`` email
  with its ``google_sub`` kept: the password opens it at /auth/login and Google sign-in
  still does, exactly as for an email account linked to Google;
- the change keeps signing out every OTHER session, is checked in bcrypt bytes, and is
  rate-limited per account (``PASSWORD_CHANGE_RATE_LIMIT``).
"""

from collections.abc import AsyncGenerator, Callable

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import AUTH_PROVIDER_EMAIL, AUTH_PROVIDER_GOOGLE
from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.shared import verify_password
from majlisna.api.controllers.user import UserController
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.table import User
from majlisna.api.models.user import UserUpdatePassword
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.error import (
    CurrentPasswordRequiredError,
    GoogleConfirmationRequiredError,
    InvalidCredentialsError,
    PasswordTooLongError,
)
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.dependencies import get_session, get_settings, get_social_auth_service
from majlisna.settings import Settings

CLIENT_ID = "majlisna-web.apps.googleusercontent.com"
OWNER_SUB = "google-sub-owner"
OWNER_EMAIL = "g.only@test.com"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
PASSWORD = "password123"  # create_user's default
NEW_PASSWORD = "Chosen-Passw0rd!"
# 40 characters, 80 bytes of UTF-8: over bcrypt's 72 bytes.
ARABIC_40_CHARS = "كلمة" * 10


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _fake_google(sub: str, email: str, audience: str = CLIENT_ID) -> Callable[[httpx.Request], httpx.Response]:
    """Google's tokeninfo and userinfo for a token minted for ``audience``, naming ``sub``."""

    def _answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tokeninfo":
            return httpx.Response(200, json={"aud": audience, "azp": audience, "sub": sub, "expires_in": "3599"})
        return httpx.Response(
            200, json={"sub": sub, "email": email, "email_verified": True, "given_name": "Real", "family_name": "Owner"}
        )

    return _answer


def _google_service(settings: Settings, sub: str, email: str, audience: str = CLIENT_ID) -> SocialAuthService:
    """The real verification, against a fake Google: only the network is stood in for."""
    return SocialAuthService(settings, transport=httpx.MockTransport(_fake_google(sub, email, audience)))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _password_url(user: User) -> str:
    return f"/api/v1/users/{user.id}/password"


async def _fresh_user(session: AsyncSession, user_id) -> User:
    session.expunge_all()
    return (await session.exec(select(User).where(User.id == user_id))).one()


async def _google_sign_in(session: AsyncSession, google_settings: Settings, email: str = OWNER_EMAIL):
    """One "Continue with Google": opens a session, creating the account the first time."""
    return await AuthController(session, google_settings).social_login(
        social_auth_service=_google_service(google_settings, OWNER_SUB, email), access_token="google-token"
    )


async def _google_user(session: AsyncSession, google_settings: Settings, email: str = OWNER_EMAIL) -> tuple:
    """A Google-only account (random sentinel password), signed in; returns (user, access token)."""
    result = await _google_sign_in(session, google_settings, email)
    user = (await session.exec(select(User).where(User.email_address == email))).one()
    assert user.auth_provider == AUTH_PROVIDER_GOOGLE
    return user, result.access_token


class _RecordingEmailService:
    """Keeps the reset link's token instead of sending it."""

    token: str = ""

    async def send_password_reset_email(self, _to: str, _username: str, url: str) -> bool:
        self.token = url.split("token=", 1)[1]
        return True


@pytest.fixture(name="google_settings")
def get_google_settings(test_settings: Settings) -> Settings:
    return test_settings.model_copy(update={"google_client_id_web": CLIENT_ID})


@pytest_asyncio.fixture(name="api")
async def get_api(
    test_app: FastAPI, session: AsyncSession, google_settings: Settings
) -> AsyncGenerator[httpx.AsyncClient]:
    """The real app on the test database, Google standing in for the owner; fresh rate-limit budgets."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: google_settings
    test_app.dependency_overrides[get_social_auth_service] = lambda: _google_service(
        google_settings, OWNER_SUB, OWNER_EMAIL
    )
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    limiter.reset()
    test_app.dependency_overrides.clear()


# ─── A Google-only account sets a password, confirmed with Google ────────────


@pytest.mark.asyncio
async def test_a_google_only_account_sets_a_password_confirmed_with_google(
    api: httpx.AsyncClient, session: AsyncSession, google_settings: Settings
):
    """Two devices signed in with Google; the password is set from the first: the second is signed out."""
    # Prepare
    user, phone = await _google_user(session, google_settings)
    laptop = (await _google_sign_in(session, google_settings)).access_token
    auth = AuthController(session, google_settings)
    phone_sid, laptop_sid = auth.decode_token(phone).sid, auth.decode_token(laptop).sid

    # Act
    response = await api.patch(
        _password_url(user),
        json={"google_access_token": "fresh-google-token", "new_password": NEW_PASSWORD},
        headers=_bearer(phone),
    )

    # Assert — the answer, then the stored row
    assert response.status_code == 200, response.text
    assert response.json()["auth_provider"] == AUTH_PROVIDER_EMAIL
    stored = await _fresh_user(session, user.id)
    assert stored.auth_provider == AUTH_PROVIDER_EMAIL
    assert stored.google_sub == OWNER_SUB
    assert verify_password(NEW_PASSWORD, stored.password) is True
    rows = {str(row.id): row for row in (await session.exec(select(AuthSession))).all()}
    assert rows[str(phone_sid)].revoked_at is None
    assert rows[str(laptop_sid)].revoked_at is not None
    assert (await api.get(ME_URL, headers=_bearer(phone))).status_code == 200
    assert (await api.get(ME_URL, headers=_bearer(laptop))).json()["error_key"] == "errors.api.sessionRevoked"


@pytest.mark.asyncio
async def test_the_password_a_google_account_set_opens_it_and_google_still_does(
    api: httpx.AsyncClient, session: AsyncSession, google_settings: Settings
):
    """The point of the feature: both doors open the same account afterwards."""
    # Prepare
    user, access_token = await _google_user(session, google_settings)
    set_response = await api.patch(
        _password_url(user),
        json={"google_access_token": "fresh-google-token", "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )
    assert set_response.status_code == 200, set_response.text

    # Act
    login = await api.post(LOGIN_URL, json={"email": OWNER_EMAIL, "password": NEW_PASSWORD})
    google_again = await _google_sign_in(session, google_settings)

    # Assert
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == str(user.id)
    assert google_again.is_new_user is False
    assert google_again.user.id == str(user.id)
    stored = await _fresh_user(session, user.id)
    assert stored.google_sub == OWNER_SUB
    assert (await session.exec(select(User).where(User.email_address == OWNER_EMAIL))).all() == [stored]


@pytest.mark.asyncio
async def test_a_google_token_of_another_account_sets_nothing(
    api: httpx.AsyncClient, session: AsyncSession, test_app: FastAPI, google_settings: Settings
):
    """A valid token, minted for this app, but naming someone else's Google account: 403."""
    # Prepare
    user, access_token = await _google_user(session, google_settings)
    sentinel = user.password
    test_app.dependency_overrides[get_social_auth_service] = lambda: _google_service(
        google_settings, "someone-else", "someone.else@test.com"
    )

    # Act
    response = await api.patch(
        _password_url(user),
        json={"google_access_token": "their-token", "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )

    # Assert
    assert response.status_code == 403
    assert response.json()["error_key"] == "errors.api.googleAccountMismatch"
    stored = await _fresh_user(session, user.id)
    assert stored.auth_provider == AUTH_PROVIDER_GOOGLE
    assert stored.password == sentinel
    login = await api.post(LOGIN_URL, json={"email": OWNER_EMAIL, "password": NEW_PASSWORD})
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_a_google_token_minted_for_another_app_is_a_401(
    api: httpx.AsyncClient, session: AsyncSession, test_app: FastAPI, google_settings: Settings
):
    """The sign-in's audience check runs here too: the owner's own token, for another app, confirms nothing."""
    # Prepare
    user, access_token = await _google_user(session, google_settings)
    sentinel = user.password
    test_app.dependency_overrides[get_social_auth_service] = lambda: _google_service(
        google_settings, OWNER_SUB, OWNER_EMAIL, audience="another-app.apps.googleusercontent.com"
    )

    # Act
    response = await api.patch(
        _password_url(user),
        json={"google_access_token": "token-for-another-app", "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )

    # Assert
    assert response.status_code == 401
    assert response.json()["error_key"] == "errors.api.invalidCredentials"
    stored = await _fresh_user(session, user.id)
    assert stored.auth_provider == AUTH_PROVIDER_GOOGLE
    assert stored.password == sentinel


@pytest.mark.asyncio
async def test_a_google_only_account_cannot_confirm_with_a_typed_password(
    api: httpx.AsyncClient, session: AsyncSession, google_settings: Settings
):
    """Its stored password is not a credential (the login refuses it): Google is asked for, by name."""
    # Prepare
    user, access_token = await _google_user(session, google_settings)
    sentinel = user.password

    # Act
    response = await api.patch(
        _password_url(user),
        json={"current_password": "anything-i-could-type", "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )

    # Assert
    assert response.status_code == 403
    assert response.json()["error_key"] == "errors.api.googleConfirmationRequired"
    stored = await _fresh_user(session, user.id)
    assert stored.auth_provider == AUTH_PROVIDER_GOOGLE
    assert stored.password == sentinel


@pytest.mark.asyncio
async def test_an_account_with_a_password_still_confirms_with_it_not_with_google(
    api: httpx.AsyncClient, session: AsyncSession, auth_controller: AuthController, create_user
):
    """An email account linked to Google: a Google token is refused by name, the password still works.

    On a shared computer the Google session is often still open; the password is the
    stronger proof, so an account that has one keeps confirming with it.
    """
    # Prepare
    user = await create_user(username="linked", email=OWNER_EMAIL)
    user.google_sub = OWNER_SUB
    session.add(user)
    await session.commit()
    access_token = (await auth_controller.login(OWNER_EMAIL, PASSWORD)).access_token

    # Act
    with_google = await api.patch(
        _password_url(user),
        json={"google_access_token": "fresh-google-token", "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )
    # read now: the next request mutates the same row in this session
    password_kept = verify_password(PASSWORD, (await _fresh_user(session, user.id)).password)
    with_password = await api.patch(
        _password_url(user),
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )

    # Assert
    assert with_google.status_code == 403
    assert with_google.json()["error_key"] == "errors.api.currentPasswordRequired"
    assert password_kept is True
    assert with_password.status_code == 200, with_password.text
    stored = await _fresh_user(session, user.id)
    assert stored.auth_provider == AUTH_PROVIDER_EMAIL
    assert verify_password(NEW_PASSWORD, stored.password) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "confirmation",
    [{}, {"current_password": PASSWORD, "google_access_token": "fresh-google-token"}],
    ids=["neither", "both"],
)
async def test_a_password_change_names_exactly_one_confirmation(
    api: httpx.AsyncClient, session: AsyncSession, auth_controller: AuthController, create_user, confirmation: dict
):
    """Neither, or both: a validation error, nothing changed."""
    # Prepare
    user = await create_user(username="confirmer", email="confirmer@test.com")
    access_token = (await auth_controller.login("confirmer@test.com", PASSWORD)).access_token

    # Act
    response = await api.patch(
        _password_url(user), json={**confirmation, "new_password": NEW_PASSWORD}, headers=_bearer(access_token)
    )

    # Assert
    assert response.status_code == 422
    assert response.json()["error_key"] == "errors.api.validation"
    assert verify_password(PASSWORD, (await _fresh_user(session, user.id)).password) is True


@pytest.mark.parametrize(
    "body",
    [
        {"google_access_token": "fresh-google-token", "new_password": ARABIC_40_CHARS},
        {"current_password": ARABIC_40_CHARS, "new_password": NEW_PASSWORD},
    ],
    ids=["google, new over 72 bytes", "password, current over 72 bytes"],
)
def test_both_confirmations_keep_the_bcrypt_byte_check(body: dict):
    """SEC F10 on either path: a password over 72 bytes is the translated 400, never a hash attempt."""
    # Act / Assert
    with pytest.raises(PasswordTooLongError):
        UserUpdatePassword(**body)


@pytest.mark.asyncio
async def test_a_password_change_is_rate_limited_per_account(
    api: httpx.AsyncClient, session: AsyncSession, auth_controller: AuthController, create_user, google_settings
):
    """Guessing the current password from a stolen session hits a per-account limit; other accounts do not."""
    # Prepare
    user = await create_user(username="guessed", email="guessed@test.com")
    access_token = (await auth_controller.login("guessed@test.com", PASSWORD)).access_token
    google_user, google_token = await _google_user(session, google_settings)

    # Act — five wrong guesses, then the right password
    guesses = [
        (
            await api.patch(
                _password_url(user),
                json={"current_password": f"guess-{index}", "new_password": NEW_PASSWORD},
                headers=_bearer(access_token),
            )
        ).status_code
        for index in range(5)
    ]
    sixth = await api.patch(
        _password_url(user),
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )
    another_account = await api.patch(
        _password_url(google_user),
        json={"google_access_token": "fresh-google-token", "new_password": NEW_PASSWORD},
        headers=_bearer(google_token),
    )

    # Assert
    assert guesses == [401] * 5
    assert sixth.status_code == 429
    assert sixth.json()["error_key"] == "errors.api.rateLimitExceeded"
    assert verify_password(PASSWORD, (await _fresh_user(session, user.id)).password) is True
    assert another_account.status_code == 200, another_account.text


@pytest.mark.asyncio
async def test_a_google_confirmation_nothing_can_verify_confirms_nothing(
    session: AsyncSession, google_settings: Settings
):
    """Fail closed: a controller call with a Google token but no verifier changes nothing."""
    # Prepare
    user, _ = await _google_user(session, google_settings)
    sentinel = user.password

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await UserController(session).update_user_password(user.id, None, NEW_PASSWORD, google_access_token="token")
    assert (await _fresh_user(session, user.id)).password == sentinel


@pytest.mark.asyncio
async def test_the_controller_refuses_the_other_kind_of_confirmation(
    session: AsyncSession, google_settings: Settings, create_user
):
    """Each kind of account names the confirmation it lacks."""
    # Prepare
    google_user, _ = await _google_user(session, google_settings)
    password_user = await create_user(username="haspassword", email="haspassword@test.com")
    service = _google_service(google_settings, OWNER_SUB, OWNER_EMAIL)
    controller = UserController(session)

    # Act / Assert
    with pytest.raises(GoogleConfirmationRequiredError):
        await controller.update_user_password(google_user.id, "typed", NEW_PASSWORD)
    with pytest.raises(CurrentPasswordRequiredError):
        await controller.update_user_password(
            password_user.id, None, NEW_PASSWORD, google_access_token="token", social_auth_service=service
        )


# ─── "Forgot password?" gives a Google-only account a usable password ─────────


@pytest.mark.asyncio
async def test_a_reset_gives_a_google_only_account_a_password_that_opens_it(
    api: httpx.AsyncClient, session: AsyncSession, google_settings: Settings
):
    """The reset link reaches the address Google verified: the password it sets now works at login."""
    # Prepare
    user, _ = await _google_user(session, google_settings)
    auth = AuthController(session, google_settings)
    email_service = _RecordingEmailService()
    await auth.request_password_reset(OWNER_EMAIL, email_service)

    # Act
    await auth.reset_password(email_service.token, NEW_PASSWORD)
    login = await api.post(LOGIN_URL, json={"email": OWNER_EMAIL, "password": NEW_PASSWORD})
    google_again = await _google_sign_in(session, google_settings)

    # Assert
    assert login.status_code == 200, login.text
    assert google_again.user.id == str(user.id)
    stored = await _fresh_user(session, user.id)
    assert stored.auth_provider == AUTH_PROVIDER_EMAIL
    assert stored.google_sub == OWNER_SUB
    assert verify_password(NEW_PASSWORD, stored.password) is True
