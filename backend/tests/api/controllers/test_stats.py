from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from freezegun import freeze_time

from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import UserGameLink
from majlisna.api.models.table import Game
from majlisna.api.schemas.error import InvalidLeaderboardSortError, UserNotFoundError
from majlisna.api.schemas.stats import DailyGameRecord, GameDurationStats, HeadToHeadStats


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
    """Ranking by something the leaderboard does not rank by is a 400, not a 500."""

    # Arrange — no setup needed

    # Act / Assert
    with pytest.raises(InvalidLeaderboardSortError) as excinfo:
        await stats_controller.get_leaderboard(stat_field="nonexistent_field")
    assert excinfo.value.status_code == 400


async def test_get_leaderboard_rejects_a_column_it_does_not_rank_by(stats_controller: StatsController):
    """A real UserStats column outside the whitelist is refused too (it used to be getattr)."""

    # Act / Assert
    with pytest.raises(InvalidLeaderboardSortError):
        await stats_controller.get_leaderboard(stat_field="user_id")


async def test_get_leaderboard_by_win_rate(stats_controller: StatsController, create_user):
    """`win_rate` ranks by won / played (it is not a column), ties broken by wins."""

    # Arrange — perfect: 2/2 (100 %), single: 1/1 (100 %), half: 1/2 (50 %), none: 0/1
    perfect = await create_user(username="perfect", email="perfect@test.com")
    single = await create_user(username="single", email="single@test.com")
    half = await create_user(username="half", email="half@test.com")
    none = await create_user(username="none", email="none@test.com")
    for _ in range(2):
        await stats_controller.update_stats_after_game(perfect.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(single.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(half.id, "undercover", won=True, role="civilian")
    await stats_controller.update_stats_after_game(half.id, "undercover", won=False, role="civilian")
    await stats_controller.update_stats_after_game(none.id, "undercover", won=False, role="civilian")

    # Act
    leaderboard = await stats_controller.get_leaderboard(stat_field="win_rate", limit=10)

    # Assert
    assert [e.user_id for e in leaderboard] == [perfect.id, single.id, half.id, none.id]
    assert [e.win_rate for e in leaderboard] == [100.0, 100.0, 50.0, 0.0]


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


# ========== get_game_history_for_charts ==========


async def test_game_history_returns_daily_records(stats_controller: StatsController, create_user, create_room, session):
    """Two finished games on different days produce two DailyGameRecord entries with correct win/loss counts."""

    # Arrange
    user1 = await create_user(username="hist1", email="hist1@test.com")
    user2 = await create_user(username="hist2", email="hist2@test.com")
    room = await create_room(owner=user1)

    now = datetime.now()
    day1 = now - timedelta(days=2)
    day2 = now - timedelta(days=1)

    # Game 1: user1 is civilian, civilians win -> user1 wins (day1)
    game1 = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=day1,
        end_time=day1 + timedelta(minutes=15),
        live_state={
            "players": [
                {"user_id": str(user1.id), "role": "civilian", "team": None},
                {"user_id": str(user2.id), "role": "undercover", "team": None},
            ],
            "winner": "civilians",
        },
    )
    session.add(game1)
    await session.commit()

    link1 = UserGameLink(user_id=user1.id, game_id=game1.id)
    session.add(link1)
    await session.commit()

    # Game 2: user1 is civilian, undercovers win -> user1 loses (day2)
    game2 = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=day2,
        end_time=day2 + timedelta(minutes=20),
        live_state={
            "players": [
                {"user_id": str(user1.id), "role": "civilian", "team": None},
                {"user_id": str(user2.id), "role": "undercover", "team": None},
            ],
            "winner": "undercovers",
        },
    )
    session.add(game2)
    await session.commit()

    link2 = UserGameLink(user_id=user1.id, game_id=game2.id)
    session.add(link2)
    await session.commit()

    # Act
    records = await stats_controller.get_game_history_for_charts(user1.id, days=30)

    # Assert
    assert len(records) == 2
    assert all(isinstance(r, DailyGameRecord) for r in records)
    # Records are sorted by date ascending
    assert records[0].date <= records[1].date
    # Day1: 1 win, Day2: 1 loss
    day1_record = records[0]
    day2_record = records[1]
    assert day1_record.wins == 1
    assert day1_record.losses == 0
    assert day1_record.total == 1
    assert day2_record.wins == 0
    assert day2_record.losses == 1
    assert day2_record.total == 1


async def test_game_history_empty_when_no_games(stats_controller: StatsController, create_user):
    """A user with no games gets an empty list from get_game_history_for_charts."""

    # Arrange
    user = await create_user(username="nohist", email="nohist@test.com")

    # Act
    records = await stats_controller.get_game_history_for_charts(user.id, days=30)

    # Assert
    assert records == []


