from sqlmodel import select

from ipg.api.controllers.achievement import ACHIEVEMENT_DEFINITIONS, AchievementController
from ipg.api.controllers.stats import StatsController
from ipg.api.models.stats import AchievementDefinition, UserStats


async def test_seed_achievements(achievement_controller: AchievementController):
    """Seeding achievements creates exactly as many definitions as ACHIEVEMENT_DEFINITIONS contains."""

    # Arrange — no prior definitions in the database

    # Act
    await achievement_controller.seed_achievements()

    # Assert
    result = await achievement_controller.session.exec(select(AchievementDefinition))
    definitions = result.all()
    assert len(definitions) == len(ACHIEVEMENT_DEFINITIONS)


async def test_seed_achievements_idempotent(achievement_controller: AchievementController):
    """Seeding achievements twice does not duplicate any definition records."""

    # Arrange
    await achievement_controller.seed_achievements()

    # Act
    await achievement_controller.seed_achievements()

    # Assert
    result = await achievement_controller.session.exec(select(AchievementDefinition))
    definitions = result.all()
    assert len(definitions) == len(ACHIEVEMENT_DEFINITIONS)


async def test_get_user_achievements_empty(achievement_controller: AchievementController, create_user):
    """A new user with no unlocked achievements returns all definitions with no progress."""

    # Arrange
    user = await create_user(username="noachieve", email="noachieve@test.com")
    await achievement_controller.seed_achievements()

    # Act
    achievements = await achievement_controller.get_user_achievements(user.id)

    # Assert — all definitions returned, none unlocked
    assert len(achievements) == len(ACHIEVEMENT_DEFINITIONS)
    assert all(not a.unlocked for a in achievements)
    assert all(a.progress == 0 for a in achievements)


async def test_unlock_achievement_creates_record(achievement_controller: AchievementController, create_user):
    """Unlocking an achievement creates a UserAchievement with correct user_id, achievement_id, and unlocked_at."""

    # Arrange
    user = await create_user(username="unlock", email="unlock@test.com")
    await achievement_controller.seed_achievements()
    result = await achievement_controller.session.exec(select(AchievementDefinition))
    defn = result.first()

    # Act
    ua = await achievement_controller.unlock_achievement(user.id, defn.id)

    # Assert
    assert ua.id is not None
    assert ua.user_id == user.id
    assert ua.achievement_id == defn.id
    assert ua.unlocked_at is not None
    assert ua.progress == 1
    assert ua.created_at is not None
    assert ua.updated_at is not None


async def test_unlock_achievement_idempotent(achievement_controller: AchievementController, create_user):
    """Unlocking the same achievement twice returns the same record without creating a duplicate."""

    # Arrange
    user = await create_user(username="idempotent", email="idem@test.com")
    await achievement_controller.seed_achievements()
    result = await achievement_controller.session.exec(select(AchievementDefinition))
    defn = result.first()
    ua1 = await achievement_controller.unlock_achievement(user.id, defn.id)

    # Act
    ua2 = await achievement_controller.unlock_achievement(user.id, defn.id)

    # Assert
    assert ua1.id == ua2.id
    assert ua1.achievement_id == ua2.achievement_id
    assert ua1.user_id == ua2.user_id


async def test_check_achievements_unlocks_on_threshold(
    achievement_controller: AchievementController,
    stats_controller: StatsController,
    create_user,
):
    """Playing and winning one game meets the threshold for first_game and first_win achievements."""

    # Arrange
    user = await create_user(username="threshold", email="threshold@test.com")
    await achievement_controller.seed_achievements()
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Act
    newly_unlocked = await achievement_controller.check_achievements(user.id, stats)

    # Assert
    unlocked_codes = [d.code for d in newly_unlocked]
    assert "first_game" in unlocked_codes
    assert "first_win" in unlocked_codes


