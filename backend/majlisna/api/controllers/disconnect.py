import asyncio
import math
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import AsyncExitStack, contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from typing import NamedTuple
from uuid import UUID

from loguru import logger
from sqlalchemy import and_, delete, or_, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DISCONNECT_CHECK_INTERVAL_SECONDS,
    DISCONNECT_SWEEP_LOCK_KEY,
    GRACE_PERIOD_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    LOBBY_GRACE_PERIOD_SECONDS,
    ORPHANED_GAME_SWEEP_EVERY_TICKS,
    PAUSED_GAME_GRACE_PERIOD_SECONDS,
)
from majlisna.api.controllers.codenames_helpers import (
    CodenamesGameStatus,
    CodenamesRole,
    CodenamesTeam,
    release_departed_operative,
)
from majlisna.api.controllers.game_cancel import cancel_running_game, detach_room_if_current
from majlisna.api.controllers.game_end_stats import codenames_winners, record_game_end, undercover_winners
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.controllers.quiz_rules import settle_round_if_everyone_answered
from majlisna.api.controllers.undercover_rules import repair_turn_after_dropout, winning_team
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.table import Game, Room
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.utils.game_pause import is_paused
from majlisna.api.utils.game_state import mark_player_left

# ─── Presence: telling the table that someone came back (BDP-04) ─────────────


class HeartbeatResult(StrEnum):
    """What ``update_heartbeat`` found, so the Socket.IO handler knows whom to tell."""

    # No seat in the room (kicked, left, swept): the socket has no business there.
    NOT_A_MEMBER = "not_a_member"
    # Present already: last_seen_at moved, nobody else needs telling.
    REFRESHED = "refreshed"
    # Was away (connected False, or a grace clock running) and is back: the room must hear it.
    RESTORED = "restored"


# Called with a room id whenever a REST request brings an away member back
# (``announce_presence_restored``). Controllers cannot reach Socket.IO (``ws.server``
# imports the handlers, which import the controllers), so the worker's checker loop
# registers its ``on_room_changed`` here for as long as it runs. No listener (tests,
# scripts): nothing is announced.
_presence_listeners: list[Callable[[str], None]] = []


@contextmanager
def presence_listener(callback: Callable[[str], None]) -> Iterator[None]:
    """Have ``callback(room_id)`` called for every presence a REST heartbeat restores, while inside."""
    _presence_listeners.append(callback)
    try:
        yield
    finally:
        _presence_listeners.remove(callback)


def announce_presence_restored(room_id: UUID | str | None) -> None:
    """A REST heartbeat (``BaseGameController._update_heartbeat_throttled``,
    ``RoomController.get_room_state``) brought an away member of ``room_id`` back.

    The Socket.IO handlers broadcast their own restorations; the REST paths need this
    because a page polling REST while its socket is down restores the link FIRST, and
    the socket's reconnect then finds nothing to restore and announces nothing — the
    rest of the table kept showing the player away. Fire-and-forget by nature: the
    listener schedules the broadcast, the request does not wait for it.
    """
    if room_id is None:
        return
    for listener in list(_presence_listeners):
        listener(str(room_id))


def refresh_presence(link: RoomUserLink) -> bool:
    """Mark ``link`` present now. True when it was away: connected False, or a grace clock running.

    Staged only (no ``session.add``, no commit). Naive ``now``, like every
    ``RoomUserLink`` timestamp (root CLAUDE.md).
    """
    was_away = not link.connected or link.disconnected_at is not None
    link.last_seen_at = datetime.now()
    link.connected = True
    link.disconnected_at = None
    return was_away


# ─── The sweep ───────────────────────────────────────────────────────────────


async def _mark_stale_users(session: AsyncSession) -> set[str]:
    """Mark connected users with stale heartbeats as disconnected. Returns affected room IDs."""
    now = datetime.now()
    stale_threshold = datetime.fromtimestamp(now.timestamp() - HEARTBEAT_STALE_SECONDS)

    newly_stale = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.connected == True)  # noqa: E712
            # The IS NOT NULL test comes FIRST on purpose. `last_seen_at` is nullable, so
            # the ignore below would otherwise be free to hide a real NULL bug; with the
            # guard ahead of it, a NULL row is excluded before the comparison is reached.
            .where(RoomUserLink.last_seen_at != None)  # noqa: E711
            .where(RoomUserLink.last_seen_at < stale_threshold)  # ty: ignore[unsupported-operator]
        )
    ).all()

    # Also catch users who never sent a heartbeat (last_seen_at is NULL)
    # but have been in the room longer than the stale threshold.
    # This handles cases where Socket.IO never connected (e.g., page load interrupted,
    # WebSocket blocked by firewall, or navigation race conditions).
    never_heartbeat = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.connected == True)  # noqa: E712
            .where(RoomUserLink.last_seen_at == None)  # noqa: E711
            .where(RoomUserLink.joined_at < stale_threshold)
        )
    ).all()

    room_ids: set[str] = set()
    for link in [*newly_stale, *never_heartbeat]:
        link.connected = False
        link.disconnected_at = now
        session.add(link)
        if link.room_id:
            room_ids.add(str(link.room_id))
        logger.info("Marking user {} as disconnected in room {} (stale heartbeat)", link.user_id, link.room_id)

    if newly_stale or never_heartbeat:
        await session.commit()
    return room_ids


