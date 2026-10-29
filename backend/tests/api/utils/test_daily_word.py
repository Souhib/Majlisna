"""Tests for the pure rules of the word of the day (utils/daily_word.py)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from freezegun import freeze_time

from majlisna.api.constants import DAILY_WORD_EPOCH, DEFAULT_WORD_QUIZ_MAX_HINTS
from majlisna.api.utils.daily_word import (
    compute_streaks,
    daily_word_number,
    ladder_length,
    makkah_day,
    next_day_starts_at,
    solved_score,
)

TODAY = date(2026, 11, 10)


def _days_before(*offsets: int) -> list[date]:
    return [TODAY - timedelta(days=offset) for offset in offsets]


# ─── The calendar ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("instant", "day"),
    [
        (datetime(2026, 10, 28, 20, 59, 59, tzinfo=UTC), date(2026, 10, 28)),  # 23:59:59 in Makkah
        (datetime(2026, 10, 28, 21, 0, 0, tzinfo=UTC), date(2026, 10, 29)),  # midnight in Makkah
        (datetime(2026, 10, 28, 0, 0, 0, tzinfo=UTC), date(2026, 10, 28)),  # 03:00 in Makkah
        (datetime(2026, 10, 27, 22, 30, 0, tzinfo=UTC), date(2026, 10, 28)),  # still the 27th in UTC
        (datetime(2026, 10, 28, 20, 59, 59), date(2026, 10, 28)),  # a naive instant is UTC
    ],
)
def test_the_day_turns_at_midnight_in_makkah(instant: datetime, day: date):
    """Makkah is UTC+3 all year: the day turns at 21:00 UTC, not at UTC midnight."""
    # Act / Assert
    assert makkah_day(instant) == day


def test_makkah_day_defaults_to_now():
    """Without an instant it is the day in Makkah right now."""
    # Prepare / Act
    with freeze_time("2026-12-31T21:00:00Z"):
        day = makkah_day()

    # Assert
    assert day == date(2027, 1, 1)


@pytest.mark.parametrize(
    ("day", "number"),
    [(DAILY_WORD_EPOCH, 1), (DAILY_WORD_EPOCH + timedelta(days=1), 2), (date(2027, 10, 29), 366)],
)
def test_number_counts_from_the_epoch(day: date, number: int):
    """The launch day (the epoch) is #1, and every Makkah day adds one."""
    # Act / Assert
    assert daily_word_number(day) == number


@pytest.mark.parametrize("days_before", [1, 30])
def test_a_day_before_the_epoch_reads_one(days_before: int):
    """A database played before launch never shows #0 or a negative number."""
    # Act / Assert
    assert daily_word_number(DAILY_WORD_EPOCH - timedelta(days=days_before)) == 1


def test_the_next_word_comes_out_at_the_next_makkah_midnight():
    """The next day starts at 21:00 UTC — what the client's countdown counts down to."""
    # Act
    starts_at = next_day_starts_at(date(2026, 10, 28))

    # Assert
    assert starts_at == datetime(2026, 10, 28, 21, 0, tzinfo=UTC)
    assert starts_at.utcoffset() == timedelta(0)


# ─── The ladder and its score ─────────────────────────────────


def _hints(count: int) -> dict:
    return {str(rung): {"en": f"Hint {rung}"} for rung in range(1, count + 1)}


@pytest.mark.parametrize(
    ("hints", "length"),
    [
        (_hints(6), 6),
        (_hints(9), DEFAULT_WORD_QUIZ_MAX_HINTS),  # capped like Kalimat
        (_hints(3), 3),
        ({"1": {"en": "a"}, "2": {"en": "b"}, "4": {"en": "d"}}, 2),  # consecutive rungs only
        ({}, 1),  # never below the rung everyone starts with
        (None, 1),
    ],
)
def test_ladder_length(hints: dict | None, length: int):
    """The consecutive rungs "1".."n", capped at six, at least one."""
    # Act / Assert
    assert ladder_length(hints) == length


@pytest.mark.parametrize(("hints_revealed", "score"), [(1, 6), (2, 5), (3, 4), (6, 1)])
def test_solved_score_is_kalimats_rule(hints_revealed: int, score: int):
    """Found on the first rung: 6 points; one less per rung revealed, down to 1."""
    # Act / Assert
    assert solved_score(6, hints_revealed) == score


# ─── Streaks ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("solved", "gave_up_today", "expected"),
    [
        ([], False, (0, 0)),
        (_days_before(0), False, (1, 1)),
        (_days_before(0, 1, 2), False, (3, 3)),
        # Today still open: the run ending yesterday stands.
        (_days_before(1, 2), False, (2, 2)),
        # A missed day ended the run; the best one is remembered.
        (_days_before(1, 4, 5, 6), False, (1, 3)),
        (_days_before(2, 3), False, (0, 2)),
        # A give-up closes today unsolved: the streak is over.
        (_days_before(1, 2, 3), True, (0, 3)),
        # The current run counts toward the best.
        (_days_before(0, 1, 2, 3, 9, 10), False, (4, 4)),
        # Duplicates and order do not matter.
        ([*_days_before(1, 0), *_days_before(0)], False, (2, 2)),
    ],
)
def test_compute_streaks(solved: list[date], gave_up_today: bool, expected: tuple[int, int]):
    """Consecutive solved Makkah days ending today, or yesterday while today is open."""
    # Act
    streaks = compute_streaks(solved, today=TODAY, gave_up_today=gave_up_today)

    # Assert
    assert streaks == expected
