"""Narrowing access to ``Game.live_state``.

The column is nullable — a Game row can exist before its state is written — but every
game-logic path reaches the state only after establishing that it is there, and then
indexes it freely. Typed as ``dict | None``, that produced roughly two hundred mypy
errors (``Value of type "dict | None" is not indexable``) across the four game
controllers, all of them noise about an invariant the code already enforces.

``require_state`` states the invariant once, in a place that raises if it is ever
false, so callers get a plain ``dict`` and the type checker has nothing left to say.
Handlers that would rather bail than raise (the disconnect paths) assign
``game.live_state`` to a local and guard that instead — narrowing a local survives
intervening calls, narrowing an attribute does not.
"""

from datetime import UTC, datetime
from uuid import UUID

from majlisna.api.constants import LEFT_PLAYER_IDS_KEY
from majlisna.api.models.error import GameNotFoundError
from majlisna.api.models.table import Game


def require_state(game: Game) -> dict:
    """The game's live state, or ``GameNotFoundError`` if it has none.

    Raising rather than returning ``{}`` is deliberate: an empty state is not a
    playable game, and silently handing one back would turn a missing row into a
    confusing mid-game failure several frames later.
    """
    state = game.live_state
    if not state:
        raise GameNotFoundError(game_id=game.id)
    return state


def as_utc(instant: datetime | None) -> datetime | None:
    """A ``Game.start_time`` / ``end_time`` as an aware UTC datetime (None stays None).

    The columns are ``TIMESTAMP WITH TIME ZONE`` and always written with
    ``datetime.now(UTC)``, but SQLite reads them back naive — and a naive ISO string
    reaches the browser without an offset, where ``new Date()`` takes it as local time.
    """
    if instant is None:
        return None
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def mark_player_left(state: dict, user_id: UUID | str) -> None:
    """Record that ``user_id`` left the game before its end (``state[LEFT_PLAYER_IDS_KEY]``).

    Every departure path must call it — a voluntary leave, a kick, the grace sweep, an
    account deletion — so the same player may be marked more than once; the list keeps
    each id once, in departure order. Owner rule (b): a leaver gets NEITHER a win NOR a loss, in
    all four games — ``game_end_stats.scorable_players`` drops every id listed here, so
    an Undercover drop-out (kept in ``state["players"]``, dead) never shares the win.

    Mutates ``state`` in place: the caller still owes ``flag_modified(game, "live_state")``.
    """
    left = state.setdefault(LEFT_PLAYER_IDS_KEY, [])
    leaver = str(user_id)
    if leaver not in left:
        left.append(leaver)


def left_player_ids(state: dict) -> set[str]:
    """The user ids ``mark_player_left`` recorded (empty for a state without any)."""
    return set(state.get(LEFT_PLAYER_IDS_KEY) or ())
