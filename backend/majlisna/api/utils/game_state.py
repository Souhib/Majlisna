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
