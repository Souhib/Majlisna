import asyncio
import math
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DISCONNECT_CHECK_INTERVAL_SECONDS,
    GRACE_PERIOD_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    LOBBY_GRACE_PERIOD_SECONDS,
    PAUSED_GAME_GRACE_PERIOD_SECONDS,
)
from majlisna.api.controllers.codenames_helpers import CodenamesGameStatus, CodenamesRole, CodenamesTeam
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
    (``_still_expired``), because a resume or a reconnect may have committed since.

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

        room = rooms.get(link.room_id)
        if not _past_grace(link, _grace_seconds(room, paused_game_ids)):
            continue
        fresh = await _still_expired(session, link)
        if fresh is None:
            continue

        room_ids.add(str(link.room_id))
        if room and room.active_game_id:
            game_ids.add(str(room.active_game_id))
        await _handle_permanent_disconnect(session, fresh)
    return room_ids, game_ids


async def _load_rooms(session: AsyncSession, room_ids: set[UUID]) -> dict[UUID, Room]:
    """The rooms of a sweep, keyed by id — one query."""
    if not room_ids:
        return {}
    rows = (await session.exec(select(Room).where(col(Room.id).in_(room_ids)))).all()
    return {room.id: room for room in rows}


async def _paused_game_ids(session: AsyncSession, game_ids: set[UUID | None]) -> set[UUID]:
    """Which of these running games the host has paused for the prayer — one query."""
    ids = {game_id for game_id in game_ids if game_id}
    if not ids:
        return set()
    games = (
        await session.exec(select(Game).where(col(Game.id).in_(ids)).where(Game.game_status == GameStatus.IN_PROGRESS))
    ).all()
    return {game.id for game in games if is_paused(game.live_state)}


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

    The window is not closed entirely: this runs outside the game lock (the removal
    path takes it per game), so a resume committing between this read and the
    removal can still slip through. It shrinks from a whole sweep to milliseconds.
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


async def disconnect_checker_loop(
    engine: AsyncEngine,
    on_room_changed: Callable[[str], None] | None = None,
    on_game_changed: Callable[[str], None] | None = None,
) -> None:
    """Background task that checks for stale heartbeats periodically."""
    while True:
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                stale_rooms = await _mark_stale_users(session)
                expired_rooms, expired_games = await _remove_expired_users(session)

                if on_room_changed:
                    for rid in stale_rooms | expired_rooms:
                        on_room_changed(rid)

                if on_game_changed:
                    for gid in expired_games:
                        on_game_changed(gid)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in disconnect checker loop")

        await asyncio.sleep(DISCONNECT_CHECK_INTERVAL_SECONDS)


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


async def mark_user_disconnected(session: AsyncSession, user_id: str, room_id: str) -> None:
    """Mark a user as disconnected (but not permanently removed). Called on Socket.IO disconnect."""
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == UUID(room_id))
            .where(RoomUserLink.user_id == UUID(user_id))
            .where(RoomUserLink.connected == True)  # noqa: E712
        )
    ).first()
    if link:
        link.connected = False
        link.disconnected_at = datetime.now()
        session.add(link)
        await session.commit()
        logger.info("Socket.IO disconnect: marked user {} as disconnected in room {}", user_id, room_id)


async def update_heartbeat(session: AsyncSession, user_id: str, room_id: str) -> None:
    """Update heartbeat for a user. Called on Socket.IO connect."""
    link = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.room_id == UUID(room_id))
            .where(RoomUserLink.user_id == UUID(user_id))
        )
    ).first()
    if link:
        link.last_seen_at = datetime.now()
        link.connected = True
        if link.disconnected_at is not None:
            link.disconnected_at = None
        session.add(link)
        await session.commit()


async def _handle_permanent_disconnect(session: AsyncSession, link: RoomUserLink) -> None:
    """Handle permanent disconnect: remove from room, handle game disconnect."""
    user_id = link.user_id
    room_id = link.room_id

    # Delete the link (remove user from room)
    await session.delete(link)

    room = (await session.exec(select(Room).where(Room.id == room_id))).first()
    if not room:
        await session.commit()
        return

    # Handle active game disconnect
    if room.active_game_id:
        game = (await session.exec(select(Game).where(Game.id == room.active_game_id))).first()
        if game and game.live_state and game.game_status == GameStatus.IN_PROGRESS:
            await _handle_game_disconnect(session, game, str(user_id), room)

    # Check remaining connected users
    remaining = (
        await session.exec(
            select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.connected == True)  # noqa: E712
        )
    ).all()

    if not remaining:
        # Deactivate empty room
        room.type = RoomType.INACTIVE
        room.active_game_id = None
        session.add(room)
    elif room.owner_id == user_id:
        # Transfer ownership, preferring an actual player. `remaining` includes
        # spectators, so handing it to remaining[0] blindly could make a
        # spectator the host — and the host is who starts games, changes settings
        # and kicks, while _prepare_game_start excludes spectators from the
        # roster. Fall back to a spectator only if nobody else is left.
        next_owner = next((link for link in remaining if not link.is_spectator), remaining[0])
        room.owner_id = next_owner.user_id
        session.add(room)

    await session.commit()
    logger.info("Permanently disconnected user {} from room {}", user_id, room_id)


