from datetime import datetime
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import HEARTBEAT_THROTTLE_SECONDS
from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.game_end_stats import scorable_players
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.error import (
    GameNotFoundError,
    NotEnoughPlayersError,
    PlayerRemovedFromGameError,
    RoomNotFoundError,
)
from majlisna.api.models.game import GameStatus
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.error import BaseError, TooManyPlayersError


class BaseGameController:
    """Base class for game controllers with shared utility methods."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._room_controller = RoomController(session)
        self._game_controller = GameController(session)
        self._stats_controller = StatsController(session)
        self._achievement_controller = AchievementController(session)

    async def _prepare_game_start(
        self, room_id: UUID, *, min_players: int = 1, max_players: int | None = None
    ) -> tuple[Room, list[User]]:
        """Shared game start preparation: validate room, check no active game, fetch players.

        Handles room locking, active game validation, and bulk user fetch (avoids N+1).
        Must be called inside a game lock context.

        Returns:
            tuple of (Room, list[User]) — the room and non-spectator player users.

        Raises:
            BaseError: if room already has an active game.
            RoomNotFoundError: if no players found.
            NotEnoughPlayersError: if fewer than min_players.
            TooManyPlayersError: if more than max_players (when given).
        """
        # Scalar columns only — this path never serializes the Room, and the
        # eager-loading variant would pull every past game's live_state JSON.
        db_room = await self._room_controller.get_room_without_relations(room_id)

        # Authoritative active-game check. The caller holds the room advisory
        # lock, which serializes execution, but under READ COMMITTED a second
        # concurrent starter can still read a stale active_game_id from an older
        # MVCC snapshot (a plain SELECT returned None even after the first game
        # had committed). SELECT ... FOR UPDATE takes a row lock and returns the
        # latest committed row version, closing that window. SQLite ignores
        # FOR UPDATE, so fall back to the value already loaded above.
        active_game_id = db_room.active_game_id
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            active_game_id = (
                await self.session.execute(select(Room.active_game_id).where(Room.id == room_id).with_for_update())
            ).scalar_one()

        if active_game_id:
            raise BaseError(
                message=f"Room {room_id} already has an active game",
                frontend_message="A game is already in progress.",
                status_code=400,
            )

        # Get non-spectator players in the room (don't filter by connected —
        # heartbeat may be stale after a game ends and the player stays on the page)
        links = (
            await self.session.exec(
                select(RoomUserLink).where(
                    RoomUserLink.room_id == db_room.id,
                    RoomUserLink.is_spectator == False,  # noqa: E712
                )
            )
        ).all()

        if not links:
            raise RoomNotFoundError(room_id=room_id)

        # Bulk fetch all users in one query (fixes N+1), preserving link order
        user_ids = [link.user_id for link in links]
        users_result = (
            await self.session.exec(
                select(User).where(User.id.in_(user_ids))  # type: ignore[union-attr]
            )
        ).all()

        # Reorder to match original link order (IN clause doesn't guarantee order)
        users_by_id = {u.id: u for u in users_result}
        player_users = [users_by_id[uid] for uid in user_ids if uid in users_by_id]

        if len(player_users) < min_players:
            raise NotEnoughPlayersError(player_count=len(player_users), required=min_players)
        if max_players is not None and len(player_users) > max_players:
            raise TooManyPlayersError(player_count=len(player_users), allowed=max_players)

        return db_room, player_users

    async def _get_game(self, game_id: UUID) -> Game:
        """Fetch a Game from PostgreSQL or raise GameNotFoundError."""
        game = (await self.session.exec(select(Game).where(Game.id == game_id))).first()
        if not game or not game.live_state:
            raise GameNotFoundError(game_id=game_id)
        return game

    async def _check_is_host(self, room_id: UUID, user_id: UUID) -> bool:
        """Check if the user is the host of the room."""
        room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
        if room:
            return room.owner_id == user_id
        return False

    @staticmethod
    def _require_room_host(room: Room, user_id: UUID) -> None:
        """Raise 403 unless the user is the host (owner) of the room."""
        if room.owner_id != user_id:
            raise BaseError(
                message=f"User {user_id} is not the host of room {room.id}",
                frontend_message="Only the host can do this.",
                status_code=403,
            )

    @staticmethod
    def _check_game_in_progress(game: Game) -> None:
        """Raise 400 if the game is not currently in progress.

        Mutations on a finished/cancelled game must be rejected — otherwise a
        late request (e.g. timer-expired arriving after the game ended) can
        re-run the end-of-game flow and double-count stats.
        """
        if game.game_status != GameStatus.IN_PROGRESS:
            raise BaseError(
                message=f"Game {game.id} is not in progress (status={game.game_status})",
                frontend_message="This game is already over.",
                status_code=400,
            )

    async def _update_heartbeat_throttled(self, room_id: UUID, user_id: UUID) -> None:
        """Update heartbeat only if last_seen_at is stale (>HEARTBEAT_THROTTLE_SECONDS)."""
        link = (
            await self.session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == room_id).where(RoomUserLink.user_id == user_id)
            )
        ).first()
        if not link:
            return
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

    async def _check_spectator(self, game: Game, user_id: UUID, player: dict | None) -> bool:
        """Check if user is a spectator. Raises PlayerRemovedFromGameError if not player and not spectator."""
        if player:
            return False
        link = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == game.room_id)
                .where(RoomUserLink.user_id == user_id)
                .where(RoomUserLink.is_spectator == True)  # noqa: E712
            )
        ).first()
        if not link:
            raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game.id))
        return True

    async def _scorable_players(self, state: dict) -> list[dict]:
        """The players from live_state whose User row still exists.

        Delegates to ``game_end_stats.scorable_players`` — the disconnect handlers
        need the same rule and cannot import a controller (that would close the
        ``base_game`` → ``room`` → ``disconnect`` cycle).
        """
        return await scorable_players(self.session, state)

    @staticmethod
    def _resolve_multilingual(data: dict | None, lang: str) -> str | None:
        """Resolve a multilingual dict {en, ar, fr} to a string in the requested language."""
        if not data or not isinstance(data, dict):
            return None
        return data.get(lang) or data.get("en") or next(iter(data.values()), None)
