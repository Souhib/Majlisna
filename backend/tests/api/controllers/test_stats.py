from datetime import UTC, datetime
from uuid import uuid4

import pytest
from freezegun import freeze_time

from ipg.api.controllers.stats import StatsController
from ipg.api.schemas.error import UserNotFoundError


async def test_get_or_create_user_stats_creates(stats_controller: StatsController, create_user):
    """Creating stats for a new user initialises every counter to zero and sets no last_played_at."""

    # Arrange
    user = await create_user(username="statsuser", email="stats@test.com")

    # Act
    stats = await stats_controller.get_or_create_user_stats(user.id)

    # Assert
    assert stats.id is not None
    assert stats.user_id == user.id
    assert stats.total_games_played == 0
    assert stats.total_games_won == 0
    assert stats.total_games_lost == 0
    assert stats.undercover_games_played == 0
    assert stats.undercover_games_won == 0
    assert stats.codenames_games_played == 0
    assert stats.codenames_games_won == 0
    assert stats.times_civilian == 0
    assert stats.civilian_wins == 0
    assert stats.times_undercover == 0
    assert stats.undercover_wins == 0
    assert stats.times_mr_white == 0
    assert stats.mr_white_wins == 0
    assert stats.times_spymaster == 0
    assert stats.spymaster_wins == 0
    assert stats.times_operative == 0
    assert stats.operative_wins == 0
    assert stats.rooms_created == 0
    assert stats.current_win_streak == 0
    assert stats.longest_win_streak == 0
    assert stats.current_play_streak_days == 0
    assert stats.longest_play_streak_days == 0
    assert stats.last_played_at is None


async def test_get_or_create_user_stats_returns_existing(stats_controller: StatsController, create_user):
    """Calling get_or_create twice for the same user returns the same record without duplication."""

    # Arrange
    user = await create_user(username="existing", email="existing@test.com")
    stats1 = await stats_controller.get_or_create_user_stats(user.id)

    # Act
    stats2 = await stats_controller.get_or_create_user_stats(user.id)

    # Assert
    assert stats1.id == stats2.id
    assert stats1.user_id == stats2.user_id


async def test_get_user_stats_found(stats_controller: StatsController, create_user):
    """Retrieving stats for a user that has a record returns the correct user_id."""

    # Arrange
    user = await create_user(username="found", email="found@test.com")
    await stats_controller.get_or_create_user_stats(user.id)

    # Act
    stats = await stats_controller.get_user_stats(user.id)

    # Assert
    assert stats.user_id == user.id
    assert stats.id is not None


async def test_get_user_stats_not_found(stats_controller: StatsController):
    """Retrieving stats for a non-existent user raises UserNotFoundError."""

    # Arrange
    random_id = uuid4()

    # Act / Assert
    with pytest.raises(UserNotFoundError):
        await stats_controller.get_user_stats(random_id)


async def test_update_stats_undercover_win(stats_controller: StatsController, create_user):
    """Winning one undercover game as civilian increments all relevant global, game-type, and role counters."""

    # Arrange
    user = await create_user(username="ucwin", email="ucwin@test.com")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Assert — global counters
    assert stats.total_games_played == 1
    assert stats.total_games_won == 1
    assert stats.total_games_lost == 0
    # Assert — undercover game-type counters
    assert stats.undercover_games_played == 1
    assert stats.undercover_games_won == 1
    # Assert — civilian role counters
    assert stats.times_civilian == 1
    assert stats.civilian_wins == 1
    # Assert — unrelated role counters remain zero
    assert stats.times_undercover == 0
    assert stats.undercover_wins == 0
    assert stats.times_mr_white == 0
    assert stats.mr_white_wins == 0
    # Assert — codenames counters remain zero
    assert stats.codenames_games_played == 0
    assert stats.codenames_games_won == 0
    assert stats.times_spymaster == 0
    assert stats.spymaster_wins == 0
    assert stats.times_operative == 0
    assert stats.operative_wins == 0
    # Assert — streaks
    assert stats.current_win_streak == 1
    assert stats.longest_win_streak == 1
    assert stats.current_play_streak_days == 1
    assert stats.longest_play_streak_days == 1
    # Assert — last played updated
    assert stats.last_played_at is not None


