from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable

# Both tables store the sha256 hex digest of the token in `token` (64 characters), never
# the token itself: the link carries the token, `AuthController` redeems it by digest
# (`controllers/auth.token_digest`), so reading the table yields nothing usable (PD-15,
# SEC F06). The column kept its name, so there was no schema change; links issued before
# the change stopped working (production held one, already expired). Expired rows are
# purged whenever a new token of the same kind is issued. `expires_at` reads back NAIVE on
# SQLite: compare it through `controllers/auth.utc_instant`.


class PasswordResetToken(BaseTable, table=True):
    """Token for password reset requests (``token`` is its sha256 digest)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    token: str = Field(unique=True, index=True)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used: bool = Field(default=False)


class EmailVerificationToken(BaseTable, table=True):
    """Token for email verification (``token`` is its sha256 digest)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    token: str = Field(unique=True, index=True)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used: bool = Field(default=False)
