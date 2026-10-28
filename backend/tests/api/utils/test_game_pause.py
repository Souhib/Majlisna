"""Unit tests for the prayer-pause helpers (utils/game_pause.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from majlisna.api.models.game import GameType
from majlisna.api.utils.game_pause import (
    clock_now,
    is_paused,
    parse_instant,
    pause_record,
    paused_since,
    remaining_seconds_at,
    shifted_instant,
    time_anchor_keys,
)

PAUSED_AT = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
RESUMED_AT = PAUSED_AT + timedelta(minutes=10)
PAUSED_FOR = RESUMED_AT - PAUSED_AT


def _paused_state() -> dict:
    return {"paused": {"by": "u", "by_username": "host", "at": PAUSED_AT.isoformat(), "reason": "salah"}}


def test_an_anchor_set_before_the_pause_moves_by_the_whole_pause():
    """The time already counted is kept and the pause adds none."""
    # Prepare
    anchor = PAUSED_AT - timedelta(seconds=20)

    # Act
    shifted = shifted_instant(anchor, PAUSED_FOR, RESUMED_AT)

    # Assert
    assert shifted == anchor + PAUSED_FOR
    assert (RESUMED_AT - shifted).total_seconds() == 20


def test_an_anchor_set_during_the_pause_lands_on_the_resume():
    """It had counted nothing yet, so it starts counting at the resume — not after it."""
    # Prepare
    anchor = PAUSED_AT + timedelta(minutes=3)

    # Act
    shifted = shifted_instant(anchor, PAUSED_FOR, RESUMED_AT)

    # Assert
    assert shifted == RESUMED_AT


def test_shifting_works_on_naive_timestamps_too():
    """RoomUserLink timestamps are naive local time; the same rule applies."""
    # Prepare
    resumed_naive = datetime(2026, 10, 28, 12, 10)
    disconnected_before = resumed_naive - PAUSED_FOR - timedelta(seconds=60)

    # Act
    shifted = shifted_instant(disconnected_before, PAUSED_FOR, resumed_naive)

    # Assert
    assert shifted.tzinfo is None
    assert (resumed_naive - shifted).total_seconds() == 60


def test_parse_instant_reads_a_naive_value_as_utc():
    # Act
    parsed = parse_instant("2026-10-28T12:00:00")

    # Assert
    assert parsed == PAUSED_AT


def test_pause_record_of_a_running_game_is_none():
    # Act / Assert
    assert pause_record({"players": []}) is None
    assert pause_record({"paused": None}) is None
    assert pause_record(None) is None
    assert is_paused({"paused": None}) is False
    assert paused_since({}) is None


def test_a_paused_state_reports_when_it_stopped():
    # Prepare
    state = _paused_state()

    # Act / Assert
    assert is_paused(state) is True
    assert paused_since(state) == PAUSED_AT


def test_the_game_clock_stands_still_while_paused():
    """clock_now reads the pause instant while paused, the real time otherwise."""
    # Prepare
    before = datetime.now(UTC)

    # Act
    frozen = clock_now(_paused_state())
    running = clock_now({})

    # Assert
    assert frozen == PAUSED_AT
    assert before <= running <= datetime.now(UTC)


@pytest.mark.parametrize("game_type", list(GameType))
def test_every_game_type_names_the_clocks_a_resume_shifts(game_type: GameType):
    """A game type with no anchors would let its clocks run through the prayer."""
    # Act
    keys = time_anchor_keys(game_type.value)

    # Assert
    assert keys
    assert all(key.endswith("_started_at") for key in keys)


def test_an_unknown_game_type_shifts_nothing():
    # Act / Assert
    assert time_anchor_keys("chess") == ()


@pytest.mark.parametrize(
    ("anchor_offset", "expected"),
    [
        (-20, 10.0),  # 20 s of a 30 s timer counted before the pause
        (-45, 0.0),  # already over: never negative
        (60, 30.0),  # restarted after the pause began: the whole duration, never more
        (0, 30.0),
    ],
)
def test_remaining_seconds_are_clamped_to_the_timer(anchor_offset: int, expected: float):
    """What a frozen countdown shows: within [0, duration] whatever the anchor."""
    # Prepare
    anchor = PAUSED_AT + timedelta(seconds=anchor_offset)

    # Act
    remaining = remaining_seconds_at(anchor, 30, PAUSED_AT)

    # Assert
    assert remaining == expected
