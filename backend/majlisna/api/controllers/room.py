import secrets
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import HEARTBEAT_THROTTLE_SECONDS, PUBLIC_ID_GENERATION_ATTEMPTS
from majlisna.api.controllers.disconnect import _handle_permanent_disconnect
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.shared import create_random_public_id
from majlisna.api.models.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomCreate, RoomJoin, RoomStatus, RoomType
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.error import BaseError
from majlisna.api.schemas.room import (
    ActiveRoomResponse,
    KickPlayerResponse,
    RematchResponse,
    RoomInviteResponse,
    RoomPlayerState,
    RoomSettings,
    RoomState,
    ShareLinkResponse,
    UpdateRoomSettingsResponse,
)


def _passwords_match(stored: str, supplied: str) -> bool:
    """Constant-time PIN comparison that tolerates any client input.

    ``secrets.compare_digest`` on **str** arguments raises TypeError as soon as
    either side holds a non-ASCII character, and nothing validates the shape of
    the PIN a client sends: ``RoomJoin.password`` only coerces to str, and the
    spectator request takes a bare str. So joining with a PIN like "é123"
    crashed the endpoint into a 500 instead of answering "wrong password".
    Comparing the UTF-8 bytes keeps the timing guarantee and never raises.
    """
    return secrets.compare_digest(stored.encode("utf-8"), supplied.encode("utf-8"))


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
        room_public_id = await self._generate_unique_public_id()
        password = f"{secrets.randbelow(10000):04d}"
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

    async def _generate_unique_public_id(self) -> str:
        """Pick a room code that is free across ALL rooms, not just active ones.

        Room.public_id carries a DB-level UNIQUE constraint and rooms are only
        soft-deleted (marked INACTIVE), so old codes stay in the table forever.
        Checking collisions against active rooms alone eventually produced an
        unhandled IntegrityError — a 500 on room creation.
        """
        for _ in range(PUBLIC_ID_GENERATION_ATTEMPTS):
            candidate = create_random_public_id()
            taken = (await self.session.exec(select(Room.public_id).where(Room.public_id == candidate))).first()
            if not taken:
                return candidate
        raise BaseError(
            message=f"Could not allocate a free room code after {PUBLIC_ID_GENERATION_ATTEMPTS} attempts",
            frontend_message="Couldn't create a room right now. Please try again.",
            status_code=503,
        )

    async def check_if_user_is_in_room(self, user_id: UUID, room_id: UUID) -> bool:
        # .first(), not .one(): duplicate links for the same (room, user) are
        # possible on legacy data, and "is the user in the room" must answer that
        # question rather than blow up with MultipleResultsFound.
        link = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == room_id)
                .where(RoomUserLink.user_id == user_id)
                .where(RoomUserLink.connected == True)  # noqa: E712
            )
        ).first()
        return link is not None

    async def get_active_room_by_public_id(self, public_id: str) -> Room:
        try:
            return (
                await self.session.exec(
                    select(Room).where(Room.public_id == public_id).where(Room.type == RoomType.ACTIVE)
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=public_id) from None

    async def get_room_by_id(self, room_id: UUID) -> Room:
        """Get a room with `users` and `games` eagerly loaded.

        Only for callers that serialize the Room (RoomView needs `.users`, and a
        lazy load on an async session raises MissingGreenlet). Everything that
        just reads scalar columns should use ``get_room_without_relations`` instead —
        `selectinload(Room.games)` pulls the full `live_state` JSON of every game
        ever played in the room.
        """
        try:
            return (
                await self.session.exec(
                    select(Room).where(Room.id == room_id).options(selectinload(Room.users), selectinload(Room.games))
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None

    async def get_room_without_relations(self, room_id: UUID) -> Room:
        """Get a room without eager-loading any relationship.

        ``get_room_state`` runs on every heartbeat and on every Socket.IO
        broadcast, and it only reads scalar columns — yet it went through
        ``get_room_by_id``, whose ``selectinload(Room.games)`` fetches the
        ``live_state`` JSON of every past game in that room on each call.
        """
        room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
        if room is None:
            raise RoomNotFoundError(room_id=room_id)
        return room

    async def delete_room(self, room_id: UUID, user_id: UUID) -> None:
        """Delete (deactivate) a room by its id. Only the room owner may delete.

        Soft-delete: the room is marked INACTIVE and every member link is
        removed, so game history rows (which reference room.id) stay intact
        instead of triggering FK violations on hard delete.
        """
        try:
            db_room = (await self.session.exec(select(Room).where(Room.id == room_id))).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None
        if db_room.owner_id != user_id:
            raise BaseError(
                message="Only the room owner can delete the room.",
                frontend_message="Only the room owner can delete the room.",
                status_code=403,
            )
        links = (await self.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()
        for link in links:
            await self.session.delete(link)
        db_room.type = RoomType.INACTIVE
        db_room.active_game_id = None
        self.session.add(db_room)
        await self.session.commit()
        logger.info("Room deleted (deactivated): room={} by user={}", room_id, user_id)

    async def join_room(self, room_join: RoomJoin, user_id: UUID) -> Room:
        """Add a user to a room. Handles reconnection if link exists with connected=False.

        The user identity always comes from the authenticated JWT (user_id
        parameter) — a client can never join as someone else.
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
        # Only ACTIVE rooms are joinable. public_id is globally unique and rooms
        # are only soft-deleted, so without the type filter a stale code let a
        # user re-attach to a room that had been closed — landing them in a lobby
        # that can never start a game.
        try:
            db_room = (
                await self.session.exec(
                    select(Room).where(Room.public_id == room_join.public_room_id).where(Room.type == RoomType.ACTIVE)
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_join.public_room_id) from None
        if not _passwords_match(db_room.password, room_join.password):
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
        logger.info("Room join: user={} room={}", user_id, db_room.id)
        return room

    async def leave_room(self, room_id: UUID, user_id: UUID) -> Room:
        """Remove a user from a room.

        Voluntary leave fully removes the user (deletes RoomUserLink) so they
        won't see a "rejoin" prompt and are free to create/join other rooms.
        This reuses _handle_permanent_disconnect which also handles game cleanup,
        ownership transfer, and room deactivation when empty.

        The user identity always comes from the authenticated JWT — a client
        can never remove someone else from a room.
        """
        try:
            db_room = (
                await self.session.exec(select(Room).where(Room.id == room_id).options(selectinload(Room.users)))
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None

        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None

        link = (
            await self.session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == db_user.id)
            )
        ).first()
        if not link:
            raise UserNotInRoomError(user_id=db_user.id, room_id=room_id)  # type: ignore

        await _handle_permanent_disconnect(self.session, link)
        logger.info("Room leave: user={} room={}", user_id, room_id)

        room = (
            await self.session.exec(
                select(Room).where(Room.id == db_room.id).options(selectinload(Room.users), selectinload(Room.games))
            )
        ).one()
        return room

    async def join_room_as_spectator(self, room_id: UUID, user_id: UUID, password: str) -> Room:
        """Add a user to a room as a spectator.

        Requires the room PIN — spectating a private room without knowing its
        password is not allowed.
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
        try:
            db_room = (await self.session.exec(select(Room).where(Room.id == room_id))).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None
        if not _passwords_match(db_room.password, password):
            raise WrongRoomPasswordError(room_id=db_room.id)

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
            # An active player cannot demote themselves to spectator mid-game.
            # Their entry stays in live_state["players"] either way, so flipping
            # the flag only desynchronises the two views: the game still expects
            # them to describe/vote, while the lobby and the next game's roster
            # treat them as a spectator — and nothing (not even the host) can
            # flip it back.
            if not existing_link.is_spectator and db_room.active_game_id:
                raise BaseError(
                    message=f"User {user_id} is an active player in room {room_id} and cannot switch to spectator",
                    frontend_message="You're playing this game — leave the room to stop playing.",
                    status_code=409,
                )
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
        """Get room state for all players.

        Only room members may read the state (it carries the room PIN). The
        Socket.IO notify layer calls this with update_heartbeat=False and a
        placeholder user, which skips the membership check — broadcasts are
        restricted to socket rooms that already enforce membership at connect.
        """
        room = await self.get_room_without_relations(room_id)

        # Update heartbeat for the requesting user
        if update_heartbeat:
            link = (
                await self.session.exec(
                    select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
                )
            ).first()
            if not link:
                raise UserNotInRoomError(user_id=user_id, room_id=room_id)  # type: ignore
            needs_update = (
                link.disconnected_at is not None
                or not link.connected
                or not link.last_seen_at
                or (datetime.now() - link.last_seen_at).total_seconds() > HEARTBEAT_THROTTLE_SECONDS
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
        room = await self.get_room_without_relations(room_id)
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
        room = await self.get_room_without_relations(room_id)
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
        room = await self.get_room_without_relations(room_id)
        if room.owner_id != user_id:
            raise BaseError(
                message="Only the host can trigger a rematch.",
                frontend_message="Only the host can trigger a rematch.",
                status_code=403,
            )
        # Close the outgoing game before detaching it. Only clearing
        # active_game_id left the row IN_PROGRESS forever: it stayed mutable
        # (every mutation guard only checks game_status), it kept showing up as a
        # live game in history, and those rows accumulated with no way to end them.
        previous_game_id = room.active_game_id
        if previous_game_id:
            previous_game = (await self.session.exec(select(Game).where(Game.id == previous_game_id))).first()
            if previous_game and previous_game.game_status == GameStatus.IN_PROGRESS:
                previous_game.game_status = GameStatus.CANCELLED
                previous_game.end_time = datetime.now(UTC)
                self.session.add(previous_game)
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

    async def invite_friend_to_room(self, room_id: UUID, inviter_id: UUID, friend_user_id: UUID) -> RoomInviteResponse:
        """Invite a friend to join the room. Validates friendship and room membership.

        The Socket.IO `room_invite` event is emitted by the route via
        ``notify_room_invite`` after this validation passes — controllers do not
        touch the Socket.IO server directly.
        """
        await self.get_room_without_relations(room_id)

        # Verify the inviter is in the room
        inviter_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == inviter_id,
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
        friends = await friend_controller.get_friends(inviter_id)
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

        return RoomInviteResponse(
            room_id=str(room_id),
            invited_user_id=str(friend_user_id),
            message="Invite sent",
        )

    async def get_share_link(self, room_id: UUID, user_id: UUID) -> ShareLinkResponse:
        """Generate a share link for the room. Only room members can get the link."""
        room = await self.get_room_without_relations(room_id)
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
        return ShareLinkResponse(public_id=room.public_id, password=room.password)
