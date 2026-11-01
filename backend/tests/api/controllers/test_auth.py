import asyncio
import hashlib
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest
from jose import jwt
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.models.table import User
from majlisna.api.models.token import EmailVerificationToken, PasswordResetToken
from majlisna.api.models.user import UserCreate
from majlisna.api.schemas.auth import LoginResult, TokenPayload
from majlisna.api.schemas.error import (
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    InvalidTokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UsernameAlreadyTakenError,
)
from majlisna.api.schemas.social_auth import SocialTokenPayload
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.settings import Settings


async def test_register_success(auth_controller: AuthController):
    """Registering a new user persists all fields and hashes the password."""
    # Arrange
    user_create = UserCreate(
        username="newuser",
        email_address="new@test.com",
        password="secret123",
    )

    # Act
    user = await auth_controller.register(user_create)

    # Assert
    assert user.id is not None
    assert user.username == "newuser"
    assert user.email_address == "new@test.com"
    assert user.password != "secret123"
    assert user.country is None


async def test_register_duplicate_email(auth_controller: AuthController, session: AsyncSession):
    """Registering an address twice is a named 409, not the unique constraint's raw IntegrityError (a 500).

    This test used to assert the IntegrityError — i.e. it pinned the 500 the route
    then answered with.
    """
    # Arrange
    user_create_1 = UserCreate(
        username="user1",
        email_address="dup@test.com",
        password="secret123",
    )
    user_create_2 = UserCreate(
        username="user2",
        email_address="dup@test.com",
        password="secret456",
    )
    await auth_controller.register(user_create_1)

    # Act & Assert
    with pytest.raises(UserAlreadyExistsError):
        await auth_controller.register(user_create_2)
    rows = (await session.exec(select(User).where(User.email_address == "dup@test.com"))).all()
    assert [u.username for u in rows] == ["user1"]


