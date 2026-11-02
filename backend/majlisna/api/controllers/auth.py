import hashlib
import re
import secrets
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from loguru import logger
from pydantic import ValidationError
from sqlalchemy import delete, func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    AUTH_PROVIDER_GOOGLE,
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
    REFRESH_REUSE_GRACE_SECONDS,
    SESSION_ABSOLUTE_LIFETIME_DAYS,
    SOCIAL_USERNAME_SUFFIX_ATTEMPTS,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)
from majlisna.api.controllers.shared import (
    async_get_password_hash,
    async_verify_password,
    get_password_hash,
    verify_password,
)
from majlisna.api.controllers.user import (
    has_own_password,
    set_own_password,
    username_claim_lock,
    username_is_taken,
)
from majlisna.api.models.auth_session import AuthSession, revoke_user_sessions
from majlisna.api.models.table import User
from majlisna.api.models.token import EmailVerificationToken, PasswordResetToken
from majlisna.api.models.user import UserCreate
from majlisna.api.schemas.auth import LoginResult, LoginUserData, TokenPairResponse, TokenPayload
from majlisna.api.schemas.error import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    InvalidTokenError,
    SessionRevokedError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UsernameAlreadyTakenError,
    UserNotFoundError,
)
from majlisna.api.schemas.social_auth import SocialLoginResult, SocialLoginUserData, SocialTokenPayload
from majlisna.api.services.email import EmailService
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.settings import Settings

# JWT `type` claim values, used to keep access and refresh tokens from being
# used interchangeably (a refresh token must not authenticate API calls, and an
# access token must not mint a new token pair at /refresh).
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Precomputed bcrypt hash used only to equalize login response time when the
# email is unknown, so an attacker can't enumerate accounts by timing. Never
# matches any real password.
_DUMMY_PASSWORD_HASH = "$2b$12$crI5y/d5tqE1WJc6OVnBvOpy.Qj7TL6eITLs6R0pNjaB5mAoLRBFq"


def normalize_email(email: str) -> str:
    """The one spelling of an address: trimmed and lowercased (SEC F14).

    Every door that takes an address goes through it: register, login, forgot-password,
    resend-verification and the Google lookup. ``User.email_address`` used to be unique
    only by exact match, so ``Ali@Example.com`` and ``ali@example.com`` registered as two
    accounts of one mailbox. Lowercased with ``str.lower`` (not ``casefold``) because the
    lookup compares with SQL ``lower()``, which does not fold ``ß`` to ``ss``: the two
    sides must agree. New rows are stored normalised; rows registered before keep their
    case and are still found (``get_user_by_email`` lowers the column too).
    """
    return email.strip().lower()


def token_digest(token: str) -> str:
    """The sha256 hex digest a reset or verification token is stored as (PD-15, SEC F06).

    The link carries the token; the database only its digest, so a read of the table (a
    dump, a backup, the DB console) yields nothing a browser can redeem.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def utc_instant(instant: datetime) -> datetime:
    """``instant`` as an aware UTC datetime.

    The token and session columns are ``TIMESTAMP WITH TIME ZONE`` and always written
    aware, but SQLite (dev, tests) reads them back NAIVE: comparing that with
    ``datetime.now(UTC)`` raised ``TypeError`` — every dev reset and verification link
    answered 500 (TQ-03).
    """
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def session_is_live(auth_session: AuthSession, now: datetime) -> bool:
    """Neither revoked nor past its absolute ``expires_at``."""
    return auth_session.revoked_at is None and utc_instant(auth_session.expires_at) > now


def decode_jwt(
    token: str, settings: Settings, expected_type: str | None = None, *, verify_expiry: bool = True
) -> TokenPayload:
    """Decode and validate one of our JWTs (signature always; expiry unless told otherwise).

    :raises InvalidTokenError: malformed, badly signed, of the wrong ``type``, or with
        claims that are not ours.
    :raises TokenExpiredError: past ``exp`` (only when ``verify_expiry``).
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_encryption_algorithm],
            options={"verify_exp": verify_expiry},
        )
        token_payload = TokenPayload(**payload)
    except ExpiredSignatureError as e:
        raise TokenExpiredError() from e
    except (JWTError, ValidationError) as e:
        raise InvalidTokenError() from e

    if expected_type is not None and token_payload.type != expected_type:
        raise InvalidTokenError()
    return token_payload


