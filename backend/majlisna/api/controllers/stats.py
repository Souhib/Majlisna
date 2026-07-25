from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import NoResultFound
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import CACHE_TTL_LEADERBOARD_SECONDS, CACHE_TTL_USER_STATS_SECONDS
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import UserGameLink
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, User
from majlisna.api.schemas.error import UserNotFoundError
from majlisna.api.schemas.stats import DailyGameRecord, GameDurationStats, HeadToHeadStats, LeaderboardEntry
from majlisna.api.utils.cache import cache


class StatsController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user_stats(self, user_id: UUID, *, commit: bool = True) -> UserStats:
        """Get existing stats for a user, or create a new record if none exists.

        :param user_id: The id of the user.
        :return: The user's stats record.
        """
        result = (await self.session.exec(select(UserStats).where(UserStats.user_id == user_id))).first()

        if result is not None:
            return result

        new_stats = UserStats(user_id=user_id)
        self.session.add(new_stats)
        if commit:
            await self.session.commit()
            await self.session.refresh(new_stats)
        return new_stats

    async def get_user_stats(self, user_id: UUID) -> UserStats:
        """Get stats for a user. Raises UserNotFoundError if no stats exist.

        :param user_id: The id of the user.
        :return: The user's stats record.
        :raises UserNotFoundError: If no stats record exists for this user.
        """
        cache_key = f"user_stats:{user_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        try:
            stats = (await self.session.exec(select(UserStats).where(UserStats.user_id == user_id))).one()
            cache.set(cache_key, stats, CACHE_TTL_USER_STATS_SECONDS)
            return stats
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

    async def update_stats_after_game(  # noqa: C901, PLR0912, PLR0915
        self,
        user_id: UUID,
        game_type: str,
        won: bool,
        role: str | None = None,
        *,
        commit: bool = True,
    ) -> UserStats:
        """Increment relevant counters after a game ends.

        :param user_id: The id of the user.
        :param game_type: The type of game ("undercover" or "codenames").
        :param won: Whether the user won the game.
        :param role: The role the user played (e.g. "civilian", "undercover",
            "mr_white", "spymaster", "operative").
        :return: The updated stats record.
        """
        stats = await self.get_or_create_user_stats(user_id, commit=commit)

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
        now = datetime.now(UTC)
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
        if commit:
            await self.session.commit()
            await self.session.refresh(stats)

        cache.invalidate(f"user_stats:{user_id}")
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

        cache.set(cache_key, entries, CACHE_TTL_LEADERBOARD_SECONDS)
        return entries

    async def get_game_history_for_charts(self, user_id: UUID, days: int = 30) -> list[DailyGameRecord]:
        """Get daily win/loss counts for a user over the last N days."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        results = await self.session.exec(
            select(Game)
            .join(UserGameLink, Game.id == UserGameLink.game_id)
            .where(UserGameLink.user_id == user_id)
            .where(Game.game_status == GameStatus.FINISHED)
            .where(Game.end_time >= cutoff)
        )
        games = results.all()

        daily: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0})
        for game in games:
            if not game.end_time:
                continue
            day_str = game.end_time.date().isoformat()
            state = game.live_state or {}
            winner = state.get("winner")
            # Determine if this user won
            won = self._did_user_win(game, user_id, winner)
            if won:
                daily[day_str]["wins"] += 1
            else:
                daily[day_str]["losses"] += 1

        records = []
        for day_str in sorted(daily):
            d = daily[day_str]
            records.append(
                DailyGameRecord(
                    date=day_str,
                    wins=d["wins"],
                    losses=d["losses"],
                    total=d["wins"] + d["losses"],
                )
            )
        return records

    async def get_game_duration_stats(self, user_id: UUID) -> GameDurationStats:
        """Compute game duration analytics for a user."""
        results = await self.session.exec(
            select(Game)
            .join(UserGameLink, Game.id == UserGameLink.game_id)
            .where(UserGameLink.user_id == user_id)
            .where(Game.game_status == GameStatus.FINISHED)
            .where(Game.end_time.is_not(None))  # type: ignore[union-attr]
        )
        games = results.all()

        durations: list[float] = []
        undercover_durations: list[float] = []
        codenames_durations: list[float] = []

        for game in games:
            if not game.end_time or not game.start_time:
                continue
            seconds = (game.end_time - game.start_time).total_seconds()
            if seconds <= 0:
                continue
            durations.append(seconds)
            if game.type == GameType.UNDERCOVER:
                undercover_durations.append(seconds)
            elif game.type == GameType.CODENAMES:
                codenames_durations.append(seconds)

        if not durations:
            return GameDurationStats(
                average_seconds=0,
                fastest_seconds=None,
                longest_seconds=None,
                undercover_avg_seconds=None,
                codenames_avg_seconds=None,
                total_games_with_duration=0,
            )

        return GameDurationStats(
            average_seconds=round(sum(durations) / len(durations), 1),
            fastest_seconds=round(min(durations), 1),
            longest_seconds=round(max(durations), 1),
            undercover_avg_seconds=(
                round(sum(undercover_durations) / len(undercover_durations), 1) if undercover_durations else None
            ),
            codenames_avg_seconds=(
                round(sum(codenames_durations) / len(codenames_durations), 1) if codenames_durations else None
            ),
            total_games_with_duration=len(durations),
        )

    async def get_head_to_head(self, user_id: UUID, opponent_id: UUID) -> HeadToHeadStats:
        """Get head-to-head stats between two players."""
        # Find games both players participated in
        opponent_games_query = select(UserGameLink.game_id).where(UserGameLink.user_id == opponent_id)

        shared_game_ids = (
            await self.session.exec(
                select(UserGameLink.game_id)
                .where(UserGameLink.user_id == user_id)
                .where(UserGameLink.game_id.in_(opponent_games_query))  # type: ignore[union-attr]
            )
        ).all()

        if not shared_game_ids:
            return HeadToHeadStats(
                user_id=user_id,
                opponent_id=opponent_id,
                user_wins=0,
                opponent_wins=0,
                draws=0,
                total_games=0,
            )

        games = (
            await self.session.exec(
                select(Game).where(
                    Game.id.in_(shared_game_ids),  # type: ignore[union-attr]
                    Game.game_status == GameStatus.FINISHED,
                )
            )
        ).all()

        user_wins = 0
        opponent_wins = 0
        draws = 0

        for game in games:
            state = game.live_state or {}
            winner = state.get("winner")
            u_won = self._did_user_win(game, user_id, winner)
            o_won = self._did_user_win(game, opponent_id, winner)
            if u_won and not o_won:
                user_wins += 1
            elif o_won and not u_won:
                opponent_wins += 1
            else:
                draws += 1

        return HeadToHeadStats(
            user_id=user_id,
            opponent_id=opponent_id,
            user_wins=user_wins,
            opponent_wins=opponent_wins,
            draws=draws,
            total_games=len(games),
        )

    @staticmethod
    def _did_user_win(game: Game, user_id: UUID, winner: str | None) -> bool:
        """Determine if the user won the given game."""
        if not winner:
            return False
        state = game.live_state or {}
        players = state.get("players", [])
        str_uid = str(user_id)

        if game.type == GameType.UNDERCOVER:
            for p in players:
                if p.get("user_id") == str_uid:
                    role = p.get("role", "")
                    if winner == "civilians" and role == "civilian":
                        return True
                    return winner == "undercovers" and role in ("undercover", "mr_white")
        elif game.type == GameType.CODENAMES:
            for p in players:
                if p.get("user_id") == str_uid:
                    return p.get("team") == winner
        return False
