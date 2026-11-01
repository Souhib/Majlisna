"""Ending a running game that nothing else will end, and letting go of its room.

**BR-05.** Deactivating a room — its last connected member leaves, or ``delete_room`` —
cleared ``room.active_game_id`` and left the game IN_PROGRESS. Once the room no longer
points at a game nothing can end it: later departures skip it (``active_game_id`` is
None), it reads "In progress" in every history forever, and its words can never be
kept or summarised (``GameStillInProgressError``). The prayer pause made it realistic:
every phone asleep past the 45-minute paused grace during a Jumu'ah orphaned the game.
Every path that deactivates a room cancels its running game first, here.

**BR-06.** A finish path cleared ``room.active_game_id`` unconditionally, so finishing
an OLD game (a cancelled one still played from a stale tab) unlinked the room's NEW
running game. ``detach_room_if_current`` is the one rule for every finish path.

Imports models and SQLAlchemy only — never ``room`` or ``disconnect``: ``base_game``
imports ``RoomController``, which imports ``disconnect``, so a controller import here
would close that cycle. Same reason as ``game_end_stats`` and ``undercover_rules``.
"""

from datetime import UTC, datetime

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import PAUSE_STATE_KEY
from majlisna.api.models.game import GameStatus
from majlisna.api.models.table import Game, Room


def detach_room_if_current(room: Room, game: Game) -> None:
    """Clear ``room.active_game_id`` only if it is ``game`` (BR-06).

    Does not ``session.add`` the room: a room loaded through the caller's session is
    tracked already, and the caller commits.
    """
    if room.active_game_id == game.id:
        room.active_game_id = None


async def cancel_running_game(session: AsyncSession, game: Game, room: Room | None = None) -> bool:
    """End ``game`` as CANCELLED if it is still running, and detach its room (BR-05).

    - Not IN_PROGRESS (finished, already cancelled, never started): nothing changes,
      returns False.
    - Otherwise: ``game_status = CANCELLED``, ``end_time = now`` (UTC), the prayer-pause
      record removed from ``live_state`` (a cancelled game is not paused, and nobody
      can resume it), and ``detach_room_if_current``. Returns True.

    ``room`` is the game's room when the caller already holds it; otherwise it is
    loaded by ``game.room_id``.

    **The caller holds ``get_game_lock`` and commits; this never commits.** On
    PostgreSQL the lock is transaction-scoped, so a commit here would release it in the
    middle of the caller's critical section. No stats are written: a cancelled game
    counts for no one.
    """
    if game.game_status != GameStatus.IN_PROGRESS:
        return False

    game.game_status = GameStatus.CANCELLED
    game.end_time = datetime.now(UTC)
    state = game.live_state
    if state and PAUSE_STATE_KEY in state:
        del state[PAUSE_STATE_KEY]
        game.live_state = state
        flag_modified(game, "live_state")
    session.add(game)

    if room is None and game.room_id is not None:
        room = await session.get(Room, game.room_id)
    if room is not None:
        detach_room_if_current(room, game)
        session.add(room)
    return True