@pytest.mark.parametrize("second_username", ["admin", "Admin", "ADMIN"])
async def test_register_rejects_a_taken_username_in_any_case(
    auth_controller: AuthController, session: AsyncSession, second_username: str
):
    """A second account cannot take an existing username, whatever its case.

    `user.username` has no unique constraint, so this used to register a second
    "admin" (201) — e2e/tests/auth/validation.spec.ts "duplicate username shows error".
    """
    # Arrange
    await auth_controller.register(UserCreate(username="admin", email_address="first@test.com", password="secret123"))

    # Act & Assert
    with pytest.raises(UsernameAlreadyTakenError) as exc_info:
        await auth_controller.register(
            UserCreate(username=second_username, email_address="second@test.com", password="secret456")
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_key == "errors.api.usernameAlreadyTaken"
    assert exc_info.value.error_params == {"username": second_username}
    assert (await auth_controller.get_user_by_email("second@test.com")) is None
    rows = (await session.exec(select(User))).all()
    assert [u.username for u in rows] == ["admin"]


async def test_social_signup_does_not_reuse_a_username_taken_in_another_case(
    auth_controller: AuthController, create_user
):
    """A Google sign-up whose generated name matches an account in another case gets a suffix."""
    # Arrange
    await create_user(username="Yusuf", email="yusuf@test.com")
    payload = SocialTokenPayload(sub="google-sub-1", email="yusuf.g@gmail.com", first_name="Yusuf", email_verified=True)

    # Act
    user = await auth_controller._create_social_user(payload)

    # Assert
    assert user.username.lower() != "yusuf"
    assert user.username.startswith("yusuf_")


async def test_social_signup_tries_another_suffix_when_the_first_is_taken(
    auth_controller: AuthController, create_user, monkeypatch: pytest.MonkeyPatch
):
    """The suffixed fallback is checked too: a taken one moves on to the next candidate."""
    # Arrange
    await create_user(username="yusuf", email="yusuf@test.com")
    await create_user(username="Yusuf_aaaa", email="yusuf.a@test.com")
    suffixes = iter(["yusuf_aaaa", "yusuf_bbbb", "yusuf_cccc"])
    monkeypatch.setattr(AuthController, "_suffixed_username", staticmethod(lambda _name: next(suffixes)))
    payload = SocialTokenPayload(sub="google-sub-2", email="yusuf.g@gmail.com", first_name="Yusuf", email_verified=True)

    # Act
    user = await auth_controller._create_social_user(payload)

    # Assert
    assert user.username == "yusuf_bbbb"


async def test_social_signup_gives_up_when_every_candidate_is_taken(
    auth_controller: AuthController, create_user, monkeypatch: pytest.MonkeyPatch
):
    """Every candidate taken (never in practice: three random suffixes) is a named 409, not a duplicate.

    The repeated suffix also pins that a candidate is claimed once: the SQLite
    fallback's lock is not reentrant, so claiming it twice would hang this test.
    """
    # Arrange
    await create_user(username="yusuf", email="yusuf@test.com")
    await create_user(username="yusuf_aaaa", email="yusuf.a@test.com")
    monkeypatch.setattr(AuthController, "_suffixed_username", staticmethod(lambda _name: "yusuf_aaaa"))
    payload = SocialTokenPayload(sub="google-sub-3", email="yusuf.g@gmail.com", first_name="Yusuf", email_verified=True)

    # Act & Assert
    with pytest.raises(UsernameAlreadyTakenError):
        await auth_controller._create_social_user(payload)
    assert (await auth_controller.get_user_by_email("yusuf.g@gmail.com")) is None


# ─── Concurrent claims of one new username (postgres) ─────────


async def _register_own_session(engine: AsyncEngine, settings: Settings, username: str, email: str) -> User:
    """``register`` in a fresh session, as one request would run it.

    Concurrent tasks must not share one AsyncSession (see test_concurrent_mutations
    ``_mutate``): production gives every request its own, and the username lock
    serialises them across connections.
    """
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await AuthController(own_session, settings).register(
            UserCreate(username=username, email_address=email, password="secret123")
        )


async def _social_signup_own_session(engine: AsyncEngine, settings: Settings, sub: str, email: str) -> User:
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        payload = SocialTokenPayload(sub=sub, email=email, first_name="Zubayr", email_verified=True)
        return await AuthController(own_session, settings)._create_social_user(payload)


@pytest.mark.postgres
async def test_two_concurrent_registrations_of_one_new_username_admit_exactly_one(
    engine: AsyncEngine, session: AsyncSession, test_settings: Settings
):
    """Both requests pass the check before either commits — without the lock, both won."""
    # Act
    results = await asyncio.gather(
        _register_own_session(engine, test_settings, "khadija", "khadija.one@test.com"),
        _register_own_session(engine, test_settings, "khadija", "khadija.two@test.com"),
        return_exceptions=True,
    )

    # Assert — one account, one named 409, one row
    successes = [r for r in results if isinstance(r, User)]
    refusals = [r for r in results if isinstance(r, UsernameAlreadyTakenError)]
    assert len(successes) == 1, results
    assert len(refusals) == 1, results
    rows = (await session.exec(select(User).where(User.username == "khadija"))).all()
    assert [row.email_address for row in rows] == [successes[0].email_address]


@pytest.mark.postgres
async def test_two_concurrent_google_signups_of_one_name_never_share_it(
    engine: AsyncEngine, session: AsyncSession, test_settings: Settings
):
    """Two new Google accounts generating the same name: one gets it, the other a suffix."""
    # Act
    results = await asyncio.gather(
        _social_signup_own_session(engine, test_settings, "google-sub-a", "zubayr.a@gmail.com"),
        _social_signup_own_session(engine, test_settings, "google-sub-b", "zubayr.b@gmail.com"),
        return_exceptions=True,
    )

    # Assert
    assert all(isinstance(r, User) for r in results), results
    usernames = sorted(r.username for r in results if isinstance(r, User))
    assert usernames[0] == "zubayr"
    assert usernames[1].startswith("zubayr_")
    rows = (await session.exec(select(User).where(User.username == "zubayr"))).all()
    assert len(rows) == 1


async def test_login_success(auth_controller: AuthController, create_user, test_settings: Settings):
    """Logging in with correct credentials returns tokens and user data."""
    # Arrange
    await create_user(username="loginuser", email="login@test.com", password="mypassword")

    # Act
    result = await auth_controller.login("login@test.com", "mypassword")

    # Assert
    assert isinstance(result, LoginResult)
    assert result.access_token
    assert result.refresh_token
    assert result.user.username == "loginuser"
    assert result.user.email == "login@test.com"

    access_payload = jwt.decode(
        result.access_token,
        test_settings.jwt_secret_key,
        algorithms=[test_settings.jwt_encryption_algorithm],
    )
    refresh_payload = jwt.decode(
        result.refresh_token,
        test_settings.jwt_secret_key,
        algorithms=[test_settings.jwt_encryption_algorithm],
    )
    assert access_payload["email"] == "login@test.com"
    assert refresh_payload["email"] == "login@test.com"
    assert access_payload["sub"] == refresh_payload["sub"]


async def test_login_wrong_password(auth_controller: AuthController, create_user):
    """Logging in with an incorrect password raises InvalidCredentialsError."""
    # Arrange
    await create_user(username="wrongpw", email="wrongpw@test.com", password="correctpass")

    # Act & Assert
    with pytest.raises(InvalidCredentialsError):
        await auth_controller.login("wrongpw@test.com", "wrongpass")


async def test_login_nonexistent_email(auth_controller: AuthController):
    """Logging in with a nonexistent email raises InvalidCredentialsError."""
    # Arrange
    email = "nonexistent@test.com"

    # Act & Assert
    with pytest.raises(InvalidCredentialsError):
        await auth_controller.login(email, "anypassword")


async def test_create_access_token(auth_controller: AuthController, test_settings: Settings):
    """Creating an access token encodes sub, email, and exp within 15 minutes."""
    # Arrange
    user_id = "user-123"
    email = "user@test.com"
    before = datetime.now(UTC)

    # Act
    token = auth_controller.create_access_token(user_id, email)

    # Assert
    payload = jwt.decode(
        token,
        test_settings.jwt_secret_key,
        algorithms=[test_settings.jwt_encryption_algorithm],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@test.com"
    assert "exp" in payload
    exp_dt = datetime.fromtimestamp(payload["exp"], tz=UTC)
    expected_min = before + timedelta(minutes=test_settings.access_token_expire_minutes - 1)
    expected_max = before + timedelta(minutes=test_settings.access_token_expire_minutes + 1)
    assert expected_min <= exp_dt <= expected_max


async def test_create_refresh_token(auth_controller: AuthController, test_settings: Settings):
    """Creating a refresh token encodes sub, email, and exp within ~7 days."""
    # Arrange
    user_id = "user-456"
    email = "user2@test.com"
    before = datetime.now(UTC)

    # Act
    token = auth_controller.create_refresh_token(user_id, email)

    # Assert
    payload = jwt.decode(
        token,
        test_settings.jwt_secret_key,
        algorithms=[test_settings.jwt_encryption_algorithm],
    )
    assert payload["sub"] == "user-456"
    assert payload["email"] == "user2@test.com"
    assert "exp" in payload
    exp_dt = datetime.fromtimestamp(payload["exp"], tz=UTC)
    expected_min = before + timedelta(days=test_settings.refresh_token_expire_days - 1)
    expected_max = before + timedelta(days=test_settings.refresh_token_expire_days + 1)
    assert expected_min <= exp_dt <= expected_max


async def test_login_returns_a_session_pair(auth_controller: AuthController, create_user, test_settings: Settings):
    """The pair a login answers: both tokens decode to the same user and the same session.

    (``create_token_pair`` minted a pair with no session behind it; it is gone, so no
    caller can hand out tokens a logout or a reset cannot end.)
    """
    # Arrange
    created = await create_user(username="pairuser", email="pair@test.com", password="pairpass123")

    # Act
    result = await auth_controller.login("pair@test.com", "pairpass123")

    # Assert
    assert result.access_token
    assert result.refresh_token
    access_payload = jwt.decode(
        result.access_token, test_settings.jwt_secret_key, algorithms=[test_settings.jwt_encryption_algorithm]
    )
    refresh_payload = jwt.decode(
        result.refresh_token, test_settings.jwt_secret_key, algorithms=[test_settings.jwt_encryption_algorithm]
    )
    assert access_payload["sub"] == refresh_payload["sub"] == str(created.id)
    assert access_payload["email"] == refresh_payload["email"] == "pair@test.com"
    assert access_payload["sid"] == refresh_payload["sid"]
    assert not hasattr(auth_controller, "create_token_pair")


async def test_decode_token_valid(auth_controller: AuthController):
    """Decoding a freshly created token returns all TokenPayload fields."""
    # Arrange
    token = auth_controller.create_access_token("decode-user", "decode@test.com")

    # Act
    payload = auth_controller.decode_token(token)

    # Assert
    assert isinstance(payload, TokenPayload)
    assert payload.sub == "decode-user"
    assert payload.email == "decode@test.com"
    assert payload.exp > 0


async def test_access_and_refresh_tokens_carry_type_claim(auth_controller: AuthController, test_settings: Settings):
    """Access and refresh tokens embed distinct `type` claims."""
    # Arrange / Act
    access = auth_controller.create_access_token("u1", "u1@test.com")
    refresh = auth_controller.create_refresh_token("u1", "u1@test.com")

    # Assert
    access_payload = jwt.decode(
        access, test_settings.jwt_secret_key, algorithms=[test_settings.jwt_encryption_algorithm]
    )
    refresh_payload = jwt.decode(
        refresh, test_settings.jwt_secret_key, algorithms=[test_settings.jwt_encryption_algorithm]
    )
    assert access_payload["type"] == "access"
    assert refresh_payload["type"] == "refresh"


async def test_decode_token_rejects_wrong_type(auth_controller: AuthController):
    """A refresh token is rejected when an access token is expected, and vice versa."""
    # Arrange
    access = auth_controller.create_access_token("u1", "u1@test.com")
    refresh = auth_controller.create_refresh_token("u1", "u1@test.com")

    # Act & Assert — refresh token cannot authenticate API calls
    with pytest.raises(InvalidTokenError):
        auth_controller.decode_token(refresh, expected_type="access")
    # Access token cannot mint a new token pair at /refresh
    with pytest.raises(InvalidTokenError):
        auth_controller.decode_token(access, expected_type="refresh")

    # Sanity: matching types decode fine
    assert auth_controller.decode_token(access, expected_type="access").type == "access"
    assert auth_controller.decode_token(refresh, expected_type="refresh").type == "refresh"


async def test_decode_token_expired(auth_controller: AuthController, test_settings: Settings):
    """Decoding an expired token raises TokenExpiredError."""
    # Arrange
    expired_payload = {
        "sub": "expired-user",
        "email": "expired@test.com",
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    token = jwt.encode(
        expired_payload,
        test_settings.jwt_secret_key,
        algorithm=test_settings.jwt_encryption_algorithm,
    )

    # Act & Assert
    with pytest.raises(TokenExpiredError):
        auth_controller.decode_token(token)


async def test_decode_token_invalid(auth_controller: AuthController):
    """Decoding a garbage string raises InvalidTokenError."""
    # Arrange
    garbage_token = "garbage.invalid.token"

    # Act & Assert
    with pytest.raises(InvalidTokenError):
        auth_controller.decode_token(garbage_token)


async def test_decode_token_wrong_secret(auth_controller: AuthController):
    """Decoding a token signed with a different secret raises InvalidTokenError."""
    # Arrange
    payload = {
        "sub": "wrong-secret-user",
        "email": "wrong@test.com",
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "completely-different-secret", algorithm="HS256")

    # Act & Assert
    with pytest.raises(InvalidTokenError):
        auth_controller.decode_token(token)


async def test_verify_password_correct():
    """Verifying a password against its own hash returns True."""
    # Arrange
    plain_password = "mypassword"
    hashed = get_password_hash(plain_password)

    # Act
    result = AuthController.verify_password(plain_password, hashed)

    # Assert
    assert result is True


async def test_verify_password_incorrect():
    """Verifying a wrong password against a hash returns False."""
    # Arrange
    hashed = get_password_hash("mypassword")

    # Act
    result = AuthController.verify_password("wrongpassword", hashed)

    # Assert
    assert result is False


async def test_get_user_by_email_found(auth_controller: AuthController, create_user):
    """Looking up an existing user by email returns the User with correct fields."""
    # Arrange
    created = await create_user(username="findme", email="findme@test.com", password="pass123")

    # Act
    found = await auth_controller.get_user_by_email("findme@test.com")

    # Assert
    assert found is not None
    assert found.id == created.id
    assert found.username == "findme"
    assert found.email_address == "findme@test.com"


async def test_get_user_by_email_not_found(auth_controller: AuthController):
    """Looking up a nonexistent email returns None."""
    # Arrange
    email = "nobody@test.com"

    # Act
    result = await auth_controller.get_user_by_email(email)

    # Assert
    assert result is None


# ─── SEC F14: one account per mailbox, whatever the case ─────


async def test_an_address_in_another_case_cannot_register_twice(auth_controller: AuthController, session: AsyncSession):
    """'Ali@Example.com' is the mailbox 'ali@example.com' already registered (probe
    test_f14_email_unique_only_case_sensitively: both registered, 201 and 201)."""
    # Prepare
    await auth_controller.register(UserCreate(username="ali", email_address="ali@example.com", password="secret123"))

    # Act / Assert
    with pytest.raises(UserAlreadyExistsError):
        await auth_controller.register(
            UserCreate(username="ali_two", email_address="Ali@Example.com", password="secret456")
        )
    rows = (await session.exec(select(User))).all()
    assert [row.username for row in rows] == ["ali"]


async def test_registration_stores_the_address_lowercased(auth_controller: AuthController, session: AsyncSession):
    """The stored address is the normalised one, so the later guarded unique index (WP-21) holds."""
    # Act
    user = await auth_controller.register(
        UserCreate(username="maryam", email_address="  Maryam@Example.COM ", password="secret123")
    )

    # Assert
    stored = (await session.exec(select(User).where(User.id == user.id))).one()
    assert stored.email_address == "maryam@example.com"


@pytest.mark.parametrize("typed", ["login@test.com", "Login@Test.com", "LOGIN@TEST.COM", " login@test.com "])
async def test_login_works_in_any_case(auth_controller: AuthController, create_user, typed: str):
    """The address a player types at login is compared case-insensitively."""
    # Prepare
    created = await create_user(username="loginuser", email="login@test.com", password="mypassword")

    # Act
    result = await auth_controller.login(typed, "mypassword")

    # Assert
    assert result.user.id == str(created.id)


async def test_a_legacy_mixed_case_row_is_still_found(auth_controller: AuthController, create_user):
    """Rows registered before normalisation keep their case; the lookup compares lower() on both sides."""
    # Prepare
    created = await create_user(username="legacy", email="Legacy.Player@Example.com")

    # Act
    found = await auth_controller.get_user_by_email("legacy.player@example.com")

    # Assert
    assert found is not None
    assert found.id == created.id


async def test_forgot_password_and_resend_find_the_account_in_any_case(auth_controller: AuthController, create_user):
    """Both mails reach the account whatever case the form was filled in."""
    # Prepare
    await create_user(username="caseuser", email="case@test.com")
    mail = Mock()
    mail.send_password_reset_email = AsyncMock(return_value=True)
    mail.send_verification_email = AsyncMock(return_value=True)

    # Act
    await auth_controller.request_password_reset("CASE@Test.com", mail)
    await auth_controller.resend_verification("Case@TEST.com", mail)

    # Assert
    mail.send_password_reset_email.assert_awaited_once()
    mail.send_verification_email.assert_awaited_once()


async def test_google_sign_in_finds_an_account_registered_in_another_case(
    auth_controller: AuthController, session: AsyncSession, create_user, test_settings: Settings
):
    """A Google address in lowercase used to miss the mixed-case row and create a second account."""
    # Prepare — a verified account, so the link is the ordinary one
    created = await create_user(username="hamza", email="Hamza@Example.com")
    created.email_verified = True
    session.add(created)
    await session.commit()
    service = SocialAuthService(test_settings)
    service.verify_google_access_token = AsyncMock(
        return_value=SocialTokenPayload(sub="g-hamza", email="hamza@example.com", email_verified=True)
    )

    # Act
    result = await auth_controller.social_login(social_auth_service=service, access_token="google-token")

    # Assert
    assert result.is_new_user is False
    assert result.user.id == str(created.id)
    assert len((await session.exec(select(User))).all()) == 1


# ─── TQ-03 / PD-15: reset and verification, end to end ───────


def _mail() -> Mock:
    mail = Mock()
    mail.send_password_reset_email = AsyncMock(return_value=True)
    mail.send_verification_email = AsyncMock(return_value=True)
    return mail


def _token_in(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def _reread(session: AsyncSession, model, user_id):
    """Rows as the database has them now: SQLite hands back NAIVE timestamps only on a real read."""
    session.expire_all()
    return (await session.exec(select(model).where(model.user_id == user_id))).all()


async def test_password_reset_round_trip_then_login(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """request → reset → login with the new password. On SQLite the reset used to raise
    "can't compare offset-naive and offset-aware datetimes" (a 500 on every dev reset link)."""
    # Prepare
    user = await create_user(username="tq03", email="tq03@test.com", password="oldpass123")
    mail = _mail()
    await auth_controller.request_password_reset("tq03@test.com", mail)
    raw_token = _token_in(mail.send_password_reset_email.await_args.args[2])
    session.expire_all()

    # Act
    assert await auth_controller.reset_password(raw_token, "newpass456")

    # Assert
    assert (await auth_controller.login("tq03@test.com", "newpass456")).user.id == str(user.id)
    with pytest.raises(InvalidCredentialsError):
        await auth_controller.login("tq03@test.com", "oldpass123")
    assert await _reread(session, PasswordResetToken, user.id) == []


async def test_a_reset_token_works_once(auth_controller: AuthController, session: AsyncSession, create_user):
    """A used token is refused, and the password it set stays."""
    # Prepare
    await create_user(username="once", email="once@test.com", password="oldpass123")
    mail = _mail()
    await auth_controller.request_password_reset("once@test.com", mail)
    raw_token = _token_in(mail.send_password_reset_email.await_args.args[2])
    await auth_controller.reset_password(raw_token, "newpass456")
    session.expire_all()

    # Act / Assert
    with pytest.raises(InvalidOrExpiredTokenError):
        await auth_controller.reset_password(raw_token, "thirdpass789")
    assert (await auth_controller.login("once@test.com", "newpass456")).user.username == "once"


async def test_an_expired_reset_token_is_refused(auth_controller: AuthController, session: AsyncSession, create_user):
    """Past ``expires_at`` the link is dead, on both dialects."""
    # Prepare
    user = await create_user(username="late", email="late@test.com", password="oldpass123")
    mail = _mail()
    await auth_controller.request_password_reset("late@test.com", mail)
    raw_token = _token_in(mail.send_password_reset_email.await_args.args[2])
    await session.exec(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await session.commit()
    session.expire_all()

    # Act / Assert
    with pytest.raises(InvalidOrExpiredTokenError):
        await auth_controller.reset_password(raw_token, "newpass456")
    assert (await auth_controller.login("late@test.com", "oldpass123")).user.username == "late"


async def test_the_reset_token_is_stored_as_its_sha256_digest(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """A database read (a dump, a backup) must not yield a usable reset link (PD-15, SEC F06)."""
    # Prepare
    user = await create_user(username="digest", email="digest@test.com")
    mail = _mail()

    # Act
    await auth_controller.request_password_reset("digest@test.com", mail)

    # Assert
    raw_token = _token_in(mail.send_password_reset_email.await_args.args[2])
    [stored] = await _reread(session, PasswordResetToken, user.id)
    assert re.fullmatch(r"[0-9a-f]{64}", stored.token)
    assert stored.token == hashlib.sha256(raw_token.encode()).hexdigest()
    assert raw_token not in stored.token


async def test_the_stored_digest_itself_does_not_reset(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """Whoever reads the column holds the digest, which is not the link's token."""
    # Prepare
    user = await create_user(username="reader", email="reader@test.com", password="oldpass123")
    await auth_controller.request_password_reset("reader@test.com", _mail())
    [stored] = await _reread(session, PasswordResetToken, user.id)

    # Act / Assert
    with pytest.raises(InvalidOrExpiredTokenError):
        await auth_controller.reset_password(stored.token, "newpass456")


async def test_requesting_a_reset_purges_expired_tokens(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """Expired links of anyone are deleted, so the table stays bounded."""
    # Prepare — another account's long-expired link
    other = await create_user(username="other", email="other@test.com")
    session.add(PasswordResetToken(user_id=other.id, token="0" * 64, expires_at=datetime.now(UTC) - timedelta(days=2)))
    await session.commit()
    await create_user(username="asker", email="asker@test.com")

    # Act
    await auth_controller.request_password_reset("asker@test.com", _mail())

    # Assert
    assert await _reread(session, PasswordResetToken, other.id) == []


async def test_email_verification_round_trip(auth_controller: AuthController, session: AsyncSession, create_user):
    """send → verify sets ``email_verified`` (part of the admin gate). Crashed on SQLite too."""
    # Prepare
    user = await create_user(username="tq03b", email="tq03b@test.com")
    user_id = user.id
    mail = _mail()
    await auth_controller.send_verification_email(user, mail)
    raw_token = _token_in(mail.send_verification_email.await_args.args[2])
    [stored_token] = await _reread(session, EmailVerificationToken, user_id)
    stored_digest = stored_token.token

    # Act
    assert await auth_controller.verify_email(raw_token)

    # Assert
    assert stored_digest == hashlib.sha256(raw_token.encode()).hexdigest()
    session.expire_all()
    assert (await session.exec(select(User).where(User.id == user_id))).one().email_verified is True
    assert await _reread(session, EmailVerificationToken, user_id) == []
    with pytest.raises(InvalidOrExpiredTokenError):
        await auth_controller.verify_email(raw_token)


async def test_an_expired_verification_token_is_refused(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """And the account stays unverified."""
    # Prepare
    user = await create_user(username="lateverify", email="lateverify@test.com")
    user_id = user.id
    mail = _mail()
    await auth_controller.send_verification_email(user, mail)
    raw_token = _token_in(mail.send_verification_email.await_args.args[2])
    await session.exec(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user_id)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await session.commit()
    session.expire_all()

    # Act / Assert
    with pytest.raises(InvalidOrExpiredTokenError):
        await auth_controller.verify_email(raw_token)
    assert (await session.exec(select(User).where(User.id == user_id))).one().email_verified is False


async def test_resend_verification_sends_a_new_link(
    auth_controller: AuthController, session: AsyncSession, create_user
):
    """Resend replaces the earlier link: the old one stops working, the new one verifies."""
    # Prepare
    user = await create_user(username="resend", email="resend@test.com")
    mail = _mail()
    await auth_controller.send_verification_email(user, mail)
    first = _token_in(mail.send_verification_email.await_args.args[2])

    # Act
    await auth_controller.resend_verification("resend@test.com", mail)
    second = _token_in(mail.send_verification_email.await_args.args[2])

    # Assert
    session.expire_all()
    with pytest.raises(InvalidOrExpiredTokenError):
        await auth_controller.verify_email(first)
    assert await auth_controller.verify_email(second)
