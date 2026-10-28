from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    HEARTBEAT_THROTTLE_SECONDS,
    HOST_USERNAME_STATE_KEY,
    PAUSE_RECORD_AT,
    PAUSE_RECORD_BY,
    PAUSE_RECORD_BY_USERNAME,
    PAUSE_RECORD_REASON,
    PAUSE_STATE_KEY,
    PRAYER_PAUSE_MAX_SECONDS,
)
from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.game_end_stats import scorable_players
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.stats import StatsController
from majlisna.api.controllers.term_script import TermScriptController
from majlisna.api.models.error import (
    GameNotFoundError,
    NotEnoughPlayersError,
    PlayerRemovedFromGameError,
    RoomNotFoundError,
)
from majlisna.api.models.game import GamePauseReason, GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.common import GameColophon, GamePause, PauseGameResponse, PhaseTimer, ResumeGameResponse
from majlisna.api.schemas.error import (
    GameAlreadyOverError,
    GameAlreadyPausedError,
    GameNotPausedError,
    GamePausedError,
    NotRoomHostError,
    OnlyHostCanPauseError,
    RoomHasActiveGameError,
    SpectatorCannotPauseError,
    TooManyPlayersError,
)
from majlisna.api.utils.game_pause import (
    is_paused,
    parse_instant,
    pause_record,
    paused_since,
    remaining_seconds_at,
    shifted_instant,
    time_anchor_keys,
)
from majlisna.api.utils.game_state import as_utc, require_state
from majlisna.api.utils.multilingual import resolve_multilingual


