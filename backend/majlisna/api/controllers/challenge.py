import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.challenge import ChallengeDefinition, ChallengeType, UserChallenge
from majlisna.api.models.game import GameType
from majlisna.api.schemas.challenge import ActiveChallenge

# The conditions beyond "play", "win" and "play_as_role" (``_matches_challenge``).
CONDITION_WIN_AS_ROLE = "win_as_role"
CONDITION_PLAY_DISTINCT_TYPES = "play_distinct_types"

# Seed data for challenge definitions
CHALLENGE_DEFINITIONS: list[dict] = [
    # Daily challenges — play-based
    {
        "code": "daily_play_any",
        "description": "Play any game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": None,
        "condition": "play",
        "role": None,
    },
    {
        "code": "daily_play_undercover",
        "description": "Play an Undercover game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "undercover",
        "condition": "play",
        "role": None,
    },
    {
        "code": "daily_play_codenames",
        "description": "Play a Codenames game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "codenames",
        "condition": "play",
        "role": None,
    },
    # Daily challenges — win-based
    {
        "code": "daily_win_any",
        "description": "Win any game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": None,
        "condition": "win",
        "role": None,
    },
    {
        "code": "daily_win_undercover",
        "description": "Win an Undercover game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "undercover",
        "condition": "win",
        "role": None,
    },
    {
        "code": "daily_win_codenames",
        "description": "Win a Codenames game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "codenames",
        "condition": "win",
        "role": None,
    },
    # Daily challenges — Word Quiz
    {
        "code": "daily_play_wordquiz",
        "description": "Play a Word Quiz game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "word_quiz",
        "condition": "play",
        "role": None,
    },
    {
        "code": "daily_win_wordquiz",
        "description": "Win a Word Quiz game",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "word_quiz",
        "condition": "win",
        "role": None,
    },
    # Daily challenges — role-based
    {
        "code": "daily_play_spymaster",
        "description": "Play as Spymaster in Codenames",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "codenames",
        "condition": "play_as_role",
        "role": "spymaster",
    },
    {
        "code": "daily_play_operative",
        "description": "Play as Operative in Codenames",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "codenames",
        "condition": "play_as_role",
        "role": "operative",
    },
    {
        "code": "daily_play_civilian",
        "description": "Play as Civilian in Undercover",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "undercover",
        "condition": "play_as_role",
        "role": "civilian",
    },
    {
        "code": "daily_play_undercover_role",
        "description": "Play as Undercover in Undercover",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "undercover",
        "condition": "play_as_role",
        "role": "undercover",
    },
    {
        "code": "daily_play_mrwhite",
        "description": "Play as Mr. White in Undercover",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 1,
        "game_type": "undercover",
        "condition": "play_as_role",
        "role": "mr_white",
    },
    # Daily challenges — multi-game
    {
        "code": "daily_play_2",
        "description": "Play 2 games today",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 2,
        "game_type": None,
        "condition": "play",
        "role": None,
    },
    {
        "code": "daily_play_3",
        "description": "Play 3 games today",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 3,
        "game_type": None,
        "condition": "play",
        "role": None,
    },
    {
        "code": "daily_win_2",
        "description": "Win 2 games today",
        "challenge_type": ChallengeType.DAILY,
        "target_count": 2,
        "game_type": None,
        "condition": "win",
        "role": None,
    },
    # Weekly challenges
    {
        "code": "weekly_play_3",
        "description": "Play 3 games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": None,
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_play_5",
        "description": "Play 5 games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 5,
        "game_type": None,
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_play_10",
        "description": "Play 10 games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 10,
        "game_type": None,
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_win_2",
        "description": "Win 2 games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 2,
        "game_type": None,
        "condition": "win",
        "role": None,
    },
    {
        "code": "weekly_win_3",
        "description": "Win 3 games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": None,
        "condition": "win",
        "role": None,
    },
    {
        "code": "weekly_win_5",
        "description": "Win 5 games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 5,
        "game_type": None,
        "condition": "win",
        "role": None,
    },
    {
        "code": "weekly_play_both",
        "description": "Play both Undercover and Codenames",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 2,
        "game_type": None,
        "condition": CONDITION_PLAY_DISTINCT_TYPES,
        "role": None,
    },
    {
        "code": "weekly_play_all_3",
        "description": "Play 3 different games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": None,
        "condition": CONDITION_PLAY_DISTINCT_TYPES,
        "role": None,
    },
    # Weekly challenges — game-specific
    {
        "code": "weekly_play_undercover_3",
        "description": "Play 3 Undercover games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": "undercover",
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_play_codenames_3",
        "description": "Play 3 Codenames games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": "codenames",
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_play_wordquiz_3",
        "description": "Play 3 Word Quiz games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": "word_quiz",
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_win_undercover_2",
        "description": "Win 2 Undercover games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 2,
        "game_type": "undercover",
        "condition": "win",
        "role": None,
    },
    {
        "code": "weekly_win_codenames_2",
        "description": "Win 2 Codenames games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 2,
        "game_type": "codenames",
        "condition": "win",
        "role": None,
    },
    {
        "code": "weekly_win_wordquiz_2",
        "description": "Win 2 Word Quiz games this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 2,
        "game_type": "word_quiz",
        "condition": "win",
        "role": None,
    },
    # Weekly challenges — role-based
    {
        "code": "weekly_play_spymaster_3",
        "description": "Play as Spymaster 3 times this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": "codenames",
        "condition": "play_as_role",
        "role": "spymaster",
    },
    {
        "code": "weekly_win_undercover_role",
        "description": "Win as the Undercover agent this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 1,
        "game_type": "undercover",
        "condition": CONDITION_WIN_AS_ROLE,
        "role": "undercover",
    },
]

