import random
import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import (
    CODENAMES_BOARD_SIZE,
    DEFAULT_CODENAMES_CLUE_TIMER_SECONDS,
    DEFAULT_CODENAMES_GUESS_TIMER_SECONDS,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
)
from ipg.api.controllers.base_game import BaseGameController
from ipg.api.controllers.codenames import CodenamesController
from ipg.api.controllers.codenames_helpers import (
    CodenamesCardType,
    CodenamesGameStatus,
    CodenamesRole,
    CodenamesTeam,
    assign_players,
    build_board,
    get_board_for_player,
    get_player_from_game,
)
from ipg.api.controllers.game_lock import get_game_lock
from ipg.api.models.error import (
    CardAlreadyRevealedError,
    ClueWordIsOnBoardError,
    GameNotInProgressError,
    InvalidCardIndexError,
    NoClueGivenError,
    NotOperativeError,
    NotSpymasterError,
    NotYourTurnError,
)
from ipg.api.models.game import GameCreate, GameStatus, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room
from ipg.api.schemas.codenames import (
    CodenamesBoardState,
    CodenamesPlayerView,
    EndTurnResponse,
    GiveClueResponse,
    GuessCardResponse,
)
from ipg.api.schemas.common import GameStartResponse, HintRecordResponse, TimerExpiredResponse
from ipg.api.schemas.error import BaseError


