from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.stats import (
    AchievementCategory,
    AchievementDefinition,
    UserAchievement,
    UserStats,
)
from ipg.api.schemas.stats import AchievementWithProgress

# All achievement definitions to seed into the database
ACHIEVEMENT_DEFINITIONS: list[dict] = [
    # ── BEGINNER ──────────────────────────────────────────────────────────
    {
        "code": "first_game",
        "category": AchievementCategory.BEGINNER,
        "name": "First Steps",
        "description": "Play your first game",
        "icon": "star",
        "threshold": 1,
        "tier": 1,
        "game_type": None,
        "stat_field": "total_games_played",
    },
    {
        "code": "first_win",
        "category": AchievementCategory.BEGINNER,
        "name": "Taste of Victory",
        "description": "Win your first game",
        "icon": "trophy",
        "threshold": 1,
        "tier": 1,
        "game_type": None,
        "stat_field": "total_games_won",
    },
    {
        "code": "first_room",
        "category": AchievementCategory.BEGINNER,
        "name": "Host With the Most",
        "description": "Create your first room",
        "icon": "door",
        "threshold": 1,
        "tier": 1,
        "game_type": None,
        "stat_field": "rooms_created",
    },
    # ── UNDERCOVER_MASTER ─────────────────────────────────────────────────
    {
        "code": "civilian_wins_5",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Good Citizen",
        "description": "Win 5 games as a Civilian",
        "icon": "shield",
        "threshold": 5,
        "tier": 1,
        "game_type": "undercover",
        "stat_field": "civilian_wins",
    },
    {
        "code": "civilian_wins_25",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Trusted Citizen",
        "description": "Win 25 games as a Civilian",
        "icon": "shield",
        "threshold": 25,
        "tier": 3,
        "game_type": "undercover",
        "stat_field": "civilian_wins",
    },
    {
        "code": "civilian_wins_100",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Citizen Legend",
        "description": "Win 100 games as a Civilian",
        "icon": "shield",
        "threshold": 100,
        "tier": 5,
        "game_type": "undercover",
        "stat_field": "civilian_wins",
    },
    {
        "code": "undercover_wins_3",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Sneaky",
        "description": "Win 3 games as Undercover",
        "icon": "mask",
        "threshold": 3,
        "tier": 1,
        "game_type": "undercover",
        "stat_field": "undercover_wins",
    },
    {
        "code": "undercover_wins_10",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Master of Disguise",
        "description": "Win 10 games as Undercover",
        "icon": "mask",
        "threshold": 10,
        "tier": 3,
        "game_type": "undercover",
        "stat_field": "undercover_wins",
    },
    {
        "code": "undercover_wins_50",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Shadow Lord",
        "description": "Win 50 games as Undercover",
        "icon": "mask",
        "threshold": 50,
        "tier": 5,
        "game_type": "undercover",
        "stat_field": "undercover_wins",
    },
    {
        "code": "mr_white_wins_1",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "White Out",
        "description": "Win your first game as Mr. White",
        "icon": "ghost",
        "threshold": 1,
        "tier": 2,
        "game_type": "undercover",
        "stat_field": "mr_white_wins",
    },
    {
        "code": "mr_white_wins_5",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Ghost Protocol",
        "description": "Win 5 games as Mr. White",
        "icon": "ghost",
        "threshold": 5,
        "tier": 4,
        "game_type": "undercover",
        "stat_field": "mr_white_wins",
    },
    {
        "code": "mr_white_wins_25",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Phantom Menace",
        "description": "Win 25 games as Mr. White",
        "icon": "ghost",
        "threshold": 25,
        "tier": 6,
        "game_type": "undercover",
        "stat_field": "mr_white_wins",
    },
    {
        "code": "mr_white_guess_1",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Lucky Guess",
        "description": "Correctly guess the word as Mr. White",
        "icon": "lightbulb",
        "threshold": 1,
        "tier": 2,
        "game_type": "undercover",
        "stat_field": "mr_white_correct_guesses",
    },
    {
        "code": "mr_white_guess_5",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Mind Reader",
        "description": "Correctly guess the word as Mr. White 5 times",
        "icon": "lightbulb",
        "threshold": 5,
        "tier": 4,
        "game_type": "undercover",
        "stat_field": "mr_white_correct_guesses",
    },
    {
        "code": "perfect_undercover",
        "category": AchievementCategory.UNDERCOVER_MASTER,
        "name": "Perfect Infiltrator",
        "description": "Win as Undercover without receiving any votes",
        "icon": "ninja",
        "threshold": 1,
        "tier": 5,
        "game_type": "undercover",
        "stat_field": None,  # Special: checked via custom logic
    },
    # ── CODENAMES_MASTER ──────────────────────────────────────────────────
    {
        "code": "spymaster_wins_5",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Junior Spymaster",
        "description": "Win 5 games as Spymaster",
        "icon": "brain",
        "threshold": 5,
        "tier": 1,
        "game_type": "codenames",
        "stat_field": "spymaster_wins",
    },
    {
        "code": "spymaster_wins_25",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Senior Spymaster",
        "description": "Win 25 games as Spymaster",
        "icon": "brain",
        "threshold": 25,
        "tier": 3,
        "game_type": "codenames",
        "stat_field": "spymaster_wins",
    },
    {
        "code": "spymaster_wins_100",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Legendary Spymaster",
        "description": "Win 100 games as Spymaster",
        "icon": "brain",
        "threshold": 100,
        "tier": 5,
        "game_type": "codenames",
        "stat_field": "spymaster_wins",
    },
    {
        "code": "operative_wins_5",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Field Agent",
        "description": "Win 5 games as Operative",
        "icon": "spy",
        "threshold": 5,
        "tier": 1,
        "game_type": "codenames",
        "stat_field": "operative_wins",
    },
    {
        "code": "operative_wins_25",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Special Agent",
        "description": "Win 25 games as Operative",
        "icon": "spy",
        "threshold": 25,
        "tier": 3,
        "game_type": "codenames",
        "stat_field": "operative_wins",
    },
    {
        "code": "operative_wins_100",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Elite Operative",
        "description": "Win 100 games as Operative",
        "icon": "spy",
        "threshold": 100,
        "tier": 5,
        "game_type": "codenames",
        "stat_field": "operative_wins",
    },
    {
        "code": "perfect_round_1",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Flawless Round",
        "description": "Complete a perfect round in Codenames",
        "icon": "sparkle",
        "threshold": 1,
        "tier": 3,
        "game_type": "codenames",
        "stat_field": "codenames_perfect_rounds",
    },
    {
        "code": "sweep_victory",
        "category": AchievementCategory.CODENAMES_MASTER,
        "name": "Clean Sweep",
        "description": "Win a Codenames game without any wrong guesses",
        "icon": "broom",
        "threshold": 1,
        "tier": 4,
        "game_type": "codenames",
        "stat_field": None,  # Special: checked via custom logic
    },
    # ── SOCIAL ────────────────────────────────────────────────────────────
    {
        "code": "play_10_games",
        "category": AchievementCategory.SOCIAL,
        "name": "Getting Started",
        "description": "Play 10 games",
        "icon": "gamepad",
        "threshold": 10,
        "tier": 1,
        "game_type": None,
        "stat_field": "total_games_played",
    },
    {
        "code": "play_50_games",
        "category": AchievementCategory.SOCIAL,
        "name": "Regular Player",
        "description": "Play 50 games",
        "icon": "gamepad",
        "threshold": 50,
        "tier": 2,
        "game_type": None,
        "stat_field": "total_games_played",
    },
    {
        "code": "play_100_games",
        "category": AchievementCategory.SOCIAL,
        "name": "Dedicated Player",
        "description": "Play 100 games",
        "icon": "gamepad",
        "threshold": 100,
        "tier": 3,
        "game_type": None,
        "stat_field": "total_games_played",
    },
    {
        "code": "play_500_games",
        "category": AchievementCategory.SOCIAL,
        "name": "Veteran",
        "description": "Play 500 games",
        "icon": "medal",
        "threshold": 500,
        "tier": 5,
        "game_type": None,
        "stat_field": "total_games_played",
    },
    {
        "code": "host_5_rooms",
        "category": AchievementCategory.SOCIAL,
        "name": "Party Starter",
        "description": "Create 5 rooms",
        "icon": "house",
        "threshold": 5,
        "tier": 1,
        "game_type": None,
        "stat_field": "rooms_created",
    },
    {
        "code": "host_25_rooms",
        "category": AchievementCategory.SOCIAL,
        "name": "Event Organizer",
        "description": "Create 25 rooms",
        "icon": "house",
        "threshold": 25,
        "tier": 3,
        "game_type": None,
        "stat_field": "rooms_created",
    },
    {
        "code": "host_100_rooms",
        "category": AchievementCategory.SOCIAL,
        "name": "Community Leader",
        "description": "Create 100 rooms",
        "icon": "crown",
        "threshold": 100,
        "tier": 5,
        "game_type": None,
        "stat_field": "rooms_created",
    },
    # ── STREAK ────────────────────────────────────────────────────────────
    {
        "code": "win_streak_3",
        "category": AchievementCategory.STREAK,
        "name": "Hat Trick",
        "description": "Win 3 games in a row",
        "icon": "fire",
        "threshold": 3,
        "tier": 1,
        "game_type": None,
        "stat_field": "longest_win_streak",
    },
    {
        "code": "win_streak_5",
        "category": AchievementCategory.STREAK,
        "name": "On Fire",
        "description": "Win 5 games in a row",
        "icon": "fire",
        "threshold": 5,
        "tier": 2,
        "game_type": None,
        "stat_field": "longest_win_streak",
    },
    {
        "code": "win_streak_10",
        "category": AchievementCategory.STREAK,
        "name": "Unstoppable",
        "description": "Win 10 games in a row",
        "icon": "fire",
        "threshold": 10,
        "tier": 4,
        "game_type": None,
        "stat_field": "longest_win_streak",
    },
    {
        "code": "win_streak_20",
        "category": AchievementCategory.STREAK,
        "name": "Legendary Streak",
        "description": "Win 20 games in a row",
        "icon": "fire",
        "threshold": 20,
        "tier": 6,
        "game_type": None,
        "stat_field": "longest_win_streak",
    },
    {
        "code": "play_streak_7",
        "category": AchievementCategory.STREAK,
        "name": "Weekly Warrior",
        "description": "Play games 7 days in a row",
        "icon": "calendar",
        "threshold": 7,
        "tier": 2,
        "game_type": None,
        "stat_field": "longest_play_streak_days",
    },
    {
        "code": "play_streak_30",
        "category": AchievementCategory.STREAK,
        "name": "Monthly Devotee",
        "description": "Play games 30 days in a row",
        "icon": "calendar",
        "threshold": 30,
        "tier": 4,
        "game_type": None,
        "stat_field": "longest_play_streak_days",
    },
    {
        "code": "play_streak_100",
        "category": AchievementCategory.STREAK,
        "name": "Century Player",
        "description": "Play games 100 days in a row",
        "icon": "calendar",
        "threshold": 100,
        "tier": 6,
        "game_type": None,
        "stat_field": "longest_play_streak_days",
    },
    # ── SPECIAL ───────────────────────────────────────────────────────────
    {
        "code": "assassin_finder",
        "category": AchievementCategory.SPECIAL,
        "name": "Assassin Finder",
        "description": "Pick the Assassin card in Codenames",
        "icon": "skull",
        "threshold": 1,
        "tier": 2,
        "game_type": "codenames",
        "stat_field": None,
    },
    {
        "code": "unanimous_vote",
        "category": AchievementCategory.SPECIAL,
        "name": "Unanimous Decision",
        "description": "Be part of a unanimous vote in Undercover",
        "icon": "handshake",
        "threshold": 1,
        "tier": 2,
        "game_type": "undercover",
        "stat_field": None,
    },
    {
        "code": "last_survivor",
        "category": AchievementCategory.SPECIAL,
        "name": "Last One Standing",
        "description": "Be the last surviving player in an Undercover game",
        "icon": "crown",
        "threshold": 1,
        "tier": 3,
        "game_type": "undercover",
        "stat_field": None,
    },
]