async def test_update_stats_undercover_loss(stats_controller: StatsController, create_user):
    """Losing one undercover game as undercover increments loss and role counters, streak stays at zero."""

    # Arrange
    user = await create_user(username="ucloss", email="ucloss@test.com")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=False, role="undercover")

    # Assert — global counters
    assert stats.total_games_played == 1
    assert stats.total_games_won == 0
    assert stats.total_games_lost == 1
    # Assert — undercover game-type counters
    assert stats.undercover_games_played == 1
    assert stats.undercover_games_won == 0
    # Assert — undercover role counters
    assert stats.times_undercover == 1
    assert stats.undercover_wins == 0
    # Assert — win streak is zero after a loss
    assert stats.current_win_streak == 0
    assert stats.longest_win_streak == 0


async def test_update_stats_codenames_spymaster_win(stats_controller: StatsController, create_user):
    """Winning one codenames game as spymaster increments codenames and spymaster counters."""

    # Arrange
    user = await create_user(username="cnspy", email="cnspy@test.com")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "codenames", won=True, role="spymaster")

    # Assert — global counters
    assert stats.total_games_played == 1
    assert stats.total_games_won == 1
    assert stats.total_games_lost == 0
    # Assert — codenames game-type counters
    assert stats.codenames_games_played == 1
    assert stats.codenames_games_won == 1
    # Assert — spymaster role counters
    assert stats.times_spymaster == 1
    assert stats.spymaster_wins == 1
    # Assert — operative counters remain zero
    assert stats.times_operative == 0
    assert stats.operative_wins == 0
    # Assert — undercover counters remain zero
    assert stats.undercover_games_played == 0
    assert stats.undercover_games_won == 0


async def test_update_stats_codenames_operative_loss(stats_controller: StatsController, create_user):
    """Losing one codenames game as operative increments codenames played and operative times but not wins."""

    # Arrange
    user = await create_user(username="cnop", email="cnop@test.com")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "codenames", won=False, role="operative")

    # Assert — global counters
    assert stats.total_games_played == 1
    assert stats.total_games_won == 0
    assert stats.total_games_lost == 1
    # Assert — codenames game-type counters
    assert stats.codenames_games_played == 1
    assert stats.codenames_games_won == 0
    # Assert — operative role counters
    assert stats.times_operative == 1
    assert stats.operative_wins == 0
    # Assert — spymaster counters remain zero
    assert stats.times_spymaster == 0
    assert stats.spymaster_wins == 0


async def test_update_stats_mr_white_win(stats_controller: StatsController, create_user):
    """Winning one undercover game as mr_white increments mr_white role counters and global win counters."""

    # Arrange
    user = await create_user(username="mrw", email="mrw@test.com")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="mr_white")

    # Assert — mr_white role counters
    assert stats.times_mr_white == 1
    assert stats.mr_white_wins == 1
    # Assert — other undercover role counters remain zero
    assert stats.times_civilian == 0
    assert stats.civilian_wins == 0
    assert stats.times_undercover == 0
    assert stats.undercover_wins == 0
    # Assert — global counters
    assert stats.total_games_played == 1
    assert stats.total_games_won == 1
    assert stats.undercover_games_played == 1
    assert stats.undercover_games_won == 1


async def test_win_streak_increments(stats_controller: StatsController, create_user):
    """Winning three consecutive games sets both current and longest win streak to three."""

    # Arrange
    user = await create_user(username="streak", email="streak@test.com")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Assert
    assert stats.current_win_streak == 3
    assert stats.longest_win_streak == 3


async def test_win_streak_resets_on_loss(stats_controller: StatsController, create_user):
    """A loss after two wins resets the current streak to zero while preserving the longest at two."""

    # Arrange
    user = await create_user(username="reset", email="reset@test.com")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=False, role="civilian")

    # Assert
    assert stats.current_win_streak == 0
    assert stats.longest_win_streak == 2


