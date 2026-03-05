from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt
from sqlalchemy.exc import IntegrityError

from ipg.api.controllers.auth import AuthController
from ipg.api.controllers.shared import get_password_hash
from ipg.api.models.user import UserCreate
from ipg.api.schemas.auth import LoginResult, TokenPairResponse, TokenPayload
from ipg.api.schemas.error import InvalidCredentialsError, InvalidTokenError, TokenExpiredError
from ipg.settings import Settings


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


async def test_register_duplicate_email(auth_controller: AuthController):
    """Registering two users with the same email raises IntegrityError."""
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
    with pytest.raises(IntegrityError):
        await auth_controller.register(user_create_2)


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
