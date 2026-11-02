import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    HEARTBEAT_THROTTLE_SECONDS,
    PUBLIC_ID_GENERATION_ATTEMPTS,
    ROOM_INVITE_LIFETIME_MINUTES,
    ROOM_INVITE_LIST_LIMIT,
    ROOM_PASSWORD_LENGTH,
)
from majlisna.api.controllers.auth import utc_instant
from majlisna.api.controllers.disconnect import (
    _handle_permanent_disconnect,
    announce_presence_restored,
    away_seconds_left,
    member_grace_seconds,
    refresh_presence,
)
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.game_cancel import cancel_running_game
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.controllers.shared import create_random_public_id
from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.error import (
    RoomNotFoundError,
    UserAlreadyInRoomError,
    UserNotFoundError,
    UserNotInRoomError,
    WrongRoomPasswordError,
)
from majlisna.api.models.game import GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomCreate, RoomJoin, RoomStatus, RoomType
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.room_invite import RoomInvite
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.common import StatusResponse
from majlisna.api.schemas.error import (
    CannotKickYourselfError,
    CanOnlyInviteFriendsError,
    FriendAlreadyInRoomError,
    InviterNotInRoomError,
    NotRoomHostError,
    PlayerCannotSpectateError,
    RoomBannedError,
    RoomBanNotFoundError,
    RoomCodeUnavailableError,
    RoomInviteExpiredError,
    RoomInviteNotFoundError,
)
from majlisna.api.schemas.room import (
    ActiveRoomResponse,
    KickPlayerResponse,
    RematchResponse,
    RoomBanView,
    RoomInviteResponse,
    RoomInviteView,
    RoomPlayerState,
    RoomSettings,
    RoomState,
    ShareLinkResponse,
    UpdateRoomSettingsResponse,
)
from majlisna.api.utils.dialect import dialect_insert

# The lifted-ban answer of DELETE /rooms/{id}/bans/{user_id}.
BAN_LIFTED_STATUS = "lifted"


