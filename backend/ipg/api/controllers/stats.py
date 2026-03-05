from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import NoResultFound
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.stats import UserStats
from ipg.api.models.table import User
from ipg.api.schemas.error import UserNotFoundError
from ipg.api.schemas.stats import LeaderboardEntry
from ipg.api.utils.cache import cache

LEADERBOARD_TTL_SECONDS = 30


class StatsController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user_stats(self, user_id: UUID) -> UserStats:
        """Get existing stats for a user, or create a new record if none exists.

        :param user_id: The id of the user.
        :return: The user's stats record.
        """
        result = (await self.session.exec(select(UserStats).where(UserStats.user_id == user_id))).first()

        if result is not None:
            return result

        new_stats = UserStats(user_id=user_id)
        self.session.add(new_stats)
        await self.session.commit()
        await self.session.refresh(new_stats)
        return new_stats

    async def get_user_stats(self, user_id: UUID) -> UserStats:
        """Get stats for a user. Raises UserNotFoundError if no stats exist.

        :param user_id: The id of the user.
        :return: The user's stats record.
        :raises UserNotFoundError: If no stats record exists for this user.
        """
        try:
            return (await self.session.exec(select(UserStats).where(UserStats.user_id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def update_stats_after_game(  # noqa: C901, PLR0912, PLR0915
        self,
        user_id: UUID,
        game_type: str,
        won: bool,
        role: str | None = None,
    ) -> UserStats:
        """Increment relevant counters after a game ends.

        :param user_id: The id of the user.
        :param game_type: The type of game ("undercover" or "codenames").
        :param won: Whether the user won the game.
        :param role: The role the user played (e.g. "civilian", "undercover",
            "mr_white", "spymaster", "operative").
        :return: The updated stats record.
        """
        stats = await self.get_or_create_user_stats(user_id)

        # Global counts
        stats.total_games_played += 1
        if won:
            stats.total_games_won += 1
        else:
            stats.total_games_lost += 1

        # Win streak tracking
        if won:
            stats.current_win_streak += 1
            stats.longest_win_streak = max(stats.longest_win_streak, stats.current_win_streak)
        else:
            stats.current_win_streak = 0

        # Play streak tracking
        now = datetime.now()
        if stats.last_played_at is not None:
            days_since_last = (now.date() - stats.last_played_at.date()).days
            if days_since_last == 1:
                stats.current_play_streak_days += 1
            elif days_since_last > 1:
                stats.current_play_streak_days = 1
            # days_since_last == 0 means same day, streak stays the same
        else:
            stats.current_play_streak_days = 1

        stats.longest_play_streak_days = max(stats.longest_play_streak_days, stats.current_play_streak_days)

        stats.last_played_at = now

        # Per-game-type counts
        if game_type == "undercover":
            stats.undercover_games_played += 1
            if won:
                stats.undercover_games_won += 1

            # Undercover role stats
            if role == "civilian":
                stats.times_civilian += 1
                if won:
                    stats.civilian_wins += 1
            elif role == "undercover":
                stats.times_undercover += 1
                if won:
                    stats.undercover_wins += 1
            elif role == "mr_white":
                stats.times_mr_white += 1
                if won:
                    stats.mr_white_wins += 1

        elif game_type == "codenames":
            stats.codenames_games_played += 1
            if won:
                stats.codenames_games_won += 1

            # Codenames role stats
            if role == "spymaster":
                stats.times_spymaster += 1
                if won:
                    stats.spymaster_wins += 1
            elif role == "operative":
                stats.times_operative += 1
                if won:
                    stats.operative_wins += 1

        stats.updated_at = now
        self.session.add(stats)
        await self.session.commit()
        await self.session.refresh(stats)

        cache.invalidate_prefix("leaderboard:")

        return stats

    async def get_leaderboard(
        self,
        stat_field: str = "total_games_won",
        limit: int = 10,
    ) -> Sequence[LeaderboardEntry]:
        """Return the top users ranked by a given stat field, with usernames.

        :param stat_field: The name of the UserStats column to sort by (descending).
        :param limit: Maximum number of results to return.
        :return: A list of LeaderboardEntry with username included.
        :raises ValueError: If the stat field does not exist on UserStats.
        """
        cache_key = f"leaderboard:{stat_field}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        column = getattr(UserStats, stat_field, None)
        if column is None:
            raise ValueError(f"Invalid stat field: {stat_field}")

        results = await self.session.exec(
            select(UserStats, User.username)
            .join(User, UserStats.user_id == User.id)
            .order_by(col(column).desc())
            .limit(limit)
        )

        entries: list[LeaderboardEntry] = []
        for stats, username in results.all():
            played = stats.total_games_played
            win_rate = (stats.total_games_won / played * 100) if played > 0 else 0.0
            entries.append(
                LeaderboardEntry(
                    user_id=stats.user_id,
                    username=username,
                    total_games_played=played,
                    total_games_won=stats.total_games_won,
                    win_rate=round(win_rate, 1),
                    current_win_streak=stats.current_win_streak,
                    longest_win_streak=stats.longest_win_streak,
                )
            )

        cache.set(cache_key, entries, LEADERBOARD_TTL_SECONDS)
        return entries
