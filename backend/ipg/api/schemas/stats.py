from uuid import UUID

from ipg.api.schemas.shared import BaseModel


class LeaderboardEntry(BaseModel):
    """A leaderboard row with username included."""

    user_id: UUID
    username: str
    total_games_played: int
    total_games_won: int
    win_rate: float
    current_win_streak: int
    longest_win_streak: int


class AchievementWithProgress(BaseModel):
    """Achievement definition combined with user progress."""

    code: str
    name: str
    description: str
    icon: str
    category: str
    tier: int
    threshold: int
    progress: int
    unlocked: bool
