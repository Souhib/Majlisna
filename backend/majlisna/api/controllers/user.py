import asyncio
from collections.abc import AsyncGenerator, MutableMapping, Sequence
from contextlib import asynccontextmanager, nullcontext
from uuid import UUID
from weakref import WeakValueDictionary

from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import AUTH_PROVIDER_EMAIL, USERNAME_LOCK_PREFIX
from majlisna.api.controllers.disconnect import _handle_permanent_disconnect
from majlisna.api.controllers.shared import (
    async_get_password_hash,
    async_verify_password,
)
from majlisna.api.models.auth_session import AuthSession, revoke_user_sessions
from majlisna.api.models.challenge import UserChallenge
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.daily_word import DailyWordPlay
from majlisna.api.models.error import UserAlreadyExistsError, UsernameAlreadyTakenError, UserNotFoundError
from majlisna.api.models.friendship import Friendship
from majlisna.api.models.notebook import NotebookEntry
from majlisna.api.models.relationship import RoomUserLink, UserGameLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.room_invite import RoomInvite
from majlisna.api.models.stats import UserAchievement, UserStats
from majlisna.api.models.table import Activity, Event, Game, Room, User
from majlisna.api.models.token import EmailVerificationToken, PasswordResetToken
from majlisna.api.models.user import UserCreate, UserUpdate
from majlisna.api.schemas.error import (
    CurrentPasswordRequiredError,
    GoogleAccountMismatchError,
    GoogleConfirmationRequiredError,
    InvalidCredentialsError,
)
from majlisna.api.schemas.user import DepartedRoom
from majlisna.api.services.social_auth import SocialAuthService

# Weak-valued for the reason `game_lock._fallback_locks` is: the `async with` is the
# only strong reference, so an entry lives exactly as long as a claim holds or awaits it.
_fallback_username_locks: MutableMapping[str, asyncio.Lock] = WeakValueDictionary()


@asynccontextmanager
async def username_claim_lock(session: AsyncSession, username: str) -> AsyncGenerator[None, None]:
    """Serialise every claim of one username, in any case, until the claimer commits.

    ``username_is_taken`` is a check-then-insert with no constraint behind it, so two
    concurrent registrations (or renames) to the same new name could both pass it and
    both commit. Holding this lock across the check AND the insert's commit closes that:
    the second claimer waits, then its check sees the first one's committed row.

    - PostgreSQL: ``pg_advisory_xact_lock(hashtext('username:' || lower(name)))`` —
      blocking, TRANSACTION-scoped, so it is released by the caller's commit or
      rollback (the request's session closing rolls back on an error) and survives
      PgBouncer's transaction pooling. Never take the session-level variant: it leaks
      when the pool recycles a connection. The hash is 32 bits, so two names may share
      a key; they merely wait for each other.
    - SQLite (dev, tests): an in-process ``asyncio.Lock`` keyed on ``name.lower()``,
      like ``get_game_lock``. Python's full Unicode fold is at least as coarse as
      SQLite's ASCII ``lower()``, so names the check confuses always share a lock.

    The caller must commit inside the block — one commit for the whole claim — and,
    for the fallback, the lock is released when the block exits.
    """
    dialect = session.bind.dialect.name if session.bind else ""
    if dialect == "postgresql":
        # `execute`, not `exec`: SQLModel deprecates it, but `exec` is typed for
        # Select statements only and cannot carry raw SQL with bound parameters.
        await session.execute(  # ty: ignore[deprecated]
            text("SELECT pg_advisory_xact_lock(hashtext(CAST(:prefix AS text) || lower(CAST(:username AS text))))"),
            {"prefix": USERNAME_LOCK_PREFIX, "username": username},
        )
        yield  # released by the caller's commit/rollback, not here
        return

    # The local `lock` keeps the weak entry alive; no await between lookup and insert.
    key = username.lower()
    lock = _fallback_username_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _fallback_username_locks[key] = lock
    async with lock:
        yield