async def _remove_expired_users(session: AsyncSession) -> tuple[set[str], set[str]]:
    """Permanently remove users whose grace period has expired.

    The rooms and their active games are read in ONE query each for the whole sweep —
    this runs every few seconds, and a paused game keeps its expired-looking links for
    up to ``PAUSED_GAME_GRACE_PERIOD_SECONDS``, so per-link lookups were two queries
    per away player per tick. Each removal is then re-checked against fresh rows
    UNDER the game lock (``_remove_member(..., only_if_expired=True)``), because a
    resume or a reconnect may have committed since.

    Returns (affected_room_ids, affected_game_ids).
    """
    grace_threshold = datetime.fromtimestamp(datetime.now().timestamp() - GRACE_PERIOD_SECONDS)

    expired = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.connected == False)  # noqa: E712
            # IS NOT NULL first — same reason as _mark_stale_users above.
            .where(RoomUserLink.disconnected_at != None)  # noqa: E711
            .where(RoomUserLink.disconnected_at < grace_threshold)  # ty: ignore[unsupported-operator]
        )
    ).all()
    if not expired:
        return set(), set()

    rooms = await _load_rooms(session, {link.room_id for link in expired if link.room_id})
    paused_game_ids = await _paused_game_ids(session, {room.active_game_id for room in rooms.values()})

    room_ids: set[str] = set()
    game_ids: set[str] = set()
    for link in expired:
        if not link.room_id:
            await _handle_permanent_disconnect(session, link)
            continue

        # A cheap pre-filter on the sweep's own rows; the decision is taken under the lock.
        if not _past_grace(link, _grace_seconds(rooms.get(link.room_id), paused_game_ids)):
            continue
        removal = await _remove_member(session, link, only_if_expired=True)
        if not removal.removed:
            continue
        room_ids.add(str(link.room_id))
        if removal.game_id:
            game_ids.add(str(removal.game_id))
    return room_ids, game_ids


async def _load_rooms(session: AsyncSession, room_ids: set[UUID]) -> dict[UUID, Room]:
    """The rooms of a sweep, keyed by id — one query."""
    if not room_ids:
        return {}
    rows = (await session.exec(select(Room).where(col(Room.id).in_(room_ids)))).all()
    return {room.id: room for room in rows}


async def _paused_game_ids(session: AsyncSession, game_ids: set[UUID | None]) -> set[UUID]:
    """Which of these running games the host has paused for the prayer — one query.

    Columns, not entities: a ``Game`` loaded here would sit in the session's identity
    map, and a later plain ``select(Game)`` in the same session would hand back that
    copy — read before the game lock, possibly before another move (BR-04).
    """
    ids = {game_id for game_id in game_ids if game_id}
    if not ids:
        return set()
    rows = (
        await session.exec(
            select(Game.id, Game.live_state)
            .where(col(Game.id).in_(ids))
            .where(Game.game_status == GameStatus.IN_PROGRESS)
        )
    ).all()
    return {game_id for game_id, live_state in rows if is_paused(live_state)}


def _grace_seconds(room: Room | None, paused_game_ids: set[UUID]) -> int:
    """How long a disconnected member of this room is kept.

    - A link whose room is gone: the ordinary grace (there is nothing to protect).

    - A lobby (no active game) keeps them longer: mobile users background the tab
      all the time, and the host can kick an idle player.
    - A game the host has paused for the prayer keeps them far longer: phones lock
      and sockets drop while everyone prays, and nobody is waiting on anyone. Finite
      on purpose — a host who never comes back is still removed, ownership transfers,
      and the new host can resume. On resume the game also moves `disconnected_at`
      forward by the pause (BaseGameController.resume_game), so the ordinary grace
      then counts only time the game was running.
    - A running game: the ordinary grace.
    """
    if room is None:
        return GRACE_PERIOD_SECONDS
    if not room.active_game_id:
        return LOBBY_GRACE_PERIOD_SECONDS
    if room.active_game_id in paused_game_ids:
        return PAUSED_GAME_GRACE_PERIOD_SECONDS
    return GRACE_PERIOD_SECONDS


def member_grace_seconds(room: Room, active_game: Game | None) -> int:
    """The grace ``_remove_expired_users`` applies to this room's away members, from rows already read.

    The same rule as the sweep (``_grace_seconds``), for a caller that has the room
    and its active game in hand: ``RoomController.get_room_state`` uses it to show
    each away player's countdown without another query.
    """
    paused: set[UUID] = set()
    if (
        active_game is not None
        and active_game.game_status == GameStatus.IN_PROGRESS
        and is_paused(active_game.live_state)
    ):
        paused.add(active_game.id)
    return _grace_seconds(room, paused)


