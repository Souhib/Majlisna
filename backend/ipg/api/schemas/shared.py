from datetime import UTC, datetime

from pydantic import ConfigDict
from sqlalchemy import TIMESTAMP
from sqlmodel import Field, SQLModel


class BaseModel(SQLModel):
    """Base model for all Pydantic models and SQLModel schemas.

    Provides common configuration for all models in the application including:
    - Attribute-based initialization
    - Name population from field aliases
    - Arbitrary type support for complex fields
    - Strict extra field validation
    """

    model_config = ConfigDict(  # type: ignore
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        extra="forbid",
    )


class BaseTable(BaseModel):
    """Base model for all database tables with timezone-aware timestamps.

    Automatically includes created_at and updated_at fields with PostgreSQL
    TIMESTAMP WITH TIME ZONE support for proper timezone handling.
    """

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP(timezone=True),  # type: ignore[invalid-argument-type]
        description="Timestamp when the record was created (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP(timezone=True),  # type: ignore[invalid-argument-type]
        description="Timestamp when the record was last updated (UTC)",
    )
