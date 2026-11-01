from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    CODENAMES_BOARD_SIZE,
    CODENAMES_CLUE_TURN_KEY,
    CODENAMES_REVEAL_LOG_KEY,
    DEFAULT_CODENAMES_CLUE_TIMER_SECONDS,
    DEFAULT_CODENAMES_GUESS_TIMER_SECONDS,
    HINT_USAGE_MAX_WORDS_PER_USER,
    HOST_USERNAME_STATE_KEY,
    MAX_PLAYERS_CODENAMES,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
)
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.codenames import CodenamesController
from majlisna.api.controllers.codenames_helpers import (
    CodenamesCardType,
    CodenamesGameStatus,
    CodenamesRole,
    CodenamesTeam,
    advance_clue_turn,
    apply_card_reveal,
    assign_players,
    build_board,
    clue_names_a_card,
    counted_operative_votes,
    current_operative_ids,
    get_board_for_player,
    get_player_from_game,
    hint_is_visible,
    new_turn,
    switch_turn,
    tally_operative_votes,
    top_voted_cards,
)
from majlisna.api.controllers.game_cancel import detach_room_if_current
from majlisna.api.controllers.game_end_stats import codenames_winners, record_game_end
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.models.error import (
    CardAlreadyRevealedError,
    ClueWordIsOnBoardError,
    GameNotInProgressError,
    InvalidCardIndexError,
    NoClueGivenError,
    NotOperativeError,
    NotSpymasterError,
    NotYourTurnError,
    PlayerRemovedFromGameError,
)
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.codenames import (
    CodenamesBoardState,
    CodenamesClueGuess,
    CodenamesClueHistoryEntry,
    CodenamesPlayerView,
    EndTurnResponse,
    GiveClueResponse,
    GuessCardResponse,
)
from majlisna.api.schemas.common import (
    GameStartResponse,
    HintRecordResponse,
    PhaseTimer,
    TimerExpiredAction,
    TimerExpiredResponse,
)
from majlisna.api.schemas.error import (
    BaseError,
    ClueAlreadyGivenError,
    ClueMustBeOneWordError,
)
from majlisna.api.schemas.term_script import TermScriptForms
from majlisna.api.utils.game_pause import is_paused, parse_instant
from majlisna.api.utils.game_state import require_state
from majlisna.api.utils.rng import rng


