"""A presence write and the seat's deletion by another transaction (PostgreSQL).

``update_heartbeat`` and ``mark_user_disconnected`` read the seat, then write it. A seat
deleted in between — a leave, a kick or the sweep committing on another connection — left
the ORM's UPDATE matching no row, and the flush raised ``StaleDataError`` ("expected to
update 1 row(s); 0 were matched"): logged at WARNING with its traceback by the Socket.IO
handler (``_welcome_to_game``, the heartbeat, the disconnect), so sent to the error tracker,
for an ordinary race. Both now read the seat FOR UPDATE: a deletion that comes after the
read waits for the write's commit, one that came before leaves nothing to write.

The deletion is attempted from another connection between the read and the write (when the
write commits), with NOWAIT, so the test never waits: it reports whether the seat could be
taken from under the write.
"""

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from asyncpg.exceptions import LockNotAvailableError
from sqlalchemy import delete
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.disconnect import HeartbeatResult, mark_user_disconnected, update_heartbeat
from majlisna.api.models.relationship import RoomUserLink

pytestmark = pytest.mark.postgres


async def _delete_seat_unless_locked(engine: AsyncEngine, link_id: int) -> bool:
    """Delete the seat from another connection; False, at once, when a transaction holds its row."""
    async with AsyncSession(engine) as other:
        try:
            await other.exec(
                select(RoomUserLink.id).where(col(RoomUserLink.id) == link_id).with_for_update(nowait=True)
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != LockNotAvailableError.sqlstate:
                raise
            return False
        await other.exec(delete(RoomUserLink).where(col(RoomUserLink.id) == link_id))
        await other.commit()
        return True


async def _seated(session: AsyncSession, create_user, create_room, *, connected: bool) -> RoomUserLink:
    host = await create_user(username="presence_host", email="presence_host@test.com")
    room = await create_room(owner=host)
    guest = await create_user(username="presence_guest", email="presence_guest@test.com")
    away_since = datetime.now() - timedelta(seconds=30)
    link = RoomUserLink(
        room_id=room.id,
        user_id=guest.id,
        connected=connected,
        last_seen_at=datetime.now() if connected else away_since,
        disconnected_at=None if connected else away_since,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def _seat_exists(engine: AsyncEngine, link_id: int) -> bool:
    async with AsyncSession(engine) as fresh:
        return (await fresh.exec(select(RoomUserLink.id).where(col(RoomUserLink.id) == link_id))).first() is not None


async def test_a_heartbeat_keeps_the_seat_it_writes_until_its_commit(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """The seat cannot be deleted between the heartbeat's read and its write; the deletion goes on after."""
    # Prepare — an away seat; its deletion is attempted as the heartbeat commits
    link = await _seated(session, create_user, create_room, connected=False)
    link_id, room_id, user_id = link.id, link.room_id, link.user_id
    assert link_id is not None and room_id is not None and user_id is not None
    taken: list[bool] = []
    commit = session.commit

    async def commit_while_another_transaction_deletes_the_seat() -> None:
        taken.append(await _delete_seat_unless_locked(engine, link_id))
        await commit()

    # Act
    with patch.object(session, "commit", commit_while_another_transaction_deletes_the_seat):
        result = await update_heartbeat(session, str(user_id), str(room_id))

    # Assert — written, never pulled from under the write; deleted right after
    assert result is HeartbeatResult.RESTORED
    assert taken == [False]
    assert await _delete_seat_unless_locked(engine, link_id) is True
    assert await _seat_exists(engine, link_id) is False


async def test_a_heartbeat_for_a_seat_deleted_first_answers_not_a_member(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """The deletion committed before the heartbeat read the seat: nothing to write, no error."""
    # Prepare
    link = await _seated(session, create_user, create_room, connected=True)
    link_id, room_id, user_id = link.id, UUID(str(link.room_id)), UUID(str(link.user_id))
    assert link_id is not None
    assert await _delete_seat_unless_locked(engine, link_id) is True

    # Act
    result = await update_heartbeat(session, str(user_id), str(room_id))

    # Assert
    assert result is HeartbeatResult.NOT_A_MEMBER


async def test_a_disconnect_keeps_the_seat_it_marks_away_until_its_commit(
    session: AsyncSession, engine: AsyncEngine, create_user, create_room
):
    """The same for the away mark: a deletion between its read and its write waits for its commit."""
    # Prepare — a present seat; its deletion is attempted as the away mark commits
    link = await _seated(session, create_user, create_room, connected=True)
    link_id, room_id, user_id = link.id, link.room_id, link.user_id
    assert link_id is not None and room_id is not None and user_id is not None
    taken: list[bool] = []
    commit = session.commit

    async def commit_while_another_transaction_deletes_the_seat() -> None:
        taken.append(await _delete_seat_unless_locked(engine, link_id))
        await commit()

    # Act
    with patch.object(session, "commit", commit_while_another_transaction_deletes_the_seat):
        flipped = await mark_user_disconnected(session, str(user_id), str(room_id))

    # Assert
    assert flipped is True
    assert taken == [False]
    assert await _delete_seat_unless_locked(engine, link_id) is True