async def username_is_taken(session: AsyncSession, username: str, *, exclude_user_id: UUID | None = None) -> bool:
    """Whether another account already uses ``username``, ignoring case.

    ``user.username`` is indexed but NOT unique in the model; the unique functional
    index on ``lower(username)`` exists on PostgreSQL only (the baseline migration), as
    a backstop — so registration, renames and Google sign-up ask here first, inside
    ``username_claim_lock``, which is what keeps two concurrent claims of one new name
    from both passing.

    Both sides go through the database's ``lower()`` (ASCII on SQLite, full Unicode
    on PostgreSQL; Arabic has no case), the same fold the PostgreSQL lock key uses.
    """
    statement = select(User.id).where(func.lower(User.username) == func.lower(username))
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return (await session.exec(statement.limit(1))).first() is not None


def has_own_password(user: User) -> bool:
    """Whether the stored password is one the account's owner chose: ``auth_provider`` email.

    A Google-only account (``auth_provider`` google) holds a random sentinel nobody ever
    saw, and the login refuses it. There is no "has a password" column, and none is needed:
    ``auth_provider`` already is that flag — ``AuthController.login`` reads it so — and
    ``set_own_password`` moves it to email. An email account that later used "Continue
    with Google" keeps email and gains a ``google_sub``: both doors open it.
    """
    return user.auth_provider == AUTH_PROVIDER_EMAIL