class CodenamesGameController(BaseGameController):
    """REST controller for Codenames game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses asyncio.Lock per game_id for concurrency control.
    """

    GAME_TYPE = GameType.CODENAMES

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._codenames_controller = CodenamesController(session)

    async def create_and_start(
        self,
        room_id: UUID,
        user_id: UUID,
        word_pack_ids: list[UUID] | None = None,
    ) -> GameStartResponse:
        """Start a new Codenames game in the given room. Host only."""
        async with get_game_lock(f"room:{room_id}", self.session):
            db_room, player_users = await self._prepare_game_start(
                room_id, min_players=4, max_players=MAX_PLAYERS_CODENAMES
            )
            self._require_room_host(db_room, user_id)

            room_user_dicts = [{"user_id": str(u.id), "username": u.username} for u in player_users]

            random_words = await self._codenames_controller.get_random_words(
                count=CODENAMES_BOARD_SIZE,
                pack_ids=word_pack_ids,
            )
            word_strings = [w.word for w in random_words]
            word_hints = {w.word: w.hint for w in random_words if w.hint}

            first_team = rng.choice([CodenamesTeam.RED, CodenamesTeam.BLUE])
            board = build_board(word_strings, first_team)
            players = assign_players(room_user_dicts, first_team)

            red_remaining = sum(1 for card in board if card["card_type"] == CodenamesCardType.RED.value)
            blue_remaining = sum(1 for card in board if card["card_type"] == CodenamesCardType.BLUE.value)

            db_game = await self._game_controller.create_game(
                GameCreate(
                    room_id=db_room.id,
                    number_of_players=len(room_user_dicts),
                    type=GameType.CODENAMES,
                    game_configurations={
                        "first_team": first_team.value,
                        "word_pack_ids": [str(pid) for pid in word_pack_ids] if word_pack_ids else [],
                        "board_words": word_strings,
                    },
                ),
                # One transaction: hold the room lock until active_game_id commits.
                commit=False,
            )

            live_state: dict = {
                "board": board,
                "players": players,
                "current_team": first_team.value,
                "current_turn": new_turn(first_team.value),
                "red_remaining": red_remaining,
                "blue_remaining": blue_remaining,
                "status": CodenamesGameStatus.IN_PROGRESS.value,
                "winner": None,
                "word_hints": word_hints,
                "hint_usage": {},
                "clue_history": [],
                # Every card turned, and the clue it was turned under (WP-09).
                CODENAMES_REVEAL_LOG_KEY: [],
                CODENAMES_CLUE_TURN_KEY: 0,
                "timer_config": {
                    "clue_seconds": (getattr(db_room, "settings", None) or {}).get(
                        "codenames_clue_timer", DEFAULT_CODENAMES_CLUE_TIMER_SECONDS
                    ),
                    "guess_seconds": (getattr(db_room, "settings", None) or {}).get(
                        "codenames_guess_timer", DEFAULT_CODENAMES_GUESS_TIMER_SECONDS
                    ),
                },
                "timer_started_at": datetime.now(UTC).isoformat(),
                HOST_USERNAME_STATE_KEY: await self._host_username_at_start(db_room, player_users),
            }

            db_game.live_state = live_state
            db_game.game_status = GameStatus.IN_PROGRESS
            flag_modified(db_game, "live_state")
            self.session.add(db_game)

            # Set active game on room
            db_room.active_game_id = db_game.id
            self.session.add(db_room)
            await self.session.commit()

            return GameStartResponse(
                game_id=str(db_game.id),
                room_id=str(db_room.id),
            )

    async def give_clue(self, game_id: UUID, user_id: UUID, clue_word: str, clue_number: int) -> GiveClueResponse:
        """Process a spymaster giving a clue."""
        logger.info("Codenames clue: game={} user={} word={} number={}", game_id, user_id, clue_word, clue_number)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = require_state(game)

            self._ensure_in_progress(game, state)
            self._ensure_not_paused(game, state)

            player = get_player_from_game(state["players"], str(user_id))

            if player["team"] != state["current_team"]:
                raise NotYourTurnError(user_id=str(user_id))
            if player["role"] != CodenamesRole.SPYMASTER.value:
                raise NotSpymasterError(user_id=str(user_id))

            if state["current_turn"].get("clue_word") is not None:
                raise ClueAlreadyGivenError()

            clue = await self._validated_clue(state, clue_word)

            state["current_turn"] = {
                "team": state["current_team"],
                "clue_word": clue,
                "clue_number": clue_number,
                "guesses_made": 0,
                "max_guesses": CODENAMES_BOARD_SIZE if clue_number == 0 else clue_number + 1,
                "card_votes": {},
            }

            state["timer_started_at"] = datetime.now(UTC).isoformat()

            # Count the clue, then append it to the clue history: a reveal's clue_turn
            # is this clue's 1-based position there.
            advance_clue_turn(state)
            state.setdefault("clue_history", []).append(
                {
                    "team": state["current_team"],
                    "clue_word": clue,
                    "clue_number": clue_number,
                    "guesses": [],
                }
            )

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return GiveClueResponse(
            game_id=str(game_id),
            clue_word=clue,
            clue_number=clue_number,
        )

    async def _validated_clue(self, state: dict, clue_word: str) -> str:
        """The clue as the table will read it: stripped, one word, and no card's word (BR-14).

        A board word with a trailing space passed the on-board check, and a blank clue
        or a whole sentence ("the Sunnah", with the Sunnah card on the board) was given
        as it came. Blank or holding whitespace → ``ClueMustBeOneWordError``; a card's
        word in any case, accent or script — every card also prints its Arabic form —
        → ``ClueWordIsOnBoardError``.
        """
        clue = clue_word.strip()
        if len(clue.split()) != 1:
            raise ClueMustBeOneWordError()
        board_words = [card["word"] for card in state["board"]]
        board_scripts = await self._term_script_controller.get_forms(board_words)
        if clue_names_a_card(clue, board_words, (script.ar for script in board_scripts.values())):
            raise ClueWordIsOnBoardError(clue_word=clue)
        return clue

    async def guess_card(self, game_id: UUID, user_id: UUID, card_index: int) -> GuessCardResponse:
        """Process an operative voting for a card (or instant reveal if solo operative)."""
        logger.info("Codenames guess: game={} user={} card={}", game_id, user_id, card_index)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = require_state(game)

            self._ensure_in_progress(game, state)
            self._ensure_not_paused(game, state)
            self._validate_guess(state, str(user_id), card_index)

            # The quorum is the operatives on the team NOW, and only their votes count
            # (BR-09): a departed operative's ballot neither completes it nor picks a card.
            total_operatives = len(current_operative_ids(state))

            # Single operative: instant reveal (skip voting)
            if total_operatives <= 1:
                return await self._reveal_card(game, state, card_index, [str(user_id)])

            # Multi-operative: record vote
            card_votes = state["current_turn"].setdefault("card_votes", {})
            previous_vote = card_votes.get(str(user_id))
            card_votes[str(user_id)] = card_index
            vote_changed = previous_vote is not None and previous_vote != card_index

            # Keep only the ballots that count: a stale one would still show on the card.
            votes = counted_operative_votes(state)
            state["current_turn"]["card_votes"] = votes
            winning_index = tally_operative_votes(state)

            # Not all voted yet — save and return progress
            if winning_index is None:
                game.live_state = state
                flag_modified(game, "live_state")
                self.session.add(game)
                await self.session.commit()

                return GuessCardResponse(
                    game_id=str(game_id),
                    all_voted=False,
                    vote_changed=vote_changed,
                    card_votes_count=len(votes),
                    total_operatives=total_operatives,
                )

            # Every operative voted — the card is the most voted (a tie was drawn at random)
            was_tied = len(top_voted_cards(votes)) > 1
            voter_ids = [voter for voter, card in votes.items() if card == winning_index]

            result = await self._reveal_card(game, state, winning_index, voter_ids)
            result.all_voted = True
            result.tied = was_tied
            result.card_votes_count = total_operatives
            result.total_operatives = total_operatives
            return result

    async def _reveal_card(self, game: Game, state: dict, card_index: int, voter_ids: list[str]) -> GuessCardResponse:
        """Turn a card (``apply_card_reveal``: the state, the clue history and the reveal
        log), end the game if that decided it, and commit — once, under the caller's lock."""
        outcome = apply_card_reveal(state, card_index, voter_ids)

        if state["status"] == CodenamesGameStatus.FINISHED.value:
            await self._finish_game(game, state)

        game.live_state = state
        flag_modified(game, "live_state")
        self.session.add(game)
        await self.session.commit()

        return GuessCardResponse(
            game_id=str(game.id),
            card_index=card_index,
            card_type=state["board"][card_index]["card_type"],
            result=outcome.value,
        )

    async def _finish_game(self, game: Game, state: dict) -> None:
        """End the Game row of a game ``live_state`` says is over, and stage its stats. No commit.

        The room is let go of only if it still points at THIS game
        (``detach_room_if_current``, BR-06): finishing an old game used to unlink the
        room's new running one.
        """
        game.game_status = GameStatus.FINISHED
        game.end_time = datetime.now(UTC)
        room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
        if room:
            detach_room_if_current(room, game)
            self.session.add(room)
        newly_unlocked = await self._process_game_end_stats(state, state.get("winner", ""))
        if newly_unlocked:
            state["newly_unlocked_achievements"] = newly_unlocked

    async def end_turn(self, game_id: UUID, user_id: UUID) -> EndTurnResponse:
        """Allow an operative to voluntarily end their turn."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = require_state(game)

            self._ensure_in_progress(game, state)
            self._ensure_not_paused(game, state)

            player = get_player_from_game(state["players"], str(user_id))

            if player["team"] != state["current_team"]:
                raise NotYourTurnError(user_id=str(user_id))
            if player["role"] != CodenamesRole.OPERATIVE.value:
                raise NotOperativeError(user_id=str(user_id))
            # BR-15: before the clue there is nothing to end — one operative (or a crafted
            # request) passed the team's whole turn. The UI hides the button until then.
            if not state["current_turn"].get("clue_word"):
                raise NoClueGivenError()

            switch_turn(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return EndTurnResponse(
            game_id=str(game_id),
            current_team=state["current_team"],
        )

    async def get_board(
        self, game_id: UUID, user_id: UUID, sid: str | None = None, lang: str = "en", update_heartbeat: bool = True
    ) -> CodenamesBoardState:
        """Get the current board state for a player or spectator. Used for polling."""
        game = await self._get_game(game_id)
        state = require_state(game)

        # Try to find the user as a player first
        is_spectator = False
        try:
            player = get_player_from_game(state["players"], str(user_id))
        except BaseError:
            # Check if user is a spectator
            link = (
                await self.session.exec(
                    select(RoomUserLink)
                    .where(RoomUserLink.room_id == game.room_id)
                    .where(RoomUserLink.user_id == user_id)
                    .where(RoomUserLink.is_spectator == True)  # noqa: E712
                )
            ).first()
            if not link:
                raise
            is_spectator = True
            player = None

        word_hints = state.get("word_hints", {})
        is_spymaster = player["role"] == CodenamesRole.SPYMASTER.value if player else False
        is_finished = state["status"] == CodenamesGameStatus.FINISHED.value
        # ONE lookup for the whole board. Every card's Latin word is visible to
        # every viewer, so its Arabic form is too; the clue history only names
        # board words, so the same map covers it.
        scripts = await self._term_script_controller.get_forms(card["word"] for card in state["board"])

        # End-game board reveal or spectator view: show all card types when game is finished
        if is_finished:
            board_view = [
                {
                    "index": i,
                    "word": card["word"],
                    "word_ar": self._script_ar(scripts, card["word"]),
                    "word_ar_vocalized": self._script_ar_vocalized(scripts, card["word"]),
                    "revealed": True,
                    "card_type": card["card_type"],
                    "hint": self._resolve_multilingual(word_hints.get(card["word"]), lang),
                }
                for i, card in enumerate(state["board"])
            ]
        elif is_spectator:
            # Spectators see operative view (revealed cards only, no card types for unrevealed)
            board_view = [
                {
                    "index": i,
                    "word": card["word"],
                    "word_ar": self._script_ar(scripts, card["word"]),
                    "word_ar_vocalized": self._script_ar_vocalized(scripts, card["word"]),
                    "revealed": card.get("revealed", False),
                    "card_type": card["card_type"] if card.get("revealed", False) else None,
                    "hint": self._resolve_multilingual(word_hints.get(card["word"]), lang)
                    if card.get("revealed", False)
                    else None,
                }
                for i, card in enumerate(state["board"])
            ]
        else:
            if player is None:
                # Unreachable: _check_spectator raises unless the caller is a player
                # or a spectator, and both other branches are taken first. Stated
                # rather than assumed, so the invariant is checked.
                raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game_id))
            board_view = get_board_for_player(state["board"], player)
            # Add hints: revealed cards and spymaster see hints, unrevealed cards for operatives get null
            for card_view in board_view:
                word = card_view["word"]
                card_view["word_ar"] = self._script_ar(scripts, word)
                card_view["word_ar_vocalized"] = self._script_ar_vocalized(scripts, word)
                if card_view.get("revealed") or is_spymaster:
                    card_view["hint"] = self._resolve_multilingual(word_hints.get(word), lang)
                else:
                    card_view["hint"] = None

        # Check host status (and the host's name, for the colophon — same query)
        owner_id, host_username = await self._get_room_host(game.room_id)
        is_host = owner_id is not None and owner_id == user_id
        colophon = self._build_colophon(game, state, host_username)

        # Update heartbeat (throttled: skip if last_seen_at is recent to reduce write contention)
        if update_heartbeat:
            await self._update_heartbeat_throttled(game.room_id, user_id)

        return CodenamesBoardState(
            game_id=str(game.id),
            room_id=str(game.room_id),
            team=player["team"] if player else "spectator",
            role=player["role"] if player else "spectator",
            is_host=is_host,
            is_spectator=is_spectator,
            board=board_view,
            current_team=state["current_team"],
            red_remaining=state["red_remaining"],
            blue_remaining=state["blue_remaining"],
            status=state["status"],
            current_turn=state["current_turn"],
            winner=state["winner"],
            clue_history=self._build_clue_history(state, scripts),
            timer_config=state.get("timer_config"),
            timer_started_at=state.get("timer_started_at"),
            newly_unlocked_achievements=state.get("newly_unlocked_achievements"),
            paused=self._build_pause(game, state),
            can_pause=self._can_pause(game, state, user_id, owner_id, is_spectator=is_spectator),
            can_resume=self._can_resume(game, state, user_id, owner_id),
            players=[
                CodenamesPlayerView(
                    user_id=p["user_id"],
                    username=p["username"],
                    team=p["team"],
                    role=p["role"],
                )
                for p in state["players"]
            ],
            host_username=colophon.host_username,
            started_at=colophon.started_at,
            ended_at=colophon.ended_at,
        )

    def _phase_timer(self, state: dict) -> PhaseTimer | None:
        """The current turn's timer: the guess timer once a clue is given, else the clue timer.

        Same durations as ``handle_timer_expired``.
        """
        started_at = state.get("timer_started_at")
        if not started_at or state.get("status") != CodenamesGameStatus.IN_PROGRESS.value:
            return None
        timer_config = state.get("timer_config") or {}
        current_turn = state.get("current_turn") or {}
        if current_turn.get("clue_word"):
            seconds = timer_config.get("guess_seconds", DEFAULT_CODENAMES_GUESS_TIMER_SECONDS)
        else:
            seconds = timer_config.get("clue_seconds", DEFAULT_CODENAMES_CLUE_TIMER_SECONDS)
        if not seconds:
            return None  # 0 means no time limit
        return PhaseTimer(started_at=parse_instant(started_at), duration_seconds=seconds)

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> TimerExpiredResponse:
        """Handle timer expiration — auto end-turn. Validates timer actually expired."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = require_state(game)
            # Only someone in the game fires its timers (SEC F08): a player or a spectator.
            await self._require_participant(game, state, user_id)
            self._ensure_in_progress(game, state)

            # No clock runs while the host has paused the game for the prayer. Not an
            # error: clients fire this from their own local timers.
            if is_paused(state):
                return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.PAUSED)

            # Server-side validation: check the timer has actually expired
            timer_config = state.get("timer_config", {})
            timer_started_at = state.get("timer_started_at")
            if timer_started_at:
                # Use the appropriate timer based on whether a clue has been given
                current_turn = state.get("current_turn", {})
                if current_turn and current_turn.get("clue_word"):
                    allowed = timer_config.get("guess_seconds", DEFAULT_CODENAMES_GUESS_TIMER_SECONDS)
                else:
                    allowed = timer_config.get("clue_seconds", DEFAULT_CODENAMES_CLUE_TIMER_SECONDS)
                if allowed == 0:
                    return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.TIMER_NOT_EXPIRED)
                started = datetime.fromisoformat(timer_started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                now = datetime.now(UTC)
                elapsed = (now - started).total_seconds()
                if elapsed < allowed - TIMER_EXPIRATION_TOLERANCE_SECONDS:
                    return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.TIMER_NOT_EXPIRED)

            switch_turn(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.AUTO_END_TURN)

    @staticmethod
    def _script_ar(scripts: dict[str, TermScriptForms], word: str) -> str | None:
        """The Arabic form of a board word, or None when it has no TermScript row."""
        script = scripts.get(word)
        return script.ar if script else None

    @staticmethod
    def _script_ar_vocalized(scripts: dict[str, TermScriptForms], word: str) -> str | None:
        """The vocalised Arabic form of a board word, or None when absent or not certain.

        The bare form alone is ambiguous on a card: أحد is Uhud or "one", ثور is
        Thawr or "a bull". The harakat disambiguate, from the same batched lookup.
        """
        script = scripts.get(word)
        return script.ar_vocalized if script else None

    def _build_clue_history(self, state: dict, scripts: dict[str, TermScriptForms]) -> list[CodenamesClueHistoryEntry]:
        """The clue history with each guessed word's Arabic form attached."""
        return [
            CodenamesClueHistoryEntry(
                team=entry["team"],
                clue_word=entry["clue_word"],
                clue_number=entry["clue_number"],
                guesses=[
                    CodenamesClueGuess(
                        word=guess["word"],
                        word_ar=self._script_ar(scripts, guess["word"]),
                        word_ar_vocalized=self._script_ar_vocalized(scripts, guess["word"]),
                        card_type=guess["card_type"],
                        correct=guess["correct"],
                    )
                    for guess in entry.get("guesses", [])
                ],
            )
            for entry in state.get("clue_history", [])
        ]

    @staticmethod
    def _ensure_in_progress(game: Game, state: dict) -> None:
        """Every move first: the Game ROW and ``live_state`` must both say IN_PROGRESS (BR-06).

        Checking ``live_state["status"]`` alone kept a CANCELLED game (a rematch, a closed
        room) playable from a stale tab, and finishing it rewrote it as FINISHED, credited
        wins and losses, and unlinked the room's new game. Answers
        ``GameNotInProgressError``, the error a Codenames move has always given for a game
        that is over.
        """
        if game.game_status != GameStatus.IN_PROGRESS or state.get("status") != CodenamesGameStatus.IN_PROGRESS.value:
            raise GameNotInProgressError(game_id=str(game.id))

    def _validate_guess(self, state: dict, user_id: str, card_index: int) -> None:
        """Validate that the guess is legal (``_ensure_in_progress`` has run)."""
        player = get_player_from_game(state["players"], user_id)
        if player["team"] != state["current_team"]:
            raise NotYourTurnError(user_id=user_id)
        if player["role"] != CodenamesRole.OPERATIVE.value:
            raise NotOperativeError(user_id=user_id)
        if state["current_turn"] is None or state["current_turn"].get("clue_word") is None:
            raise NoClueGivenError()
        if card_index < 0 or card_index >= CODENAMES_BOARD_SIZE:
            raise InvalidCardIndexError(card_index=card_index)
        if state["board"][card_index]["revealed"]:
            raise CardAlreadyRevealedError(card_index=card_index)

    async def record_hint_view(self, game_id: UUID, user_id: UUID, word: str) -> HintRecordResponse:
        """Record that a player opened a card's meaning (once per word per game).

        Only someone in the game (``_require_participant``: else 403), and only a board
        word whose meaning the caller can open — every card for the spymaster, a turned
        card for an operative (``hint_is_visible``). Anything else answers
        ``recorded=False`` and changes nothing: a spectator has no hint usage, and a
        made-up word is not a hint. The list is capped at ``HINT_USAGE_MAX_WORDS_PER_USER``.

        It took any word from any signed-in caller: anyone with a game id grew its
        ``live_state`` without bound, and a player farmed the hint achievements with
        made-up words (BR-13, SEC F07).
        """
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = require_state(game)
            player = await self._require_participant(game, state, user_id)
            # Hint views feed achievements ("won without hints"), so they must not
            # be accepted after the game has ended — the end-of-game stats have
            # already been computed from hint_usage.
            self._check_game_in_progress(game)

            card = next((card for card in state["board"] if card["word"] == word), None)
            if player is None or card is None or not hint_is_visible(card, player):
                return HintRecordResponse(game_id=str(game_id), recorded=False)

            user_hints = state.setdefault("hint_usage", {}).setdefault(str(user_id), [])
            if word in user_hints:
                return HintRecordResponse(game_id=str(game_id), recorded=True)
            if len(user_hints) >= HINT_USAGE_MAX_WORDS_PER_USER:
                return HintRecordResponse(game_id=str(game_id), recorded=False)
            user_hints.append(word)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return HintRecordResponse(game_id=str(game_id), recorded=True)

    async def _process_game_end_stats(self, state: dict, winner: str) -> list[dict]:
        """Stage the end-of-game stat and achievement writes. See game_end_stats."""
        return await record_game_end(
            self.session,
            state,
            game_type="codenames",
            winners=codenames_winners(state, winner),
            default_role="operative",
        )