def away_seconds_left(link: RoomUserLink, grace_seconds: int, now: datetime | None = None) -> int | None:
    """Whole seconds before the sweep removes this away member; None while they are connected.

    Rounded UP, so a fresh disconnect in the lobby reads 600 ("away · 10:00") and 0
    means "due at the next sweep" (it runs every DISCONNECT_CHECK_INTERVAL_SECONDS).
    Clamped to ``[0, grace_seconds]``. Naive arithmetic on purpose: every
    ``RoomUserLink`` timestamp is naive (root CLAUDE.md), so ``now`` is too. A link
    marked disconnected without a ``disconnected_at`` is never swept, so it has no
    countdown either.
    """
    if link.connected or link.disconnected_at is None:
        return None
    instant = now if now is not None else datetime.now()
    left = math.ceil(grace_seconds - (instant - link.disconnected_at).total_seconds())
    return min(max(left, 0), grace_seconds)


def _past_grace(link: RoomUserLink, grace_seconds: int) -> bool:
    """Whether ``link`` has been disconnected for longer than ``grace_seconds`` (naive, like the column)."""
    threshold = datetime.fromtimestamp(datetime.now().timestamp() - grace_seconds)
    return link.disconnected_at is not None and link.disconnected_at < threshold


async def _still_expired(session: AsyncSession, link: RoomUserLink) -> RoomUserLink | None:
    """The link re-read from the database if it is STILL past its grace, else None.

    The sweep's rows were read before any removal. Since then the player may have
    reconnected, or the host may have resumed a paused game — which moves every away
    player's ``disconnected_at`` forward (``_shift_disconnect_grace``) — or paused
    one. Removing on the stale row would drop a player at a timestamp that no
    longer exists. A few queries per *removal*, which is rare — not per link per tick.

    ``_remove_member`` calls it UNDER the game lock, which a resume holds too, so the
    answer cannot change between this check and the removal.
    """
    fresh = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.id == link.id).execution_options(populate_existing=True)
        )
    ).first()
    if fresh is None or fresh.connected or fresh.disconnected_at is None:
        return None
    room = (
        await session.exec(select(Room).where(Room.id == fresh.room_id).execution_options(populate_existing=True))
    ).first()
    paused = await _paused_game_ids(session, {room.active_game_id if room else None})
    return fresh if _past_grace(fresh, _grace_seconds(room, paused)) else None


async def _cancel_orphaned_games(session: AsyncSession) -> tuple[set[str], set[str]]:
    """Cancel every running game its room has let go of (BR-05). Returns (room_ids, game_ids).

    An orphan is IN_PROGRESS while its room is INACTIVE or points at another game.
    Nothing else can end it: every departure path starts from ``room.active_game_id``.
    The deactivation paths now cancel the game themselves; this step also cleans the
    orphans written before they did. One query finds them (rare, so each is then
    re-checked and cancelled under its own lock, one commit each).
    """
    candidates = (
        await session.exec(
            select(Game.id)
            .join(Room, col(Room.id) == col(Game.room_id))
            .where(Game.game_status == GameStatus.IN_PROGRESS)
            .where(
                or_(
                    col(Room.type) == RoomType.INACTIVE,
                    and_(col(Room.active_game_id).is_not(None), col(Room.active_game_id) != col(Game.id)),
                )
            )
        )
    ).all()

    room_ids: set[str] = set()
    game_ids: set[str] = set()
    for game_id in candidates:
        async with get_game_lock(str(game_id), session):
            game = await _fresh_game(session, game_id)
            room = await _fresh_room(session, game.room_id) if game is not None and game.room_id else None
            if game is None or room is None or not _is_orphaned(game, room):
                await session.commit()
                continue
            await cancel_running_game(session, game, room)
            await session.commit()
        logger.warning("Cancelled orphaned game {} of room {} (room type {})", game_id, room.id, room.type)
        room_ids.add(str(room.id))
        game_ids.add(str(game_id))
    return room_ids, game_ids


def _is_orphaned(game: Game, room: Room) -> bool:
    """A running game whose room no longer leads to it."""
    if game.game_status != GameStatus.IN_PROGRESS:
        return False
    if room.type == RoomType.INACTIVE:
        return True
    return room.active_game_id is not None and room.active_game_id != game.id


async def _win_sweep_election(session: AsyncSession) -> bool:
    """Whether this worker sweeps this tick (BDP-11, PD-12).

    PostgreSQL: the worker whose transaction takes ``pg_try_advisory_xact_lock`` on
    ``DISCONNECT_SWEEP_LOCK_KEY`` — transaction-scoped, never the session-level
    ``pg_advisory_lock``, which leaks when the pool recycles a connection. The others
    skip the tick. SQLite (dev, tests) has one process: always.
    """
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return True
    # `execute`, not `exec`: `exec` is typed for Select statements and cannot carry raw
    # SQL with bound parameters (same as game_lock).
    result = await session.execute(  # ty: ignore[deprecated]
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DISCONNECT_SWEEP_LOCK_KEY}
    )
    return bool(result.scalar())