async def test_play_streak_consecutive_days(stats_controller: StatsController, create_user):
    """Playing on three consecutive days increments the play streak to three."""

    # Arrange
    user = await create_user(username="playstreak", email="playstreak@test.com")
    day1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    day2 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    day3 = datetime(2025, 1, 3, 12, 0, 0, tzinfo=UTC)

    with freeze_time(day1):
        await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")
    with freeze_time(day2):
        await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Act
    with freeze_time(day3):
        stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Assert
    assert stats.current_play_streak_days == 3
    assert stats.longest_play_streak_days == 3


async def test_play_streak_resets_on_gap(stats_controller: StatsController, create_user):
    """Skipping a day resets the play streak to one, and longest stays at one."""

    # Arrange
    user = await create_user(username="gap", email="gap@test.com")
    day1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    day3 = datetime(2025, 1, 3, 12, 0, 0, tzinfo=UTC)

    with freeze_time(day1):
        await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Act
    with freeze_time(day3):
        stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Assert
    assert stats.current_play_streak_days == 1
    assert stats.longest_play_streak_days == 1


async def test_play_streak_same_day_no_change(stats_controller: StatsController, create_user):
    """Playing twice on the same day keeps the play streak at one."""

    # Arrange
    user = await create_user(username="sameday", email="sameday@test.com")
    day1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    with freeze_time(day1):
        await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Act
    with freeze_time(day1):
        stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Assert
    assert stats.current_play_streak_days == 1
    assert stats.longest_play_streak_days == 1


async def test_get_leaderboard_sorting(stats_controller: StatsController, create_user):
    """The leaderboard returns users ordered by the specified stat field descending."""

    # Arrange
    u1 = await create_user(username="top", email="top@test.com")
    u2 = await create_user(username="mid", email="mid@test.com")
    u3 = await create_user(username="low", email="low@test.com")
    for _ in range(3):
        await stats_controller.update_stats_after_game(u1.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(u2.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(u3.id, "undercover", won=False, role="civilian")

    # Act
    leaderboard = await stats_controller.get_leaderboard(stat_field="total_games_won", limit=10)

    # Assert
    assert len(leaderboard) == 3
    assert leaderboard[0].user_id == u1.id
    assert leaderboard[0].total_games_won == 3
    assert leaderboard[1].user_id == u2.id
    assert leaderboard[1].total_games_won == 1
    assert leaderboard[2].user_id == u3.id
    assert leaderboard[2].total_games_won == 0


async def test_get_leaderboard_limit(stats_controller: StatsController, create_user):
    """The leaderboard respects the limit parameter and returns at most that many entries."""

    # Arrange
    for i in range(5):
        u = await create_user(username=f"lb{i}", email=f"lb{i}@test.com")
        await stats_controller.update_stats_after_game(u.id, "undercover", won=True, role="civilian")

    # Act
    leaderboard = await stats_controller.get_leaderboard(limit=3)

    # Assert
    assert len(leaderboard) == 3


async def test_get_leaderboard_invalid_field(stats_controller: StatsController):
    """Requesting a leaderboard with a non-existent stat field raises ValueError."""

    # Arrange — no setup needed

    # Act / Assert
    with pytest.raises(ValueError, match="Invalid stat field"):
        await stats_controller.get_leaderboard(stat_field="nonexistent_field")


async def test_update_stats_multiple_games(stats_controller: StatsController, create_user):
    """Playing three games increments total_games_played to three regardless of outcomes."""

    # Arrange
    user = await create_user(username="multi", email="multi@test.com")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(user.id, "codenames", won=False, role="operative")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="undercover")

    # Assert
    assert stats.total_games_played == 3
    assert stats.total_games_won == 2
    assert stats.total_games_lost == 1
    assert stats.undercover_games_played == 2
    assert stats.codenames_games_played == 1


async def test_update_stats_win_then_loss_then_win(stats_controller: StatsController, create_user):
    """A win-loss-win sequence resets the current streak to one while longest remains at one."""

    # Arrange
    user = await create_user(username="wlw", email="wlw@test.com")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(user.id, "undercover", won=False, role="civilian")

    # Act
    stats = await stats_controller.update_stats_after_game(user.id, "undercover", won=True, role="civilian")

    # Assert
    assert stats.current_win_streak == 1
    assert stats.longest_win_streak == 1
    assert stats.total_games_played == 3
    assert stats.total_games_won == 2
    assert stats.total_games_lost == 1
