from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.shared import get_password_hash, verify_password
from majlisna.api.controllers.user import UserController
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.notebook import NotebookEntry, NotebookGameType
from majlisna.api.models.room import RoomType
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Room, User
from majlisna.api.models.user import UserCreate, UserUpdate
from majlisna.api.schemas.error import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UsernameAlreadyTakenError,
    UserNotFoundError,
)


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
    # Password must be hashed at rest, never stored in clear.
    assert user.password != "password123"
    assert verify_password("password123", user.password) is True
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
    assert verify_password("password123", found_user.password) is True
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
    user_update = UserUpdate(username="after")

    # Act
    updated_user = await user_controller.update_user_by_id(created_user.id, user_update)

    # Assert
    assert updated_user.id == created_user.id
    assert updated_user.username == "after"
    assert updated_user.email_address == "update@test.com"
    assert verify_password("password123", updated_user.password) is True
    assert updated_user.country is None


async def test_update_user_rejects_another_accounts_username_in_any_case(
    user_controller: UserController, session: AsyncSession, create_user
):
    """A rename onto someone else's name (any case) is a named 409 and changes nothing."""
    # Arrange
    await create_user(username="Maryam", email="maryam@test.com")
    bilal = await create_user(username="bilal", email="bilal@test.com")

    # Act & Assert
    with pytest.raises(UsernameAlreadyTakenError):
        await user_controller.update_user_by_id(bilal.id, UserUpdate(username="maryam"))
    await session.refresh(bilal)
    assert bilal.username == "bilal"


async def test_update_user_may_recase_their_own_username(
    user_controller: UserController, session: AsyncSession, create_user
):
    """Changing only the case of one's own name is not a collision with oneself."""
    # Arrange
    yusuf = await create_user(username="yusuf", email="yusuf@test.com")

    # Act
    updated = await user_controller.update_user_by_id(yusuf.id, UserUpdate(username="Yusuf"))

    # Assert
    assert updated.username == "Yusuf"
    fetched = (await session.exec(select(User).where(User.id == yusuf.id))).one()
    assert fetched.username == "Yusuf"


async def test_create_user_rejects_a_taken_username(
    user_controller: UserController, session: AsyncSession, create_user
):
    """The internal create path applies the same rule as registration."""
    # Arrange
    await create_user(username="Admin", email="admin@test.com")

    # Act & Assert
    with pytest.raises(UsernameAlreadyTakenError):
        await user_controller.create_user(
            UserCreate(username="admin", email_address="other@test.com", password="pw123456")
        )
    rows = (await session.exec(select(User).where(User.email_address == "other@test.com"))).all()
    assert rows == []


@pytest.mark.parametrize("username", ["admin ", "ad min", "a<b>c", "me@home"])
def test_user_update_refuses_the_shapes_registration_refuses(username: str):
    """A rename obeys registration's shape rule, so "admin " cannot slip past the taken check."""
    # Act & Assert
    with pytest.raises(ValidationError):
        UserUpdate(username=username)


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
    user_update = UserUpdate(username="changed")

    # Act
    updated_user = await user_controller.update_user_by_id(created_user.id, user_update)

    # Assert
    assert updated_user.id == created_user.id
    assert updated_user.username == "changed"
    assert updated_user.email_address == "partial@test.com"
    assert verify_password("password123", updated_user.password) is True
    assert updated_user.country is None


async def test_update_user_not_found(user_controller: UserController):
    """Updating a user with a non-existent ID raises UserNotFoundError."""
    # Arrange
    non_existent_id = uuid4()
    user_update = UserUpdate(username="nobody")

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
    updated_user = await user_controller.update_user_password(created_user.id, "oldpassword123", "newpassword456")

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
        await user_controller.update_user_password(non_existent_id, "oldpassword123", "newpassword456")