async def test_game_history_respects_days_cutoff(stats_controller: StatsController, create_user, create_room, session):
    """A game older than the days cutoff is excluded from game history."""

    # Arrange
    user = await create_user(username="cutoff", email="cutoff@test.com")
    room = await create_room(owner=user)

    old_time = datetime.now() - timedelta(days=60)

    game = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=old_time,
        end_time=old_time + timedelta(minutes=10),
        live_state={
            "players": [
                {"user_id": str(user.id), "role": "civilian", "team": None},
            ],
            "winner": "civilians",
        },
    )
    session.add(game)
    await session.commit()

    link = UserGameLink(user_id=user.id, game_id=game.id)
    session.add(link)
    await session.commit()

    # Act
    records = await stats_controller.get_game_history_for_charts(user.id, days=30)

    # Assert
    assert records == []


# ========== get_game_duration_stats ==========


async def test_game_duration_stats_with_games(stats_controller: StatsController, create_user, create_room, session):
    """Games with start and end times produce correct avg/fastest/longest duration stats."""

    # Arrange
    user = await create_user(username="dur1", email="dur1@test.com")
    room = await create_room(owner=user)

    base_time = datetime(2025, 6, 1, 12, 0)

    # Game 1: 10 minutes = 600 seconds
    game1 = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=base_time,
        end_time=base_time + timedelta(minutes=10),
        live_state={"players": [{"user_id": str(user.id), "role": "civilian"}], "winner": "civilians"},
    )
    session.add(game1)
    await session.commit()
    session.add(UserGameLink(user_id=user.id, game_id=game1.id))
    await session.commit()

    # Game 2: 30 minutes = 1800 seconds
    game2 = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=base_time,
        end_time=base_time + timedelta(minutes=30),
        live_state={"players": [{"user_id": str(user.id), "role": "civilian"}], "winner": "civilians"},
    )
    session.add(game2)
    await session.commit()
    session.add(UserGameLink(user_id=user.id, game_id=game2.id))
    await session.commit()

    # Act
    result = await stats_controller.get_game_duration_stats(user.id)

    # Assert
    assert isinstance(result, GameDurationStats)
    assert result.total_games_with_duration == 2
    assert result.fastest_seconds == 600.0
    assert result.longest_seconds == 1800.0
    assert result.average_seconds == 1200.0  # (600 + 1800) / 2


async def test_game_duration_stats_no_games(stats_controller: StatsController, create_user):
    """A user with no games gets zero/None duration stats."""

    # Arrange
    user = await create_user(username="nodur", email="nodur@test.com")

    # Act
    result = await stats_controller.get_game_duration_stats(user.id)

    # Assert
    assert isinstance(result, GameDurationStats)
    assert result.average_seconds == 0
    assert result.fastest_seconds is None
    assert result.longest_seconds is None
    assert result.undercover_avg_seconds is None
    assert result.codenames_avg_seconds is None
    assert result.total_games_with_duration == 0


async def test_game_duration_stats_per_type(stats_controller: StatsController, create_user, create_room, session):
    """Undercover and codenames games produce separate per-type average durations."""

    # Arrange
    user = await create_user(username="durtype", email="durtype@test.com")
    room = await create_room(owner=user)

    base_time = datetime(2025, 6, 1, 12, 0)

    # Undercover game: 20 minutes = 1200 seconds
    uc_game = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=3,
        start_time=base_time,
        end_time=base_time + timedelta(minutes=20),
        live_state={"players": [{"user_id": str(user.id), "role": "civilian"}], "winner": "civilians"},
    )
    session.add(uc_game)
    await session.commit()
    session.add(UserGameLink(user_id=user.id, game_id=uc_game.id))
    await session.commit()

    # Codenames game: 40 minutes = 2400 seconds
    cn_game = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.CODENAMES,
        game_status=GameStatus.FINISHED,
        number_of_players=4,
        start_time=base_time,
        end_time=base_time + timedelta(minutes=40),
        live_state={"players": [{"user_id": str(user.id), "role": "operative", "team": "red"}], "winner": "red"},
    )
    session.add(cn_game)
    await session.commit()
    session.add(UserGameLink(user_id=user.id, game_id=cn_game.id))
    await session.commit()

    # Act
    result = await stats_controller.get_game_duration_stats(user.id)

    # Assert
    assert result.total_games_with_duration == 2
    assert result.undercover_avg_seconds == 1200.0
    assert result.codenames_avg_seconds == 2400.0
    assert result.average_seconds == 1800.0  # (1200 + 2400) / 2


# ========== get_head_to_head ==========


