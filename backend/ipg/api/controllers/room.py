import random
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.disconnect import _handle_permanent_disconnect
from ipg.api.controllers.friend import FriendController
from ipg.api.controllers.shared import create_random_public_id
from ipg.api.models.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from ipg.api.models.event import EventCreate
from ipg.api.models.game import GameType
from ipg.api.models.relationship import RoomActivityLink, RoomUserLink
from ipg.api.models.room import RoomCreate, RoomJoin, RoomLeave, RoomStatus, RoomType
from ipg.api.models.table import Activity, Game, Room, User
from ipg.api.schemas.error import BaseError
from ipg.api.schemas.room import (
    ActiveRoomResponse,
    KickPlayerResponse,
    RematchResponse,
    RoomInviteResponse,
    RoomPlayerState,
    RoomSettings,
    RoomState,
    UpdateRoomSettingsResponse,
)


class RoomController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_room(self, owner_id: UUID, game_type: GameType) -> Room:
        is_user_in_room = (
            await self.session.exec(
                select(RoomUserLink).where(RoomUserLink.user_id == owner_id).where(RoomUserLink.connected == True)  # noqa: E712
            )
        ).first()
        if is_user_in_room:
            raise UserAlreadyInRoomError(user_id=owner_id, room_id=is_user_in_room.room_id)
        active_rooms = await self._get_all_active_rooms()
        room_public_id = create_random_public_id()
        while any(room.public_id == room_public_id for room in active_rooms):
            room_public_id = create_random_public_id()
        password = f"{random.randint(0, 9999):04d}"
        room_create = RoomCreate(status=RoomStatus.ONLINE, password=password, owner_id=owner_id)
        new_room = Room(**room_create.model_dump(), public_id=room_public_id, settings={"game_type": game_type.value})
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
            db_room = (await self.session.exec(select(Room).where(Room.public_id == room_join.public_room_id))).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_join.public_room_id) from None
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
        logger.info("Room join: user={} room={}", room_join.user_id, db_room.id)
        return room

    async def leave_room(self, room_leave: RoomLeave) -> Room:
        """Remove a user from a room.

        Voluntary leave fully removes the user (deletes RoomUserLink) so they
        won't see a "rejoin" prompt and are free to create/join other rooms.
        This reuses _handle_permanent_disconnect which also handles game cleanup,
        ownership transfer, and room deactivation when empty.
        """
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

        link = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == room_leave.room_id)
                .where(RoomUserLink.user_id == db_user.id)
            )
        ).first()
        if not link:
            raise UserNotInRoomError(user_id=db_user.id, room_id=room_leave.room_id)  # type: ignore

        await _handle_permanent_disconnect(self.session, link)
        logger.info("Room leave: user={} room={}", room_leave.user_id, room_leave.room_id)

        room = (
            await self.session.exec(
                select(Room).where(Room.id == db_room.id).options(selectinload(Room.users), selectinload(Room.games))
            )
        ).one()
        return room

    async def join_room_as_spectator(self, room_id: UUID, user_id: UUID) -> Room:
        """Add a user to a room as a spectator."""
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
        try:
            db_room = (await self.session.exec(select(Room).where(Room.id == room_id))).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None

        # Check for existing link
        existing_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == db_room.id,
                    RoomUserLink.user_id == db_user.id,
                )
            )
        ).first()
        if existing_link:
            existing_link.connected = True
            existing_link.is_spectator = True
            existing_link.last_seen_at = datetime.now()
            existing_link.disconnected_at = None
            self.session.add(existing_link)
        else:
            link = RoomUserLink(
                room_id=db_room.id,
                user_id=db_user.id,
                last_seen_at=datetime.now(),
                is_spectator=True,
            )
            self.session.add(link)
        await self.session.commit()

        room = (
            await self.session.exec(
                select(Room).where(Room.id == db_room.id).options(selectinload(Room.users), selectinload(Room.games))
            )
        ).one()
        logger.info("Room spectator join: user={} room={}", user_id, room_id)
        return room

    async def get_room_state(self, room_id: UUID, user_id: UUID, update_heartbeat: bool = True) -> RoomState:
        """Get room state for all players."""
        room = await self.get_room_by_id(room_id)

        # Update heartbeat for the requesting user
        if update_heartbeat:
            link = (
                await self.session.exec(
                    select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
                )
            ).first()
            if link:
                needs_update = (
                    link.disconnected_at is not None
                    or not link.connected
                    or not link.last_seen_at
                    or (datetime.now() - link.last_seen_at).total_seconds() > 10
                )
                if needs_update:
                    link.last_seen_at = datetime.now()
                    link.connected = True
                    if link.disconnected_at is not None:
                        link.disconnected_at = None
                    self.session.add(link)
                    await self.session.commit()

        # Get ALL users in the room (including temporarily disconnected).
        # Users are only removed from this list when permanently disconnected
        # (RoomUserLink deleted after grace period). This keeps the player count
        # stable during brief Socket.IO reconnections.
        all_links = (await self.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()

        user_ids = [rul.user_id for rul in all_links]
        users = (await self.session.exec(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
        user_map = {u.id: u for u in users}

        players: list[RoomPlayerState] = []
        for rul in all_links:
            u = user_map.get(rul.user_id)
            if u:
                players.append(
                    RoomPlayerState(
                        user_id=str(u.id),
                        username=u.username,
                        is_connected=rul.connected,
                        is_disconnected=not rul.connected,
                        is_host=room.owner_id == u.id,
                        is_spectator=rul.is_spectator,
                    )
                )

        # Get game type from active game, or from room settings (set at creation)
        game_type = None
        if room.active_game_id:
            game = (await self.session.exec(select(Game).where(Game.id == room.active_game_id))).first()
            if game:
                game_type = game.type.value
        if not game_type and room.settings and room.settings.get("game_type"):
            game_type = room.settings["game_type"]

        return RoomState(
            id=str(room.id),
            public_id=room.public_id,
            password=room.password,
            owner_id=str(room.owner_id),
            active_game_id=str(room.active_game_id) if room.active_game_id else None,
            game_type=game_type,
            players=players,
            type=room.type.value,
            settings=room.settings,
        )

    async def kick_player(self, room_id: UUID, host_id: UUID, target_id: UUID) -> KickPlayerResponse:
        """Kick a player from the room. Only the host can kick."""
        room = await self.get_room_by_id(room_id)
        if room.owner_id != host_id:
            raise BaseError(
                message="Only the host can kick players.",
                frontend_message="Only the host can kick players.",
                status_code=403,
            )
        if target_id == host_id:
            raise BaseError(
                message="You cannot kick yourself.",
                frontend_message="You cannot kick yourself.",
                status_code=400,
            )

        link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == target_id,
                )
            )
        ).first()
        if not link:
            raise UserNotInRoomError(user_id=target_id, room_id=room_id)

        await _handle_permanent_disconnect(self.session, link)
        return KickPlayerResponse(message="Player kicked")

    async def update_room_settings(
        self, room_id: UUID, user_id: UUID, settings: RoomSettings
    ) -> UpdateRoomSettingsResponse:
        """Update room settings. Only the host can update."""
        room = await self.get_room_by_id(room_id)
        if room.owner_id != user_id:
            raise BaseError(
                message="Only the host can update room settings.",
                frontend_message="Only the host can update room settings.",
                status_code=403,
            )
        # Merge non-None fields into existing settings
        existing = room.settings or {}
        for key, value in settings.model_dump(exclude_none=True).items():
            existing[key] = value
        room.settings = existing
        flag_modified(room, "settings")
        self.session.add(room)
        await self.session.commit()
        return UpdateRoomSettingsResponse(room_id=str(room_id), settings=RoomSettings(**room.settings))

    async def rematch(self, room_id: UUID, user_id: UUID) -> RematchResponse:
        """Clear active game and return to lobby. Preserves room settings and connected players."""
        room = await self.get_room_by_id(room_id)
        if room.owner_id != user_id:
            raise BaseError(
                message="Only the host can trigger a rematch.",
                frontend_message="Only the host can trigger a rematch.",
                status_code=403,
            )
        room.active_game_id = None
        self.session.add(room)
        await self.session.commit()
        return RematchResponse(room_id=str(room_id), status="lobby")

    async def get_active_room_for_user(self, user_id: UUID) -> ActiveRoomResponse | None:
        """Return the user's active room (connected or recently disconnected) if any."""
        link = (
            await self.session.exec(
                select(RoomUserLink)
                .join(Room, Room.id == RoomUserLink.room_id)
                .where(
                    RoomUserLink.user_id == user_id,
                    Room.type == RoomType.ACTIVE,
                )
                .order_by(RoomUserLink.joined_at.desc())  # type: ignore
            )
        ).first()
        if not link:
            return None
        room = (await self.session.exec(select(Room).where(Room.id == link.room_id))).first()
        if not room:
            return None
        return ActiveRoomResponse(
            room_id=str(room.id),
            public_id=room.public_id,
            is_connected=link.connected,
        )

    async def invite_friend_to_room(self, room_id: UUID, host_id: UUID, friend_user_id: UUID) -> RoomInviteResponse:
        """Invite a friend to join the room. Validates friendship and room membership."""
        room = await self.get_room_by_id(room_id)

        # Verify the inviter is in the room
        inviter_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == host_id,
                    RoomUserLink.connected == True,  # noqa: E712
                )
            )
        ).first()
        if not inviter_link:
            raise BaseError(
                message="You must be in the room to invite friends.",
                frontend_message="You must be in the room to invite friends.",
                status_code=400,
            )

        # Verify friendship exists
        friend_controller = FriendController(self.session)
        friends = await friend_controller.get_friends(host_id)
        is_friend = any(str(f.user_id) == str(friend_user_id) for f in friends)
        if not is_friend:
            raise BaseError(
                message="You can only invite friends.",
                frontend_message="You can only invite friends.",
                status_code=400,
            )

        # Check if the friend is already in the room
        existing = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == friend_user_id,
                    RoomUserLink.connected == True,  # noqa: E712
                )
            )
        ).first()
        if existing:
            raise BaseError(
                message="User is already in the room.",
                frontend_message="This user is already in the room.",
                status_code=400,
            )

        # Emit Socket.IO invite event to the friend's personal room
        from ipg.api.ws.server import sio  # noqa: PLC0415

        inviter = (await self.session.exec(select(User).where(User.id == host_id))).first()
        await sio.emit(
            "room_invite",
            {
                "room_id": str(room.id),
                "public_id": room.public_id,
                "password": room.password,
                "invited_by": inviter.username if inviter else "Someone",
            },
            room=f"user:{friend_user_id}",
        )

        return RoomInviteResponse(
            room_id=str(room_id),
            invited_user_id=str(friend_user_id),
            message="Invite sent",
        )

    async def get_share_link(self, room_id: UUID, user_id: UUID) -> dict:
        """Generate a share link for the room. Only room members can get the link."""
        room = await self.get_room_by_id(room_id)
        # Verify user is in the room
        link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == user_id,
                    RoomUserLink.connected == True,  # noqa: E712
                )
            )
        ).first()
        if not link:
            raise UserNotInRoomError(user_id=user_id, room_id=room_id)
        return {
            "public_id": room.public_id,
            "password": room.password,
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
