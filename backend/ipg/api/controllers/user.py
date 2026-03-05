from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.shared import get_password_hash
from ipg.api.models.error import UserAlreadyExistsError, UserNotFoundError
from ipg.api.models.table import User
from ipg.api.models.user import UserCreate, UserUpdate


class UserController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self, user_create: UserCreate) -> User:
        """
        Create a new user in the database and return the created user.

        :param user_create: The body of the user we have to create.
        :return: The created user.
        """
        try:
            new_user = User(**user_create.model_dump())
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)
            return new_user
        except IntegrityError:
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
            return (
                await self.session.exec(
                    select(User).where(User.id == user_id).options(selectinload(User.rooms), selectinload(User.games))
                )
            ).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def update_user_by_id(self, user_id: UUID, user_update: UserUpdate) -> User:
        """
        Update a user in the database by id. If the user does not exist it raises an NoResultFound exception.
        :param user_id: The id of the user to update.
        :param user_update: The parameters we want to update.
        :return: The updated user.
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
            db_user_data = user_update.model_dump(exclude_unset=True)
            db_user.sqlmodel_update(db_user_data)
            self.session.add(db_user)
            await self.session.commit()
            await self.session.refresh(db_user)
            return db_user
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def delete_user(self, user_id: UUID) -> None:
        """
        Delete a user from the database by id. If the user does not exist it raises an NoResultFound exception.
        :param user_id: The id of the user to delete.
        :return: None
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
            await self.session.delete(db_user)
            await self.session.commit()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def update_user_password(self, user_id: UUID, password: str) -> User:
        """
        Update the password of a user in the database by id. If the user does not exist it raises an NoResultFound exception.
        :param user_id: The id of the user to update.
        :param password: The new password of the user.
        :return: The updated user.
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
            db_user.password = get_password_hash(password)
            self.session.add(db_user)
            await self.session.commit()
            await self.session.refresh(db_user)
            return db_user
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