async def test_head_to_head_with_shared_games(stats_controller: StatsController, create_user, create_room, session):
    """Two users who played together have correct user_wins/opponent_wins/draws in head-to-head stats."""

    # Arrange
    user1 = await create_user(username="h2h1", email="h2h1@test.com")
    user2 = await create_user(username="h2h2", email="h2h2@test.com")
    room = await create_room(owner=user1)

    base_time = datetime(2025, 6, 1, 12, 0)

    # Game 1: civilians win -> user1 (civilian) wins, user2 (undercover) loses
    game1 = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=base_time,
        end_time=base_time + timedelta(minutes=15),
        live_state={
            "players": [
                {"user_id": str(user1.id), "role": "civilian", "team": None},
                {"user_id": str(user2.id), "role": "undercover", "team": None},
            ],
            "winner": "civilians",
        },
    )
    session.add(game1)
    await session.commit()
    session.add(UserGameLink(user_id=user1.id, game_id=game1.id))
    session.add(UserGameLink(user_id=user2.id, game_id=game1.id))
    await session.commit()

    # Game 2: undercovers win -> user2 (undercover) wins, user1 (civilian) loses
    game2 = Game(
        id=uuid4(),
        room_id=room.id,
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=2,
        start_time=base_time,
        end_time=base_time + timedelta(minutes=20),
        live_state={
            "players": [
                {"user_id": str(user1.id), "role": "civilian", "team": None},
                {"user_id": str(user2.id), "role": "undercover", "team": None},
            ],
            "winner": "undercovers",
        },
    )
    session.add(game2)
    await session.commit()
    session.add(UserGameLink(user_id=user1.id, game_id=game2.id))
    session.add(UserGameLink(user_id=user2.id, game_id=game2.id))
    await session.commit()

    # Act
    result = await stats_controller.get_head_to_head(user1.id, user2.id)

    # Assert
    assert isinstance(result, HeadToHeadStats)
    assert result.user_id == user1.id
    assert result.opponent_id == user2.id
    assert result.user_wins == 1
    assert result.opponent_wins == 1
    assert result.draws == 0
    assert result.total_games == 2


async def test_head_to_head_no_shared_games(stats_controller: StatsController, create_user):
    """Two users who never played together get all-zero head-to-head stats."""

    # Arrange
    user1 = await create_user(username="h2hn1", email="h2hn1@test.com")
    user2 = await create_user(username="h2hn2", email="h2hn2@test.com")

    # Act
    result = await stats_controller.get_head_to_head(user1.id, user2.id)

    # Assert
    assert isinstance(result, HeadToHeadStats)
    assert result.user_id == user1.id
    assert result.opponent_id == user2.id
    assert result.user_wins == 0
    assert result.opponent_wins == 0
    assert result.draws == 0
    assert result.total_games == 0


# ========== _did_user_win ==========


async def test_did_user_win_undercover_civilian_wins(create_user):
    """In undercover, a civilian player wins when winner is 'civilians'."""

    # Arrange
    user = await create_user(username="dwciv", email="dwciv@test.com")
    game = Game(
        id=uuid4(),
        room_id=uuid4(),
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=3,
        live_state={
            "players": [
                {"user_id": str(user.id), "role": "civilian", "team": None},
            ],
            "winner": "civilians",
        },
    )

    # Act
    result = StatsController._did_user_win(game, user.id, "civilians")

    # Assert
    assert result is True


async def test_did_user_win_undercover_undercover_wins(create_user):
    """In undercover, an undercover player wins when winner is 'undercovers'."""

    # Arrange
    user = await create_user(username="dwuc", email="dwuc@test.com")
    game = Game(
        id=uuid4(),
        room_id=uuid4(),
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=3,
        live_state={
            "players": [
                {"user_id": str(user.id), "role": "undercover", "team": None},
            ],
            "winner": "undercovers",
        },
    )

    # Act
    result = StatsController._did_user_win(game, user.id, "undercovers")

    # Assert
    assert result is True


async def test_did_user_win_codenames(create_user):
    """In codenames, a player wins when their team matches the winner."""

    # Arrange
    user = await create_user(username="dwcn", email="dwcn@test.com")
    game = Game(
        id=uuid4(),
        room_id=uuid4(),
        type=GameType.CODENAMES,
        game_status=GameStatus.FINISHED,
        number_of_players=4,
        live_state={
            "players": [
                {"user_id": str(user.id), "role": "operative", "team": "red"},
            ],
            "winner": "red",
        },
    )

    # Act
    result = StatsController._did_user_win(game, user.id, "red")

    # Assert
    assert result is True


async def test_did_user_win_no_winner(create_user):
    """When winner is None, _did_user_win returns False."""

    # Arrange
    user = await create_user(username="dwnw", email="dwnw@test.com")
    game = Game(
        id=uuid4(),
        room_id=uuid4(),
        type=GameType.UNDERCOVER,
        game_status=GameStatus.FINISHED,
        number_of_players=3,
        live_state={
            "players": [
                {"user_id": str(user.id), "role": "civilian", "team": None},
            ],
            "winner": None,
        },
    )

    # Act
    result = StatsController._did_user_win(game, user.id, None)

    # Assert
    assert result is False