async def run_sweep_tick(
    engine: AsyncEngine,
    on_room_changed: Callable[[str], None] | None = None,
    on_game_changed: Callable[[str], None] | None = None,
    *,
    cancel_orphans: bool = True,
) -> bool:
    """One tick of the shared sweep, done by ONE worker of all. False when another worker has it.

    Every uvicorn worker runs ``disconnect_checker_loop``, and every one of them used to
    sweep the same rows: four room broadcasts for one change, and the losers' DELETE
    warning "expected to delete 1 row(s); 0 were matched". The tick now runs under an
    election (``_win_sweep_election``) held by a transaction of its own — it does
    nothing but hold the lock, never a write — because the sweep itself commits once per
    removal, and a commit releases a transaction-scoped lock. The sweep's own
    transaction ends with a COMMIT even when it only read: a session closed on a
    read-only transaction rolls it back, and those rollbacks outnumbered real commits
    ten to one in the production metrics (PD-12).
    """
    async with AsyncSession(engine, expire_on_commit=False) as election:
        if not await _win_sweep_election(election):
            await election.commit()
            return False
        async with AsyncSession(engine, expire_on_commit=False) as session:
            stale_rooms = await _mark_stale_users(session)
            expired_rooms, expired_games = await _remove_expired_users(session)
            orphan_rooms, orphan_games = await _cancel_orphaned_games(session) if cancel_orphans else (set(), set())
            await session.commit()
        await election.commit()

    if on_room_changed:
        for room_id in stale_rooms | expired_rooms | orphan_rooms:
            on_room_changed(room_id)
    if on_game_changed:
        for game_id in expired_games | orphan_games:
            on_game_changed(game_id)
    return True


async def disconnect_checker_loop(
    engine: AsyncEngine,
    on_room_changed: Callable[[str], None] | None = None,
    on_game_changed: Callable[[str], None] | None = None,
    on_worker_tick: Callable[[AsyncSession], Awaitable[object]] | None = None,
) -> None:
    """The worker's background presence service, every ``DISCONNECT_CHECK_INTERVAL_SECONDS``.

    - The shared sweep (``run_sweep_tick``): one worker of all per tick.
    - ``on_worker_tick(session)``, in EVERY worker, outside the election: work about this
      worker's own sockets (``ws.handlers.audit_local_socket_memberships`` — a kick
      served by another worker cannot reach a socket held here).
    - While it runs, ``on_room_changed`` also hears every presence a REST request of
      this worker restores (``announce_presence_restored``).
    """
    tick = 0
    with presence_listener(on_room_changed) if on_room_changed else _no_listener():
        while True:
            try:
                await run_sweep_tick(
                    engine,
                    on_room_changed,
                    on_game_changed,
                    cancel_orphans=tick % ORPHANED_GAME_SWEEP_EVERY_TICKS == 0,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in disconnect checker loop")

            if on_worker_tick is not None:
                try:
                    async with AsyncSession(engine, expire_on_commit=False) as session:
                        await on_worker_tick(session)
                        await session.commit()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in the worker tick of the disconnect checker loop")

            tick += 1
            await asyncio.sleep(DISCONNECT_CHECK_INTERVAL_SECONDS)


@contextmanager
def _no_listener() -> Iterator[None]:
    yield


# ─── Socket.IO presence ──────────────────────────────────────────────────────


async def _record_disconnect_game_end(
    session: AsyncSession,
    state: dict,
    *,
    game_type: str,
    winners: set[str],
    default_role: str,
) -> None:
    """Record stats and achievements for a game that ended because someone dropped.

    Ending by disconnect is a very common path — a player closing the tab decides
    plenty of games — and it used to record NOTHING: the handlers flipped the game to
    FINISHED and wrote the winner, but never ran the stat/achievement flow. Those
    games counted for no one: not in totals, not in win streaks, not towards a badge.

    Staged only, no commit: the caller is inside ``get_game_lock`` and commits once
    at the end of its block. A failure propagates and rolls the whole handler back,
    leaving the game IN_PROGRESS for the next checker pass rather than half-ended.
    """
    newly_unlocked = await record_game_end(
        session,
        state,
        game_type=game_type,
        winners=winners,
        default_role=default_role,
    )
    if newly_unlocked:
        state["newly_unlocked_achievements"] = newly_unlocked


async def mark_user_disconnected(session: AsyncSession, user_id: str, room_id: str) -> bool:
    """Mark a user as disconnected (but not permanently removed). Called on Socket.IO disconnect.

    True when it flipped a connected link: only then is there news for the room. An
    already-away link (the sweep marked it, and broadcast it) or a removed seat is not.
    The seat is read FOR UPDATE, like ``update_heartbeat``'s (see there).
    """
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == UUID(room_id))
            .where(RoomUserLink.user_id == UUID(user_id))
            .where(RoomUserLink.connected == True)  # noqa: E712
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if not link:
        return False
    link.connected = False
    link.disconnected_at = datetime.now()
    session.add(link)
    await session.commit()
    logger.info("Socket.IO disconnect: marked user {} as disconnected in room {}", user_id, room_id)
    return True


