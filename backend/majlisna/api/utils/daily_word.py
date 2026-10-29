"""Pure rules of the word of the day (Kalimat al-yawm, كلمة اليوم): its calendar, its
score and its streaks. No session, no I/O — the controller feeds them what it read.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from majlisna.api.constants import DAILY_WORD_EPOCH, DAILY_WORD_TIMEZONE, DEFAULT_WORD_QUIZ_MAX_HINTS

MAKKAH = ZoneInfo(DAILY_WORD_TIMEZONE)
_ONE_DAY = timedelta(days=1)


def makkah_day(instant: datetime | None = None) -> date:
    """The day it is in Makkah at ``instant`` (now by default). A naive instant is UTC."""
    moment = instant or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(MAKKAH).date()


def daily_word_number(day: date) -> int:
    """The day's number: #1 on ``DAILY_WORD_EPOCH``, one more each Makkah day.

    Never below 1: a day before the epoch (a database played before launch) reads #1,
    never #0 or a negative number.
    """
    return max((day - DAILY_WORD_EPOCH).days + 1, 1)


def next_day_starts_at(day: date) -> datetime:
    """The UTC instant the day after ``day`` begins, i.e. the next midnight in Makkah."""
    return datetime.combine(day + _ONE_DAY, time.min, tzinfo=MAKKAH).astimezone(UTC)


def ladder_length(hints: Mapping[str, object] | None) -> int:
    """How many rungs the word's ladder has: the consecutive ``"1"``, ``"2"``… present,
    capped at Word Quiz's ``DEFAULT_WORD_QUIZ_MAX_HINTS``, and never less than one (the
    rung everyone starts with). Every seeded word has the full six."""
    rungs = 0
    while rungs < DEFAULT_WORD_QUIZ_MAX_HINTS and (hints or {}).get(str(rungs + 1)):
        rungs += 1
    return max(rungs, 1)


def solved_score(max_hints: int, hints_revealed: int) -> int:
    """Kalimat's rule: found on the first rung pays ``max_hints``, one point less per rung.

    Never below one: whoever finds the word scores. A give-up scores 0 (not computed here).
    """
    return max(max_hints - hints_revealed + 1, 1)


def compute_streaks(solved_days: Iterable[date], *, today: date, gave_up_today: bool) -> tuple[int, int]:
    """(current streak, best streak) over the days a player solved.

    The current streak is the run of consecutive solved days ending today — or ending
    yesterday while today is still open, so a player is not shown 0 every morning before
    they play. A give-up closes today unsolved: the streak is then 0. The best streak is
    the longest run ever, the current one included.
    """
    days = sorted(set(solved_days))
    best = 0
    run = 0
    previous: date | None = None
    for day in days:
        run = run + 1 if previous is not None and day - previous == _ONE_DAY else 1
        best = max(best, run)
        previous = day

    solved = set(days)
    if today in solved:
        anchor = today
    elif gave_up_today:
        return 0, best
    else:
        anchor = today - _ONE_DAY
    current = 0
    while anchor in solved:
        current += 1
        anchor -= _ONE_DAY
    return current, best