async def _handle_game_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle game-specific disconnect logic."""
    state = game.live_state
    if not state:
        return

    if game.type == GameType.UNDERCOVER:
        await _handle_undercover_disconnect(session, game, user_id, room)
    elif game.type == GameType.CODENAMES:
        await _handle_codenames_disconnect(session, game, user_id, room)
    elif game.type == GameType.WORD_QUIZ:
        await _handle_wordquiz_disconnect(session, game, user_id, room)
    elif game.type == GameType.MCQ_QUIZ:
        await _handle_mcqquiz_disconnect(session, game, user_id, room)


async def _handle_undercover_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle undercover game disconnect: mark player dead, check win conditions."""
    async with get_game_lock(str(game.id), session):
        # Re-fetch to avoid stale state
        # Re-read under the lock. Assigned to a new name and then narrowed: the
        # parameter is a Game, and rebinding it to the Optional result of .first()
        # is the sort of thing that only looks harmless.
        locked_game = (await session.exec(select(Game).where(Game.id == game.id))).first()
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
        awaiting_mr_white_guess = repair_turn_after_dropout(state, user_id)

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
            room.active_game_id = None
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
                game.game_status = GameStatus.CANCELLED
                game.end_time = datetime.now(UTC)
                room.active_game_id = None
                session.add(room)

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
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


async def _handle_codenames_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle codenames game disconnect: check if team is empty."""
    async with get_game_lock(str(game.id), session):
        # Re-read under the lock. Assigned to a new name and then narrowed: the
        # parameter is a Game, and rebinding it to the Optional result of .first()
        # is the sort of thing that only looks harmless.
        locked_game = (await session.exec(select(Game).where(Game.id == game.id))).first()
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

        # Remove player from game
        state["players"] = [p for p in state["players"] if p["user_id"] != user_id]

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

        if red < 2 or blue < 2:
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
            game.game_status = GameStatus.FINISHED
            game.end_time = datetime.now(UTC)
            room.active_game_id = None
            session.add(room)
            await _record_disconnect_game_end(
                session,
                state,
                game_type="codenames",
                winners=codenames_winners(state, state["winner"]),
                default_role="operative",
            )

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()


async def _handle_wordquiz_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle Word Quiz game disconnect: remove player, end if no players left.

    A departure can also complete the open round — the leaver was the last player who
    had not found the word — and nothing else would close it: no answer can arrive, so
    it sat open until its timer. It moves to results here, under the same lock and in
    the same commit (``quiz_rules.settle_round_if_everyone_answered``); while paused,
    the resume does it.
    """
    async with get_game_lock(str(game.id), session):
        # Re-read under the lock. Assigned to a new name and then narrowed: the
        # parameter is a Game, and rebinding it to the Optional result of .first()
        # is the sort of thing that only looks harmless.
        locked_game = (await session.exec(select(Game).where(Game.id == game.id))).first()
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
            game.game_status = GameStatus.CANCELLED
            game.end_time = datetime.now(UTC)
            room.active_game_id = None
            session.add(room)
        elif settle_round_if_everyone_answered(state, GameType.WORD_QUIZ):
            # The leaver was the last one who had not found the word.
            logger.info("Word Quiz drop-out completed round: game={} user={}", game.id, user_id)

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()


async def _handle_mcqquiz_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle MCQ Quiz game disconnect: remove player, end if no players left.

    Like Word Quiz, a departure that leaves every remaining player answered moves the
    round to results at once, under the same lock and in the same commit; while
    paused, the resume does it (``quiz_rules.settle_round_if_everyone_answered``).
    """
    async with get_game_lock(str(game.id), session):
        # Re-read under the lock. Assigned to a new name and then narrowed: the
        # parameter is a Game, and rebinding it to the Optional result of .first()
        # is the sort of thing that only looks harmless.
        locked_game = (await session.exec(select(Game).where(Game.id == game.id))).first()
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
            game.game_status = GameStatus.CANCELLED
            game.end_time = datetime.now(UTC)
            room.active_game_id = None
            session.add(room)
        elif settle_round_if_everyone_answered(state, GameType.MCQ_QUIZ):
            # The leaver was the last one who had not answered.
            logger.info("MCQ drop-out completed round: game={} user={}", game.id, user_id)

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()