def _new_room_pin(previous: str | None = None) -> str:
    """A random room PIN of ROOM_PASSWORD_LENGTH digits (``secrets``), never ``previous``.

    A kick rotates the PIN (owner rule (c)): the kicked player holds the share link, and
    a "rotation" that drew the same PIN one time in ten thousand would leave it working.
    Drawing from the other 9 999 values keeps the draw uniform over what remains.
    """
    space = 10**ROOM_PASSWORD_LENGTH
    if previous is None or not previous.isdigit() or len(previous) != ROOM_PASSWORD_LENGTH:
        value = secrets.randbelow(space)
    else:
        value = (int(previous) + 1 + secrets.randbelow(space - 1)) % space
    return f"{value:0{ROOM_PASSWORD_LENGTH}d}"


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
        await self._ensure_not_seated_elsewhere(owner_id)
        room_public_id = await self._generate_unique_public_id()
        room_create = RoomCreate(status=RoomStatus.ONLINE, password=_new_room_pin(), owner_id=owner_id)
        new_room = Room(**room_create.model_dump(), public_id=room_public_id, settings={"game_type": game_type.value})
        self.session.add(new_room)
        # The room row must exist before the link that references it.
        await self.session.flush()
        self.session.add(
            RoomUserLink(
                room_id=new_room.id,
                user_id=new_room.owner_id,
                last_seen_at=datetime.now(),
            )
        )
        # PD-05: "Rooms created" read 0 for every host — nothing ever wrote it. Counted in
        # the same transaction as the room, so a room never exists without its count.
        stats = await StatsController(self.session).get_or_create_user_stats(owner_id, commit=False)
        stats.rooms_created += 1
        self.session.add(stats)
        await self.session.commit()
        return await self._load_room_for_view(new_room.id)

    async def _load_room_for_view(self, room_id: UUID) -> Room:
        """The room with ``users`` eagerly loaded, which is all ``RoomView`` serializes.

        Never ``selectinload(Room.games)`` (BDP-09): that read the ``live_state`` JSON of
        every game ever played in the room — dozens on a rematch night — on every join,
        leave and spectate, and ``RoomView`` threw it away (it has no games field, on
        purpose: ``live_state`` holds the roles and words).
        """
        try:
            return (
                await self.session.exec(
                    select(Room).where(Room.id == room_id).options(selectinload(Room.users))  # ty: ignore[invalid-argument-type]
                )
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None

    async def _ensure_not_seated_elsewhere(self, user_id: UUID, room_id: UUID | None = None) -> None:
        """One live room at a time: refuse (``UserAlreadyInRoomError``, 409) a user who is
        connected in another ACTIVE room than ``room_id``.

        ``create_room`` always enforced it; ``join_room`` did not, so a share link seated a
        player in room B while they still sat in room A, whose host could then deal them
        into a game they never saw (BR-21, FR-2). ``details.room_id`` names the room they
        are in, so the client can offer "Leave it and join".

        Only membership of a LIVE room blocks. Without the join, a link to an INACTIVE
        room barred the user forever: a room is deactivated when its last *connected*
        member leaves, which leaves the links of anyone currently marked disconnected
        behind — and Socket.IO ``connect`` flips such a link back to connected on the
        next reconnect. The player then could not create a room, while
        ``get_active_room_for_user`` (which does filter on ACTIVE) reported no room to
        leave, so the UI offered no way out either. An away (disconnected) seat does not
        block either: the sweep frees it, and the rejoin banner offers to leave it.
        """
        statement = (
            select(RoomUserLink)
            .join(Room, Room.id == RoomUserLink.room_id)  # ty: ignore[invalid-argument-type]
            .where(RoomUserLink.user_id == user_id)
            .where(RoomUserLink.connected == True)  # noqa: E712
            .where(Room.type == RoomType.ACTIVE)
        )
        if room_id is not None:
            statement = statement.where(RoomUserLink.room_id != room_id)
        seated = (await self.session.exec(statement)).first()
        if seated:
            raise UserAlreadyInRoomError(user_id=user_id, room_id=seated.room_id)

    async def _ensure_not_banned(self, room_id: UUID, user_id: UUID) -> None:
        """Refuse (``RoomBannedError``, 403) a user the host kicked from this room.

        Checked before the PIN, so a banned player learns nothing from trying PINs.
        """
        ban = (
            await self.session.exec(
                select(RoomBan.id).where(RoomBan.room_id == room_id).where(RoomBan.user_id == user_id)
            )
        ).first()
        if ban is not None:
            raise RoomBannedError(room_id=room_id)

    @staticmethod
    def _require_host(room: Room, user_id: UUID, action: str) -> None:
        if room.owner_id != user_id:
            message = f"Only the host can {action}."
            raise NotRoomHostError(message=message, frontend_message=message)

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
        raise RoomCodeUnavailableError(attempts=PUBLIC_ID_GENERATION_ATTEMPTS)

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
        """Get a room with `users` eagerly loaded, for callers that serialize it.

        RoomView needs `.users`, and a lazy load on an async session raises
        MissingGreenlet. Everything that just reads scalar columns should use
        ``get_room_without_relations`` instead.
        """
        return await self._load_room_for_view(room_id)

    async def get_room_without_relations(self, room_id: UUID) -> Room:
        """Get a room without eager-loading any relationship.

        ``get_room_state`` runs on every heartbeat and on every Socket.IO
        broadcast, and it only reads scalar columns.
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
            raise NotRoomHostError(
                message="Only the room owner can delete the room.",
                frontend_message="Only the room owner can delete the room.",
            )
        async with self._room_and_game_locks(db_room):
            await self._cancel_active_game(db_room)
            links = (await self.session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()
            for link in links:
                await self.session.delete(link)
            # Its invites go with it (no foreign key declares ON DELETE).
            await self.session.exec(
                delete(RoomInvite)
                .where(col(RoomInvite.room_id) == room_id)
                .execution_options(synchronize_session=False)
            )
            db_room.type = RoomType.INACTIVE
            db_room.active_game_id = None
            self.session.add(db_room)
            await self.session.commit()
        logger.info("Room deleted (deactivated): room={} by user={}", room_id, user_id)

    @asynccontextmanager
    async def _room_and_game_locks(self, room: Room) -> AsyncGenerator[None, None]:
        """Hold the room lock, then the lock of the room's active game, if any.

        The room lock (``room:{id}``) is the one a game start holds while it deals, so no
        game is dealt into a room while it closes or rematches. The game lock makes a
        move that arrives at the same time wait, then see the game CANCELLED. Always in
        this order — nothing takes a game lock and then a room lock — and the caller
        commits INSIDE, once: on PostgreSQL both are transaction-scoped.
        """
        async with get_game_lock(f"room:{room.id}", self.session):
            # Re-read under the room lock: a start that committed while we waited set
            # active_game_id after our first read.
            await self.session.refresh(room)
            if room.active_game_id is None:
                yield
                return
            async with get_game_lock(str(room.active_game_id), self.session):
                yield

    async def _cancel_active_game(self, room: Room) -> None:
        """End the room's running game as CANCELLED (BR-05, BR-06). Never commits.

        Closing a room (``delete_room``) or a rematch only cleared ``active_game_id``:
        the game stayed IN_PROGRESS forever, still accepting moves, and nothing could
        end it once the room stopped pointing at it. The caller holds
        ``_room_and_game_locks`` and commits.
        """
        if room.active_game_id is None:
            return
        game = (
            await self.session.exec(
                select(Game).where(Game.id == room.active_game_id).execution_options(populate_existing=True)
            )
        ).first()
        if game is not None:
            await cancel_running_game(self.session, game, room)

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
        await self._ensure_not_banned(db_room.id, db_user.id)
        if not _passwords_match(db_room.password, room_join.password):
            raise WrongRoomPasswordError(room_id=db_room.id)
        await self._ensure_not_seated_elsewhere(db_user.id, db_room.id)
        room = await self._take_seat(db_room.id, db_user.id)
        logger.info("Room join: user={} room={}", user_id, db_room.id)
        return room

    async def _take_seat(self, room_id: UUID, user_id: UUID) -> Room:
        """Seat ``user_id`` as a player in ``room_id``, in ONE commit, once the door's checks
        passed (``join_room``: ban, PIN, one room at a time; ``accept_invite``: the invite,
        ban, one room at a time). Re-uses their link when they have one (a reconnection).

        A seat taken through either door spends the invites the player holds to that room:
        the accepted one, or one made moot by a join with the code and PIN.
        """
        await self.session.exec(
            delete(RoomInvite)
            .where(col(RoomInvite.room_id) == room_id)
            .where(col(RoomInvite.invitee_id) == user_id)
            .execution_options(synchronize_session=False)
        )
        # Check for existing connected link
        existing_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == user_id,
                    RoomUserLink.connected == True,  # noqa: E712
                )
            )
        ).first()
        if existing_link:
            # Update heartbeat for existing connected user
            existing_link.last_seen_at = datetime.now()
            self.session.add(existing_link)
            await self.session.commit()
            return await self._load_room_for_view(room_id)

        # Check for disconnected link (reconnection)
        disconnected_link = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == room_id,
                    RoomUserLink.user_id == user_id,
                    RoomUserLink.connected == False,  # noqa: E712
                )
            )
        ).first()
        if disconnected_link:
            disconnected_link.connected = True
            disconnected_link.last_seen_at = datetime.now()
            disconnected_link.disconnected_at = None
            self.session.add(disconnected_link)
        else:
            self.session.add(RoomUserLink(room_id=room_id, user_id=user_id, last_seen_at=datetime.now()))
        await self.session.commit()
        return await self._load_room_for_view(room_id)

    async def leave_room(self, room_id: UUID, user_id: UUID) -> Room:
        """Remove a user from a room.

        Voluntary leave fully removes the user (deletes RoomUserLink) so they
        won't see a "rejoin" prompt and are free to create/join other rooms.
        This reuses _handle_permanent_disconnect which also handles game cleanup,
        ownership transfer, and room deactivation when empty.

        The user identity always comes from the authenticated JWT — a client
        can never remove someone else from a room.
        """
        db_room = await self.get_room_without_relations(room_id)

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
            raise UserNotInRoomError(user_id=db_user.id, room_id=room_id)

        await _handle_permanent_disconnect(self.session, link)
        logger.info("Room leave: user={} room={}", user_id, room_id)

        return await self._load_room_for_view(db_room.id)

    async def join_room_as_spectator(self, room_id: UUID, user_id: UUID, password: str) -> Room:
        """Add a user to a room as a spectator.

        Requires the room PIN — spectating a private room without knowing its
        password is not allowed. Same doors as ``join_room``: an ACTIVE room only
        (BR-22: a deleted room accepted spectators), no banned user (checked before the
        PIN), and not while seated in another live room.
        """
        try:
            db_user = (await self.session.exec(select(User).where(User.id == user_id))).one()
        except NoResultFound:
            raise UserNotFoundError(user_id=user_id) from None
        try:
            db_room = (
                await self.session.exec(select(Room).where(Room.id == room_id).where(Room.type == RoomType.ACTIVE))
            ).one()
        except NoResultFound:
            raise RoomNotFoundError(room_id=room_id) from None
        await self._ensure_not_banned(db_room.id, db_user.id)
        if not _passwords_match(db_room.password, password):
            raise WrongRoomPasswordError(room_id=db_room.id)
        await self._ensure_not_seated_elsewhere(db_user.id, db_room.id)

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
                raise PlayerCannotSpectateError(user_id=user_id, room_id=room_id)
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

        room = await self._load_room_for_view(db_room.id)
        logger.info("Room spectator join: user={} room={}", user_id, room_id)
        return room

    async def get_room_state(self, room_id: UUID, user_id: UUID, update_heartbeat: bool = True) -> RoomState:
        """Get room state for all players.

        Only room members may read the state (it carries the room PIN). The
        Socket.IO notify layer calls this with update_heartbeat=False and a
        placeholder user, which skips the membership check — broadcasts are
        restricted to socket rooms that already enforce membership at connect.
        """
        # Before the first read: whatever was committed earlier is in this state (RoomState.as_of_ms).
        as_of_ms = time.time_ns() // 1_000_000
        room = await self.get_room_without_relations(room_id)

        # Update heartbeat for the requesting user
        if update_heartbeat:
            link = (
                await self.session.exec(
                    select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
                )
            ).first()
            if not link:
                raise UserNotInRoomError(user_id=user_id, room_id=room_id)
            needs_update = (
                link.disconnected_at is not None
                or not link.connected
                or not link.last_seen_at
                or (datetime.now() - link.last_seen_at).total_seconds() > HEARTBEAT_THROTTLE_SECONDS
            )
            if needs_update:
                restored = refresh_presence(link)
                self.session.add(link)
                await self.session.commit()
                if restored:
                    # A lobby polling REST while its socket is down brings the player
                    # back first; the socket's reconnect then finds nothing to restore,
                    # so this is where the table learns it (BDP-04, WP-04).
                    announce_presence_restored(room_id)

        # Get ALL users in the room (including temporarily disconnected).
        # Users are only removed from this list when permanently disconnected
        # (RoomUserLink deleted after grace period). This keeps the player count
        # stable during brief Socket.IO reconnections.
        #
        # In the order people sat down (join time, then id for a tie). Without an
        # ORDER BY the rows came back in heap order, which moves whenever a link row
        # is updated (every heartbeat): two phones loaded at different moments seated
        # the same table differently, and a reload reshuffled the halqa.
        all_links = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == room_id)
                .order_by(RoomUserLink.joined_at, RoomUserLink.user_id)  # ty: ignore[invalid-argument-type]
            )
        ).all()

        user_ids = [rul.user_id for rul in all_links]
        users = (await self.session.exec(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []  # ty: ignore[unresolved-attribute]
        user_map = {u.id: u for u in users}

        # The active game decides both the game type and how long an away member is
        # kept (lobby 10 min, running game 3 min, paused game 45 min).
        game = None
        if room.active_game_id:
            game = (await self.session.exec(select(Game).where(Game.id == room.active_game_id))).first()
        grace_seconds = member_grace_seconds(room, game)
        now = datetime.now()  # naive, like every RoomUserLink timestamp

        players: list[RoomPlayerState] = []
        for rul in all_links:
            # RoomUserLink.user_id is nullable in the model, so ask only when there is
            # something to ask about rather than looking up None.
            u = user_map.get(rul.user_id) if rul.user_id else None
            if u:
                players.append(
                    RoomPlayerState(
                        user_id=str(u.id),
                        username=u.username,
                        is_connected=rul.connected,
                        is_disconnected=not rul.connected,
                        is_host=room.owner_id == u.id,
                        is_spectator=rul.is_spectator,
                        away_seconds_left=away_seconds_left(rul, grace_seconds, now),
                    )
                )

        # Get game type from active game, or from room settings (set at creation)
        game_type = game.type.value if game else None
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
            as_of_ms=as_of_ms,
        )

    async def kick_player(self, room_id: UUID, host_id: UUID, target_id: UUID) -> KickPlayerResponse:
        """Kick a player from the room: host only, never yourself (owner rule (c)).

        A kick is a ban for the room's lifetime, not a removal the player undoes a second
        later with the same code and PIN (BR-20, SEC F04). Together, so that the first
        commit carries all four:

        - a ``RoomBan`` (room, target, banned_by=host) — idempotent on the unique pair;
        - a new PIN, different from the old one: the kicked player holds the share link,
          and so does anyone they forwarded it to;
        - the invites to this room the kicked player sent, deleted: an invite opens the
          room without the PIN, so it is the other thing they handed out (their friend's
          strip then answers 404). An invite a member sent stands, even one to the kicked
          player, whom the ban refuses at accept;
        - ``_handle_permanent_disconnect``, which removes the seat and plays the
          departure into a running game. The kicked player is a leaver there: neither a
          win nor a loss (owner rule (b), ``mark_player_left``).

        The route then tells the player (``you_were_kicked``), detaches their socket, and
        only then pushes the room state that carries the new PIN.
        """
        room = await self.get_room_without_relations(room_id)
        self._require_host(room, host_id, "kick players")
        if target_id == host_id:
            raise CannotKickYourselfError()

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

        await self._insert_ban(room_id, target_id, banned_by=host_id)
        # Before the PIN is staged: a statement autoflushes, and the room's UPDATE flushed
        # before the game lock deadlocks with a move that holds that lock and finishes the
        # game, which writes the room row (``_handle_permanent_disconnect``, "Lock order").
        await self.session.exec(
            delete(RoomInvite)
            .where(col(RoomInvite.room_id) == room_id)
            .where(col(RoomInvite.inviter_id) == target_id)
            .execution_options(synchronize_session=False)
        )
        room.password = _new_room_pin(room.password)
        self.session.add(room)
        # Commits (the ban, the revoked invites and the PIN with the departure).
        await _handle_permanent_disconnect(self.session, link)
        logger.info(
            "Room kick: user={} room={} by host={} (banned, their invites revoked, PIN rotated)",
            target_id,
            room_id,
            host_id,
        )
        return KickPlayerResponse(message="Player kicked")

    async def _insert_ban(self, room_id: UUID, user_id: UUID, *, banned_by: UUID) -> None:
        """``INSERT … ON CONFLICT DO NOTHING`` on (room, user): a second ban is a no-op,
        never a second row or an IntegrityError. Does not commit."""
        now = datetime.now(UTC)
        statement = (
            dialect_insert(self.session, RoomBan)
            .values(
                id=uuid4(),
                room_id=room_id,
                user_id=user_id,
                banned_by=banned_by,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["room_id", "user_id"])
        )
        await self.session.exec(statement)

    async def list_bans(self, room_id: UUID, user_id: UUID) -> list[RoomBanView]:
        """The players banned from the room, oldest ban first. Host only."""
        room = await self.get_room_without_relations(room_id)
        self._require_host(room, user_id, "see who is banned")
        rows = (
            await self.session.exec(
                select(RoomBan, User)
                .join(User, User.id == RoomBan.user_id)  # ty: ignore[invalid-argument-type]
                .where(RoomBan.room_id == room_id)
                .order_by(RoomBan.created_at, RoomBan.user_id)  # ty: ignore[invalid-argument-type]
            )
        ).all()
        return [RoomBanView(user_id=user.id, username=user.username, banned_at=ban.created_at) for ban, user in rows]

    async def lift_ban(self, room_id: UUID, host_id: UUID, user_id: UUID) -> StatusResponse:
        """Lift a ban. Host only; ``RoomBanNotFoundError`` (404) when there is none.

        The player is not re-seated, and the old PIN is not restored: they come back
        through a join with the current PIN, like anyone else.
        """
        room = await self.get_room_without_relations(room_id)
        self._require_host(room, host_id, "lift a ban")
        ban = (
            await self.session.exec(select(RoomBan).where(RoomBan.room_id == room_id).where(RoomBan.user_id == user_id))
        ).first()
        if ban is None:
            raise RoomBanNotFoundError(room_id=room_id, user_id=user_id)
        await self.session.delete(ban)
        await self.session.commit()
        logger.info("Room ban lifted: user={} room={} by host={}", user_id, room_id, host_id)
        return StatusResponse(status=BAN_LIFTED_STATUS)

    async def update_room_settings(
        self, room_id: UUID, user_id: UUID, settings: RoomSettings
    ) -> UpdateRoomSettingsResponse:
        """Update room settings. Only the host can update."""
        room = await self.get_room_without_relations(room_id)
        if room.owner_id != user_id:
            raise NotRoomHostError(
                message="Only the host can update room settings.",
                frontend_message="Only the host can update room settings.",
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
        """Clear active game and return to lobby. Preserves room settings and connected players.

        The outgoing game is closed before it is detached: only clearing
        ``active_game_id`` left the row IN_PROGRESS forever — still mutable, still a
        live game in history. It is cancelled under its game lock (BR-06), so a move
        racing the rematch either lands before it or sees CANCELLED, never a game the
        room no longer points at; a finished game stays finished.
        """
        room = await self.get_room_without_relations(room_id)
        self._require_host(room, user_id, "trigger a rematch")
        async with self._room_and_game_locks(room):
            await self._cancel_active_game(room)
            room.active_game_id = None
            self.session.add(room)
            await self.session.commit()
        return RematchResponse(room_id=str(room_id), status="lobby")

    async def get_active_room_for_user(self, user_id: UUID) -> ActiveRoomResponse | None:
        """Return the user's active room (connected or recently disconnected) if any."""
        link = (
            await self.session.exec(
                select(RoomUserLink)
                .join(Room, Room.id == RoomUserLink.room_id)  # ty: ignore[invalid-argument-type]
                .where(
                    RoomUserLink.user_id == user_id,
                    Room.type == RoomType.ACTIVE,
                )
                .order_by(RoomUserLink.joined_at.desc())  # ty: ignore[unresolved-attribute]
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
        """Invite a friend to the room: store the invite (``RoomInvite``) and return it.

        The inviter must be seated (connected) in the room, the invitee a friend not
        seated (connected) in it. One live invite per (room, invitee): inviting again
        refreshes it — the same id, the latest inviter, a full
        ``ROOM_INVITE_LIFETIME_MINUTES`` again — and every expired invite is purged.

        The invite carries no PIN: it is accepted by its id (``accept_invite``), so a kick
        that rotates the PIN after it was sent does not stop it. The Socket.IO
        ``room_invite`` push is the route's (``notify_room_invite`` with ``invite``):
        controllers do not touch the Socket.IO server.
        """
        room = await self.get_room_without_relations(room_id)

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
            raise InviterNotInRoomError()

        # Verify friendship exists
        friend_controller = FriendController(self.session)
        friends = await friend_controller.get_friends(inviter_id)
        is_friend = any(str(f.user_id) == str(friend_user_id) for f in friends)
        if not is_friend:
            raise CanOnlyInviteFriendsError()

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
            raise FriendAlreadyInRoomError()

        inviter = (await self.session.exec(select(User).where(User.id == inviter_id))).one()
        invite_id, expires_at = await self._store_invite(room_id, inviter_id, friend_user_id)
        await self.session.commit()
        logger.info("Room invite: user={} room={} by user={} invite={}", friend_user_id, room_id, inviter_id, invite_id)
        return RoomInviteResponse(
            room_id=str(room_id),
            invited_user_id=str(friend_user_id),
            message="Invite sent",
            invite=RoomInviteView(
                id=invite_id,
                room_id=room_id,
                public_id=room.public_id,
                invited_by=inviter.username,
                expires_at=expires_at,
            ),
        )

    async def _store_invite(self, room_id: UUID, inviter_id: UUID, invitee_id: UUID) -> tuple[UUID, datetime]:
        """Create or refresh the (room, invitee) invite; its id and ``expires_at``. Does not commit.

        An upsert on the unique pair (``INSERT … ON CONFLICT DO UPDATE``), so two members
        inviting one friend at once leave one row, never an IntegrityError. The expired
        invites, anyone's, are deleted first (``synchronize_session=False``: the ORM's
        in-Python ``expires_at < now`` would compare SQLite's naive values with an aware
        ``now``).
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ROOM_INVITE_LIFETIME_MINUTES)
        await self.session.exec(
            delete(RoomInvite).where(col(RoomInvite.expires_at) < now).execution_options(synchronize_session=False)
        )
        insert = dialect_insert(self.session, RoomInvite).values(
            id=uuid4(),
            room_id=room_id,
            inviter_id=inviter_id,
            invitee_id=invitee_id,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        upsert = insert.on_conflict_do_update(
            index_elements=["room_id", "invitee_id"],
            set_={
                "inviter_id": insert.excluded.inviter_id,
                "updated_at": insert.excluded.updated_at,
                "expires_at": insert.excluded.expires_at,
            },
        ).returning(col(RoomInvite.id))
        invite_id = (await self.session.exec(upsert)).scalar_one()
        return invite_id, expires_at

    async def accept_invite(self, invite_id: UUID, user_id: UUID) -> Room:
        """Seat the invitee in the invite's room, without the PIN; the seat spends the invite.

        The doors of ``join_room`` but the PIN, in this order:

        - the invite is the caller's (anyone else's, or one used up, is
          ``RoomInviteNotFoundError``, 404: nobody learns of another's invite);
        - not past ``expires_at`` (``RoomInviteExpiredError``, 410);
        - the room is ACTIVE (``RoomNotFoundError``, 404, as for a join);
        - the caller is not banned from it (``RoomBannedError``, 403): a kick after the
          invite was sent closes it like any door;
        - not seated in another live room (``UserAlreadyInRoomError``, 409, naming it): the
          invite stays, so the client can offer "Leave it and join" and accept again.

        The invite row is locked first (``SELECT … FOR UPDATE``; SQLite has no row locks):
        two tabs accepting at once take turns, and the second finds it spent (404), never
        a second insert of the seat's unique pair.
        """
        invite = (
            await self.session.exec(
                select(RoomInvite)
                .where(RoomInvite.id == invite_id)
                .where(RoomInvite.invitee_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).first()
        if invite is None:
            raise RoomInviteNotFoundError(invite_id=invite_id)
        if utc_instant(invite.expires_at) <= datetime.now(UTC):
            raise RoomInviteExpiredError(invite_id=invite_id)
        room = (
            await self.session.exec(select(Room).where(Room.id == invite.room_id).where(Room.type == RoomType.ACTIVE))
        ).first()
        if room is None:
            raise RoomNotFoundError(room_id=invite.room_id)
        await self._ensure_not_banned(room.id, user_id)
        await self._ensure_not_seated_elsewhere(user_id, room.id)
        seated = await self._take_seat(room.id, user_id)
        logger.info("Room invite accepted: user={} room={} invite={}", user_id, room.id, invite_id)
        return seated

    async def list_invites(self, user_id: UUID) -> list[RoomInviteView]:
        """The caller's live invites, newest first: not expired, to an ACTIVE room.

        What the app shell shows when it opens (an invite sent while the page was closed);
        the strip takes the first. At most ``ROOM_INVITE_LIST_LIMIT``. Never the PIN.
        """
        rows = (
            await self.session.exec(
                select(RoomInvite, Room.public_id, User.username)
                .join(Room, Room.id == RoomInvite.room_id)  # ty: ignore[invalid-argument-type]
                .join(User, User.id == RoomInvite.inviter_id)  # ty: ignore[invalid-argument-type]
                .where(RoomInvite.invitee_id == user_id)
                .where(col(RoomInvite.expires_at) > datetime.now(UTC))
                .where(Room.type == RoomType.ACTIVE)
                .order_by(col(RoomInvite.expires_at).desc(), col(RoomInvite.id))
                .limit(ROOM_INVITE_LIST_LIMIT)
            )
        ).all()
        return [
            RoomInviteView(
                id=invite.id,
                room_id=invite.room_id,
                public_id=public_id,
                invited_by=username,
                expires_at=utc_instant(invite.expires_at),
            )
            for invite, public_id, username in rows
        ]

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
