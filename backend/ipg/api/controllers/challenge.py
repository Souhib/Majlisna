import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.challenge import ChallengeDefinition, ChallengeType, UserChallenge
from ipg.api.schemas.challenge import ActiveChallenge

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
        "condition": "play",
        "role": None,
    },
    {
        "code": "weekly_play_all_3",
        "description": "Play all 3 game types this week",
        "challenge_type": ChallengeType.WEEKLY,
        "target_count": 3,
        "game_type": None,
        "condition": "play",
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
        "condition": "win",
        "role": None,
    },
]

DAILY_CHALLENGE_COUNT = 3
WEEKLY_CHALLENGE_COUNT = 2


class ChallengeController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seed_challenges(self) -> None:
        """Create all ChallengeDefinition records if they don't already exist."""
        existing_codes_result = await self.session.exec(select(ChallengeDefinition.code))
        existing_codes: set[str] = set(existing_codes_result.all())

        for defn_data in CHALLENGE_DEFINITIONS:
            if defn_data["code"] in existing_codes:
                continue
            definition = ChallengeDefinition(**defn_data)
            self.session.add(definition)

        await self.session.commit()

    async def get_active_challenges(self, user_id: UUID) -> Sequence[ActiveChallenge]:
        """Get active (non-expired) challenges for a user, assigning new ones if needed."""
        now = datetime.now(UTC)

        # Fetch current non-expired challenges
        active = (
            await self.session.exec(
                select(UserChallenge).where(
                    UserChallenge.user_id == user_id,
                    UserChallenge.expires_at > now,
                )
            )
        ).all()

        # Check if we need to assign new daily/weekly challenges
        active_daily = [c for c in active if self._is_daily(c)]
        active_weekly = [c for c in active if not self._is_daily(c)]

        needs_assign = len(active_daily) < DAILY_CHALLENGE_COUNT or len(active_weekly) < WEEKLY_CHALLENGE_COUNT

        if needs_assign:
            await self._assign_missing_challenges(user_id, active_daily, active_weekly, now)
            # Re-fetch
            active = (
                await self.session.exec(
                    select(UserChallenge).where(
                        UserChallenge.user_id == user_id,
                        UserChallenge.expires_at > now,
                    )
                )
            ).all()

        # Load definitions for the active challenges
        challenge_ids = [c.challenge_id for c in active]
        if not challenge_ids:
            return []

        definitions = (
            await self.session.exec(select(ChallengeDefinition).where(ChallengeDefinition.id.in_(challenge_ids)))  # type: ignore[union-attr]
        ).all()
        defn_map = {d.id: d for d in definitions}

        results: list[ActiveChallenge] = []
        for uc in active:
            defn = defn_map.get(uc.challenge_id)
            if not defn:
                continue
            results.append(
                ActiveChallenge(
                    id=uc.id,  # type: ignore[arg-type]
                    code=defn.code,
                    description=defn.description,
                    challenge_type=defn.challenge_type.value,
                    target_count=defn.target_count,
                    game_type=defn.game_type,
                    condition=defn.condition,
                    role=defn.role,
                    progress=uc.progress,
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
    ) -> list[ActiveChallenge]:
        """Check and update challenge progress after a game. Returns newly completed challenges."""
        now = datetime.now(UTC)

        active = (
            await self.session.exec(
                select(UserChallenge).where(
                    UserChallenge.user_id == user_id,
                    UserChallenge.expires_at > now,
                    UserChallenge.completed == False,  # noqa: E712
                )
            )
        ).all()

        if not active:
            return []

        challenge_ids = [c.challenge_id for c in active]
        definitions = (
            await self.session.exec(select(ChallengeDefinition).where(ChallengeDefinition.id.in_(challenge_ids)))  # type: ignore[union-attr]
        ).all()
        defn_map = {d.id: d for d in definitions}

        newly_completed: list[ActiveChallenge] = []

        for uc in active:
            defn = defn_map.get(uc.challenge_id)
            if not defn:
                continue

            if not self._matches_challenge(defn, game_type, won, role):
                continue

            uc.progress += 1
            if uc.progress >= defn.target_count:
                uc.completed = True
                newly_completed.append(
                    ActiveChallenge(
                        id=uc.id,  # type: ignore[arg-type]
                        code=defn.code,
                        description=defn.description,
                        challenge_type=defn.challenge_type.value,
                        target_count=defn.target_count,
                        game_type=defn.game_type,
                        condition=defn.condition,
                        role=defn.role,
                        progress=uc.progress,
                        completed=uc.completed,
                        assigned_at=uc.assigned_at.isoformat(),
                        expires_at=uc.expires_at.isoformat(),
                    )
                )

            self.session.add(uc)

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
    ) -> None:
        """Assign random daily and weekly challenges to fill missing slots."""
        # Load all definitions
        all_definitions = (await self.session.exec(select(ChallengeDefinition))).all()
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
                    challenge_id=defn.id,  # type: ignore[arg-type]
                    progress=0,
                    completed=False,
                    assigned_at=now,
                    expires_at=tomorrow,
                )
                self.session.add(uc)

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
                    challenge_id=defn.id,  # type: ignore[arg-type]
                    progress=0,
                    completed=False,
                    assigned_at=now,
                    expires_at=next_week,
                )
                self.session.add(uc)

        await self.session.commit()

    def _is_daily(self, uc: UserChallenge) -> bool:
        """Check if a user challenge expires within ~24 hours (daily challenge heuristic)."""
        duration = uc.expires_at - uc.assigned_at
        return duration <= timedelta(days=1, hours=1)

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

        return False