async def test_check_achievements_skips_already_unlocked(
    achievement_controller: AchievementController,
    stats_controller: StatsController,
    create_user,
):
    """Checking achievements a second time with the same stats does not re-unlock previously unlocked ones."""

    # Arrange
    user = await create_user(username="skipunlocked", email="skip@test.com")
    await achievement_controller.seed_achievements()
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")
    first_unlocked = await achievement_controller.check_achievements(user.id, stats)

    # Act
    second_unlocked = await achievement_controller.check_achievements(user.id, stats)

    # Assert
    first_codes = {d.code for d in first_unlocked}
    second_codes = {d.code for d in second_unlocked}
    assert len(first_codes) > 0
    assert len(first_codes & second_codes) == 0


async def test_check_achievements_skips_special(
    achievement_controller: AchievementController,
    create_user,
):
    """Special achievements with stat_field=None are never auto-unlocked, even with very high stats."""

    # Arrange
    user = await create_user(username="special", email="special@test.com")
    await achievement_controller.seed_achievements()
    stats = UserStats(
        user_id=user.id,
        total_games_played=1000,
        total_games_won=500,
    )

    # Act
    newly_unlocked = await achievement_controller.check_achievements(user.id, stats)

    # Assert
    unlocked_codes = [d.code for d in newly_unlocked]
    assert "assassin_finder" not in unlocked_codes
    assert "unanimous_vote" not in unlocked_codes
    assert "last_survivor" not in unlocked_codes
    assert "perfect_undercover" not in unlocked_codes
    assert "sweep_victory" not in unlocked_codes


async def test_check_achievements_threshold_not_met(
    achievement_controller: AchievementController,
    create_user,
):
    """A user with all-zero stats does not unlock any achievements."""

    # Arrange
    user = await create_user(username="notmet", email="notmet@test.com")
    await achievement_controller.seed_achievements()
    stats = UserStats(user_id=user.id)

    # Act
    newly_unlocked = await achievement_controller.check_achievements(user.id, stats)

    # Assert
    assert len(newly_unlocked) == 0


async def test_check_achievements_high_stats_multiple_unlocks(
    achievement_controller: AchievementController,
    create_user,
):
    """High stat values unlock many achievements spanning beginner, social, and streak categories."""

    # Arrange
    user = await create_user(username="multi", email="multi@test.com")
    await achievement_controller.seed_achievements()
    stats = UserStats(
        user_id=user.id,
        total_games_played=100,
        total_games_won=50,
        undercover_games_played=60,
        undercover_games_won=30,
        civilian_wins=25,
        rooms_created=5,
        longest_win_streak=5,
    )

    # Act
    newly_unlocked = await achievement_controller.check_achievements(user.id, stats)

    # Assert
    unlocked_codes = [d.code for d in newly_unlocked]
    assert "first_game" in unlocked_codes
    assert "first_win" in unlocked_codes
    assert "play_10_games" in unlocked_codes
    assert "play_50_games" in unlocked_codes
    assert "play_100_games" in unlocked_codes
    assert "host_5_rooms" in unlocked_codes
    assert "win_streak_3" in unlocked_codes
    assert "win_streak_5" in unlocked_codes


async def test_get_user_achievements_after_unlock(
    achievement_controller: AchievementController,
    create_user,
):
    """After unlocking one achievement, get_user_achievements returns all definitions with progress."""

    # Arrange
    user = await create_user(username="afterunlock", email="afterunlock@test.com")
    await achievement_controller.seed_achievements()
    result = await achievement_controller.session.exec(select(AchievementDefinition))
    defn = result.first()
    await achievement_controller.unlock_achievement(user.id, defn.id)

    # Act
    achievements = await achievement_controller.get_user_achievements(user.id)

    # Assert — returns all definitions, with the unlocked one marked
    assert len(achievements) == len(ACHIEVEMENT_DEFINITIONS)
    unlocked = [a for a in achievements if a.unlocked]
    assert len(unlocked) == 1
    assert unlocked[0].code == defn.code
    assert unlocked[0].name == defn.name
    assert unlocked[0].progress == 1
