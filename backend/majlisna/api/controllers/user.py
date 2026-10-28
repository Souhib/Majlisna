from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.shared import (
    async_get_password_hash,
    async_verify_password,
)
from majlisna.api.models.challenge import UserChallenge
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.error import UserAlreadyExistsError, UsernameAlreadyTakenError, UserNotFoundError
from majlisna.api.models.friendship import Friendship
from majlisna.api.models.notebook import NotebookEntry
from majlisna.api.models.relationship import RoomUserLink, UserGameLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.stats import UserAchievement, UserStats
from majlisna.api.models.table import Activity, Event, Game, Room, User
from majlisna.api.models.token import EmailVerificationToken, PasswordResetToken
from majlisna.api.models.user import UserCreate, UserUpdate
from majlisna.api.schemas.error import InvalidCredentialsError


async def username_is_taken(session: AsyncSession, username: str, *, exclude_user_id: UUID | None = None) -> bool:
    """Whether another account already uses ``username``, ignoring case.

    ``user.username`` is indexed but NOT unique, and with no migrations a unique
    (functional) index cannot be added to the existing table — so registration and
    renames ask here first. Two concurrent requests for the same new name can still
    both pass the check (see backend/CLAUDE.md, "Usernames are unique, by check").

    ``lower()`` folds ASCII on SQLite and full Unicode on PostgreSQL; Arabic has no
    case, so the difference only touches accented Latin letters in dev.
    """
    statement = select(User.id).where(func.lower(User.username) == username.lower())
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return (await session.exec(statement.limit(1))).first() is not None


class UserController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self, user_create: UserCreate) -> User:
        """
        Create a new user in the database and return the created user.

        Only the safe, client-editable fields are copied — security-sensitive
        columns always get their server-side defaults (no mass assignment).

        :param user_create: The body of the user we have to create.
        :return: The created user.
        """
        if await username_is_taken(self.session, user_create.username):
            raise UsernameAlreadyTakenError(username=user_create.username)
        try:
            # Always hash the password — storing it in clear leaves plaintext
            # credentials in the DB and produces accounts that can never log in.
            new_user = User(
                username=user_create.username,
                email_address=user_create.email_address,
                password=await async_get_password_hash(user_create.password),
                country=user_create.country,
                bio=user_create.bio,
            )
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)
            return new_user
        except IntegrityError:
            await self.session.rollback()
            raise UserAlreadyExistsError(email_address=user_create.email_address) from None

    async def get_users(self) -> Sequence[User]:
        """
        Get all users from the database.
        :return: A list of all users in the database.
        """
        return (await self.session.exec(select(User))).all()

    async def get_user_by_id(self, user_id: UUID) -> User:
        """
        Get a user from the database by id. If the user does not exist, raise a NoResultFound exception.
        :param user_id: The id of the user to get.
        :return: The user with the given id.
        """
        try:
            return (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def update_user_by_id(self, user_id: UUID, user_update: UserUpdate) -> User:
        """
        Update a user in the database by id. If the user does not exist it raises an NoResultFound exception.
        :param user_id: The id of the user to update.
        :param user_update: The parameters we want to update.
        :return: The updated user.
        :raises UsernameAlreadyTakenError: the new username belongs to another account (any case).
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
            db_user_data = user_update.model_dump(exclude_unset=True)
            new_username = db_user_data.get("username")
            # Renaming to another account's name (any case) is refused; changing only
            # the case of one's own name is not a collision.
            if new_username and await username_is_taken(self.session, new_username, exclude_user_id=user_id):
                raise UsernameAlreadyTakenError(username=new_username)
            db_user.sqlmodel_update(db_user_data)
            self.session.add(db_user)
            await self.session.commit()
            await self.session.refresh(db_user)
            return db_user
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def _purge_user_references(self, user_id: UUID) -> None:
        """Remove or anonymize every row referencing this user so the user row can be deleted.

        No FK in the schema declares an ON DELETE action, so deleting a user with any
        related data (stats, achievements, owned rooms, chat, friendships, …) would
        otherwise raise a foreign-key violation. This does the cleanup explicitly:
        child rows are deleted, nullable "actor" references are anonymized, and owned
        rooms are orphaned (owner set to NULL) and deactivated.
        """
        # Orphan + deactivate rooms this user owns (owner_id is nullable).
        for room in (await self.session.exec(select(Room).where(Room.owner_id == user_id))).all():
            room.owner_id = None
            room.type = RoomType.INACTIVE
            self.session.add(room)

        # Delete rows that belong to the user.
        for statement in (
            select(UserStats).where(UserStats.user_id == user_id),
            select(UserAchievement).where(UserAchievement.user_id == user_id),
            select(UserChallenge).where(UserChallenge.user_id == user_id),
            select(ChatMessage).where(ChatMessage.user_id == user_id),
            select(NotebookEntry).where(NotebookEntry.user_id == user_id),
            select(RoomUserLink).where(RoomUserLink.user_id == user_id),
            select(UserGameLink).where(UserGameLink.user_id == user_id),
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id),
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id),
            select(Friendship).where(or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id)),  # ty: ignore[invalid-argument-type]
        ):
            for row in (await self.session.exec(statement)).all():
                await self.session.delete(row)

        # Keep these rows, drop the (nullable) reference to the user.
        for game in (await self.session.exec(select(Game).where(Game.user_id == user_id))).all():
            game.user_id = None
            self.session.add(game)
        for event in (await self.session.exec(select(Event).where(Event.user_id == user_id))).all():
            event.user_id = None
            self.session.add(event)
        for activity in (await self.session.exec(select(Activity).where(Activity.user_id == user_id))).all():
            activity.user_id = None
            self.session.add(activity)

    async def delete_user(self, user_id: UUID) -> None:
        """Delete a user by id, cleaning up all rows that reference them first."""
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
        await self._purge_user_references(user_id)
        await self.session.flush()  # apply the cleanup before removing the user row
        await self.session.delete(db_user)
        await self.session.commit()

    async def delete_user_account(self, user_id: UUID, password: str) -> None:
        """Delete a user account after password confirmation, cleaning up all references."""
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

        if not await async_verify_password(password, db_user.password):
            raise InvalidCredentialsError()

        await self._purge_user_references(user_id)
        await self.session.flush()  # apply the cleanup before removing the user row
        await self.session.delete(db_user)
        await self.session.commit()

    async def update_user_password(self, user_id: UUID, current_password: str, new_password: str) -> User:
        """
        Update a user's password after verifying their current one.

        :param user_id: The id of the user to update.
        :param current_password: The user's current password (must match).
        :param new_password: The new password to set.
        :return: The updated user.
        :raises InvalidCredentialsError: If the current password is wrong.
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

        # Require the current password so a hijacked session can't silently
        # change it (consistent with account deletion, which also re-checks).
        if not await async_verify_password(current_password, db_user.password):
            raise InvalidCredentialsError()

        db_user.password = await async_get_password_hash(new_password)
        self.session.add(db_user)
        await self.session.commit()
        await self.session.refresh(db_user)
        return db_user