async def test_delete_user_account_success(user_controller: UserController, session: AsyncSession, create_user):
    """Deleting a user account with correct password removes the user."""
    # Prepare
    user = await create_user(username="delaccount", email="delaccount@test.com", password="mypassword")
    user.password = get_password_hash("mypassword")
    session.add(user)
    await session.commit()

    # Act
    await user_controller.delete_user_account(user.id, "mypassword")

    # Assert — user is deleted
    deleted_user = (await session.exec(select(User).where(User.id == user.id))).first()
    assert deleted_user is None


async def test_delete_user_account_with_related_data(
    user_controller: UserController, session: AsyncSession, create_user, create_room, game_controller
):
    """Deleting an account that owns a room, has stats and kept words succeeds (no FK violation)."""
    # Prepare — a user who owns a room (via create_room), has a stats row, and has
    # kept words from a finished game in their notebook
    user = await create_user(username="richuser", email="rich@test.com", password="mypassword")
    user.password = get_password_hash("mypassword")
    session.add(user)
    await session.commit()
    room = await create_room(owner=user)
    session.add(UserStats(user_id=user.id))
    game = await game_controller.create_game(GameCreate(room_id=room.id, type=GameType.UNDERCOVER, number_of_players=1))
    game.game_status = GameStatus.FINISHED
    session.add(game)
    session.add(
        NotebookEntry(user_id=user.id, term="Sabr", game_type=NotebookGameType.UNDERCOVER, source_game_id=game.id)
    )
    session.add(NotebookEntry(user_id=user.id, term="Uhud", game_type=NotebookGameType.CODENAMES))
    await session.commit()

    # Act
    await user_controller.delete_user_account(user.id, "mypassword")

    # Assert — the user is gone; the owned room is orphaned + deactivated, not deleted
    assert (await session.exec(select(User).where(User.id == user.id))).first() is None
    refreshed_room = (await session.exec(select(Room).where(Room.id == room.id))).first()
    assert refreshed_room is not None
    assert refreshed_room.owner_id is None
    assert refreshed_room.type == RoomType.INACTIVE
    assert (await session.exec(select(UserStats).where(UserStats.user_id == user.id))).first() is None
    assert (await session.exec(select(NotebookEntry).where(NotebookEntry.user_id == user.id))).all() == []


async def test_delete_user_account_wrong_password(user_controller: UserController, session: AsyncSession, create_user):
    """Deleting a user account with wrong password raises InvalidCredentialsError."""
    # Prepare
    user = await create_user(username="wrongpw", email="wrongpw@test.com", password="correctpassword")
    user.password = get_password_hash("correctpassword")
    session.add(user)
    await session.commit()

    # Act & Assert
    with pytest.raises(InvalidCredentialsError):
        await user_controller.delete_user_account(user.id, "wrongpassword")


async def test_delete_user_account_not_found(user_controller: UserController):
    """Deleting a non-existent user account raises UserNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(UserNotFoundError):
        await user_controller.delete_user_account(non_existent_id, "anypassword")


async def test_update_user_password_verifiable(user_controller: UserController):
    """Updated password can be verified; the current password is required."""
    # Prepare
    user_create = UserCreate(
        username="verifiable", email_address="verify@test.com", password="oldpass123", country=None
    )
    user = await user_controller.create_user(user_create)

    # Act
    updated = await user_controller.update_user_password(user.id, "oldpass123", "newsecurepass")

    # Assert — the new password is verifiable
    assert verify_password("newsecurepass", updated.password) is True
    assert verify_password("old", updated.password) is False


async def test_update_user_password_wrong_current_rejected(user_controller: UserController):
    """Changing the password with the wrong current password raises InvalidCredentialsError."""
    # Prepare
    user_create = UserCreate(
        username="wrongcur", email_address="wrongcur@test.com", password="realpass123", country=None
    )
    user = await user_controller.create_user(user_create)

    # Act & Assert
    with pytest.raises(InvalidCredentialsError):
        await user_controller.update_user_password(user.id, "notmypassword", "newpass")