class BaseGameController:
    """Base class for game controllers with shared utility methods."""

    # The game this controller plays. Pause and resume refuse (404) a game of another
    # type reaching this router. The clocks a resume shifts are chosen from the game's
    # own type (constants.PAUSE_TIME_ANCHOR_KEYS), never from the controller.
    GAME_TYPE: ClassVar[GameType | None] = None

    def __init__(self, session: AsyncSession):
        self.session = session
        self._room_controller = RoomController(session)
        self._game_controller = GameController(session)
        self._stats_controller = StatsController(session)
        self._achievement_controller = AchievementController(session)
        self._term_script_controller = TermScriptController(session)

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
                # `execute`, not `exec`: SQLModel deprecates it, but `exec` unwraps to
                # scalars and there is no overload for a `with_for_update()` row lock.
                await self.session.execute(select(Room.active_game_id).where(Room.id == room_id).with_for_update())  # ty: ignore[deprecated]
            ).scalar_one()

        if active_game_id:
            raise RoomHasActiveGameError(room_id=room_id)

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
                select(User).where(User.id.in_(user_ids))  # ty: ignore[unresolved-attribute]
            )
        ).all()

        # Reorder to match original link order (IN clause doesn't guarantee order)
        users_by_id = {u.id: u for u in users_result}
        # `RoomUserLink.user_id` is `UUID | None`, so ty sees a possible `None` key.
        # The membership test in front of the lookup is what makes it safe, and it is
        # not merely narrowing for the checker: `users_by_id` is keyed by `User.id`,
        # which is never None, so a None `uid` simply fails the `in` and is dropped.
        player_users = [users_by_id[uid] for uid in user_ids if uid in users_by_id]  # ty: ignore[invalid-argument-type]

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

    async def _get_room_owner_id(self, room_id: UUID | None) -> UUID | None:
        """The room's host, or None when there is no room (or it has been orphaned)."""
        room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
        return room.owner_id if room else None

    async def _get_room_host(self, room_id: UUID | None) -> tuple[UUID | None, str | None]:
        """The room's host id and username in ONE query (both None for no room / an orphaned one).

        The state reads used ``_get_room_owner_id`` for the host check; the colophon
        also needs the host's name, and this answers both without a second query.
        """
        row = (
            await self.session.exec(
                select(Room.owner_id, User.username)
                # The join condition is a SQL expression, not a Python bool — ty does
                # not model SQLModel column operators (see backend/CLAUDE.md).
                .outerjoin(User, User.id == Room.owner_id)  # ty: ignore[invalid-argument-type]
                .where(Room.id == room_id)
            )
        ).first()
        if row is None:
            return None, None
        owner_id, username = row
        return owner_id, username if owner_id is not None else None

    async def _host_username_at_start(self, room: Room, player_users: list[User]) -> str | None:
        """The starting host's username, for ``live_state[HOST_USERNAME_STATE_KEY]``.

        The host is almost always one of the players fetched for the start; only a
        host who is spectating costs a lookup.
        """
        if room.owner_id is None:
            return None
        host = next((u for u in player_users if u.id == room.owner_id), None)
        if host is None:
            host = (await self.session.exec(select(User).where(User.id == room.owner_id))).first()
        return host.username if host else None

    @staticmethod
    def _build_colophon(game: Game, state: dict, current_host_username: str | None) -> GameColophon:
        """Who hosted and when the game ran — see ``GameColophon``."""
        return GameColophon(
            host_username=state.get(HOST_USERNAME_STATE_KEY) or current_host_username,
            started_at=as_utc(game.start_time),
            ended_at=as_utc(game.end_time),
        )

    async def _check_is_host(self, room_id: UUID | None, user_id: UUID) -> bool:
        """Check if the user is the host of the room.

        Accepts None because callers pass `game.room_id`, and answering False for
        "no room" is the same answer the missing-room branch already gives."""
        return await self._get_room_owner_id(room_id) == user_id

    @staticmethod
    def _ready_quorum(state: dict, host_id: UUID | None) -> int:
        """How many "ready" marks a quiz round needs before it advances.

        The host advances a round by pressing next and is never added to
        ``ready_players``. Comparing against the full player count therefore made
        "everyone is ready" unreachable in the normal case — the host is a player
        — so the documented behaviour ("advance when all players are ready OR the
        host overrides") collapsed to "only the host can ever advance", and an
        absent host stalled the game with no timeout to rescue it (the results
        phase has none). Readiness is asked of everyone *but* the host.
        """
        host = str(host_id) if host_id else None
        return sum(1 for p in state["players"] if p["user_id"] != host)

    @staticmethod
    def _require_room_host(room: Room, user_id: UUID) -> None:
        """Raise 403 unless the user is the host (owner) of the room."""
        if room.owner_id != user_id:
            raise NotRoomHostError(message=f"User {user_id} is not the host of room {room.id}")

    @staticmethod
    def _check_game_in_progress(game: Game) -> None:
        """Raise 400 if the game is not currently in progress.

        Mutations on a finished/cancelled game must be rejected — otherwise a
        late request (e.g. timer-expired arriving after the game ended) can
        re-run the end-of-game flow and double-count stats.
        """
        if game.game_status != GameStatus.IN_PROGRESS:
            raise GameAlreadyOverError(f"Game {game.id} is not in progress (status={game.game_status})")

    async def _update_heartbeat_throttled(self, room_id: UUID | None, user_id: UUID) -> None:
        """Update heartbeat only if last_seen_at is stale (>HEARTBEAT_THROTTLE_SECONDS).

        Accepts None for the same reason as _check_is_host: no room means no link to
        refresh, which is already this method's no-op path."""
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
        return resolve_multilingual(data, lang)

    # ── The prayer pause (وقفة الصلاة) ──────────────────────────────────────

    async def pause_game(self, game_id: UUID, user_id: UUID) -> PauseGameResponse:
        """Stop a running game for the prayer. Host only, never a spectator.

        Stops every clock: from here until ``resume_game`` no move is accepted
        (``_ensure_not_paused``) and ``timer-expired`` answers without acting.
        """
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_own_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)
            if await self._get_room_owner_id(game.room_id) != user_id:
                raise OnlyHostCanPauseError(user_id=user_id, game_id=game_id)

            player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
            if await self._check_spectator(game, user_id, player):
                # A spectator host only exists when host transfer found no connected
                # player; watching the game does not give a say in stopping it.
                raise SpectatorCannotPauseError(user_id=user_id, game_id=game_id)
            if player is None:
                # Unreachable: _check_spectator raises unless the caller is a player
                # or a spectator, and the spectator branch has just been taken.
                raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game_id))
            if is_paused(state):
                raise GameAlreadyPausedError(game_id=game_id)

            record = {
                PAUSE_RECORD_BY: str(user_id),
                PAUSE_RECORD_BY_USERNAME: player["username"],
                PAUSE_RECORD_AT: datetime.now(UTC).isoformat(),
                PAUSE_RECORD_REASON: GamePauseReason.SALAH.value,
            }
            state[PAUSE_STATE_KEY] = record
            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return PauseGameResponse(game_id=str(game_id), paused=self._pause_view(state, record))

    async def resume_game(self, game_id: UUID, user_id: UUID) -> ResumeGameResponse:
        """Restart a paused game exactly where it stopped.

        Who may (``_may_resume``): the room's CURRENT owner, not whoever paused — if the
        host left during the prayer, ownership has transferred and the new host
        resumes, a spectator host included (otherwise nobody could). Any player of the
        game may too once the pause has outlasted ``PRAYER_PAUSE_MAX_SECONDS``, or at
        once when the room has no owner left (the host deleted their account), so a
        pause can never hold a table for good.

        Every clock moves forward by the paused duration (``PAUSE_TIME_ANCHOR_KEYS`` of
        the game's own type), and so does the disconnect grace of anyone still away,
        so the pause consumes neither a turn's time nor a player's grace.
        """
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_own_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)
            since = paused_since(state)
            if since is None:
                raise GameNotPausedError(game_id=game_id)
            owner_id = await self._get_room_owner_id(game.room_id)
            if not self._may_resume(state, user_id, owner_id, since):
                raise OnlyHostCanPauseError(user_id=user_id, game_id=game_id)

            resumed_at = datetime.now(UTC)
            paused_for = max(resumed_at - since, timedelta(0))
            self._shift_time_anchors(game, state, paused_for, resumed_at)
            await self._shift_disconnect_grace(game.room_id, paused_for)
            state.pop(PAUSE_STATE_KEY, None)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return ResumeGameResponse(game_id=str(game_id), paused_seconds=paused_for.total_seconds())

    async def _get_own_game(self, game_id: UUID) -> Game:
        """``_get_game``, restricted to this controller's game type (404 otherwise).

        A pause or resume reaching the wrong game's router is a request for a game
        that router does not have — the same answer as an unknown id.
        """
        game = await self._get_game(game_id)
        if self.GAME_TYPE is not None and game.type != self.GAME_TYPE:
            raise GameNotFoundError(game_id=game_id)
        return game

    @staticmethod
    def _ensure_not_paused(game: Game, state: dict) -> None:
        """Raise ``GamePausedError`` (409) while the host has paused the game.

        Called by every move. Reads (state, board) and the hint-viewed record stay
        open: they change nothing a player is competing on. A game that is no longer
        running is not paused (see ``_build_pause``) — its own "game over" error
        answers instead.
        """
        if game.game_status == GameStatus.IN_PROGRESS and is_paused(state):
            raise GamePausedError(game_id=game.id)

    def _build_pause(self, game: Game, state: dict) -> GamePause | None:
        """The pause to show in a game state, or None.

        Only a running game is paused: one that ended while paused (a drop-out
        decided it, or the host's rematch cancelled it) keeps the record in its
        ``live_state`` but must not read as paused to anyone.
        """
        record = pause_record(state)
        if record is None or game.game_status != GameStatus.IN_PROGRESS:
            return None
        return self._pause_view(state, record)

    def _pause_view(self, state: dict, record: dict) -> GamePause:
        """The pause as the client shows it, every derived value computed here.

        The frozen countdown used to be left to the client (``since - anchor``), which
        is wrong whenever a timer restarted during the pause — the anchor is then
        later than ``since`` and the countdown read more than its whole duration.
        """
        since = parse_instant(record[PAUSE_RECORD_AT])
        timer = self._phase_timer(state)
        return GamePause(
            by_user_id=record[PAUSE_RECORD_BY],
            by_username=record[PAUSE_RECORD_BY_USERNAME],
            since=since,
            reason=GamePauseReason(record[PAUSE_RECORD_REASON]),
            remaining_seconds=(
                remaining_seconds_at(timer.started_at, timer.duration_seconds, since) if timer else None
            ),
            paused_for_seconds=max((datetime.now(UTC) - since).total_seconds(), 0.0),
            anyone_can_resume_at=since + timedelta(seconds=PRAYER_PAUSE_MAX_SECONDS),
        )

    def _phase_timer(self, state: dict) -> PhaseTimer | None:  # noqa: ARG002 — overridden per game
        """The timer of the phase the game is in, or None when that phase is untimed.

        Each game overrides this with the same duration its ``_is_timer_actually_expired``
        applies; the base has no timer.
        """
        return None

    @staticmethod
    def _can_pause(game: Game, state: dict, user_id: UUID, owner_id: UUID | None, *, is_spectator: bool) -> bool:
        """Whether ``pause_game`` would accept this caller now — the state's ``can_pause``."""
        return (
            game.game_status == GameStatus.IN_PROGRESS
            and not is_paused(state)
            and owner_id == user_id
            and not is_spectator
        )

    @classmethod
    def _can_resume(cls, game: Game, state: dict, user_id: UUID, owner_id: UUID | None) -> bool:
        """Whether ``resume_game`` would accept this caller now — the state's ``can_resume``."""
        since = paused_since(state)
        return (
            game.game_status == GameStatus.IN_PROGRESS
            and since is not None
            and cls._may_resume(state, user_id, owner_id, since)
        )

    @staticmethod
    def _may_resume(state: dict, user_id: UUID, owner_id: UUID | None, since: datetime) -> bool:
        """Who may end a pause — ONE rule, used by ``resume_game`` and ``can_resume``.

        The room's current owner always may. Any other player of the game may once
        the pause has lasted ``PRAYER_PAUSE_MAX_SECONDS`` — a host whose tab stays
        open never trips the paused disconnect grace, so nothing else would ever
        hand the game back — or at once when the room has no owner at all (the host
        deleted their account: ``Room.owner_id`` is nulled, and the game would
        otherwise stay IN_PROGRESS for ever).
        """
        if owner_id == user_id:
            return True
        if not any(p["user_id"] == str(user_id) for p in state["players"]):
            return False
        if owner_id is None:
            return True
        return datetime.now(UTC) - since >= timedelta(seconds=PRAYER_PAUSE_MAX_SECONDS)

    @staticmethod
    def _shift_time_anchors(game: Game, state: dict, paused_for: timedelta, resumed_at: datetime) -> None:
        """Move every clock of the game forward by the paused duration.

        The anchors come from the game's own type, not from the controller.
        """
        for key in time_anchor_keys(game.type.value):
            anchor = state.get(key)
            if anchor:
                state[key] = shifted_instant(parse_instant(anchor), paused_for, resumed_at).isoformat()

    async def _shift_disconnect_grace(self, room_id: UUID | None, paused_for: timedelta) -> None:
        """Give anyone still disconnected the grace they had left when the game paused.

        During the pause the checker keeps them for ``PAUSED_GAME_GRACE_PERIOD_SECONDS``
        (see ``disconnect._remove_expired_users``). Without this shift the ordinary
        in-game grace would apply to ``disconnected_at`` as soon as the game resumes,
        and a player whose phone locked during the prayer would be dropped from the
        game seconds after it restarted — before they had unlocked it. Staged only:
        the caller commits once, inside the game lock.

        ``RoomUserLink`` timestamps are naive local time on purpose (see CLAUDE.md),
        so the resume instant here is the naive ``datetime.now()``.
        """
        links = (
            await self.session.exec(
                select(RoomUserLink)
                .where(RoomUserLink.room_id == room_id)
                .where(RoomUserLink.connected == False)  # noqa: E712
                .where(RoomUserLink.disconnected_at != None)  # noqa: E711
            )
        ).all()
        resumed_at = datetime.now()
        for link in links:
            if link.disconnected_at is None:
                continue
            link.disconnected_at = shifted_instant(link.disconnected_at, paused_for, resumed_at)
            self.session.add(link)
