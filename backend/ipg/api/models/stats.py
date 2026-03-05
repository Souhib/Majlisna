from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from ipg.api.schemas.shared import BaseTable


class AchievementCategory(StrEnum):
    BEGINNER = "beginner"
    UNDERCOVER_MASTER = "undercover_master"
    CODENAMES_MASTER = "codenames_master"
    SOCIAL = "social"
    STREAK = "streak"
    SPECIAL = "special"


class UserStats(BaseTable, table=True):
    """Aggregated player statistics."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", unique=True, index=True)

    # Game counts
    total_games_played: int = 0
    total_games_won: int = 0
    total_games_lost: int = 0

    # Per-game-type
    undercover_games_played: int = 0
    undercover_games_won: int = 0
    codenames_games_played: int = 0
    codenames_games_won: int = 0

    # Undercover role stats
    times_civilian: int = 0
    times_undercover: int = 0
    times_mr_white: int = 0
    civilian_wins: int = 0
    undercover_wins: int = 0
    mr_white_wins: int = 0

    # Codenames role stats
    times_spymaster: int = 0
    times_operative: int = 0
    spymaster_wins: int = 0
    operative_wins: int = 0

    # Voting/social
    total_votes_cast: int = 0
    correct_votes: int = 0
    times_eliminated: int = 0
    times_survived: int = 0

    # Streaks
    current_win_streak: int = 0
    longest_win_streak: int = 0
    current_play_streak_days: int = 0
    longest_play_streak_days: int = 0
    last_played_at: datetime | None = None

    # Mr. White special
    mr_white_correct_guesses: int = 0

    # Codenames special
    codenames_words_guessed: int = 0
    codenames_perfect_rounds: int = 0

    # Hosting
    rooms_created: int = 0
    games_hosted: int = 0


class AchievementDefinition(BaseTable, table=True):
    """Badge/achievement definitions."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(unique=True, index=True)
    category: AchievementCategory
    name: str
    description: str
    icon: str = ""
    threshold: int = 1
    tier: int = Field(default=1, ge=1, le=6)  # 1=bronze to 6=mythic
    game_type: str | None = None  # "undercover", "codenames", or None for global


class UserAchievement(BaseTable, table=True):
    """Earned/in-progress achievements per user."""

    __table_args__ = (UniqueConstraint("user_id", "achievement_id"),)

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    achievement_id: UUID = Field(foreign_key="achievementdefinition.id", index=True)
    progress: int = 0
    unlocked_at: datetime | None = None
