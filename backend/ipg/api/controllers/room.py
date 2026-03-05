from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.shared import create_random_public_id
from ipg.api.models.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from ipg.api.models.event import EventCreate
from ipg.api.models.relationship import RoomActivityLink, RoomUserLink
from ipg.api.models.room import RoomCreate, RoomJoin, RoomLeave, RoomType
from ipg.api.models.table import Activity, Game, Room, User


class RoomController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_room(self, room_create: RoomCreate) -> Room:
        is_user_in_room = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.user_id == room_create.owner_id)
                .where(RoomUserLink.connected == True)  # noqa: E712
            )
        ).first()
        if is_user_in_room:
            raise UserAlreadyInRoomError(user_id=room_create.owner_id, room_id=is_user_in_room.room_id)
        active_rooms = await self._get_all_active_rooms()
        room_public_id = create_random_public_id()
        while any(room.public_id == room_public_id for room in active_rooms):
            room_public_id = create_random_public_id()
        new_room = Room(**room_create.model_dump(), public_id=room_public_id)
        self.session.add(new_room)
        await self.session.commit()
        await self.session.refresh(new_room)
        room_user_link = RoomUserLink(
            room_id=new_room.id,
            user_id=new_room.owner_id,
            last_seen_at=datetime.now(),
        )
        self.session.add(room_user_link)
        await self.session.commit()
        # Re-fetch with relationships eagerly loaded for serialization
        room = (
            await self.session.exec(
                select(Room).where(Room.id == new_room.id).options(selectinload(Room.users), selectinload(Room.games))
            )
        ).one()
        return room

    async def check_if_user_is_in_room(self, user_id: UUID, room_id: UUID) -> bool:
        try:
            (
                await self.session.exec(
                    select(RoomUserLink)
                    .where(RoomUserLink.room_id == room_id)
                    .where(RoomUserLink.user_id == user_id)
                    .where(RoomUserLink.connected == True)  # noqa: E712
                )
            ).one()
            return True
        except NoResultFound:
            return False

    async def get_active_room_by_public_id(self, public_id: str) -> Room:
        try:
            return (
                await self.session.exec(
                    select(Room).where(Room.public_id == public_id).where(Room.type == RoomType.ACTIVE)
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=public_id) from None

    async def _get_all_active_rooms(self) -> Sequence[Room]:
        return (await self.session.exec(select(Room).where(Room.type == RoomType.ACTIVE))).all()

    async def get_rooms(self) -> Sequence[Room]:
        """Get all active rooms with users eagerly loaded."""
        return (
            await self.session.exec(select(Room).where(Room.type == RoomType.ACTIVE).options(selectinload(Room.users)))
        ).all()

    async def get_room_by_id(self, room_id: UUID) -> Room:
        """Get a room by its id."""
        try:
            return (
                await self.session.exec(
                    select(Room).where(Room.id == room_id).options(selectinload(Room.users), selectinload(Room.games))
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None

    async def delete_room(self, room_id: UUID) -> None:
        """Delete a room by its id."""
        try:
            db_room = (await self.session.exec(select(Room).where(Room.id == room_id))).one()
            await self.session.delete(db_room)
            await self.session.commit()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None

    async def join_room(self, room_join: RoomJoin) -> Room:
        """Add a user to a room. Handles reconnection if link exists with connected=False."""
        try:
            db_user = (await self.session.exec(select(User).where(User.id == room_join.user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=room_join.user_id) from None
        try:
            db_room = (await self.session.exec(select(Room).where(Room.id == room_join.room_id))).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_join.room_id) from None
        if db_room.password != room_join.password:
            raise WrongRoomPasswordError(room_id=db_room.id)

        # Check for existing connected link
        existing_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == db_room.id,
                    RoomUserLink.user_id == db_user.id,
                    RoomUserLink.connected == True,  # noqa: E712
                )
            )
        ).first()
        if existing_link:
            # Update heartbeat for existing connected user
            existing_link.last_seen_at = datetime.now()
            self.session.add(existing_link)
            await self.session.commit()
            room = (
                await self.session.exec(
                    select(Room)
                    .where(Room.id == db_room.id)
                    .options(selectinload(Room.users), selectinload(Room.games))
                )
            ).one()
            return room

        # Check for disconnected link (reconnection)
        disconnected_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == db_room.id,
                    RoomUserLink.user_id == db_user.id,
                    RoomUserLink.connected == False,  # noqa: E712
                )
            )
        ).first()
        if disconnected_link:
            disconnected_link.connected = True
            disconnected_link.last_seen_at = datetime.now()
            disconnected_link.disconnected_at = None
            self.session.add(disconnected_link)
            await self.session.commit()
        else:
            user_room_link = RoomUserLink(
                room_id=db_room.id,
                user_id=db_user.id,
                last_seen_at=datetime.now(),
            )
            self.session.add(user_room_link)
            await self.session.commit()

        room = (
            await self.session.exec(
                select(Room).where(Room.id == db_room.id).options(selectinload(Room.users), selectinload(Room.games))
            )
        ).one()
        return room

    async def leave_room(self, room_leave: RoomLeave) -> Room:
        """Remove a user from a room."""
        try:
            db_room = (
                await self.session.exec(
                    select(Room).where(Room.id == room_leave.room_id).options(selectinload(Room.users))
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_leave.room_id) from None

        try:
            db_user = (await self.session.exec(select(User).where(User.id == room_leave.user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=room_leave.user_id) from None

        if not any(user_room_link.id == db_user.id for user_room_link in db_room.users):
            raise UserNotInRoomError(user_id=db_user.id, room_id=room_leave.room_id)  # type: ignore
        if db_room.owner_id == db_user.id:
            db_room.type = RoomType.INACTIVE
            self.session.add(db_room)

        user_room_link = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == room_leave.room_id)
                .where(RoomUserLink.user_id == db_user.id)
                .where(RoomUserLink.connected == True)  # noqa: E712
            )
        ).first()
        if not user_room_link:
            raise UserNotInRoomError(user_id=db_user.id, room_id=room_leave.room_id)  # type: ignore
        user_room_link.connected = False
        self.session.add(user_room_link)
        await self.session.commit()
        room = (
            await self.session.exec(
                select(Room).where(Room.id == db_room.id).options(selectinload(Room.users), selectinload(Room.games))
            )
        ).one()
        return room

    async def get_room_state(self, room_id: UUID, user_id: UUID) -> dict:
        """Get room state with connection status for all players. Updates heartbeat."""
        room = await self.get_room_by_id(room_id)

        # Update heartbeat for requesting user
        link = (
            await self.session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
            )
        ).first()
        if link:
            link.last_seen_at = datetime.now()
            if not link.connected:
                link.connected = True
                link.disconnected_at = None
            self.session.add(link)
            await self.session.commit()

        # Get all connected users with their connection status (bulk fetch to avoid N+1)
        all_links = (await self.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()

        user_ids = [rul.user_id for rul in all_links]
        users = (await self.session.exec(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
        user_map = {u.id: u for u in users}

        players = []
        for rul in all_links:
            u = user_map.get(rul.user_id)
            if u:
                players.append(
                    {
                        "user_id": str(u.id),
                        "username": u.username,
                        "is_connected": rul.connected,
                        "is_disconnected": not rul.connected and rul.disconnected_at is not None,
                        "is_host": room.owner_id == u.id,
                    }
                )

        # Get game type from active game
        game_type = None
        if room.active_game_id:
            game = (await self.session.exec(select(Game).where(Game.id == room.active_game_id))).first()
            if game:
                game_type = game.type.value

        return {
            "id": str(room.id),
            "public_id": room.public_id,
            "password": room.password,
            "owner_id": str(room.owner_id),
            "active_game_id": str(room.active_game_id) if room.active_game_id else None,
            "game_type": game_type,
            "players": players,
            "type": room.type.value,
        }

    async def create_room_activity(self, room_id: UUID, activity_create: EventCreate) -> Activity:
        """Create an activity."""
        try:
            db_room = (await self.session.exec(select(Room).where(Room.id == room_id))).one()
            activity = Activity(
                room_id=db_room.id,
                user_id=activity_create.user_id,
                name=activity_create.name,
                data=activity_create.data,
            )
            self.session.add(activity)
            await self.session.commit()
            await self.session.refresh(activity)
            room_activity_link = RoomActivityLink(activity_id=activity.id, room_id=db_room.id)
            self.session.add(room_activity_link)
            await self.session.commit()
            return activity
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None
        except IntegrityError:
            raise UserNotFoundError(user_id=activity_create.user_id) from None
