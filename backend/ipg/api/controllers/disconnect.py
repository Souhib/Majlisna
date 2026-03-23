import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import DISCONNECT_CHECK_INTERVAL_SECONDS, GRACE_PERIOD_SECONDS, HEARTBEAT_STALE_SECONDS
from ipg.api.controllers.codenames_helpers import CodenamesGameStatus
from ipg.api.controllers.game_lock import get_game_lock
from ipg.api.models.game import GameStatus, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.room import RoomType
from ipg.api.models.table import Game, Room
from ipg.api.models.undercover import UndercoverRole


async def _mark_stale_users(session: AsyncSession) -> set[str]:
    """Mark connected users with stale heartbeats as disconnected. Returns affected room IDs."""
    now = datetime.now()
    stale_threshold = datetime.fromtimestamp(now.timestamp() - HEARTBEAT_STALE_SECONDS)

    newly_stale = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.connected == True)  # noqa: E712
            .where(RoomUserLink.last_seen_at != None)  # noqa: E711
            .where(RoomUserLink.last_seen_at < stale_threshold)
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

    Returns (affected_room_ids, affected_game_ids).
    """
    grace_threshold = datetime.fromtimestamp(datetime.now().timestamp() - GRACE_PERIOD_SECONDS)

    expired = (
        await session.exec(
            select(RoomUserLink)
            .where(RoomUserLink.connected == False)  # noqa: E712
            .where(RoomUserLink.disconnected_at != None)  # noqa: E711
            .where(RoomUserLink.disconnected_at < grace_threshold)
        )
    ).all()

    room_ids: set[str] = set()
    game_ids: set[str] = set()
    for link in expired:
        if not link.room_id:
            await _handle_permanent_disconnect(session, link)
            continue

        room = (await session.exec(select(Room).where(Room.id == link.room_id))).first()

        # Skip removal for rooms without an active game (lobby).
        # Mobile users frequently background the tab — don't punish them.
        # The host can manually kick idle players if needed.
        if room and not room.active_game_id:
            continue

        room_ids.add(str(link.room_id))
        if room and room.active_game_id:
            game_ids.add(str(room.active_game_id))
        await _handle_permanent_disconnect(session, link)
    return room_ids, game_ids


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
    elif room.owner_id == user_id and remaining:
        # Transfer ownership
        room.owner_id = remaining[0].user_id
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


async def _handle_undercover_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle undercover game disconnect: mark player dead, check win conditions."""
    async with get_game_lock(str(game.id), session):
        # Re-fetch to avoid stale state
        game = (await session.exec(select(Game).where(Game.id == game.id))).first()
        if not game or not game.live_state:
            return
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == user_id), None)
        if not player or not player["is_alive"]:
            return

        player["is_alive"] = False
        state["eliminated_players"].append(
            {
                "user_id": player["user_id"],
                "username": player["username"],
                "role": player["role"],
            }
        )

        alive_count = sum(1 for p in state["players"] if p["is_alive"])
        if alive_count < 3:
            # Cancel game
            game.game_status = GameStatus.CANCELLED
            game.end_time = datetime.now()
            room.active_game_id = None
            session.add(room)
        else:
            # Check win conditions
            num_alive_undercover = sum(
                1 for p in state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value and p["is_alive"]
            )
            num_alive_civilian = sum(
                1 for p in state["players"] if p["role"] == UndercoverRole.CIVILIAN.value and p["is_alive"]
            )
            num_alive_mr_white = sum(
                1 for p in state["players"] if p["role"] == UndercoverRole.MR_WHITE.value and p["is_alive"]
            )

            game_over = (
                (num_alive_undercover == 0 and num_alive_mr_white == 0)
                or num_alive_civilian == 0
                or (num_alive_undercover + num_alive_mr_white >= num_alive_civilian)
            )

            if game_over:
                game.game_status = GameStatus.FINISHED
                game.end_time = datetime.now()
                room.active_game_id = None
                session.add(room)

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()


async def _handle_codenames_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle codenames game disconnect: check if team is empty."""
    async with get_game_lock(str(game.id), session):
        game = (await session.exec(select(Game).where(Game.id == game.id))).first()
        if not game or not game.live_state:
            return
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == user_id), None)
        if not player:
            return

        # Remove player from game
        state["players"] = [p for p in state["players"] if p["user_id"] != user_id]

        # Check if either team is empty
        red_players = [p for p in state["players"] if p["team"] == "red"]
        blue_players = [p for p in state["players"] if p["team"] == "blue"]

        if not red_players or not blue_players:
            # End game — remaining team wins
            state["status"] = CodenamesGameStatus.FINISHED.value
            if not red_players:
                state["winner"] = "blue"
            else:
                state["winner"] = "red"
            game.game_status = GameStatus.FINISHED
            game.end_time = datetime.now()
            room.active_game_id = None
            session.add(room)

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()


async def _handle_wordquiz_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle Word Quiz game disconnect: remove player, end if no players left."""
    async with get_game_lock(str(game.id), session):
        game = (await session.exec(select(Game).where(Game.id == game.id))).first()
        if not game or not game.live_state:
            return
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == user_id), None)
        if not player:
            return

        # Remove player from game
        state["players"] = [p for p in state["players"] if p["user_id"] != user_id]

        # Remove their answer if any
        state.get("answers", {}).pop(user_id, None)

        if not state["players"]:
            # No players left — cancel game
            state["game_over"] = True
            game.game_status = GameStatus.CANCELLED
            game.end_time = datetime.now()
            room.active_game_id = None
            session.add(room)

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()