# Mapping from achievement code to the stat field it checks
_ACHIEVEMENT_STAT_MAP: dict[str, str | None] = {defn["code"]: defn["stat_field"] for defn in ACHIEVEMENT_DEFINITIONS}


class AchievementController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_achievements(self, user_id: UUID) -> Sequence[AchievementWithProgress]:
        """Get all achievements with definitions and user progress.

        Returns all achievement definitions. For each, includes the user's
        current progress and unlock status.

        :param user_id: The id of the user.
        :return: A list of AchievementWithProgress records.
        """
        # Load all definitions
        all_definitions = (await self.session.exec(select(AchievementDefinition))).all()

        # Load user's achievement progress
        user_achievements = (
            await self.session.exec(select(UserAchievement).where(UserAchievement.user_id == user_id))
        ).all()

        # Map achievement_id -> UserAchievement for quick lookup
        ua_map: dict[UUID, UserAchievement] = {ua.achievement_id: ua for ua in user_achievements}

        entries: list[AchievementWithProgress] = []
        for defn in all_definitions:
            ua = ua_map.get(defn.id)  # type: ignore[arg-type]
            entries.append(
                AchievementWithProgress(
                    code=defn.code,
                    name=defn.name,
                    description=defn.description,
                    icon=defn.icon,
                    category=defn.category.value,
                    tier=defn.tier,
                    threshold=defn.threshold,
                    progress=ua.progress if ua else 0,
                    unlocked=ua.unlocked_at is not None if ua else False,
                )
            )
        return entries

    async def check_achievements(self, user_id: UUID, stats: UserStats) -> list[AchievementDefinition]:
        """Check which achievements the user has newly unlocked based on their stats.

        For each AchievementDefinition that has a stat_field mapping, this compares
        the user's current stat value against the threshold. If the threshold is met
        and the achievement has not been unlocked yet, it is unlocked and returned.

        :param user_id: The id of the user.
        :param stats: The user's current stats.
        :return: A list of newly unlocked AchievementDefinition records.
        """
        # Load all definitions
        all_definitions = (await self.session.exec(select(AchievementDefinition))).all()

        # Load already-unlocked achievement IDs for this user
        existing = await self.session.exec(
            select(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.unlocked_at.is_not(None),  # type: ignore[union-attr]
            )
        )
        unlocked_ids: set[UUID] = {ua.achievement_id for ua in existing.all()}

        newly_unlocked: list[AchievementDefinition] = []

        for defn in all_definitions:
            if defn.id in unlocked_ids:
                continue

            stat_field = _ACHIEVEMENT_STAT_MAP.get(defn.code)
            if stat_field is None:
                # Special achievements are not auto-checked via stats
                continue

            current_value = getattr(stats, stat_field, 0)
            if current_value >= defn.threshold:
                await self.unlock_achievement(user_id, defn.id)  # type: ignore[arg-type]
                newly_unlocked.append(defn)

        return newly_unlocked

    async def unlock_achievement(self, user_id: UUID, achievement_id: UUID) -> UserAchievement:
        """Unlock an achievement for a user. Creates or updates the UserAchievement record.

        :param user_id: The id of the user.
        :param achievement_id: The id of the achievement definition.
        :return: The unlocked UserAchievement record.
        """
        # Check if a record already exists
        existing = (
            await self.session.exec(
                select(UserAchievement).where(
                    UserAchievement.user_id == user_id,
                    UserAchievement.achievement_id == achievement_id,
                )
            )
        ).first()

        now = datetime.now()

        if existing is not None:
            if existing.unlocked_at is None:
                existing.unlocked_at = now
                existing.updated_at = now
                self.session.add(existing)
                await self.session.commit()
                await self.session.refresh(existing)
            return existing

        user_achievement = UserAchievement(
            user_id=user_id,
            achievement_id=achievement_id,
            progress=1,
            unlocked_at=now,
        )
        self.session.add(user_achievement)
        await self.session.commit()
        await self.session.refresh(user_achievement)
        return user_achievement

    async def seed_achievements(self) -> None:
        """Create all AchievementDefinition records if they don't already exist.

        This is idempotent -- it skips any definition whose code already exists
        in the database.
        """
        existing_codes_result = await self.session.exec(select(AchievementDefinition.code))
        existing_codes: set[str] = set(existing_codes_result.all())

        for defn_data in ACHIEVEMENT_DEFINITIONS:
            if defn_data["code"] in existing_codes:
                continue

            # Build the definition without the stat_field key (not a DB column)
            record_data = {k: v for k, v in defn_data.items() if k != "stat_field"}
            definition = AchievementDefinition(**record_data)
            self.session.add(definition)

        await self.session.commit()
