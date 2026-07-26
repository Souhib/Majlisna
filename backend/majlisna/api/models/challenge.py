from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field

from majlisna.api.schemas.shared import BaseTable


class ChallengeType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ChallengeDefinition(BaseTable, table=True):
    """Challenge template definitions."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(unique=True, index=True)
    description: str
    challenge_type: ChallengeType
    target_count: int = 1
    game_type: str | None = None  # "undercover", "codenames", or None for any
    condition: str = "play"  # "play", "win", "play_as_role"
    role: str | None = None  # e.g., "spymaster", "civilian"


class UserChallenge(BaseTable, table=True):
    """Active challenge assigned to a user."""

    __table_args__ = (UniqueConstraint("user_id", "challenge_id", "assigned_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    challenge_id: UUID = Field(foreign_key="challengedefinition.id", index=True)
    progress: int = 0
    completed: bool = False
    assigned_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
