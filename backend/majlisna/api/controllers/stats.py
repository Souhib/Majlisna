from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Float, case
from sqlalchemy import cast as sql_cast
from sqlalchemy.exc import NoResultFound
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    CACHE_TTL_LEADERBOARD_SECONDS,
    LEADERBOARD_SORT_FIELDS,
    MIN_PLAYERS_FOR_A_WIN,
    WINNER_IDS_KEY,
)
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import UserGameLink
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, User
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.error import InvalidLeaderboardSortError, UserNotFoundError
from majlisna.api.schemas.stats import DailyGameRecord, GameDurationStats, HeadToHeadStats, LeaderboardEntry
from majlisna.api.utils.cache import cache
from majlisna.api.utils.game_state import left_player_ids


def did_user_win(game: Game, user_id: UUID | str) -> bool | None:
    """Did ``user_id`` win ``game``? The ONE answer for history, the chart and head-to-head.

    ``None`` means the game is no result for this user, and every reader skips it:

    - a game still running, or cancelled;
    - a leaver (``left_player_ids``; owner rule (b): neither a win nor a loss), and
      anyone else not in the final ``players`` — a spectator (who has a
      ``UserGameLink`` too), a Codenames or quiz leaver (removed from ``players``);
    - a solo game: a final roster below ``MIN_PLAYERS_FOR_A_WIN`` is never a win;
    - an old row whose winner was never recorded.

    Otherwise it reads ``live_state[WINNER_IDS_KEY]``, which ``record_game_end`` writes
    for every game type, and falls back to the side / team / top-score rule for rows
    written before that key. It used to know only Undercover and Codenames, so every
    quiz win was drawn as a loss on the chart, a draw head-to-head and "no result" in
    history, while ``UserStats`` counted it (BDP-05, BR-19).

    Module-level, not on ``game_end_stats``: that module imports this one.
    """
    if game.game_status != GameStatus.FINISHED:
        return None
    state = game.live_state or {}
    uid = str(user_id)
    left = left_player_ids(state)
    roster = [p for p in state.get("players", []) if p.get("user_id") not in left]
    player = next((p for p in roster if p.get("user_id") == uid), None)
    if player is None or len(roster) < MIN_PLAYERS_FOR_A_WIN:
        return None

    winner_ids = state.get(WINNER_IDS_KEY)
    if isinstance(winner_ids, list):
        return uid in winner_ids
    return _legacy_did_user_win(game.type, state, player, roster)


