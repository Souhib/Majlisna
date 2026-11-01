from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.stats import UserStats
from majlisna.api.schemas.stats import (
    AchievementWithProgress,
    DailyGameRecord,
    GameDurationStats,
    HeadToHeadStats,
    LeaderboardEntry,
)
from majlisna.dependencies import get_achievement_controller, get_stats_controller

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    responses={404: {"description": "Not found"}},
)


@router.get("/users/{user_id}/stats", response_model=UserStats)
async def get_user_stats(
    *,
    user_id: UUID,
    stats_controller: Annotated[StatsController, Depends(get_stats_controller)],
) -> UserStats:
    """Get aggregated statistics for a user (read-only: zeros for a user with no games yet).

    404 for an unknown user. This used to create the row, so an anonymous GET wrote to
    the database and an unknown id answered a 500.
    """
    return await stats_controller.read_user_stats(user_id)


@router.get("/users/{user_id}/achievements", response_model=Sequence[AchievementWithProgress])
async def get_user_achievements(
    *,
    user_id: UUID,
    achievement_controller: Annotated[AchievementController, Depends(get_achievement_controller)],
) -> Sequence[AchievementWithProgress]:
    """Get all achievements with definitions and user progress."""
    return await achievement_controller.get_user_achievements(user_id)


@router.get("/users/{user_id}/history", response_model=list[DailyGameRecord])
async def get_game_history(
    *,
    user_id: UUID,
    stats_controller: Annotated[StatsController, Depends(get_stats_controller)],
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
) -> list[DailyGameRecord]:
    """Get daily win/loss history for charts."""
    return await stats_controller.get_game_history_for_charts(user_id, days=days)


@router.get("/users/{user_id}/duration", response_model=GameDurationStats)
async def get_duration_stats(
    *,
    user_id: UUID,
    stats_controller: Annotated[StatsController, Depends(get_stats_controller)],
) -> GameDurationStats:
    """Get game duration analytics for a user."""
    return await stats_controller.get_game_duration_stats(user_id)


@router.get("/users/{user_id}/vs/{opponent_id}", response_model=HeadToHeadStats)
async def get_head_to_head(
    *,
    user_id: UUID,
    opponent_id: UUID,
    stats_controller: Annotated[StatsController, Depends(get_stats_controller)],
) -> HeadToHeadStats:
    """Get head-to-head stats between two players."""
    return await stats_controller.get_head_to_head(user_id, opponent_id)


@router.get("/leaderboard", response_model=Sequence[LeaderboardEntry])
async def get_leaderboard(
    *,
    stats_controller: Annotated[StatsController, Depends(get_stats_controller)],
    stat_field: str = Query(default="total_games_won", description="Stat field to rank by"),
    limit: int = Query(default=10, ge=1, le=100, description="Number of results"),
) -> Sequence[LeaderboardEntry]:
    """Get the leaderboard ranked by a specific stat field."""
    return await stats_controller.get_leaderboard(stat_field=stat_field, limit=limit)