class CodenamesGameController(BaseGameController):
    """REST controller for Codenames game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses asyncio.Lock per game_id for concurrency control.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._codenames_controller = CodenamesController(session)

    async def create_and_start(
        self,
        room_id: UUID,
        user_id: UUID,
        word_pack_ids: list[UUID] | None = None,
    ) -> GameStartResponse:
        """Start a new Codenames game in the given room."""
        async with get_game_lock(f"room:{room_id}", self.session):
            db_room, player_users = await self._prepare_game_start(room_id, min_players=4)

            room_user_dicts = [{"user_id": str(u.id), "username": u.username} for u in player_users]

            random_words = await self._codenames_controller.get_random_words(
                count=CODENAMES_BOARD_SIZE,
                pack_ids=word_pack_ids,
            )
            word_strings = [w.word for w in random_words]
            word_hints = {w.word: w.hint for w in random_words if w.hint}

            first_team = random.choice([CodenamesTeam.RED, CodenamesTeam.BLUE])
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
                )
            )

            live_state = {
                "board": board,
                "players": players,
                "current_team": first_team.value,
                "current_turn": {
                    "team": first_team.value,
                    "clue_word": None,
                    "clue_number": 0,
                    "guesses_made": 0,
                    "max_guesses": 0,
                    "card_votes": {},
                },
                "red_remaining": red_remaining,
                "blue_remaining": blue_remaining,
                "status": CodenamesGameStatus.IN_PROGRESS.value,
                "winner": None,
                "word_hints": word_hints,
                "hint_usage": {},
                "clue_history": [],
                "timer_config": {
                    "clue_seconds": (getattr(db_room, "settings", None) or {}).get(
                        "codenames_clue_timer", DEFAULT_CODENAMES_CLUE_TIMER_SECONDS
                    ),
                    "guess_seconds": (getattr(db_room, "settings", None) or {}).get(
                        "codenames_guess_timer", DEFAULT_CODENAMES_GUESS_TIMER_SECONDS
                    ),
                },
                "timer_started_at": datetime.now(UTC).isoformat(),
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
            state = game.live_state

            if state["status"] != CodenamesGameStatus.IN_PROGRESS.value:
                raise GameNotInProgressError(game_id=str(game_id))

            player = get_player_from_game(state["players"], str(user_id))

            if player["team"] != state["current_team"]:
                raise NotYourTurnError(user_id=str(user_id))
            if player["role"] != CodenamesRole.SPYMASTER.value:
                raise NotSpymasterError(user_id=str(user_id))

            if state["current_turn"].get("clue_word") is not None:
                raise BaseError(
                    message="A clue has already been given this turn.",
                    frontend_message="A clue has already been given this turn.",
                    status_code=400,
                )

            normalized_clue = unicodedata.normalize("NFKD", clue_word).lower()
            board_words_normalized = [unicodedata.normalize("NFKD", card["word"]).lower() for card in state["board"]]
            if normalized_clue in board_words_normalized:
                raise ClueWordIsOnBoardError(clue_word=clue_word)

            state["current_turn"] = {
                "team": state["current_team"],
                "clue_word": clue_word,
                "clue_number": clue_number,
                "guesses_made": 0,
                "max_guesses": CODENAMES_BOARD_SIZE if clue_number == 0 else clue_number + 1,
                "card_votes": {},
            }

            state["timer_started_at"] = datetime.now(UTC).isoformat()

            # Append to clue history
            if "clue_history" not in state:
                state["clue_history"] = []
            state["clue_history"].append(
                {
                    "team": state["current_team"],
                    "clue_word": clue_word,
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
            clue_word=clue_word,
            clue_number=clue_number,
        )

    async def guess_card(self, game_id: UUID, user_id: UUID, card_index: int) -> GuessCardResponse:
        """Process an operative voting for a card (or instant reveal if solo operative)."""
        logger.info("Codenames guess: game={} user={} card={}", game_id, user_id, card_index)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            self._validate_guess(state, str(user_id), card_index)

            current_team = state["current_team"]
            team_operatives = [
                p for p in state["players"] if p["team"] == current_team and p["role"] == CodenamesRole.OPERATIVE.value
            ]
            total_operatives = len(team_operatives)

            # Single operative: instant reveal (skip voting)
            if total_operatives <= 1:
                return await self._reveal_card(game, state, card_index)

            # Multi-operative: record vote
            card_votes = state["current_turn"].setdefault("card_votes", {})
            previous_vote = card_votes.get(str(user_id))
            card_votes[str(user_id)] = card_index
            vote_changed = previous_vote is not None and previous_vote != card_index

            voted_count = len(card_votes)

            # Not all voted yet — save and return progress
            if voted_count < total_operatives:
                game.live_state = state
                flag_modified(game, "live_state")
                self.session.add(game)
                await self.session.commit()

                return GuessCardResponse(
                    game_id=str(game_id),
                    all_voted=False,
                    vote_changed=vote_changed,
                    card_votes_count=voted_count,
                    total_operatives=total_operatives,
                )

            # All operatives voted — resolve
            winning_index, was_tied = self._resolve_votes(state)
            state["current_turn"]["card_votes"] = {}

            result = await self._reveal_card(game, state, winning_index)
            result.all_voted = True
            result.tied = was_tied
            result.card_votes_count = total_operatives
            result.total_operatives = total_operatives
            return result

    async def _reveal_card(self, game: Game, state: dict, card_index: int) -> GuessCardResponse:
        """Reveal a card and process the result. Commits to DB."""
        card = state["board"][card_index]
        card["revealed"] = True
        state["current_turn"]["guesses_made"] += 1

        result = self._resolve_card(state, card)

        # Append guess to clue history
        clue_history = state.get("clue_history", [])
        if clue_history:
            clue_history[-1]["guesses"].append(
                {
                    "word": card["word"],
                    "card_type": card["card_type"],
                    "correct": card["card_type"] == state["current_team"],
                }
            )

        if (
            result in ("opponent_card", "neutral", "max_guesses")
            and state["status"] == CodenamesGameStatus.IN_PROGRESS.value
        ):
            self._switch_turn(state)

        if state["status"] == CodenamesGameStatus.FINISHED.value:
            game.game_status = GameStatus.FINISHED
            game.end_time = datetime.now(UTC)
            # Clear active game on room
            room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
            if room:
                room.active_game_id = None
                self.session.add(room)
            # Process stats and achievements
            winner_team = state.get("winner", "")
            newly_unlocked = await self._process_game_end_stats(state, winner_team)
            if newly_unlocked:
                state["newly_unlocked_achievements"] = newly_unlocked

        game.live_state = state
        flag_modified(game, "live_state")
        self.session.add(game)
        await self.session.commit()

        return GuessCardResponse(
            game_id=str(game.id),
            card_index=card_index,
            card_type=card["card_type"],
            result=result,
        )

    async def end_turn(self, game_id: UUID, user_id: UUID) -> EndTurnResponse:
        """Allow an operative to voluntarily end their turn."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["status"] != CodenamesGameStatus.IN_PROGRESS.value:
                raise GameNotInProgressError(game_id=str(game_id))

            player = get_player_from_game(state["players"], str(user_id))

            if player["team"] != state["current_team"]:
                raise NotYourTurnError(user_id=str(user_id))
            if player["role"] != CodenamesRole.OPERATIVE.value:
                raise NotOperativeError(user_id=str(user_id))

            self._switch_turn(state)

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
        state = game.live_state

        # Try to find the user as a player first
        is_spectator = False
        try:
            player = get_player_from_game(state["players"], str(user_id))
        except Exception:
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

        # End-game board reveal or spectator view: show all card types when game is finished
        if is_finished:
            board_view = [
                {
                    "index": i,
                    "word": card["word"],
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
                    "revealed": card.get("revealed", False),
                    "card_type": card["card_type"] if card.get("revealed", False) else None,
                    "hint": self._resolve_multilingual(word_hints.get(card["word"]), lang)
                    if card.get("revealed", False)
                    else None,
                }
                for i, card in enumerate(state["board"])
            ]
        else:
            board_view = get_board_for_player(state["board"], player)
            # Add hints: revealed cards and spymaster see hints, unrevealed cards for operatives get null
            for card_view in board_view:
                word = card_view["word"]
                if card_view.get("revealed") or is_spymaster:
                    card_view["hint"] = self._resolve_multilingual(word_hints.get(word), lang)
                else:
                    card_view["hint"] = None

        # Check host status
        room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
        is_host = bool(room and room.owner_id == user_id)

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
            clue_history=state.get("clue_history", []),
            timer_config=state.get("timer_config"),
            timer_started_at=state.get("timer_started_at"),
            players=[
                CodenamesPlayerView(
                    user_id=p["user_id"],
                    username=p["username"],
                    team=p["team"],
                    role=p["role"],
                )
                for p in state["players"]
            ],
        )

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> TimerExpiredResponse:
        """Handle timer expiration — auto end-turn. Validates timer actually expired."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["status"] != CodenamesGameStatus.IN_PROGRESS.value:
                raise GameNotInProgressError(game_id=str(game_id))

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
                    return TimerExpiredResponse(game_id=str(game_id), action="timer_not_expired")
                started = datetime.fromisoformat(timer_started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                now = datetime.now(UTC)
                elapsed = (now - started).total_seconds()
                if elapsed < allowed - TIMER_EXPIRATION_TOLERANCE_SECONDS:
                    return TimerExpiredResponse(game_id=str(game_id), action="timer_not_expired")

            self._switch_turn(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return TimerExpiredResponse(game_id=str(game_id), action="auto_end_turn")

    def _validate_guess(self, state: dict, user_id: str, card_index: int) -> None:
        """Validate that the guess is legal."""
        if state["status"] != CodenamesGameStatus.IN_PROGRESS.value:
            raise GameNotInProgressError(game_id="")
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

    def _resolve_votes(self, state: dict) -> tuple[int, bool]:
        """Count votes and resolve winning card index. Returns (card_index, was_tied)."""
        card_votes = state["current_turn"].get("card_votes", {})
        vote_counts: dict[int, int] = {}
        for idx in card_votes.values():
            vote_counts[idx] = vote_counts.get(idx, 0) + 1

        max_count = max(vote_counts.values())
        top_cards = [idx for idx, count in vote_counts.items() if count == max_count]

        if len(top_cards) == 1:
            return top_cards[0], False

        return random.choice(top_cards), True

    def _resolve_card(self, state: dict, card: dict) -> str:
        """Resolve what happens when a card is revealed."""
        if card["card_type"] == CodenamesCardType.ASSASSIN.value:
            state["status"] = CodenamesGameStatus.FINISHED.value
            state["winner"] = (
                CodenamesTeam.BLUE.value
                if state["current_team"] == CodenamesTeam.RED.value
                else CodenamesTeam.RED.value
            )
            return "assassin"

        if card["card_type"] == state["current_team"]:
            # Own team's card
            remaining = self._decrement_remaining(state, state["current_team"])
            if remaining == 0:
                state["status"] = CodenamesGameStatus.FINISHED.value
                state["winner"] = state["current_team"]
                return "win"
            return (
                "max_guesses"
                if state["current_turn"]["guesses_made"] >= state["current_turn"]["max_guesses"]
                else "correct"
            )

        if card["card_type"] != CodenamesCardType.NEUTRAL.value:
            # Opponent's card
            other_team = (
                CodenamesTeam.BLUE.value
                if state["current_team"] == CodenamesTeam.RED.value
                else CodenamesTeam.RED.value
            )
            remaining = self._decrement_remaining(state, other_team)
            if remaining == 0:
                state["status"] = CodenamesGameStatus.FINISHED.value
                state["winner"] = other_team
                return "opponent_wins"
            return "opponent_card"

        return "neutral"

    async def record_hint_view(self, game_id: UUID, user_id: UUID, word: str) -> HintRecordResponse:
        """Record that a player viewed a hint for a word (deduplicated)."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            hint_usage = state.setdefault("hint_usage", {})
            user_key = str(user_id)
            user_hints = hint_usage.setdefault(user_key, [])
            if word not in user_hints:
                user_hints.append(word)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return HintRecordResponse(game_id=str(game_id), recorded=True)

    async def _process_game_end_stats(self, state: dict, winner: str) -> list[dict]:
        """Update stats and check achievements for all players after game ends.

        Returns a list of {user_id, achievements: [{code, name, icon, tier}]} for newly unlocked.
        """
        hint_usage = state.get("hint_usage", {})
        newly_unlocked_all: list[dict] = []
        for player in state.get("players", []):
            user_id = UUID(player["user_id"])
            role = player.get("role", "operative")
            won = player.get("team") == winner
            try:
                stats = await self._stats_controller.update_stats_after_game(
                    user_id=user_id, game_type="codenames", won=won, role=role
                )
                # Update hint-related stats
                user_hints = hint_usage.get(str(user_id), [])
                hints_viewed_count = len(user_hints)
                if hints_viewed_count > 0:
                    stats.total_hints_viewed += hints_viewed_count
                if won and hints_viewed_count == 0:
                    stats.games_without_hints += 1
                self.session.add(stats)
                await self.session.commit()
                await self.session.refresh(stats)

                unlocked = await self._achievement_controller.check_achievements(user_id, stats)
                if unlocked:
                    newly_unlocked_all.append(
                        {
                            "user_id": str(user_id),
                            "achievements": [
                                {"code": a.code, "name": a.name, "icon": a.icon, "tier": a.tier} for a in unlocked
                            ],
                        }
                    )
                logger.info("Stats updated: game=codenames user={}", user_id)
            except Exception:
                logger.exception("Failed to update stats/achievements for user {user_id}", user_id=user_id)
        return newly_unlocked_all

    def _decrement_remaining(self, state: dict, team: str) -> int:
        """Decrement the remaining card count for a team and return the new count."""
        if team == CodenamesTeam.RED.value:
            state["red_remaining"] -= 1
            return state["red_remaining"]
        state["blue_remaining"] -= 1
        return state["blue_remaining"]

    def _switch_turn(self, state: dict) -> None:
        """Switch the current turn to the other team."""
        next_team = (
            CodenamesTeam.BLUE.value if state["current_team"] == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        )
        state["current_team"] = next_team
        state["current_turn"] = {
            "team": next_team,
            "clue_word": None,
            "clue_number": 0,
            "guesses_made": 0,
            "max_guesses": 0,
            "card_votes": {},
        }
        state["timer_started_at"] = datetime.now(UTC).isoformat()
