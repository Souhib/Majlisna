"""End-of-game stat and achievement writes, shared by the normal and disconnect paths.

This lives in its own module rather than on ``BaseGameController`` because
``disconnect.py`` needs it too, and ``base_game`` imports ``RoomController``, which
imports ``disconnect`` — so a controller import from there is a cycle. Only
``stats``, ``achievement`` and the models are imported here, none of which reach
back into rooms or games.

**Nothing in here commits.** Every caller runs inside ``get_game_lock``, which on
PostgreSQL is ``pg_try_advisory_xact_lock`` — transaction scoped. A commit here would
release the game lock in the middle of the end-of-game critical section. The caller's
single ``commit()`` persists these writes.

**SQLAlchemy errors are not swallowed either.** After a failed statement the session
needs a rollback, so catching-and-continuing made every later query in the loop and
the caller's commit raise ``PendingRollbackError``, losing the whole game-end write.
"""

from collections.abc import Sequence
from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.table import User


async def scorable_players(session: AsyncSession, state: dict) -> list[dict]:
    """The players from live_state whose User row still exists.

    ``live_state["players"]`` is a snapshot frozen at game start, so a player who
    deletes their account mid-game stays in it — and ``UserStats(user_id=<gone>)``
    then fails the foreign key, which (since the stats loop no longer swallows
    SQLAlchemy errors) would make the game impossible to ever finish.

    One query for the whole set, not one per player.
    """
    players = state.get("players", [])
    if not players:
        return []
    player_ids = [UUID(p["user_id"]) for p in players]
    existing = set(
        (
            await session.exec(
                select(User.id).where(User.id.in_(player_ids))  # type: ignore[attr-defined,union-attr]
            )
        ).all()
    )
    scorable = [p for p in players if UUID(p["user_id"]) in existing]
    if len(scorable) != len(players):
        missing = [p["user_id"] for p in players if UUID(p["user_id"]) not in existing]
        logger.warning("Skipping stats for deleted users {}", missing)
    return scorable


async def record_game_end(
    session: AsyncSession,
    state: dict,
    *,
    game_type: str,
    winners: set[str],
    default_role: str = "player",
    track_hints: bool = True,
) -> list[dict]:
    """Stage the stat and achievement writes for a finished game.

    :param winners: the ``user_id`` strings of the players who won. Each game decides
        that differently (role vs. winning label in Undercover, team in Codenames,
        top score in the quizzes), so the caller resolves it and passes the answer.
    :param track_hints: whether this game type feeds the hint achievements.
    :return: ``[{user_id, achievements: [{code, name, icon, tier}]}]`` for newly
        unlocked achievements, for the client to toast.
    """
    stats_controller = StatsController(session)
    achievement_controller = AchievementController(session)
    hint_usage = state.get("hint_usage", {}) if track_hints else {}
    newly_unlocked_all: list[dict] = []

    for player in await scorable_players(session, state):
        user_id = UUID(player["user_id"])
        won = player["user_id"] in winners
        stats = await stats_controller.update_stats_after_game(
            user_id=user_id,
            game_type=game_type,
            won=won,
            role=player.get("role", default_role),
            commit=False,
        )

        if track_hints:
            hints_viewed_count = len(hint_usage.get(str(user_id), []))
            if hints_viewed_count > 0:
                stats.total_hints_viewed += hints_viewed_count
            if won and hints_viewed_count == 0:
                stats.games_without_hints += 1
            session.add(stats)

        unlocked = await achievement_controller.check_achievements(user_id, stats, commit=False)
        if unlocked:
            newly_unlocked_all.append(
                {
                    "user_id": str(user_id),
                    "achievements": [
                        {"code": a.code, "name": a.name, "icon": a.icon, "tier": a.tier} for a in unlocked
                    ],
                }
            )
        logger.info("Stats updated: game={} user={}", game_type, user_id)

    return newly_unlocked_all


def undercover_winners(state: dict, winner_label: str) -> set[str]:
    """The user_ids on the winning side of an Undercover game."""
    winning_roles = {"civilian"} if winner_label == "civilians" else {"undercover", "mr_white"}
    return {p["user_id"] for p in state.get("players", []) if p.get("role", "civilian") in winning_roles}


def codenames_winners(state: dict, winning_team: str) -> set[str]:
    """The user_ids on the winning team of a Codenames game."""
    return {p["user_id"] for p in state.get("players", []) if p.get("team") == winning_team}


def top_score_winners(players: Sequence[dict]) -> set[str]:
    """The single highest scorer of a quiz game (empty when there are no players)."""
    if not players:
        return set()
    best = max(players, key=lambda p: p["total_score"])
    return {best["user_id"]}