async def set_own_password(user: User, new_password: str) -> None:
    """Store ``new_password`` (hashed) as the account's own, so it opens the account at login.

    A Google-only account becomes ``auth_provider`` email with its ``google_sub`` kept —
    the state of an email account linked to Google: its password and Google sign-in both
    open it. Used by the change (confirmed with Google for such an account) and by the reset
    (the link reached the address Google verified). Not committed: the caller commits, with
    its session revocation.

    :raises PasswordTooLongError: over bcrypt's 72 bytes.
    """
    user.password = await async_get_password_hash(new_password)
    user.auth_provider = AUTH_PROVIDER_EMAIL


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
        # The name is claimed under its lock until the insert commits (see
        # `username_claim_lock`): one check, one insert, one commit.
        async with username_claim_lock(self.session, user_create.username):
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
            except IntegrityError:
                await self.session.rollback()
                raise UserAlreadyExistsError(email_address=user_create.email_address) from None
        await self.session.refresh(new_user)
        return new_user

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
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
        db_user_data = user_update.model_dump(exclude_unset=True)
        new_username = db_user_data.get("username")
        # A rename claims the new name like a registration does, under its lock until
        # the commit; an update that leaves the name alone takes no lock.
        async with username_claim_lock(self.session, new_username) if new_username else nullcontext():
            # Renaming to another account's name (any case) is refused; changing only
            # the case of one's own name is not a collision.
            if new_username and await username_is_taken(self.session, new_username, exclude_user_id=user_id):
                raise UsernameAlreadyTakenError(username=new_username)
            db_user.sqlmodel_update(db_user_data)
            self.session.add(db_user)
            await self.session.commit()
        await self.session.refresh(db_user)
        return db_user

    async def _leave_every_room(self, user_id: UUID) -> list[DepartedRoom]:
        """Play the ordinary departure for every seat of the user, before any purge (SEC F05).

        The purge used to delete the ``RoomUserLink`` rows directly, so the leave flow
        never ran: the deleted player stayed alive in ``live_state`` and in the
        description and vote order (an untimed round waited on them for ever), and a
        host's deletion orphaned the room under a game still IN_PROGRESS.
        ``_handle_permanent_disconnect`` — the leave, kick and sweep path — eliminates or
        repairs, transfers ownership (to a player first), deactivates an empty room and
        marks the leaver (``mark_player_left``: neither a win nor a loss, owner rule (b)).

        Each call takes that room's game lock and commits, which releases it: nothing is
        held once this returns, so the purge that follows runs outside every game lock.
        Each room's active game is read BEFORE its departure (which can end the game and
        clear ``Room.active_game_id``), for the route's ``notify_member_removed``.
        """
        links = (await self.session.exec(select(RoomUserLink).where(RoomUserLink.user_id == user_id))).all()
        seats = [(link, link.room_id) for link in links]
        departed: list[DepartedRoom] = []
        for link, room_id in seats:
            game_id = (
                (await self.session.exec(select(Room.active_game_id).where(Room.id == room_id))).first()
                if room_id
                else None
            )
            await _handle_permanent_disconnect(self.session, link)
            if room_id:
                departed.append(DepartedRoom(room_id=room_id, game_id=game_id))
        return departed

    async def _purge_user_references(self, user_id: UUID) -> None:
        """Remove or anonymize every row referencing this user so the user row can be deleted.

        No FK in the schema declares an ON DELETE action, so deleting a user with any
        related data (stats, achievements, owned rooms, chat, friendships, …) would
        otherwise raise a foreign-key violation. This does the cleanup explicitly:
        child rows are deleted, nullable "actor" references are anonymized, and owned
        rooms are orphaned (owner set to NULL) and deactivated.

        The account deletions run ``_leave_every_room`` first, so the seats are gone by
        the time this runs; the ``RoomUserLink`` delete below is a backstop for a seat
        taken in between, and the scripts (``purge_seed_data``) call this alone.
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
            select(DailyWordPlay).where(DailyWordPlay.user_id == user_id),
            select(RoomUserLink).where(RoomUserLink.user_id == user_id),
            select(UserGameLink).where(UserGameLink.user_id == user_id),
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id),
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id),
            select(Friendship).where(or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id)),  # ty: ignore[invalid-argument-type]
            select(AuthSession).where(AuthSession.user_id == user_id),
            # The bans OF this user go; the bans BY them stay (banned_by nulled below).
            select(RoomBan).where(RoomBan.user_id == user_id),
            # The room invites the user sent or received.
            select(RoomInvite).where(or_(RoomInvite.inviter_id == user_id, RoomInvite.invitee_id == user_id)),  # ty: ignore[invalid-argument-type]
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
        for ban in (await self.session.exec(select(RoomBan).where(RoomBan.banned_by == user_id))).all():
            ban.banned_by = None
            self.session.add(ban)

    async def delete_user(self, user_id: UUID) -> list[DepartedRoom]:
        """Delete a user by id (internal: no confirmation, no route), leaving every room first.

        :return: the rooms the user left (see ``_leave_every_room``).
        """
        db_user = await self.get_user_by_id(user_id)
        return await self._delete_account(db_user)

    async def delete_user_account(
        self,
        user_id: UUID,
        password: str | None = None,
        *,
        google_access_token: str | None = None,
        social_auth_service: SocialAuthService | None = None,
    ) -> list[DepartedRoom]:
        """Delete the caller's account once its owner has confirmed (SEC F05, F14).

        The confirmation comes first, so a refused one plays no departure. Then the
        account leaves every room through the ordinary departure, and only then are its
        rows purged and the user deleted.

        :param password: the password confirmation (an account with a password).
        :param google_access_token: a fresh Google access token instead, verified by
            ``social_auth_service`` exactly like a sign-in (the audience check), whose
            ``sub`` must be the account's ``google_sub``. A Google-only account's password
            is a random value its owner never saw.
        :return: the rooms the account left, for the route to detach the sockets and
            notify each room (and its game).
        :raises InvalidCredentialsError: a wrong password, an invalid Google token, or no
            confirmation at all.
        :raises GoogleAccountMismatchError: a valid Google token of another Google account
            (or for an account never linked to Google).
        """
        db_user = await self.get_user_by_id(user_id)
        if google_access_token is not None:
            await self._confirm_with_google(db_user, google_access_token, social_auth_service)
        elif password is None or not await async_verify_password(password, db_user.password):
            raise InvalidCredentialsError()
        return await self._delete_account(db_user)

    @staticmethod
    async def _confirm_with_google(
        db_user: User, google_access_token: str, social_auth_service: SocialAuthService | None
    ) -> None:
        """The Google re-confirmation: the token's verified ``sub`` is the account's ``google_sub``."""
        if social_auth_service is None:
            # Fail closed: a token nothing can verify confirms nothing.
            raise InvalidCredentialsError()
        token_payload = await social_auth_service.verify_google_access_token(google_access_token)
        if db_user.google_sub is None or token_payload.sub != db_user.google_sub:
            raise GoogleAccountMismatchError()

    @staticmethod
    async def _confirm_password_change(
        db_user: User,
        current_password: str | None,
        google_access_token: str | None,
        social_auth_service: SocialAuthService | None,
    ) -> None:
        """A password change is confirmed by the credential the account signs in with.

        - An account with a password (``has_own_password``) confirms with it. Not with
          Google, even when linked: on a shared computer Google's session is often still
          open, and the password is the stronger proof (``CurrentPasswordRequiredError``).
        - A Google-only account confirms with Google, verified like a deletion: its stored
          password is a sentinel the login refuses, so it is never a confirmation
          (``GoogleConfirmationRequiredError``).
        """
        if has_own_password(db_user):
            if google_access_token is not None:
                raise CurrentPasswordRequiredError()
            if current_password is None or not await async_verify_password(current_password, db_user.password):
                raise InvalidCredentialsError()
            return
        if google_access_token is None:
            raise GoogleConfirmationRequiredError()
        await UserController._confirm_with_google(db_user, google_access_token, social_auth_service)

    async def _delete_account(self, db_user: User) -> list[DepartedRoom]:
        """Leave every room (the departure commits per room), then purge and delete in one commit."""
        user_id = db_user.id
        departed = await self._leave_every_room(user_id)
        await self._purge_user_references(user_id)
        await self.session.flush()  # apply the cleanup before removing the user row
        await self.session.delete(db_user)
        await self.session.commit()
        return departed

    async def update_user_password(
        self,
        user_id: UUID,
        current_password: str | None,
        new_password: str,
        *,
        google_access_token: str | None = None,
        social_auth_service: SocialAuthService | None = None,
        keep_session_id: UUID | None = None,
    ) -> User:
        """
        Set the account's password once its owner has confirmed, and sign out every
        OTHER session of the account (SEC F01).

        The confirmation is the account's own credential (``_confirm_password_change``):
        the current password of an account that has one, Google for a Google-only account,
        which thereby gets a password that opens it at login (``set_own_password``).

        :param user_id: The id of the user to update.
        :param current_password: The user's current password (an account with a password).
        :param new_password: The new password to set.
        :param google_access_token: a fresh Google access token instead (a Google-only
            account), verified by ``social_auth_service`` exactly like a deletion's.
        :param keep_session_id: the caller's own session (``request.state.session_id``),
            which stays signed in. None (a legacy token names no session) revokes them all.
        :return: The updated user.
        :raises InvalidCredentialsError: a wrong current password, or an invalid Google token.
        :raises GoogleAccountMismatchError: a valid Google token of another Google account.
        :raises GoogleConfirmationRequiredError: a Google-only account confirming with a password.
        :raises CurrentPasswordRequiredError: an account with a password confirming with Google.
        :raises PasswordTooLongError: the new password is over bcrypt's 72 bytes.
        """
        db_user = await self.get_user_by_id(user_id)

        # Require a confirmation so a hijacked session can't silently change it
        # (consistent with account deletion, which also re-checks).
        await self._confirm_password_change(db_user, current_password, google_access_token, social_auth_service)

        await set_own_password(db_user, new_password)
        self.session.add(db_user)
        # Whoever else held a session (a stolen token included) is signed out with the
        # old password, in the same commit.
        await revoke_user_sessions(self.session, user_id, except_session_id=keep_session_id)
        await self.session.commit()
        await self.session.refresh(db_user)
        return db_user
