"""Server-side sessions, so a signed-in device can be signed out for real (SEC F01).

The JWTs were stateless (``sub``, ``email``, ``exp``, ``type``): logout only cleared
cookies, and neither a password change nor a reset touched any token state, so a
leaked refresh token renewed itself forever. A session row is what a token's ``sid``
claim names; the refresh token is single-use (``current_refresh_jti``, with
``previous_refresh_jti`` accepted for ``REFRESH_REUSE_GRACE_SECONDS`` after a
rotation), and the session ends at ``expires_at`` however often it is refreshed
(``SESSION_ABSOLUTE_LIFETIME_DAYS``).

Written by ``AuthController`` (login, Google sign-in and the legacy-token upgrade open a
session; ``refresh_session`` rotates it; logout, a reset, reuse detection and Google
taking an unverified account back revoke it) and checked on every request and socket
connect by ``controllers/token_auth.authenticate_caller`` (one primary-key read, joined
to the user). In the baseline migration. Account deletion deletes the
user's rows (``UserController._purge_user_references``). The timestamps read back NAIVE
on SQLite: compare them through ``controllers/auth.utc_instant``.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, update
from sqlmodel import Field
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.schemas.shared import BaseTable


class AuthSession(BaseTable, table=True):
    """One signed-in device: the ``sid`` of every token pair minted for it.

    ``created_at`` (UTC-aware) is ``BaseTable``'s. Every instant here is UTC-aware:
    none of them is compared with the naive ``RoomUserLink`` timestamps.
    """

    __tablename__ = "auth_session"

    # The tokens' "sid" claim.
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    # The absolute cap: no refresh extends a session past it.
    expires_at: datetime = Field(sa_type=TIMESTAMP(timezone=True))  # ty: ignore[invalid-argument-type]
    last_refreshed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
    )
    # The "jti" of the one refresh token that may refresh this session now.
    current_refresh_jti: str = Field(max_length=64)
    # The token it replaced, still honoured for REFRESH_REUSE_GRACE_SECONDS after
    # `rotated_at`; any other reuse of an old jti is theft and revokes the session.
    previous_refresh_jti: str | None = Field(default=None, max_length=64)
    rotated_at: datetime | None = Field(
        default=None,
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
    )
    # The sha256 digest of the pre-session (legacy) refresh token this session was
    # upgraded from, if any (``AuthController._upgrade_legacy_refresh``). Unique: a
    # legacy token upgrades ONCE; presenting it again outside the two-tab grace is a
    # replayed copy and revokes this session (review R3). In the baseline migration.
    legacy_refresh_digest: str | None = Field(default=None, max_length=64, unique=True)
    # Set by logout, "sign out everywhere", a password change or reset, reuse detection.
    revoked_at: datetime | None = Field(
        default=None,
        sa_type=TIMESTAMP(timezone=True),  # ty: ignore[invalid-argument-type]
    )


async def revoke_user_sessions(session: AsyncSession, user_id: UUID, *, except_session_id: UUID | None = None) -> int:
    """Revoke every live session of ``user_id`` (all but ``except_session_id``).

    One UPDATE (``revoked_at = now`` where it is still NULL), so an already-revoked
    session keeps the instant it ended. **Does not commit**: the caller's mutation (a
    password change, a reset, a logout) commits once, so the revocation and the change
    land together or not at all.

    :return: how many sessions this call revoked.
    """
    statement = (
        update(AuthSession)
        # SQL expressions, not Python bools — ty does not model SQLModel column
        # operators (backend/CLAUDE.md, "ty: ignore discipline").
        .where(AuthSession.user_id == user_id)  # ty: ignore[invalid-argument-type]
        .where(AuthSession.revoked_at.is_(None))  # ty: ignore[unresolved-attribute]
        .values(revoked_at=datetime.now(UTC))
    )
    if except_session_id is not None:
        statement = statement.where(AuthSession.id != except_session_id)  # ty: ignore[invalid-argument-type]
    result = await session.exec(statement)
    return result.rowcount