async def update_heartbeat(session: AsyncSession, user_id: str, room_id: str) -> HeartbeatResult:
    """Refresh a member's presence (Socket.IO connect, heartbeat, join_game) and say what it found.

    ``RESTORED`` is what the handler must announce to the room (BDP-04): the connect
    used to answer the room state to the returning socket alone, and the heartbeat
    answered nothing, so everyone else kept seeing the player away.

    The seat is read FOR UPDATE: a leave, a kick or the sweep deleting it between this
    read and the write below now waits for this commit (milliseconds; this transaction
    holds that one row and waits on nothing else). Read plainly, the deletion could commit
    first, and the flush's UPDATE matched no row: ``StaleDataError``, logged with its
    traceback at WARNING by the Socket.IO handlers, so sent to the error tracker
    (``tests/api/controllers/test_presence_writes_postgres.py``).
    """
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == UUID(room_id))
            .where(RoomUserLink.user_id == UUID(user_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if not link:
        return HeartbeatResult.NOT_A_MEMBER
    restored = refresh_presence(link)
    session.add(link)
    await session.commit()
    return HeartbeatResult.RESTORED if restored else HeartbeatResult.REFRESHED


# ─── A member leaves for good ────────────────────────────────────────────────


class _Removal(NamedTuple):
    removed: bool
    # The room's active game when the member left (whatever its status), for the
    # caller's game_updated: a departure can finish the game it was in.
    game_id: UUID | None = None


async def _handle_permanent_disconnect(session: AsyncSession, link: RoomUserLink) -> None:
    """A member leaves the room for good: the leave, kick and grace-sweep path, and account deletion.

    Signature kept on purpose: ``RoomController.kick_player`` / ``ban_player`` /
    ``leave_room`` and the account deletion (``UserController``) call it. It commits ONCE,
    the caller's staged writes included (the ban's RoomBan, deleted invites and new PIN).

    **Lock order.** It takes the lock of the room's active game BEFORE reading the
    game (BR-04), and nothing else. A caller may hold the room lock (``room:{id}``,
    taken before any game lock everywhere) but must NOT hold a game lock: the SQLite
    fallback lock is not reentrant. The pre-lock read runs with autoflush off, so a
    caller's staged writes are flushed only once the game lock is held: flushed
    before, an UPDATE of the room row would wait on a move that holds the game lock
    and finishes the game (it writes that row) while this waits on that move's lock.
    """
    await _remove_member(session, link)


async def _remove_member(session: AsyncSession, link: RoomUserLink, *, only_if_expired: bool = False) -> _Removal:
    """Remove ``link``'s member from the room and from its running game, under the game lock.

    ``only_if_expired`` (the sweep): re-check under the lock that the link is still
    past its grace — a reconnect or a resume (which holds the same lock) may have
    committed since the sweep read it.

    Every read after the lock is fresh (``populate_existing``): with
    ``expire_on_commit=False`` a plain re-select hands back the identity-mapped copy
    read before the lock, and committing that copy erased the move that held the lock
    meanwhile — the committed vote vanished, a FINISHED game lost its winner (BR-04).
    """
    user_id = link.user_id
    room_id = link.room_id
    async with AsyncExitStack() as locks:
        locked = await _lock_active_game(session, room_id, locks)
        room = await _fresh_room(session, room_id) if room_id else None
        if room is not None and room.active_game_id and room.active_game_id not in locked:
            # A game started (or replaced the one locked) between the read and the lock.
            await locks.enter_async_context(get_game_lock(str(room.active_game_id), session))
            room = await _fresh_room(session, room_id)
        game = await _fresh_game(session, room.active_game_id) if room is not None and room.active_game_id else None

        if only_if_expired and await _still_expired(session, link) is None:
            await session.commit()
            return _Removal(removed=False)
        if not await _delete_link(session, link):
            # Another departure path removed this member first (a kick racing the
            # sweep): its commit did the whole departure. Commit the caller's staged writes.
            await session.commit()
            return _Removal(removed=False)
        if room is None:
            await session.commit()
            return _Removal(removed=True)

        # Read BEFORE the departure is played: it decides whether there is a game left to play it into.
        remaining = _still_seated(
            (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all(),
            member_grace_seconds(room, game),
        )
        if not remaining:
            # Deactivate the empty room — and end its game, which nothing could end once
            # the room let go of it (BR-05): later departures skip it, it read "In
            # progress" for ever, and its words could never be kept. CANCELLED, and the
            # departure is NOT played into it first: played, it could decide the game
            # (the undercover leaving → a civilians' win) for players who are all gone
            # past their grace, and the sweep's row order — whose grace ran out first —
            # picked the result.
            if game is not None:
                _record_departure_from_cancelled_game(game, str(user_id))
                await cancel_running_game(session, game, room)
                detach_room_if_current(room, game)
            room.type = RoomType.INACTIVE
            session.add(room)
            await session.commit()
            logger.info("Permanently disconnected user {} from room {} (room emptied)", user_id, room_id)
            return _Removal(removed=True, game_id=game.id if game is not None else None)

        if game is not None and game.live_state and game.game_status == GameStatus.IN_PROGRESS:
            await _handle_game_disconnect(session, game, str(user_id), room, commit=False)

        if room.owner_id == user_id:
            room.owner_id = _next_owner(remaining).user_id
            session.add(room)

        await session.commit()
    logger.info("Permanently disconnected user {} from room {}", user_id, room_id)
    return _Removal(removed=True, game_id=game.id if game is not None else None)


def _still_seated(links: Sequence[RoomUserLink], grace_seconds: int) -> list[RoomUserLink]:
    """The seats that keep a room alive: connected, or away and still inside their grace.

    A room is empty only when nobody is coming back. Counting the connected seats alone
    (R1) cancelled a running game for players whose phones had merely locked during the
    in-person discussion (the heartbeat goes stale after 20 s, the first away player is
    swept after 180 s), and broke the prayer pause's 45 minutes: the first phone to
    outlast its grace cancelled the game for everyone still inside theirs. The grace is
    the sweep's own rule (``member_grace_seconds``). A seat marked away with no
    ``disconnected_at`` is never swept, so it is not counted either: it would keep the
    room alive for good.
    """
    return [
        link
        for link in links
        if link.connected or (link.disconnected_at is not None and not _past_grace(link, grace_seconds))
    ]


def _next_owner(remaining: Sequence[RoomUserLink]) -> RoomUserLink:
    """Who inherits the room from a departing host: a player before a spectator, connected before away.

    `remaining` includes spectators, so handing it to remaining[0] blindly could make a
    spectator the host — and the host is who starts games, changes settings and kicks,
    while _prepare_game_start excludes spectators from the roster. Within each kind, a
    connected member first; an away one is still inside their grace (``_still_seated``).
    """
    return min(remaining, key=lambda member: (member.is_spectator, not member.connected))


def _record_departure_from_cancelled_game(game: Game, user_id: str) -> None:
    """The departure that empties the room, on the running game about to be cancelled. Staged only.

    The leaver is still marked (``mark_player_left``: every departure from a running game
    is, owner rule (b)), and a quiz reads as over, as when its last player leaves.
    Nothing else of the departure is played: the game ends CANCELLED, for no one.
    """
    state = game.live_state
    if not state or game.game_status != GameStatus.IN_PROGRESS:
        return
    if any(player.get("user_id") == user_id for player in state.get("players", [])):
        mark_player_left(state, user_id)
    if game.type in (GameType.WORD_QUIZ, GameType.MCQ_QUIZ):
        state["game_over"] = True
    game.live_state = state
    flag_modified(game, "live_state")


async def _lock_active_game(session: AsyncSession, room_id: UUID | None, locks: AsyncExitStack) -> set[UUID]:
    """Take the lock of the room's active game, if any; returns the game ids locked.

    Autoflush is off for the read and the lock: see ``_handle_permanent_disconnect``.
    A column read, not the Room entity, so nothing stale enters the identity map.
    """
    if room_id is None:
        return set()
    with session.no_autoflush:
        game_id = (await session.exec(select(Room.active_game_id).where(Room.id == room_id))).first()
        if game_id is None:
            return set()
        await locks.enter_async_context(get_game_lock(str(game_id), session))
    return {game_id}


async def _fresh_room(session: AsyncSession, room_id: UUID | None) -> Room | None:
    return (
        await session.exec(select(Room).where(Room.id == room_id).execution_options(populate_existing=True))
    ).first()


async def _fresh_game(session: AsyncSession, game_id: UUID | None) -> Game | None:
    return (
        await session.exec(select(Game).where(Game.id == game_id).execution_options(populate_existing=True))
    ).first()


async def _delete_link(session: AsyncSession, link: RoomUserLink) -> bool:
    """Delete the seat; False when it was already gone.

    A statement rather than ``session.delete``: two departure paths removing the same
    member (a kick and the sweep) both deleted the same row, and the second one's flush
    warned "expected to delete 1 row(s); 0 were matched". The DELETE waits for the
    first one's commit and then counts 0, which is the answer we need.
    """
    if link.id is None:
        return False
    result = await session.exec(delete(RoomUserLink).where(col(RoomUserLink.id) == link.id))
    if link in session:
        session.expunge(link)
    return result.rowcount > 0


async def _handle_game_disconnect(
    session: AsyncSession, game: Game, user_id: str, room: Room, *, commit: bool = True
) -> None:
    """Handle game-specific disconnect logic. The caller holds ``get_game_lock``."""
    state = game.live_state
    if not state:
        return

    if game.type == GameType.UNDERCOVER:
        await _handle_undercover_disconnect(session, game, user_id, room, commit=commit)
    elif game.type == GameType.CODENAMES:
        await _handle_codenames_disconnect(session, game, user_id, room, commit=commit)
    elif game.type == GameType.WORD_QUIZ:
        await _handle_wordquiz_disconnect(session, game, user_id, room, commit=commit)
    elif game.type == GameType.MCQ_QUIZ:
        await _handle_mcqquiz_disconnect(session, game, user_id, room, commit=commit)


# Each _handle_*_disconnect runs with the game lock held by its caller
# (`_remove_member`) and, called from there, stages its writes for the caller's single
# commit (`commit=False`): two commits in one locked block would release the
# transaction-scoped lock halfway. Each re-reads the game with populate_existing, and
# records the leaver (`mark_player_left`) as soon as it finds them, before any
# end-of-game write: a leaver gets neither a win nor a loss (owner rule (b)).


async def _handle_undercover_disconnect(
    session: AsyncSession, game: Game, user_id: str, room: Room, *, commit: bool = True
) -> None:
    """Handle undercover game disconnect: mark player dead, check win conditions."""
    # Re-read, fresh. Assigned to a new name and then narrowed: the parameter is a
    # Game, and rebinding it to the Optional result of .first() is the sort of thing
    # that only looks harmless.
    locked_game = await _fresh_game(session, game.id)
    if not locked_game:
        return
    game = locked_game
    # Guard the LOCAL, not `game.live_state`: narrowing a local survives the
    # intervening awaits, narrowing an attribute does not.
    state = game.live_state
    if not state:
        return

    player = next((p for p in state["players"] if p["user_id"] == user_id), None)
    if not player:
        return
    mark_player_left(state, user_id)

    # An already-dead player still needs the repair below, so this can no
    # longer return early on them. The Mr. White who owes a guess is dead by
    # construction — they were just voted out — so bailing here is precisely
    # what left the turn stuck on `mr_white_guessing` with nobody able to
    # guess when they closed the tab instead.
    already_dead = not player["is_alive"]
    if not already_dead:
        player["is_alive"] = False
        state["eliminated_players"].append(
            {
                "user_id": player["user_id"],
                "username": player["username"],
                "role": player["role"],
                # Not a vote result: a drop-out is not "the elimination of round N",
                # so it carries 0 and vote history skips it rather than mislabelling
                # some round's outcome. See _build_vote_history.
                "round": 0,
            }
        )

    # Unblock the round the departing player was holding up: the describer
    # everyone was waiting on, the last outstanding vote, or the Mr. White who
    # owed a guess. Without this the turn had no way to advance — both
    # Undercover timers default to 0 ("no time limit"), so handle_timer_expired
    # answers timer_not_expired forever and only a host rematch freed the room.
    # See undercover_rules.repair_turn_after_dropout.
    # host_id: the ready quorum between rounds asks everyone but the host (WP-02).
    awaiting_mr_white_guess = repair_turn_after_dropout(
        state, user_id, host_id=str(room.owner_id) if room.owner_id else None
    )

    # Check win conditions BEFORE checking alive_count < 3
    # (e.g., the last undercover disconnected — civilians should win, not cancel).
    # Skipped while a Mr. White still owes a guess: a correct guess flips the
    # result, exactly as in submit_vote.
    winner = None if awaiting_mr_white_guess else winning_team(state)

    if winner:
        game.game_status = GameStatus.FINISHED
        game.end_time = datetime.now(UTC)
        # Record the winner like the normal end-of-game path does, otherwise
        # a game that ends because someone dropped shows no winner in history
        # and in the post-game summary.
        state["winner"] = "civilians" if winner == UndercoverRole.CIVILIAN.value else "undercovers"
        detach_room_if_current(room, game)
        session.add(room)
        await _record_disconnect_game_end(
            session,
            state,
            game_type="undercover",
            winners=undercover_winners(state, state["winner"]),
            default_role="civilian",
        )
    elif not awaiting_mr_white_guess and not already_dead:
        # Only a departure that actually thins the table can drop it below a
        # playable size; an already-dead player leaving changes no count.
        alive_count = sum(1 for p in state["players"] if p["is_alive"])
        if alive_count < 3:
            # Cancel game — not enough players and no winner
            await cancel_running_game(session, game, room)

    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    if commit:
        await session.commit()


def _codenames_team_strength(players: list[dict], team: str) -> int:
    """How well a Codenames team can still play: 2 = both roles, 1 = one role, 0 = gone.

    A turn needs a spymaster *and* an operative, so "has any player" was the wrong
    question. The ordering is what decides the winner when a team drops below 2:
    an empty team must never beat a crippled one.
    """
    roles = {p["role"] for p in players if p["team"] == team}
    if not roles:
        return 0
    return 2 if roles >= {CodenamesRole.SPYMASTER.value, CodenamesRole.OPERATIVE.value} else 1


async def _handle_codenames_disconnect(
    session: AsyncSession, game: Game, user_id: str, room: Room, *, commit: bool = True
) -> None:
    """Handle codenames game disconnect: check if team is empty."""
    # Re-read, fresh (see _handle_undercover_disconnect for the narrowing).
    locked_game = await _fresh_game(session, game.id)
    if not locked_game:
        return
    game = locked_game
    state = game.live_state
    if not state:
        return

    player = next((p for p in state["players"] if p["user_id"] == user_id), None)
    if not player:
        return
    mark_player_left(state, user_id)

    # Remove player from game
    state["players"] = [p for p in state["players"] if p["user_id"] != user_id]

    # Their card vote leaves with them (BR-09): it used to fill the team's quorum and
    # could be the card turned. When they were the last operative the team was
    # waiting on, the votes in hand settle the guess now — nobody left could vote again
    # to trigger it. A card that ends the game is finished below, as guess_card does.
    settled = release_departed_operative(state, user_id)

    # A team needs BOTH roles to keep playing, so "is the team empty?" was the
    # wrong question. Teams are dealt exactly one spymaster and the rest
    # operatives, so at the 4-player minimum either departure leaves a team of
    # one — non-empty, and unable to take a turn:
    #
    # - No operative: the spymaster gives a clue and nobody can guess or end
    #   the turn (both require an operative on the current team).
    # - No spymaster: nobody can give a clue, so guess_card answers
    #   NoClueGivenError and the turn can only ever be passed.
    #
    # Neither is rescued by the timer — the Codenames timers default to 0,
    # i.e. no time limit — so the game sat wedged until the host cancelled it.
    red = _codenames_team_strength(state["players"], CodenamesTeam.RED.value)
    blue = _codenames_team_strength(state["players"], CodenamesTeam.BLUE.value)

    if settled is not None and state.get("status") == CodenamesGameStatus.FINISHED.value:
        # The guess the departure settled ended the game (assassin, last card):
        # state["winner"] is the card's, not a matter of who is left standing.
        await _finish_codenames_game(session, game, room, state)
    elif red < 2 or blue < 2:
        # End the game and award it to whichever side is left standing. When
        # both are equally broken the side to move takes it, so the game always
        # records a winner rather than none.
        state["status"] = CodenamesGameStatus.FINISHED.value
        if red > blue:
            state["winner"] = CodenamesTeam.RED.value
        elif blue > red:
            state["winner"] = CodenamesTeam.BLUE.value
        else:
            state["winner"] = state.get("current_team") or CodenamesTeam.RED.value
        await _finish_codenames_game(session, game, room, state)

    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    if commit:
        await session.commit()


async def _finish_codenames_game(session: AsyncSession, game: Game, room: Room, state: dict) -> None:
    """End the Game row of a Codenames game whose ``state`` is finished, with its winner. Staged only."""
    game.game_status = GameStatus.FINISHED
    game.end_time = datetime.now(UTC)
    detach_room_if_current(room, game)
    session.add(room)
    await _record_disconnect_game_end(
        session,
        state,
        game_type="codenames",
        winners=codenames_winners(state, state["winner"]),
        default_role="operative",
    )


async def _handle_wordquiz_disconnect(
    session: AsyncSession, game: Game, user_id: str, room: Room, *, commit: bool = True
) -> None:
    """Handle Word Quiz game disconnect: remove player, end if no players left.

    A departure can also complete the open round — the leaver was the last player who
    had not found the word — and nothing else would close it: no answer can arrive, so
    it sat open until its timer. It moves to results here, under the same lock and in
    the same commit (``quiz_rules.settle_round_if_everyone_answered``); while paused,
    the resume does it.
    """
    # Re-read, fresh (see _handle_undercover_disconnect for the narrowing).
    locked_game = await _fresh_game(session, game.id)
    if not locked_game:
        return
    game = locked_game
    state = game.live_state
    if not state:
        return

    player = next((p for p in state["players"] if p["user_id"] == user_id), None)
    if not player:
        return
    mark_player_left(state, user_id)

    # Remove player from game
    state["players"] = [p for p in state["players"] if p["user_id"] != user_id]

    # Remove their answer, and their typed tries (Word Quiz results), if any
    state.get("answers", {}).pop(user_id, None)
    state.get("attempts", {}).pop(user_id, None)
    # And their "ready" mark: the quorum is computed from the remaining
    # roster, so a departed player's mark would make ready_count outrun it.
    ready_players = state.get("ready_players")
    if isinstance(ready_players, list) and user_id in ready_players:
        ready_players.remove(user_id)

    if not state["players"]:
        # No players left — cancel game
        state["game_over"] = True
        await cancel_running_game(session, game, room)
    elif settle_round_if_everyone_answered(state, GameType.WORD_QUIZ):
        # The leaver was the last one who had not found the word.
        logger.info("Word Quiz drop-out completed round: game={} user={}", game.id, user_id)

    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    if commit:
        await session.commit()


async def _handle_mcqquiz_disconnect(
    session: AsyncSession, game: Game, user_id: str, room: Room, *, commit: bool = True
) -> None:
    """Handle MCQ Quiz game disconnect: remove player, end if no players left.

    Like Word Quiz, a departure that leaves every remaining player answered moves the
    round to results at once, under the same lock and in the same commit; while
    paused, the resume does it (``quiz_rules.settle_round_if_everyone_answered``).
    """
    # Re-read, fresh (see _handle_undercover_disconnect for the narrowing).
    locked_game = await _fresh_game(session, game.id)
    if not locked_game:
        return
    game = locked_game
    state = game.live_state
    if not state:
        return

    player = next((p for p in state["players"] if p["user_id"] == user_id), None)
    if not player:
        return
    mark_player_left(state, user_id)

    # Remove player from game
    state["players"] = [p for p in state["players"] if p["user_id"] != user_id]

    # Remove their answer if any
    state.get("answers", {}).pop(user_id, None)
    # And their "ready" mark: the quorum is computed from the remaining
    # roster, so a departed player's mark would make ready_count outrun it.
    ready_players = state.get("ready_players")
    if isinstance(ready_players, list) and user_id in ready_players:
        ready_players.remove(user_id)

    if not state["players"]:
        # No players left — cancel game
        state["game_over"] = True
        await cancel_running_game(session, game, room)
    elif settle_round_if_everyone_answered(state, GameType.MCQ_QUIZ):
        # The leaver was the last one who had not answered.
        logger.info("MCQ drop-out completed round: game={} user={}", game.id, user_id)

    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    if commit:
        await session.commit()
