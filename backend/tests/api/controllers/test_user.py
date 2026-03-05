from uuid import uuid4

import pytest

from ipg.api.controllers.user import UserController
from ipg.api.models.user import UserCreate, UserUpdate
from ipg.api.schemas.error import UserAlreadyExistsError, UserNotFoundError


async def test_create_user_success(user_controller: UserController):
    """Creating a user with valid data returns a fully populated User object."""
    # Arrange
    user_create = UserCreate(
        username="newuser",
        email_address="new@test.com",
        password="password123",
        country=None,
    )

    # Act
    user = await user_controller.create_user(user_create)

    # Assert
    assert user.id is not None
    assert user.username == "newuser"
    assert user.email_address == "new@test.com"
    assert user.password == "password123"
    assert user.country is None


async def test_create_user_duplicate_email(user_controller: UserController):
    """Creating two users with the same email raises UserAlreadyExistsError."""
    # Arrange
    user_create_1 = UserCreate(
        username="user1",
        email_address="duplicate@test.com",
        password="password123",
        country=None,
    )
    user_create_2 = UserCreate(
        username="user2",
        email_address="duplicate@test.com",
        password="password456",
        country=None,
    )
    await user_controller.create_user(user_create_1)

    # Act & Assert
    with pytest.raises(UserAlreadyExistsError):
        await user_controller.create_user(user_create_2)


async def test_get_users_empty(user_controller: UserController):
    """Getting all users from an empty database returns an empty list."""
    # Arrange
    # (no users created)

    # Act
    users = await user_controller.get_users()

    # Assert
    assert len(users) == 0


async def test_get_users_multiple(user_controller: UserController):
    """Getting all users after creating three returns a list of length 3."""
    # Arrange
    await user_controller.create_user(
        UserCreate(username="user1", email_address="u1@test.com", password="password123", country=None)
    )
    await user_controller.create_user(
        UserCreate(username="user2", email_address="u2@test.com", password="password123", country=None)
    )
    await user_controller.create_user(
        UserCreate(username="user3", email_address="u3@test.com", password="password123", country=None)
    )

    # Act
    users = await user_controller.get_users()

    # Assert
    assert len(users) == 3


async def test_get_user_by_id_success(user_controller: UserController):
    """Getting a user by ID returns the correct user with all fields matching."""
    # Arrange
    user_create = UserCreate(
        username="findme",
        email_address="findme@test.com",
        password="password123",
        country=None,
    )
    created_user = await user_controller.create_user(user_create)

    # Act
    found_user = await user_controller.get_user_by_id(created_user.id)

    # Assert
    assert found_user.id == created_user.id
    assert found_user.username == "findme"
    assert found_user.email_address == "findme@test.com"
    assert found_user.password == "password123"
    assert found_user.country is None


async def test_get_user_by_id_not_found(user_controller: UserController):
    """Getting a user by a non-existent ID raises UserNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(UserNotFoundError):
        await user_controller.get_user_by_id(non_existent_id)


async def test_update_user_success(user_controller: UserController):
    """Updating a user's username changes it while leaving other fields unchanged."""
    # Arrange
    user_create = UserCreate(
        username="before",
        email_address="update@test.com",
        password="password123",
        country=None,
    )
    created_user = await user_controller.create_user(user_create)
    user_update = UserUpdate(username="after", email_address="update@test.com")

    # Act
    updated_user = await user_controller.update_user_by_id(created_user.id, user_update)

    # Assert
    assert updated_user.id == created_user.id
    assert updated_user.username == "after"
    assert updated_user.email_address == "update@test.com"
    assert updated_user.password == "password123"
    assert updated_user.country is None


async def test_update_user_partial(user_controller: UserController):
    """Partially updating a user only changes the specified field, leaving others intact."""
    # Arrange
    user_create = UserCreate(
        username="original",
        email_address="partial@test.com",
        password="password123",
        country=None,
    )
    created_user = await user_controller.create_user(user_create)
    user_update = UserUpdate(username="changed", email_address="partial@test.com")

    # Act
    updated_user = await user_controller.update_user_by_id(created_user.id, user_update)

    # Assert
    assert updated_user.id == created_user.id
    assert updated_user.username == "changed"
    assert updated_user.email_address == "partial@test.com"
    assert updated_user.password == "password123"
    assert updated_user.country is None


async def test_update_user_not_found(user_controller: UserController):
    """Updating a user with a non-existent ID raises UserNotFoundError."""
    # Arrange
    non_existent_id = uuid4()
    user_update = UserUpdate(username="nobody", email_address="nobody@test.com")

    # Act & Assert
    with pytest.raises(UserNotFoundError):
        await user_controller.update_user_by_id(non_existent_id, user_update)


async def test_delete_user_success(user_controller: UserController):
    """Deleting an existing user removes it so that get_user_by_id raises UserNotFoundError."""
    # Arrange
    user_create = UserCreate(
        username="deleteme",
        email_address="delete@test.com",
        password="password123",
        country=None,
    )
    created_user = await user_controller.create_user(user_create)

    # Act
    await user_controller.delete_user(created_user.id)

    # Assert
    with pytest.raises(UserNotFoundError):
        await user_controller.get_user_by_id(created_user.id)


async def test_delete_user_not_found(user_controller: UserController):
    """Deleting a user with a non-existent ID raises UserNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(UserNotFoundError):
        await user_controller.delete_user(non_existent_id)


async def test_update_user_password_success(user_controller: UserController):
    """Updating a user's password stores the new value and differs from the old one."""
    # Arrange
    user_create = UserCreate(
        username="pwuser",
        email_address="pw@test.com",
        password="oldpassword123",
        country=None,
    )
    created_user = await user_controller.create_user(user_create)
    old_password = created_user.password

    # Act
    updated_user = await user_controller.update_user_password(created_user.id, "newpassword456")

    # Assert
    assert updated_user.id == created_user.id
    assert updated_user.username == "pwuser"
    assert updated_user.email_address == "pw@test.com"
    assert updated_user.password != "newpassword456"  # password is hashed, not plaintext
    assert updated_user.password != old_password
    assert updated_user.country is None


async def test_update_user_password_not_found(user_controller: UserController):
    """Updating the password of a non-existent user raises UserNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(UserNotFoundError):
        await user_controller.update_user_password(non_existent_id, "newpassword456")
