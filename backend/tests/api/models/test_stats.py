"""Tests for stats model validation."""

from uuid import uuid4

from ipg.api.models.stats import AchievementCategory, AchievementDefinition, UserStats


def test_user_stats_default_values():
    """Creating UserStats with only user_id sets all counters to 0."""

    # Arrange / Act
    stats = UserStats(user_id=uuid4())

    # Assert
    assert stats.total_games_played == 0
    assert stats.total_games_won == 0
    assert stats.total_games_lost == 0
    assert stats.undercover_games_played == 0
    assert stats.codenames_games_played == 0
    assert stats.current_win_streak == 0
    assert stats.longest_win_streak == 0
    assert stats.last_played_at is None


def test_achievement_definition_all_fields():
    """Creating an AchievementDefinition with all fields succeeds."""

    # Arrange / Act
    definition = AchievementDefinition(
        code="first_game",
        category=AchievementCategory.BEGINNER,
        name="First Steps",
        description="Play your first game",
        icon="trophy",
        threshold=1,
        tier=1,
        game_type=None,
    )

    # Assert
    assert definition.code == "first_game"
    assert definition.category == AchievementCategory.BEGINNER
    assert definition.name == "First Steps"
    assert definition.tier == 1
    assert definition.icon == "trophy"


def test_achievement_category_enum_values():
    """All AchievementCategory enum values are accessible."""

    # Arrange / Act / Assert
    assert AchievementCategory.BEGINNER == "beginner"
    assert AchievementCategory.UNDERCOVER_MASTER == "undercover_master"
    assert AchievementCategory.CODENAMES_MASTER == "codenames_master"
    assert AchievementCategory.SOCIAL == "social"
    assert AchievementCategory.STREAK == "streak"
    assert AchievementCategory.SPECIAL == "special"


def test_achievement_definition_default_values():
    """AchievementDefinition defaults icon to empty string and threshold to 1."""

    # Arrange / Act
    definition = AchievementDefinition(
        code="test",
        category=AchievementCategory.SOCIAL,
        name="Test",
        description="A test achievement",
    )

    # Assert
    assert definition.icon == ""
    assert definition.threshold == 1
    assert definition.tier == 1
    assert definition.game_type is None