# The game types a CONDITION_PLAY_DISTINCT_TYPES challenge counts, by code. Its
# ``UserChallenge.progress`` holds a bitmask over this tuple (bit i = the i-th type has
# been played; no new column, ``user_challenge`` exists in production) and is shown as
# the number of bits set (``_progress_shown``). Review R7: both used to be plain "play"
# counts, so two quizzes completed "Play both Undercover and Codenames" and the same
# game three times "Play 3 different games".
DISTINCT_TYPE_CHALLENGES: dict[str, tuple[str, ...]] = {
    "weekly_play_both": (GameType.UNDERCOVER.value, GameType.CODENAMES.value),
    "weekly_play_all_3": tuple(game_type.value for game_type in GameType),
}

DAILY_CHALLENGE_COUNT = 3
WEEKLY_CHALLENGE_COUNT = 2


class ChallengeController:
    """Daily and weekly challenges.

    ``record_game_end`` (game_end_stats) is what moves them: for every scorable player
    of every finished game it calls ``assign_missing_challenges`` then
    ``check_progress``, both with ``commit=False`` because it runs inside
    ``get_game_lock`` (transaction scoped on PostgreSQL). ``check_progress`` used to
    have no caller at all, so every challenge on /challenges stayed at 0/N (BR-03).
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._definitions: Sequence[ChallengeDefinition] | None = None

    async def _all_definitions(self) -> Sequence[ChallengeDefinition]:
        """The challenge definitions, read once per controller instance.

        One controller serves every player of a game end, inside the game lock, so a
        12-player game reads the table once instead of twice per player. Memoised on
        the instance, never in the process-wide cache: they are session-bound ORM rows
        (see ``AchievementController._all_definitions``).
        """
        if self._definitions is None:
            self._definitions = (await self.session.exec(select(ChallengeDefinition))).all()
        return self._definitions

    async def seed_challenges(self) -> None:
        """Upsert every ChallengeDefinition by code: insert the missing, bring the stored up to date.

        It used to insert missing codes only, so a corrected definition (review R7: the
        Undercover-role win, the distinct-game challenges) never reached a database that
        already had the row — production keeps it from the first ``--seed``. Like the
        content seeds, CHALLENGE_DEFINITIONS is the source of truth; a stored code that
        is no longer in it is left alone (users' rows point at it).
        """
        stored = {d.code: d for d in (await self.session.exec(select(ChallengeDefinition))).all()}

        for defn_data in CHALLENGE_DEFINITIONS:
            definition = stored.get(defn_data["code"])
            if definition is None:
                self.session.add(ChallengeDefinition(**defn_data))
                continue
            for field, value in defn_data.items():
                setattr(definition, field, value)
            self.session.add(definition)

        await self.session.commit()
        self._definitions = None  # the memo above is now stale

    async def _active_rows(self, user_id: UUID, now: datetime) -> Sequence[UserChallenge]:
        """The user's challenges that have not expired yet (completed ones included)."""
        return (
            await self.session.exec(
                select(UserChallenge).where(
                    UserChallenge.user_id == user_id,
                    UserChallenge.expires_at > now,
                )
            )
        ).all()

    async def load_active(self, user_ids: Sequence[UUID]) -> dict[UUID, list[UserChallenge]]:
        """The unexpired challenges of these users (completed ones included), by user.

        ONE query for a whole game end (BDP-07): ``assign_missing_challenges`` and
        ``check_progress`` take a user's list as ``active`` instead of each reading the
        table again, once per player, inside the game lock.
        """
        by_user: dict[UUID, list[UserChallenge]] = {user_id: [] for user_id in user_ids}
        if not user_ids:
            return by_user
        rows = (
            await self.session.exec(
                select(UserChallenge).where(
                    UserChallenge.user_id.in_(user_ids),  # ty: ignore[unresolved-attribute]
                    UserChallenge.expires_at > datetime.now(UTC),
                )
            )
        ).all()
        for row in rows:
            by_user.setdefault(row.user_id, []).append(row)
        return by_user

    async def assign_missing_challenges(
        self, user_id: UUID, *, commit: bool = True, active: list[UserChallenge] | None = None
    ) -> None:
        """Fill the user's free daily and weekly slots.

        Assignment used to happen only when the player opened /challenges, so the games
        they played before ever looking counted for nothing. The game end calls this
        with ``commit=False`` before ``check_progress``.

        :param active: the user's list from ``load_active`` (read here when omitted);
            the new rows are appended to it, so ``check_progress`` counts them.
        """
        now = datetime.now(UTC)
        if active is None:
            active = list(await self._active_rows(user_id, now))
        active_daily = [c for c in active if self._is_daily(c)]
        active_weekly = [c for c in active if not self._is_daily(c)]
        if len(active_daily) < DAILY_CHALLENGE_COUNT or len(active_weekly) < WEEKLY_CHALLENGE_COUNT:
            active.extend(
                await self._assign_missing_challenges(user_id, active_daily, active_weekly, now, commit=commit)
            )

    async def get_active_challenges(self, user_id: UUID) -> Sequence[ActiveChallenge]:
        """Get active (non-expired) challenges for a user, assigning new ones if needed."""
        now = datetime.now(UTC)

        # Fetch current non-expired challenges
        active = await self._active_rows(user_id, now)

        # Check if we need to assign new daily/weekly challenges
        active_daily = [c for c in active if self._is_daily(c)]
        active_weekly = [c for c in active if not self._is_daily(c)]

        needs_assign = len(active_daily) < DAILY_CHALLENGE_COUNT or len(active_weekly) < WEEKLY_CHALLENGE_COUNT

        if needs_assign:
            await self._assign_missing_challenges(user_id, active_daily, active_weekly, now)
            # Re-fetch
            active = await self._active_rows(user_id, now)

        # Load definitions for the active challenges
        challenge_ids = [c.challenge_id for c in active]
        if not challenge_ids:
            return []

        definitions = (
            await self.session.exec(select(ChallengeDefinition).where(ChallengeDefinition.id.in_(challenge_ids)))  # ty: ignore[unresolved-attribute]
        ).all()
        defn_map = {d.id: d for d in definitions}

        results: list[ActiveChallenge] = []
        for uc in active:
            defn = defn_map.get(uc.challenge_id)
            if not defn:
                continue
            results.append(
                ActiveChallenge(
                    id=uc.id,
                    code=defn.code,
                    description=defn.description,
                    challenge_type=defn.challenge_type.value,
                    target_count=defn.target_count,
                    game_type=defn.game_type,
                    condition=defn.condition,
                    role=defn.role,
                    progress=_progress_shown(defn, uc),
                    completed=uc.completed,
                    assigned_at=uc.assigned_at.isoformat(),
                    expires_at=uc.expires_at.isoformat(),
                )
            )

        return results

    async def check_progress(
        self,
        user_id: UUID,
        game_type: str,
        won: bool,
        role: str | None,
        *,
        commit: bool = True,
        active: list[UserChallenge] | None = None,
    ) -> list[ActiveChallenge]:
        """Check and update challenge progress after a game. Returns newly completed challenges.

        :param commit: False from ``record_game_end``, which runs inside the game lock:
            a commit there would release the transaction-scoped lock mid-block.
        :param active: the user's list from ``load_active`` (read here when omitted).
        """
        now = datetime.now(UTC)

        if active is None:
            active = list(await self._active_rows(user_id, now))
        active = [c for c in active if not c.completed]

        if not active:
            return []

        defn_map = {d.id: d for d in await self._all_definitions()}

        newly_completed: list[ActiveChallenge] = []

        for uc in active:
            defn = defn_map.get(uc.challenge_id)
            if not defn:
                continue

            if not self._advance(defn, uc, game_type, won, role):
                continue

            if _progress_shown(defn, uc) >= defn.target_count:
                uc.completed = True
                newly_completed.append(
                    ActiveChallenge(
                        id=uc.id,
                        code=defn.code,
                        description=defn.description,
                        challenge_type=defn.challenge_type.value,
                        target_count=defn.target_count,
                        game_type=defn.game_type,
                        condition=defn.condition,
                        role=defn.role,
                        progress=_progress_shown(defn, uc),
                        completed=uc.completed,
                        assigned_at=uc.assigned_at.isoformat(),
                        expires_at=uc.expires_at.isoformat(),
                    )
                )

            self.session.add(uc)

        if commit:
            await self.session.commit()

        if newly_completed:
            logger.info("User {user_id} completed {count} challenges", user_id=user_id, count=len(newly_completed))

        return newly_completed

    async def _assign_missing_challenges(
        self,
        user_id: UUID,
        active_daily: list[UserChallenge],
        active_weekly: list[UserChallenge],
        now: datetime,
        *,
        commit: bool = True,
    ) -> list[UserChallenge]:
        """Assign random daily and weekly challenges to fill missing slots. Returns the new rows."""
        all_definitions = await self._all_definitions()
        assigned: list[UserChallenge] = []
        daily_defs = [d for d in all_definitions if d.challenge_type == ChallengeType.DAILY]
        weekly_defs = [d for d in all_definitions if d.challenge_type == ChallengeType.WEEKLY]

        # Existing challenge definition IDs
        active_daily_ids = {c.challenge_id for c in active_daily}
        active_weekly_ids = {c.challenge_id for c in active_weekly}

        # Assign daily challenges
        needed_daily = DAILY_CHALLENGE_COUNT - len(active_daily)
        if needed_daily > 0 and daily_defs:
            available = [d for d in daily_defs if d.id not in active_daily_ids]
            if not available:
                available = daily_defs
            chosen = random.sample(available, min(needed_daily, len(available)))
            # Daily expires at end of day (midnight UTC)
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            for defn in chosen:
                uc = UserChallenge(
                    user_id=user_id,
                    challenge_id=defn.id,
                    progress=0,
                    completed=False,
                    assigned_at=now,
                    expires_at=tomorrow,
                )
                self.session.add(uc)
                assigned.append(uc)

        # Assign weekly challenges
        needed_weekly = WEEKLY_CHALLENGE_COUNT - len(active_weekly)
        if needed_weekly > 0 and weekly_defs:
            available = [d for d in weekly_defs if d.id not in active_weekly_ids]
            if not available:
                available = weekly_defs
            chosen = random.sample(available, min(needed_weekly, len(available)))
            # Weekly expires in 7 days
            next_week = now + timedelta(days=7)
            for defn in chosen:
                uc = UserChallenge(
                    user_id=user_id,
                    challenge_id=defn.id,
                    progress=0,
                    completed=False,
                    assigned_at=now,
                    expires_at=next_week,
                )
                self.session.add(uc)
                assigned.append(uc)

        if commit:
            await self.session.commit()
        return assigned

    def _is_daily(self, uc: UserChallenge) -> bool:
        """Check if a user challenge expires within ~24 hours (daily challenge heuristic)."""
        duration = uc.expires_at - uc.assigned_at
        return duration <= timedelta(days=1, hours=1)

    def _advance(
        self, defn: ChallengeDefinition, uc: UserChallenge, game_type: str, won: bool, role: str | None
    ) -> bool:
        """Move ``uc`` forward for this game when it counts. True when it moved.

        A distinct-types challenge sets the game type's bit, once; every other one counts
        the game when ``_matches_challenge`` says it matches.
        """
        if defn.condition == CONDITION_PLAY_DISTINCT_TYPES:
            bit = _distinct_type_bit(defn.code, game_type)
            if bit == 0 or uc.progress & bit:
                return False
            uc.progress |= bit
            return True
        if self._matches_challenge(defn, game_type, won, role):
            uc.progress += 1
            return True
        return False

    def _matches_challenge(
        self,
        defn: ChallengeDefinition,
        game_type: str,
        won: bool,
        role: str | None,
    ) -> bool:
        """Check if a game result matches a challenge's conditions."""
        # Check game_type filter
        if defn.game_type and defn.game_type != game_type:
            return False

        if defn.condition == "play":
            return True
        if defn.condition == "win":
            return won
        if defn.condition == "play_as_role":
            return defn.role is not None and defn.role == role
        if defn.condition == CONDITION_WIN_AS_ROLE:
            return won and defn.role is not None and defn.role == role

        return False


def _distinct_type_bit(code: str, game_type: str) -> int:
    """The bit ``game_type`` sets in a distinct-types challenge's progress; 0 when it does not count."""
    counted = DISTINCT_TYPE_CHALLENGES.get(code, ())
    return 1 << counted.index(game_type) if game_type in counted else 0


def _progress_shown(defn: ChallengeDefinition, uc: UserChallenge) -> int:
    """The progress a player reads: a count, or for a distinct-types challenge the types played."""
    if defn.condition == CONDITION_PLAY_DISTINCT_TYPES:
        return uc.progress.bit_count()
    return uc.progress