def _legacy_did_user_win(game_type: GameType, state: dict, player: dict, roster: list[dict]) -> bool | None:
    """For a game finished before ``WINNER_IDS_KEY`` existed."""
    winner = state.get("winner")
    if game_type == GameType.UNDERCOVER:
        if winner == "civilians":
            return player.get("role") == UndercoverRole.CIVILIAN.value
        if winner == "undercovers":
            return player.get("role") in (UndercoverRole.UNDERCOVER.value, UndercoverRole.MR_WHITE.value)
        return None
    if game_type == GameType.CODENAMES:
        return player.get("team") == winner if winner else None
    # The quizzes stored one username in "winner" (a tie went to the first seat, a 0-0
    # game had a winner): rule (a) over the stored scores instead.
    best = max((p.get("total_score", 0) for p in roster), default=0)
    return best > 0 and player.get("total_score", 0) == best


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

    async def get_or_create_many(self, user_ids: Sequence[UUID]) -> dict[UUID, UserStats]:
        """The stats rows of these users, ``{user_id: row}``, staging a new one for each
        user who has none (inserted by the caller's commit).

        ONE query for a whole game end (BDP-07) instead of one per player, inside the
        game lock. The players of a game cannot be ending another one at the same moment
        (one active room per player), so a missing row has no concurrent creator to race.
        """
        if not user_ids:
            return {}
        rows = (
            await self.session.exec(
                select(UserStats).where(UserStats.user_id.in_(user_ids))  # ty: ignore[unresolved-attribute]
            )
        ).all()
        by_user = {row.user_id: row for row in rows}
        for user_id in user_ids:
            if user_id not in by_user:
                by_user[user_id] = UserStats(user_id=user_id)
                self.session.add(by_user[user_id])
        return by_user

    async def read_user_stats(self, user_id: UUID) -> UserStats:
        """The public stats of a user, read-only: what ``GET /stats/users/{id}/stats`` answers.

        It used to call ``get_or_create_user_stats``, which INSERTs and commits: an
        anonymous GET wrote a row for any existing user without one, and for an unknown
        id the insert failed its foreign key — a 500 logged at ERROR, on SQLite too
        (foreign keys are on), at will (PD-11, SEC F11). Rows are created by the game
        end and the room paths only.

        :return: the user's row, or an unsaved zero-valued ``UserStats`` when they have none.
        :raises UserNotFoundError: no such user (404).
        """
        user_exists = (await self.session.exec(select(User.id).where(User.id == user_id))).first()
        if user_exists is None:
            raise UserNotFoundError(user_id=user_id)
        row = (await self.session.exec(select(UserStats).where(UserStats.user_id == user_id))).first()
        return row if row is not None else UserStats(user_id=user_id)

    async def get_user_stats(self, user_id: UUID) -> UserStats:
        """Get stats for a user. Raises UserNotFoundError if no stats exist.

        Deliberately NOT cached. It was, for 5 minutes, and both halves of that were
        wrong:

        * `TTLCache` is per-process and production runs 4 uvicorn workers, so the
          `cache.invalidate()` at the end of `update_stats_after_game` only reached
          the worker that finished the game. The other three kept serving the
          pre-game numbers for up to five minutes — a player watched their own win
          not appear, then appear, depending on which worker answered.
        * the cached object was the SQLAlchemy `UserStats` instance, i.e. a detached
          ORM row shared between sessions.

        The query it replaces is a single indexed lookup on `user_stats.user_id`.

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
        won: bool | None,
        role: str | None = None,
        *,
        commit: bool = True,
        stats: UserStats | None = None,
    ) -> UserStats:
        """Increment relevant counters after a game ends.

        :param user_id: The id of the user.
        :param game_type: The type of game ("undercover" or "codenames").
        :param won: Whether the user won the game; ``None`` for a game that is no result
            (a solo final roster, owner rule (a)): played, neither won nor lost, and the
            win streak left as it was — what ``did_user_win`` answers for the same game.
        :param role: The role the user played (e.g. "civilian", "undercover",
            "mr_white", "spymaster", "operative").
        :param stats: the user's row, already read by ``get_or_create_many`` (read here when omitted).
        :return: The updated stats record.
        """
        if stats is None:
            stats = await self.get_or_create_user_stats(user_id, commit=commit)

        # Global counts and the win streak; a game with no result touches neither.
        stats.total_games_played += 1
        if won is True:
            stats.total_games_won += 1
            stats.current_win_streak += 1
            stats.longest_win_streak = max(stats.longest_win_streak, stats.current_win_streak)
        elif won is False:
            stats.total_games_lost += 1
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

        # Best-effort, and only on this worker — see TTLCache's docstring. The
        # leaderboard's real freshness bound is its short TTL, not this call.
        cache.invalidate_prefix("leaderboard:")

        return stats

    async def get_leaderboard(
        self,
        stat_field: str = "total_games_won",
        limit: int = 10,
    ) -> Sequence[LeaderboardEntry]:
        """Return the top users ranked by a given stat field, with usernames.

        :param stat_field: What to rank by, descending: one of LEADERBOARD_SORT_FIELDS
            (a UserStats column, or ``win_rate``, computed from won / played).
        :param limit: Maximum number of results to return.
        :return: A list of LeaderboardEntry with username included.
        :raises InvalidLeaderboardSortError: If the leaderboard does not rank by ``stat_field``.
        """
        if stat_field not in LEADERBOARD_SORT_FIELDS:
            raise InvalidLeaderboardSortError(stat_field)

        cache_key = f"leaderboard:{stat_field}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cast(Sequence[LeaderboardEntry], cached)

        if stat_field == "win_rate":
            # The same rule as the entries below: no games played is a 0 % rate. Ties go
            # to whoever won more, so one lucky game does not outrank a long record.
            rate = case(
                (
                    col(UserStats.total_games_played) > 0,
                    sql_cast(col(UserStats.total_games_won), Float) / col(UserStats.total_games_played),
                ),
                else_=0.0,
            )
            order = (rate.desc(), col(UserStats.total_games_won).desc())
        else:
            order = (col(getattr(UserStats, stat_field)).desc(),)

        results = await self.session.exec(
            select(UserStats, User.username)
            .join(User, UserStats.user_id == User.id)  # ty: ignore[invalid-argument-type]
            .order_by(*order)
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
            .join(UserGameLink, Game.id == UserGameLink.game_id)  # ty: ignore[invalid-argument-type]
            .where(UserGameLink.user_id == user_id)
            .where(Game.game_status == GameStatus.FINISHED)
            # `end_time` is nullable (it is only written when a game ends), and SQL
            # answers NULL — i.e. no match — for the comparison. That is exactly the
            # wanted semantics here: an unfinished game must not count towards recent
            # activity. The preceding FINISHED filter makes it unreachable anyway.
            .where(Game.end_time >= cutoff)  # ty: ignore[unsupported-operator]
        )
        games = results.all()

        daily: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0})
        for game in games:
            if not game.end_time:
                continue
            won = did_user_win(game, user_id)
            if won is None:
                continue  # no result for this user: a leaver, a spectator, a solo game
            day_str = game.end_time.date().isoformat()
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
            .join(UserGameLink, Game.id == UserGameLink.game_id)  # ty: ignore[invalid-argument-type]
            .where(UserGameLink.user_id == user_id)
            .where(Game.game_status == GameStatus.FINISHED)
            .where(Game.end_time.is_not(None))  # ty: ignore[unresolved-attribute]
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
                .where(UserGameLink.game_id.in_(opponent_games_query))  # ty: ignore[unresolved-attribute]
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
                    Game.id.in_(shared_game_ids),  # ty: ignore[unresolved-attribute]
                    Game.game_status == GameStatus.FINISHED,
                )
            )
        ).all()

        user_wins = 0
        opponent_wins = 0
        draws = 0
        total_games = 0

        for game in games:
            u_won = did_user_win(game, user_id)
            o_won = did_user_win(game, opponent_id)
            if u_won is None or o_won is None:
                continue  # one of them left, spectated, or it was no contest
            total_games += 1
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
            total_games=total_games,
        )
