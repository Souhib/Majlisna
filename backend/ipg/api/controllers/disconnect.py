import asyncio
import os
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.codenames_helpers import CodenamesGameStatus
from ipg.api.controllers.game_lock import cleanup_game_lock, get_game_lock
from ipg.api.models.game import GameStatus
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.room import RoomType
from ipg.api.models.table import Game, Room
from ipg.api.models.undercover import UndercoverRole

HEARTBEAT_STALE_SECONDS = int(os.getenv("HEARTBEAT_STALE_SECONDS", "10"))
GRACE_PERIOD_SECONDS = int(os.getenv("DISCONNECT_GRACE_PERIOD_SECONDS", "30"))


async def disconnect_checker_loop(engine: AsyncEngine) -> None:
    """Background task that checks for stale heartbeats every 5 seconds."""
    while True:
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                now = datetime.now()
                stale = now - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
                grace_expired = now - timedelta(seconds=GRACE_PERIOD_SECONDS)

                # Mark recently-stale users as disconnected
                newly_stale = (
                    await session.exec(
                        select(RoomUserLink)
                        .where(RoomUserLink.connected == True)  # noqa: E712
                        .where(RoomUserLink.last_seen_at != None)  # noqa: E711
                        .where(RoomUserLink.last_seen_at < stale)
                    )
                ).all()
                for link in newly_stale:
                    link.connected = False
                    link.disconnected_at = now
                    session.add(link)
                if newly_stale:
                    await session.commit()

                # Permanently remove users whose grace period expired
                expired = (
                    await session.exec(
                        select(RoomUserLink)
                        .where(RoomUserLink.connected == False)  # noqa: E712
                        .where(RoomUserLink.disconnected_at != None)  # noqa: E711
                        .where(RoomUserLink.disconnected_at < grace_expired)
                    )
                ).all()
                for link in expired:
                    await _handle_permanent_disconnect(session, link)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in disconnect checker loop")

        await asyncio.sleep(5)


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
    logger.info(f"Permanently disconnected user {user_id} from room {room_id}")


async def _handle_game_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle game-specific disconnect logic."""
    state = game.live_state
    if not state:
        return

    if game.type.value == "undercover":
        await _handle_undercover_disconnect(session, game, user_id, room)
    elif game.type.value == "codenames":
        await _handle_codenames_disconnect(session, game, user_id, room)


async def _handle_undercover_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle undercover game disconnect: mark player dead, check win conditions."""
    async with get_game_lock(str(game.id)):
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
            cleanup_game_lock(str(game.id))
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
                cleanup_game_lock(str(game.id))

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()


async def _handle_codenames_disconnect(session: AsyncSession, game: Game, user_id: str, room: Room) -> None:
    """Handle codenames game disconnect: check if team is empty."""
    async with get_game_lock(str(game.id)):
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
            cleanup_game_lock(str(game.id))

        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()
