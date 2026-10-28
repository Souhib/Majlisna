"""The prayer pause (وقفة الصلاة): pure helpers over ``live_state["paused"]``.

When the adhan comes mid-game the host pauses it: no move is accepted and no clock
runs until the host resumes. The record is ``{"by", "by_username", "at", "reason"}``
(``at`` is a UTC ISO instant; the key names live in ``constants``) and the key is
absent while the game runs.

These helpers live outside ``base_game`` for the same import reason as
``game_end_stats``: the disconnect checker has to know whether a room's game is
paused, and ``disconnect`` cannot import a controller (``base_game`` → ``room`` →
``disconnect``). Nothing here touches the session.
"""

from datetime import UTC, datetime, timedelta

from majlisna.api.constants import PAUSE_RECORD_AT, PAUSE_STATE_KEY, PAUSE_TIME_ANCHOR_KEYS


def parse_instant(value: str) -> datetime:
    """An ISO timestamp from ``live_state`` as an aware datetime (a naive one is UTC)."""
    instant = datetime.fromisoformat(value)
    return instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)


def pause_record(state: dict | None) -> dict | None:
    """The pause record of a game's state, or None while it runs."""
    if not state:
        return None
    record = state.get(PAUSE_STATE_KEY)
    return record if isinstance(record, dict) else None


def is_paused(state: dict | None) -> bool:
    return pause_record(state) is not None


def paused_since(state: dict | None) -> datetime | None:
    """When the clocks stopped, or None while the game runs."""
    record = pause_record(state)
    return parse_instant(record[PAUSE_RECORD_AT]) if record else None


def clock_now(state: dict) -> datetime:
    """The instant the game's clocks read: frozen at the pause while paused, else now.

    A read path that derives something from elapsed time (the Word Quiz hint ladder)
    must use this rather than ``datetime.now``, or a paused round would keep
    releasing hints while everyone is away praying.
    """
    since = paused_since(state)
    return since if since is not None else datetime.now(UTC)


def shifted_instant(instant: datetime, paused_for: timedelta, resumed_at: datetime) -> datetime:
    """``instant`` moved forward by the time the game spent paused, never past the resume.

    An anchor set before the pause moves by the whole pause: the time it had already
    counted is kept, the pause adds none. An anchor set *during* the pause — a
    drop-out moved an Undercover round to voting, which restarts its timer — has
    counted nothing yet, so it lands on the resume instant. ``instant`` and
    ``resumed_at`` must be both aware or both naive.
    """
    return min(instant + paused_for, resumed_at)


def time_anchor_keys(game_type: str) -> tuple[str, ...]:
    """The live_state keys a game's clocks count from, chosen by the game's OWN type.

    Never by the controller a request reached: resuming a Word Quiz game through the
    Undercover router once shifted ``timer_started_at`` (absent) and left
    ``round_started_at`` where it was, so the whole prayer counted against the round.
    """
    return PAUSE_TIME_ANCHOR_KEYS.get(game_type, ())


def remaining_seconds_at(anchor: datetime, duration_seconds: float, at: datetime) -> float:
    """How much of a ``duration_seconds`` timer started at ``anchor`` is left at ``at``.

    Clamped to ``[0, duration]``: an anchor set *after* ``at`` (a drop-out restarted an
    Undercover round's timer during the pause) has counted nothing yet, so it has its
    whole duration left — never more.
    """
    elapsed = max((at - anchor).total_seconds(), 0.0)
    return min(max(duration_seconds - elapsed, 0.0), float(duration_seconds))