def refresh_token_subject(token: str | None, settings: Settings) -> str | None:
    """The account a refresh token names, to pick its rate-limit bucket only (FR-3 d).

    Never an authentication: the controller decodes the token again and checks its
    session. The signature IS verified, so a forged ``sub`` per request cannot buy a fresh
    budget each time; anything that does not decode (forged, expired, an access token)
    answers None, and the caller falls back to the client address.
    """
    if not token:
        return None
    try:
        return decode_jwt(token, settings, expected_type=TOKEN_TYPE_REFRESH).sub
    except (InvalidTokenError, TokenExpiredError):
        return None


def _epoch(instant: datetime) -> int:
    """A JWT NumericDate: whole seconds, the same for the same instant every time."""
    return int(utc_instant(instant).timestamp())


def _new_refresh_jti() -> str:
    return secrets.token_hex(16)


def _session_id_of(payload: TokenPayload) -> UUID:
    """The ``sid`` claim as a UUID (one we signed always parses; anything else is invalid)."""
    try:
        return UUID(str(payload.sid))
    except ValueError as e:
        raise InvalidTokenError() from e


class AuthController:
    """Controller for authentication operations."""

    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password.

        Uses passlib bcrypt context from shared module.

        :param plain_password: The plain text password to verify.
        :param hashed_password: The hashed password to verify against.
        :return: True if the password matches, False otherwise.
        """
        return verify_password(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password using the shared password context.

        :param password: The plain text password to hash.
        :return: The hashed password string.
        """
        return get_password_hash(password)

    def _encode(self, payload: dict[str, Any]) -> str:
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_encryption_algorithm)

    def create_access_token(
        self, user_id: str, email: str, *, session_id: UUID | None = None, issued_at: datetime | None = None
    ) -> str:
        """Create a JWT access token (``sub``, ``email``, ``exp``, ``iat``, ``type``, and ``sid``).

        Every token the API hands out names its session (``_session_tokens``). Without
        ``session_id`` this mints the pre-session shape (no ``sid``), which
        ``authenticate_caller`` still accepts until it expires: only tests mint it now.
        """
        now = issued_at or datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": user_id,
            "email": email,
            "exp": _epoch(now + timedelta(minutes=self.settings.access_token_expire_minutes)),
            "iat": _epoch(now),
            "type": TOKEN_TYPE_ACCESS,
        }
        if session_id is not None:
            payload["sid"] = str(session_id)
        return self._encode(payload)

    def create_refresh_token(
        self,
        user_id: str,
        email: str,
        *,
        session_id: UUID | None = None,
        jti: str | None = None,
        issued_at: datetime | None = None,
        not_after: datetime | None = None,
    ) -> str:
        """Create a JWT refresh token (``sid`` and its single-use ``jti`` when given).

        ``exp`` is ``issued_at`` + ``refresh_token_expire_days``, capped at ``not_after``
        (the session's absolute end). The same arguments always encode the same token,
        which is how a raced refresh is answered the current token again
        (``refresh_session``). Without ``session_id`` / ``jti`` this mints the legacy
        shape, which ``/auth/refresh`` upgrades into a session: only tests mint it now.
        """
        now = issued_at or datetime.now(UTC)
        expires = now + timedelta(days=self.settings.refresh_token_expire_days)
        if not_after is not None:
            expires = min(expires, utc_instant(not_after))
        payload: dict[str, Any] = {
            "sub": user_id,
            "email": email,
            "exp": _epoch(expires),
            "iat": _epoch(now),
            "type": TOKEN_TYPE_REFRESH,
        }
        if session_id is not None:
            payload["sid"] = str(session_id)
        if jti is not None:
            payload["jti"] = jti
        return self._encode(payload)

    def decode_token(self, token: str, expected_type: str | None = None) -> TokenPayload:
        """Decode and validate a JWT token (``decode_jwt`` with this controller's settings).

        :param token: The JWT token string to decode.
        :param expected_type: If given ("access" or "refresh"), reject a token
            whose `type` claim does not match. Callers that don't care (e.g.
            unit tests) omit it and no type check is performed.
        :return: TokenPayload with the decoded claims.
        :raises InvalidTokenError: If the token is malformed, invalid, or of the
            wrong type.
        :raises TokenExpiredError: If the token has expired.
        """
        return decode_jwt(token, self.settings, expected_type)

    # ── Sessions (SEC F01) ───────────────────────────────────────

    async def _open_session(self, user: User) -> AuthSession:
        """A new session row for ``user`` (added, not committed: the caller commits once).

        Its ``expires_at`` is the absolute cap (``SESSION_ABSOLUTE_LIFETIME_DAYS``) that no
        refresh moves. Every sign-in adds a row, so it first drops the account's rows past
        their ``expires_at``: no token of theirs can work again (a missing session answers
        ``SessionRevokedError`` like an ended one), and the table stays bounded. Revoked
        rows still inside their lifetime are kept, as the record of who signed out when.
        ``synchronize_session=False`` for the reason ``_purge_expired_tokens`` gives.
        """
        now = datetime.now(UTC)
        await self.session.exec(
            delete(AuthSession)
            .where(col(AuthSession.user_id) == user.id)
            .where(col(AuthSession.expires_at) < now)
            .execution_options(synchronize_session=False)
        )
        auth_session = AuthSession(
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(days=SESSION_ABSOLUTE_LIFETIME_DAYS),
            last_refreshed_at=now,
            current_refresh_jti=_new_refresh_jti(),
        )
        self.session.add(auth_session)
        return auth_session

    def _session_tokens(self, user: User, auth_session: AuthSession) -> TokenPairResponse:
        """The pair for ``auth_session`` as it stands: a fresh access token, and the CURRENT refresh token.

        The refresh token is a pure function of the row (``current_refresh_jti``, issued at
        ``last_refreshed_at``, capped at ``expires_at``), so calling this again before the
        next rotation re-mints the very same string. Built from in-memory values, before the
        caller commits (a session that expires on commit would otherwise reload them).
        """
        user_id = str(user.id)
        return TokenPairResponse(
            access_token=self.create_access_token(user_id, user.email_address, session_id=auth_session.id),
            refresh_token=self.create_refresh_token(
                user_id,
                user.email_address,
                session_id=auth_session.id,
                jti=auth_session.current_refresh_jti,
                issued_at=utc_instant(auth_session.last_refreshed_at),
                not_after=auth_session.expires_at,
            ),
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    async def user_named_by(self, payload: TokenPayload) -> User:
        """The account a token names by BOTH claims: ``id == sub`` and the same address.

        Looked up by primary key: either claim alone is not enough (``email`` survives a
        delete-and-re-register of the address, SEC F09).

        :raises InvalidTokenError: no such account, or the address differs.
        """
        try:
            user_id = UUID(payload.sub)
        except ValueError as e:
            raise InvalidTokenError("User not found for token") from e
        user = (await self.session.exec(select(User).where(User.id == user_id))).first()
        if user is None or normalize_email(user.email_address) != normalize_email(payload.email):
            raise InvalidTokenError("User not found for token")
        return user

    async def _locked_session(self, session_id: UUID) -> AuthSession | None:
        """The session row, locked until the commit (``SELECT … FOR UPDATE``; SQLite has no row locks).

        Two tabs refreshing one token at once must not both rotate: the second would
        overwrite the first's jti, and the first tab's next refresh would read as theft.
        With the lock the second waits, then sees the rotation and takes the grace path.
        ``populate_existing`` so the row read after the wait is the committed one.
        """
        statement = (
            select(AuthSession)
            .where(AuthSession.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.exec(statement)).first()

    async def refresh_session(self, refresh_token: str | None) -> TokenPairResponse:
        """Spend a refresh token: rotate it, answer a raced tab, or catch a stolen copy.

        - ``type`` must be ``refresh``; the session must exist, be unrevoked and before
          ``expires_at`` — else ``SessionRevokedError``.
        - ``jti`` is the current one: rotate (previous := current, current := new,
          ``rotated_at`` := now) and mint a new pair.
        - ``jti`` is the previous one, within ``REFRESH_REUSE_GRACE_SECONDS`` of the
          rotation: two tabs raced. Re-mint the CURRENT refresh token (same jti, same exp)
          and a fresh access token.
        - Any other ``jti``: the token was used before — a copy is being replayed. The
          session is revoked (committed) and the answer is ``SessionRevokedError``.
        - ``expires_at`` never moves.

        A legacy refresh token (no ``sid``/``jti``, minted before sessions existed) carries
        nothing to track, so its digest is: it is upgraded ONCE into a new session that
        records it (``_upgrade_legacy_refresh``). That path dies by itself
        ``refresh_token_expire_days`` after the deploy, when the last legacy token
        expires; remove it then (backend/CLAUDE.md).

        :raises InvalidTokenError: no token, a bad one, or no account matching both claims.
        :raises TokenExpiredError: the refresh token expired.
        :raises SessionRevokedError: the session was signed out, ended, or a reuse was caught.
        """
        if not refresh_token:
            raise InvalidTokenError("No refresh token provided")
        payload = self.decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
        if payload.sid is None or payload.jti is None:
            return await self._upgrade_legacy_refresh(payload, refresh_token)

        auth_session = await self._locked_session(_session_id_of(payload))
        now = datetime.now(UTC)
        if auth_session is None or not session_is_live(auth_session, now):
            raise SessionRevokedError()
        if str(auth_session.user_id) != payload.sub:
            raise InvalidTokenError("Session does not belong to the token's user")
        user = await self.user_named_by(payload)

        if payload.jti == auth_session.current_refresh_jti:
            auth_session.previous_refresh_jti = auth_session.current_refresh_jti
            auth_session.current_refresh_jti = _new_refresh_jti()
            auth_session.rotated_at = now
            auth_session.last_refreshed_at = now
            self.session.add(auth_session)
            tokens = self._session_tokens(user, auth_session)
            await self.session.commit()
            return tokens

        rotated_at = auth_session.rotated_at
        if (
            payload.jti == auth_session.previous_refresh_jti
            and rotated_at is not None
            and now - utc_instant(rotated_at) <= timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS)
        ):
            tokens = self._session_tokens(user, auth_session)
            await self.session.commit()  # nothing to write: ends the transaction, releasing the row lock
            return tokens

        auth_session.revoked_at = now
        self.session.add(auth_session)
        await self.session.commit()
        logger.warning(
            "Refresh token reuse detected; session revoked",
            user_id=payload.sub,
            session_id=str(auth_session.id),
        )
        raise SessionRevokedError()

    async def _upgrade_legacy_refresh(self, payload: TokenPayload, refresh_token: str) -> TokenPairResponse:
        """A pre-session refresh token: upgraded ONCE into a new, tracked session (review R3).

        It used to open a new session on every use, so for ``refresh_token_expire_days`` a
        stolen copy outlived a logout, a reset and reuse detection: it simply upgraded
        again. The session now records the token's digest (``legacy_refresh_digest``,
        unique). Presented again:

        - within ``REFRESH_REUSE_GRACE_SECONDS`` of the upgrade, while that session is
          live: two tabs raced at the deploy — both get that session's current pair;
        - otherwise: a replayed copy. The session it opened is revoked (committed) and
          the answer is ``SessionRevokedError``, as for any reused refresh token.

        Two first presentations racing both insert; the unique digest refuses the second,
        which then takes the grace path on the row the first one committed.
        """
        user = await self.user_named_by(payload)
        digest = token_digest(refresh_token)
        upgraded = await self._session_upgraded_from(digest)
        if upgraded is not None:
            return await self._legacy_token_presented_again(user, upgraded)

        auth_session = await self._open_session(user)
        auth_session.legacy_refresh_digest = digest
        tokens = self._session_tokens(user, auth_session)
        try:
            await self.session.commit()
        except IntegrityError:
            # The rollback expires every instance: the user is read again, not lazy-loaded.
            await self.session.rollback()
            user = await self.user_named_by(payload)
            upgraded = await self._session_upgraded_from(digest)
            if upgraded is None:
                raise
            return await self._legacy_token_presented_again(user, upgraded)
        logger.info("Legacy refresh token upgraded into a session", user_id=str(user.id))
        return tokens

    async def _session_upgraded_from(self, digest: str) -> AuthSession | None:
        """The session a legacy refresh token was upgraded into, locked until the commit."""
        statement = (
            select(AuthSession)
            .where(AuthSession.legacy_refresh_digest == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.exec(statement)).first()

    async def _legacy_token_presented_again(self, user: User, upgraded: AuthSession) -> TokenPairResponse:
        """A legacy token already upgraded: the raced tab's answer, or the replay's revocation."""
        now = datetime.now(UTC)
        if (
            upgraded.user_id == user.id
            and session_is_live(upgraded, now)
            and now - utc_instant(upgraded.created_at) <= timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS)
        ):
            tokens = self._session_tokens(user, upgraded)
            await self.session.commit()  # nothing to write: ends the transaction, releasing the row lock
            return tokens
        if upgraded.revoked_at is None:
            upgraded.revoked_at = now
            self.session.add(upgraded)
        await self.session.commit()
        logger.warning(
            "Legacy refresh token presented again; its session is revoked",
            user_id=str(user.id),
            session_id=str(upgraded.id),
        )
        raise SessionRevokedError()

    def _signed_session_of(self, token: str | None, expected_type: str) -> tuple[UUID, UUID] | None:
        """(session id, user id) a token of ours names, expired or not; None for anything else.

        Logout reads it from the access token or the refresh cookie: a tab whose access
        token just expired still signs its own session out.
        """
        if not token:
            return None
        try:
            payload = decode_jwt(token, self.settings, expected_type, verify_expiry=False)
            if payload.sid is None:
                return None
            return _session_id_of(payload), UUID(payload.sub)
        except (InvalidTokenError, TokenExpiredError, ValueError):
            return None

    async def logout(self, *, access_token: str | None, refresh_token: str | None) -> None:
        """Revoke the caller's session (named by the access token or the refresh cookie).

        Logout used to only clear the cookies, so a copied token kept working for good.
        Nothing presented, or nothing of ours: nothing to revoke (the route clears the
        cookies all the same). A legacy token names no session; it dies at its ``exp``.
        """
        named = {
            pair
            for pair in (
                self._signed_session_of(access_token, TOKEN_TYPE_ACCESS),
                self._signed_session_of(refresh_token, TOKEN_TYPE_REFRESH),
            )
            if pair is not None
        }
        if not named:
            return
        now = datetime.now(UTC)
        for session_id, user_id in named:
            await self.session.exec(
                update(AuthSession)
                # SQL expressions, not Python bools (backend/CLAUDE.md, "ty: ignore discipline").
                .where(col(AuthSession.id) == session_id)
                .where(col(AuthSession.user_id) == user_id)
                .where(col(AuthSession.revoked_at).is_(None))
                .values(revoked_at=now)
            )
        await self.session.commit()

    async def login(self, email: str, password: str) -> LoginResult:
        """Authenticate a user and return tokens with user data.

        :param email: The user's email address.
        :param password: The user's plain text password.
        :return: LoginResult with tokens and user info.
        :raises InvalidCredentialsError: If the email or password is incorrect.
        """
        email = normalize_email(email)
        user = await self.get_user_by_email(email)
        if user is None or not has_own_password(user):
            # A Google-only account's password is a sentinel: never a credential until
            # its owner sets one (`set_own_password`).
            # Run a bcrypt verify against a dummy hash so the response time for
            # an unknown / non-password account matches the wrong-password path,
            # preventing account enumeration by timing.
            await async_verify_password(password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError(email=email)

        if not await async_verify_password(password, user.password):
            raise InvalidCredentialsError(email=email)

        # Checked only after the password is correct, so it can't be used to probe
        # which accounts exist. Off by default (see Settings.require_email_verification).
        if self.settings.require_email_verification and not user.email_verified:
            raise EmailNotVerifiedError()

        auth_session = await self._open_session(user)
        tokens = self._session_tokens(user, auth_session)
        await self.session.commit()
        return LoginResult(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            user=LoginUserData(
                id=str(user.id),
                username=user.username,
                email=user.email_address,
            ),
        )

    async def register(self, user_create: UserCreate) -> User:
        """Register a new user with a hashed password.

        Only the safe, client-editable fields from UserCreate are copied —
        security-sensitive columns (email_verified, auth_provider, google_sub)
        always get their server-side defaults.

        Both identities are checked before anything is written: an address already
        registered is ``UserAlreadyExistsError`` (409), a username another account
        uses in any case is ``UsernameAlreadyTakenError`` (409). The email check
        used to be left to the unique constraint, whose ``IntegrityError`` nothing
        caught — a 500 — and the username was not checked at all, so a second
        "admin" registered without complaint. The constraint still backs the email
        under a race; the username has none, so the check and the insert run under
        ``username_claim_lock`` until the commit — a second registration of the same
        new name waits, then finds it taken.

        :param user_create: The user creation data.
        :return: The newly created User.
        :raises UserAlreadyExistsError: the email address is already registered.
        :raises UsernameAlreadyTakenError: the username is taken (case-insensitively).
        """
        # Stored normalised, and checked against every case of it (SEC F14).
        email = normalize_email(user_create.email_address)
        if await self.get_user_by_email(email) is not None:
            raise UserAlreadyExistsError(email_address=email)

        async with username_claim_lock(self.session, user_create.username):
            if await username_is_taken(self.session, user_create.username):
                raise UsernameAlreadyTakenError(username=user_create.username)

            hashed_password = await async_get_password_hash(user_create.password)
            new_user = User(
                username=user_create.username,
                email_address=email,
                password=hashed_password,
                country=user_create.country,
                bio=user_create.bio,
            )
            self.session.add(new_user)
            try:
                await self.session.commit()
            except IntegrityError:
                # A concurrent registration of the same address won the unique constraint.
                await self.session.rollback()
                raise UserAlreadyExistsError(email_address=email) from None
        await self.session.refresh(new_user)
        return new_user

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by their email address, in any case (SEC F14).

        Compares ``lower(email_address)`` with the normalised address, so a row registered
        before normalisation (mixed case) is still found. Should a mailbox have two rows
        from that time (case variants; WP-21 de-duplicates them before its unique index),
        the one spelled exactly as normalised wins, then the first by spelling — the same
        row every time, never whichever the planner reads first.

        :param email: The email address to search for.
        :return: The User if found, None otherwise.
        """
        normalized = normalize_email(email)
        statement = (
            select(User)
            .where(func.lower(User.email_address) == normalized)
            .order_by((col(User.email_address) == normalized).desc(), col(User.email_address))
            .limit(1)
        )
        return (await self.session.exec(statement)).first()

    async def _purge_password_reset_tokens(self, user_id: UUID | None) -> None:
        """Delete every password-reset token for a user (single-use; keeps the table bounded)."""
        if user_id is None:
            return
        tokens = (
            await self.session.exec(select(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
        ).all()
        for reset_token in tokens:
            await self.session.delete(reset_token)

    async def _purge_email_verification_tokens(self, user_id: UUID | None) -> None:
        """Delete every email-verification token for a user (single-use; keeps the table bounded)."""
        if user_id is None:
            return
        tokens = (
            await self.session.exec(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id))
        ).all()
        for verify_token in tokens:
            await self.session.delete(verify_token)

    async def _purge_expired_tokens(self, model: type[PasswordResetToken] | type[EmailVerificationToken]) -> None:
        """Delete every expired token of ``model``, whoever it belongs to (keeps the table bounded).

        ``synchronize_session=False``: the ORM's in-Python evaluation of ``expires_at < now``
        would compare the NAIVE values SQLite loaded with an aware ``now``.
        """
        await self.session.exec(
            delete(model).where(col(model.expires_at) < datetime.now(UTC)).execution_options(synchronize_session=False)
        )

    async def request_password_reset(self, email: str, email_service: EmailService) -> bool:
        """Generate a password reset token and send email.

        The link carries the token; the table only its sha256 digest (``token_digest``).
        """
        user = await self.get_user_by_email(email)
        if not user:
            # Don't reveal whether user exists — return silently
            logger.debug("Password reset requested for unknown email")
            return True

        # Only one active reset token per user; drops any prior/stale ones.
        await self._purge_expired_tokens(PasswordResetToken)
        await self._purge_password_reset_tokens(user.id)
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
        reset_token = PasswordResetToken(user_id=user.id, token=token_digest(token), expires_at=expires_at)
        self.session.add(reset_token)
        await self.session.commit()

        reset_url = f"{self.settings.frontend_url}/auth/reset-password?token={token}"
        await email_service.send_password_reset_email(user.email_address, user.username, reset_url)
        return True

    async def reset_password(self, token: str, new_password: str) -> bool:
        """Validate reset token, update the password and sign out every session.

        A reset is the "my account was stolen" path: whoever held a session (a stolen
        refresh token included) is signed out with it, on every device (SEC F01). The
        token is redeemed by its digest.

        The password set is the account's own (``set_own_password``), a Google-only
        account's included: the link reached the address Google verified, so the password
        now opens the account at login, and Google sign-in still does. It used to be stored
        and then refused by the login (``auth_provider`` stayed google).
        """
        result = await self.session.exec(
            select(PasswordResetToken)
            .where(PasswordResetToken.token == token_digest(token))
            .where(PasswordResetToken.used == False)  # noqa: E712
        )
        reset_token = result.first()
        if not reset_token or utc_instant(reset_token.expires_at) < datetime.now(UTC):
            raise InvalidOrExpiredTokenError()

        user = (await self.session.exec(select(User).where(User.id == reset_token.user_id))).first()
        if not user:
            raise UserNotFoundError(user_id=reset_token.user_id)

        await set_own_password(user, new_password)
        self.session.add(user)
        await revoke_user_sessions(self.session, user.id)
        # Single-use: consume this token and drop any others for the user.
        await self._purge_password_reset_tokens(reset_token.user_id)
        await self.session.commit()
        return True

    async def send_verification_email(self, user: User, email_service: EmailService) -> bool:
        """Generate verification token and send email (the table keeps only its digest)."""
        # Only one active verification token per user; drops any prior/stale ones.
        await self._purge_expired_tokens(EmailVerificationToken)
        await self._purge_email_verification_tokens(user.id)
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
        verify_token = EmailVerificationToken(user_id=user.id, token=token_digest(token), expires_at=expires_at)
        self.session.add(verify_token)
        await self.session.commit()

        verify_url = f"{self.settings.frontend_url}/auth/verify-email?token={token}"
        await email_service.send_verification_email(user.email_address, user.username, verify_url)
        return True

    async def verify_email(self, token: str) -> bool:
        """Validate verification token and mark email as verified."""
        result = await self.session.exec(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token == token_digest(token))
            .where(EmailVerificationToken.used == False)  # noqa: E712
        )
        verify_token = result.first()
        if not verify_token or utc_instant(verify_token.expires_at) < datetime.now(UTC):
            raise InvalidOrExpiredTokenError()

        user = (await self.session.exec(select(User).where(User.id == verify_token.user_id))).first()
        if not user:
            raise UserNotFoundError(user_id=verify_token.user_id)

        user.email_verified = True
        self.session.add(user)
        # Single-use: consume this token and drop any others for the user.
        await self._purge_email_verification_tokens(verify_token.user_id)
        await self.session.commit()
        return True

    async def resend_verification(self, email: str, email_service: EmailService) -> bool:
        """Resend verification email."""
        user = await self.get_user_by_email(email)
        if not user or user.email_verified:
            return True  # Don't reveal info
        return await self.send_verification_email(user, email_service)

    async def social_login(
        self,
        social_auth_service: SocialAuthService,
        access_token: str,
    ) -> SocialLoginResult:
        """Authenticate a user via Google OAuth2.

        Flow:
        1. Verify access token with Google's userinfo API
        2. Look up user by google_sub (fast path for returning users)
        3. If not found, look up by email (any case) and link google_sub — to a VERIFIED
           account as is; an unverified one is first taken back for the mailbox's owner
           (``_take_back_for_mailbox_owner``, SEC F02)
        4. If email not found, create new user (auto-verified, sentinel password)
        5. Open a session and return its JWT pair + is_new_user flag

        :param social_auth_service: Service to verify tokens.
        :param access_token: OAuth2 access token from Google.
        :return: SocialLoginResult with JWT pair and is_new_user flag.
        :raises InvalidCredentialsError: If token verification fails.
        """
        token_payload = await social_auth_service.verify_google_access_token(access_token)

        # Fast path: look up by google_sub
        user = await self._get_user_by_google_sub(token_payload.sub)
        if user:
            return await self._complete_social_login(user, is_new_user=False)

        # Look up by email and link
        user = await self.get_user_by_email(token_payload.email)
        if user:
            if not user.email_verified:
                await self._take_back_for_mailbox_owner(user)
            self._link_google_sub(user, token_payload.sub)
            return await self._complete_social_login(user, is_new_user=False)

        # Create new user
        user = await self._create_social_user(token_payload)
        return await self._complete_social_login(user, is_new_user=True)

    async def _get_user_by_google_sub(self, sub: str) -> User | None:
        """Look up a user by their Google subject identifier."""
        result = await self.session.exec(select(User).where(User.google_sub == sub))
        return result.one_or_none()

    def _link_google_sub(self, user: User, sub: str) -> None:
        """Link a Google sub to an existing user account (committed with the new session)."""
        user.google_sub = sub
        self.session.add(user)
        logger.info("Linked Google account to existing user", user_id=str(user.id))

    async def _take_back_for_mailbox_owner(self, user: User) -> None:
        """Reset an UNVERIFIED account to whoever Google proves owns its address (SEC F02).

        Registration needs no verification, so anyone could register an address before its
        owner first used "Continue with Google". Linking into that account as it was let the
        first registrant's password (and sessions) keep opening the owner's profile. Google's
        verified email proves ownership; nothing about the account does. So, before linking:
        the password becomes the social sentinel, ``auth_provider`` google, the address
        verified, and every session is revoked. The first registrant's password and tokens
        stop working. Revoked first: the UPDATE flushes, and must not reach the session the
        caller opens next. Not committed: the caller commits once, with that session.
        """
        await revoke_user_sessions(self.session, user.id)
        user.password = await async_get_password_hash(self._social_sentinel_password())
        user.auth_provider = AUTH_PROVIDER_GOOGLE
        user.email_verified = True
        self.session.add(user)
        logger.warning(
            "Unverified account taken back by the Google-verified owner of its address", user_id=str(user.id)
        )

    @staticmethod
    def _social_sentinel_password() -> str:
        """A random password no one knows: a Google account cannot sign in with one."""
        return secrets.token_urlsafe(48)[:72]

    async def _create_social_user(self, token_payload: SocialTokenPayload) -> User:
        """Create a new user from Google login.

        Username is generated from Google name, with a random suffix if taken.
        Password is a random sentinel that never matches real input.

        Uniqueness is checked case-insensitively like registration and renames
        (``username_is_taken``: ``User.username`` is indexed but NOT unique), and each
        candidate is claimed under its own ``username_claim_lock`` — the generated name
        first, then up to ``SOCIAL_USERNAME_SUFFIX_ATTEMPTS`` suffixed ones. Every lock
        taken is held until the insert commits, so the name chosen cannot be claimed by
        a concurrent registration in between.

        :raises UsernameAlreadyTakenError: every candidate was taken (vanishingly rare).
        """
        base_username = self._generate_username(token_payload)
        # Distinct candidates only (generated names are lowercase): the SQLite
        # fallback's asyncio.Lock is not reentrant, so claiming one name twice in this
        # block would wait on itself forever.
        candidates = list(
            dict.fromkeys(
                [base_username]
                + [self._suffixed_username(base_username) for _ in range(SOCIAL_USERNAME_SUFFIX_ATTEMPTS)]
            )
        )

        async with AsyncExitStack() as claimed:
            username: str | None = None
            for candidate in candidates:
                await claimed.enter_async_context(username_claim_lock(self.session, candidate))
                if not await username_is_taken(self.session, candidate):
                    username = candidate
                    break
            if username is None:
                raise UsernameAlreadyTakenError(username=base_username)

            password_hash = await async_get_password_hash(self._social_sentinel_password())

            user = User(
                username=username,
                email_address=normalize_email(token_payload.email),
                password=password_hash,
                email_verified=True,
                google_sub=token_payload.sub,
                auth_provider=AUTH_PROVIDER_GOOGLE,
                profile_picture_url=token_payload.picture,
            )
            self.session.add(user)
            await self.session.commit()
        await self.session.refresh(user)

        logger.info("Created new user via Google login", user_id=str(user.id))
        return user

    @staticmethod
    def _suffixed_username(username: str) -> str:
        """``username`` with a random ``_xxxx`` suffix, still within ``USERNAME_MAX_LENGTH``."""
        suffix = f"_{secrets.token_hex(2)}"
        return f"{username[: USERNAME_MAX_LENGTH - len(suffix)]}{suffix}"

    @staticmethod
    def _generate_username(token_payload: SocialTokenPayload) -> str:
        """Generate a username from Google name or email prefix.

        The result is clamped to [USERNAME_MIN_LENGTH, USERNAME_MAX_LENGTH].
        SQLModel does not validate `table=True` models, so an out-of-range name
        inserted fine and then blew up at response time, when the User row was
        serialised through UserView (which does enforce the bounds) — a 500 on an
        otherwise successful Google sign-up. Real triggers: a two-letter Google
        first name, or a long "firstname_lastname" pair.
        """
        first = token_payload.first_name or ""
        last = token_payload.last_name or ""
        raw = f"{first}_{last}".strip("_") if (first or last) else token_payload.email.split("@")[0]
        # Lowercase, replace spaces with underscores, strip non-alphanumeric (except underscores)
        username = re.sub(r"[^a-z0-9_]", "", raw.lower().replace(" ", "_"))
        username = username[:USERNAME_MAX_LENGTH]
        if len(username) < USERNAME_MIN_LENGTH:
            # Pad with random hex rather than a fixed string so two short names
            # don't collide on every attempt.
            username = f"{username or 'user'}_{secrets.token_hex(2)}"[:USERNAME_MAX_LENGTH]
        return username

    async def _complete_social_login(self, user: User, is_new_user: bool) -> SocialLoginResult:
        """Complete social login: open a session (committing any link with it) and return its pair."""
        auth_session = await self._open_session(user)
        tokens = self._session_tokens(user, auth_session)
        await self.session.commit()

        logger.info(
            "Social login successful",
            user_id=str(user.id),
            is_new_user=is_new_user,
        )

        return SocialLoginResult(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            is_new_user=is_new_user,
            user=SocialLoginUserData(
                id=str(user.id),
                username=user.username,
                email=user.email_address,
            ),
        )
