"""The ONE place an access token becomes a ``User`` — HTTP and Socket.IO alike.

``dependencies.get_current_user`` and both Socket.IO connects (``ws/handlers.py``:
``_connect_personal``, ``_authenticate_member``) call ``authenticate_access_token`` (or
``authenticate_caller``, which also says which session the caller is on). They used to
each decode the token themselves, and drifted: the sockets resolved the user by the
``email`` claim alone and never compared ``sub``, so an access token outlived a
delete-and-re-register of its address and opened the NEW account's personal channel
(room invites, with their PIN) and rooms (SEC F09). And the access-vs-refresh rule was
never exercised on any caller, so dropping ``expected_type`` passed the whole suite
(TQ-01).

A rule about tokens goes here, and reaches every door at once — the session check of
SEC F01 included: a token whose session was signed out (logout, a reset, a reused
refresh token, Google taking an unverified account back) or has passed its absolute
``expires_at`` is refused with ``SessionRevokedError``, on every request and at every
socket connect.
"""

from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import (
    TOKEN_TYPE_ACCESS,
    AuthController,
    normalize_email,
    session_is_live,
)
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.table import User
from majlisna.api.schemas.auth import TokenPayload
from majlisna.api.schemas.error import InvalidTokenError, SessionRevokedError
from majlisna.settings import Settings


class AuthenticatedCaller(NamedTuple):
    """Who an access token names, and on which session (None for a legacy token)."""

    user: User
    session_id: UUID | None


async def _session_user(session: AsyncSession, payload: TokenPayload) -> AuthenticatedCaller:
    """The live session a ``sid`` names, and its account — ONE primary-key read for both.

    Every request and socket pays this, so it replaces the email lookup rather than adding
    to it. The account must still be the one the token names by both claims.

    :raises SessionRevokedError: no such session (account deleted), revoked, or past ``expires_at``.
    :raises InvalidTokenError: the session belongs to another account than ``sub`` / ``email``.
    """
    try:
        session_id = UUID(str(payload.sid))
    except ValueError as e:
        raise InvalidTokenError() from e
    row = (
        await session.exec(
            select(AuthSession, User)
            .join(User, col(User.id) == col(AuthSession.user_id))
            .where(col(AuthSession.id) == session_id)
        )
    ).first()
    if row is None:
        raise SessionRevokedError()
    auth_session, user = row
    if not session_is_live(auth_session, datetime.now(UTC)):
        raise SessionRevokedError()
    if str(user.id) != payload.sub or normalize_email(user.email_address) != normalize_email(payload.email):
        raise InvalidTokenError("User not found for token")
    return AuthenticatedCaller(user=user, session_id=session_id)


async def authenticate_caller(session: AsyncSession, settings: Settings, token: str) -> AuthenticatedCaller:
    """The account an ACCESS token names, by both of its claims, and its session.

    - The signature, the expiry and ``type == "access"`` (a refresh token never
      authenticates a request or a socket): ``InvalidTokenError`` /
      ``TokenExpiredError`` from ``AuthController.decode_token``.
    - A token with a ``sid`` must name a live session of that account
      (``SessionRevokedError`` otherwise).
    - A legacy token (no ``sid``, minted before sessions existed) is accepted until it
      expires — at most ``access_token_expire_minutes`` after the deploy, so nobody is
      signed out by it. Its account is looked up by ``sub`` and must have the ``email``.
    - Either claim alone is not enough: ``email`` survives a delete-and-re-register of
      the address, and ``sub`` alone would keep a token valid across an address change.

    :raises InvalidTokenError: wrong type, bad signature, or no account matching both claims.
    :raises TokenExpiredError: the token has expired.
    :raises SessionRevokedError: the token's session was signed out or has ended.
    """
    auth_controller = AuthController(session, settings)
    payload = auth_controller.decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    if payload.sid is not None:
        return await _session_user(session, payload)
    user = await auth_controller.user_named_by(payload)
    return AuthenticatedCaller(user=user, session_id=None)


async def authenticate_access_token(session: AsyncSession, settings: Settings, token: str) -> User:
    """The account an ACCESS token names (``authenticate_caller`` without the session id).

    :raises InvalidTokenError: wrong type, bad signature, or no account matching both claims.
    :raises TokenExpiredError: the token has expired.
    :raises SessionRevokedError: the token's session was signed out or has ended.
    """
    return (await authenticate_caller(session, settings, token)).user
