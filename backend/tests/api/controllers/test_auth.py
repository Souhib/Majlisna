import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.models.table import User
from majlisna.api.models.user import UserCreate
from majlisna.api.schemas.auth import LoginResult, TokenPairResponse, TokenPayload
from majlisna.api.schemas.error import (
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UsernameAlreadyTakenError,
)
from majlisna.api.schemas.social_auth import SocialTokenPayload
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


async def test_create_token_pair(auth_controller: AuthController, test_settings: Settings):
    """Creating a token pair returns both valid tokens that decode to the same user."""
    # Arrange
    user_id = "user-789"
    email = "pair@test.com"

    # Act
    pair = auth_controller.create_token_pair(user_id, email)

    # Assert
    assert isinstance(pair, TokenPairResponse)
    assert pair.access_token
    assert pair.refresh_token
    assert pair.token_type == "bearer"

    access_payload = jwt.decode(
        pair.access_token,
        test_settings.jwt_secret_key,
        algorithms=[test_settings.jwt_encryption_algorithm],
    )
    refresh_payload = jwt.decode(
        pair.refresh_token,
        test_settings.jwt_secret_key,
        algorithms=[test_settings.jwt_encryption_algorithm],
    )
    assert access_payload["sub"] == "user-789"
    assert access_payload["email"] == "pair@test.com"
    assert refresh_payload["sub"] == "user-789"
    assert refresh_payload["email"] == "pair@test.com"


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
