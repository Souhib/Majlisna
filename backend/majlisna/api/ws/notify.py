import asyncio
from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.table import Game, Room
from majlisna.api.ws.server import sio
from majlisna.api.ws.state import fetch_room_state
from majlisna.database import get_engine

# Strong references to prevent garbage collection of fire-and-forget tasks
_pending_tasks: set[asyncio.Task] = set()


def fire_notify_room_changed(room_id: str) -> None:
    """Schedule room notification (fire-and-forget). Use only from background tasks/event handlers.

    Route handlers should ``await notify_room_changed()`` directly so the
    Socket.IO event is guaranteed to be emitted before the HTTP response.
    """
    task = asyncio.create_task(notify_room_changed(room_id))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


def fire_notify_game_changed(game_id: str, room_id: str | None = None) -> None:
    """Schedule game notification (fire-and-forget). Use only from background tasks/event handlers.

    Route handlers should ``await notify_game_changed()`` directly so the
    Socket.IO event is guaranteed to be emitted before the HTTP response.
    """
    task = asyncio.create_task(notify_game_changed(game_id, room_id))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


async def _get_room_id_for_game(game_id: str) -> str | None:
    """Look up room_id from the Game table."""
    try:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            game = (await session.exec(select(Game).where(Game.id == UUID(game_id)))).first()
            return str(game.room_id) if game and game.room_id else None
    except Exception:
        logger.opt(exception=True).debug("Failed to look up room_id for game={}", game_id)
        return None


async def get_active_game_id(room_id: str) -> str | None:
    """The room's running game, if any (a fresh session, like every notify lookup).

    Routes that remove a member read it BEFORE the removal and hand it to
    ``notify_member_removed``: the removal itself can end the game and clear
    ``Room.active_game_id``.
    """
    try:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            room = (await session.exec(select(Room).where(Room.id == UUID(room_id)))).first()
            return str(room.active_game_id) if room and room.active_game_id else None
    except Exception:
        logger.opt(exception=True).debug("Failed to look up the active game of room={}", room_id)
        return None


async def notify_user_kicked(user_id: str, room_id: str) -> None:
    """Send 'you_were_kicked' event to the user's personal Socket.IO room."""
    try:
        await sio.emit("you_were_kicked", {"room_id": room_id}, to=f"user:{user_id}")
    except Exception:
        logger.opt(exception=True).error("Failed to notify kicked user={} room={}", user_id, room_id)


async def notify_room_invite(friend_user_id: str, room_id: str, invited_by: str) -> None:
    """Send a 'room_invite' event to the invited friend's personal Socket.IO room.

    Looks up the room's public_id/password in a fresh session so the invite carries
    everything the client needs to join. Awaited in the route handler after the
    invite has been validated by the controller. Best-effort: logs on failure.
    """
    try:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            room = (await session.exec(select(Room).where(Room.id == UUID(room_id)))).first()
            if not room:
                return
            await sio.emit(
                "room_invite",
                {
                    "room_id": str(room.id),
                    "public_id": room.public_id,
                    "password": room.password,
                    "invited_by": invited_by,
                },
                to=f"user:{friend_user_id}",
            )
    except Exception:
        logger.opt(exception=True).error("notify_room_invite FAILED for user={} room={}", friend_user_id, room_id)


async def notify_room_changed(room_id: str) -> None:
    """Broadcast fresh room state to all clients in the room.

    Awaited in route handlers to guarantee delivery before the HTTP response.
    """
    try:
        state = await fetch_room_state(room_id)
        await sio.emit("room_state", state, to=f"room:{room_id}")
    except Exception:
        logger.opt(exception=True).error("notify_room_changed FAILED for room={}", room_id)


async def notify_member_removed(room_id: str, game_id: str | None) -> None:
    """After a member left or was kicked: the room, and the game they were in, if any.

    A departure mid-game changes the game too — the leaver is eliminated, the turn
    moves on, the game may end (``_handle_permanent_disconnect``) — but only
    ``room_state`` used to go out. Game pages refetch on ``game_updated`` alone and
    poll only while their socket is down, so the rest of the table stayed on a stale
    game: the leaver still "describing…", the next describer never given the input.
    ``notify_game_changed`` also re-sends the room state.

    ``game_id`` is the room's active game read BEFORE the removal
    (``get_active_game_id``), never after: when the departure decides the game (the
    last Undercover kicked or gone) the room has no active game any more, and a
    lookup made then sent only ``room_state`` — the table sat on a finished game
    that still showed the leaver at their seat, with no colophon.
    """
    if game_id:
        await notify_game_changed(game_id, room_id)
    else:
        await notify_room_changed(room_id)


async def notify_chat_message(room_id: str, message_data: dict) -> None:
    """Broadcast a new chat message to all clients in the room.

    Awaited in route handlers to guarantee delivery before the HTTP response.
    """
    try:
        await sio.emit("chat_message", message_data, to=f"room:{room_id}")
    except Exception:
        logger.opt(exception=True).error("notify_chat_message FAILED for room={}", room_id)


async def notify_game_changed(game_id: str, room_id: str | None = None) -> None:
    """Broadcast the game_updated signal to the game room AND the room itself.

    Awaited in route handlers to guarantee delivery before the HTTP response.

    Instead of sending per-user state from the server (which doesn't work across
    multiple workers since get_participants is per-process), we emit a lightweight
    signal. Each client receives it and invalidates its TanStack Query cache,
    triggering a REST re-fetch of its own role-aware state.

    **Why both rooms.** Membership of ``game:{game_id}`` is built either by the
    client's own ``join_game`` or by ``auto_join_game_room``, and the latter walks a
    process-local SID map — so with 4 uvicorn workers it only reaches the players
    whose socket happens to live on the worker handling the request. The very first
    ``game_updated`` of a game (emitted by the start route, before clients have
    navigated and called ``join_game``) could therefore miss most of the table.
    ``room:{room_id}`` membership is established at connect for every member, so
    adding it closes that gap without depending on which worker serves what.

    Passing both rooms to a single emit rather than emitting twice is deliberate:
    ``get_participants`` merges a list of rooms into one recipient dict, so a client
    sitting in both — everyone on a game page — is delivered to exactly once.
    """
    # Resolve the room first: it is now part of the recipient set, not just a
    # follow-up notification.
    if not room_id:
        room_id = await _get_room_id_for_game(game_id)

    targets = [f"game:{game_id}"]
    if room_id:
        targets.append(f"room:{room_id}")

    try:
        await sio.emit("game_updated", {"game_id": game_id}, to=targets)
    except Exception:
        logger.opt(exception=True).error("notify_game_changed FAILED for game={}", game_id)

    if room_id:
        await notify_room_changed(room_id)
