from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DEFAULT_DESCRIPTION_TIMER_SECONDS,
    DEFAULT_VOTING_TIMER_SECONDS,
    HOST_USERNAME_STATE_KEY,
    MAX_PLAYERS_UNDERCOVER,
    MIN_PLAYERS_FOR_GAME,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
    UNDERCOVER_MIN_COUNT,
    UNDERCOVER_MR_WHITE_COUNT_LARGE,
    UNDERCOVER_MR_WHITE_COUNT_MEDIUM,
    UNDERCOVER_MR_WHITE_COUNT_SMALL,
    UNDERCOVER_MR_WHITE_MIN_PLAYERS,
    UNDERCOVER_MR_WHITE_THRESHOLD_MEDIUM,
    UNDERCOVER_MR_WHITE_THRESHOLD_SMALL,
    UNDERCOVER_RATIO,
    UNDERCOVER_WORD_MAX_LENGTH,
)
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.game_end_stats import record_game_end, undercover_winners
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.controllers.undercover import UndercoverController
from majlisna.api.controllers.undercover_rules import (
    eliminate_player_based_on_votes,
    enter_mr_white_guess,
    winning_team,
)
from majlisna.api.models.error import (
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
    PlayerRemovedFromGameError,
)
from majlisna.api.models.event import EventCreate
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.table import Room
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.common import (
    GameStartResponse,
    HintRecordResponse,
    PhaseTimer,
    TimerExpiredAction,
    TimerExpiredResponse,
)
from majlisna.api.schemas.error import (
    AllDescriptionsSubmittedError,
    AlreadyVotedError,
    DescriptionsNotCompleteError,
    GameNotInRoomError,
    InvalidDescriptionWordError,
    NotAGamePlayerError,
    NotDescribingPhaseError,
    NotMrWhiteGuessingPhaseError,
    NotTheMrWhiteGuesserError,
    NotYourTurnToDescribeError,
    RoundNotResolvedError,
    VoteTargetNotInGameError,
)
from majlisna.api.schemas.term_script import TermScriptForms
from majlisna.api.schemas.undercover import (
    EliminatedPlayer,
    MrWhiteGuessResponse,
    StartNextRoundResponse,
    SubmitDescriptionResponse,
    SubmitVoteResponse,
    UndercoverGameState,
    UndercoverPlayerState,
    WordExplanations,
)
from majlisna.api.utils.game_pause import is_paused, parse_instant
from majlisna.api.utils.game_state import require_state
from majlisna.api.utils.rng import rng
from majlisna.api.utils.text_match import matches_any


class UndercoverGameController(BaseGameController):
    """REST controller for Undercover game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses asyncio.Lock per game_id for concurrency control.
    """

    GAME_TYPE = GameType.UNDERCOVER

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._undercover_controller = UndercoverController(session)

    @staticmethod
    def _compute_roles(num_players: int, mr_white_enabled: bool) -> list[str]:
        """Compute the role distribution for the given number of players.

        Invariant: civilians strictly outnumber undercover + Mr. White, because the
        win rule gives the impostors the game the moment they reach parity. The
        previous table forced at least two undercovers whenever Mr. White was on,
        which dealt 4 players as 1 civilian / 2 undercover / 1 Mr. White and lost
        every 4-6 player game for the civilians at the first resolution.
        """
        num_undercover = max(UNDERCOVER_MIN_COUNT, num_players // UNDERCOVER_RATIO)
        num_mr_white = 0
        if mr_white_enabled and num_players >= UNDERCOVER_MR_WHITE_MIN_PLAYERS:
            if num_players < UNDERCOVER_MR_WHITE_THRESHOLD_SMALL:
                num_mr_white = UNDERCOVER_MR_WHITE_COUNT_SMALL
            elif num_players <= UNDERCOVER_MR_WHITE_THRESHOLD_MEDIUM:
                num_mr_white = UNDERCOVER_MR_WHITE_COUNT_MEDIUM
            else:
                num_mr_white = UNDERCOVER_MR_WHITE_COUNT_LARGE
        num_civilians = num_players - num_undercover - num_mr_white
        # Restore the invariant for any table the constants above could produce:
        # drop a Mr. White first (an optional role), then undercovers down to one.
        while num_civilians <= num_undercover + num_mr_white and num_mr_white > 0:
            num_mr_white -= 1
            num_civilians += 1
        while num_civilians <= num_undercover + num_mr_white and num_undercover > UNDERCOVER_MIN_COUNT:
            num_undercover -= 1
            num_civilians += 1

        roles = (
            [UndercoverRole.UNDERCOVER.value] * num_undercover
            + [UndercoverRole.CIVILIAN.value] * num_civilians
            + [UndercoverRole.MR_WHITE.value] * num_mr_white
        )
        rng.shuffle(roles)
        return roles

    async def _get_civilian_and_undercover_words(self) -> tuple:
        """Get the civilian and undercover words for the game."""
        term_pair = await self._undercover_controller.get_random_term_pair()
        civilian_word_id = term_pair.word1_id
        undercover_word_id = term_pair.word2_id
        if rng.choice([True, False]):
            civilian_word_id, undercover_word_id = term_pair.word2_id, term_pair.word1_id
        civilian_word = await self._undercover_controller.get_word_by_id(civilian_word_id)
        undercover_word = await self._undercover_controller.get_word_by_id(undercover_word_id)
        return civilian_word, undercover_word

    def _generate_description_order(self, players: list[dict]) -> list[str]:
        """Generate a randomized description order for alive players.

        Mr. White is never placed first.
        """
        alive_ids = [p["user_id"] for p in players if p["is_alive"]]
        rng.shuffle(alive_ids)

        if len(alive_ids) > 1:
            mr_white_ids = {
                p["user_id"] for p in players if p["role"] == UndercoverRole.MR_WHITE.value and p["is_alive"]
            }
            if alive_ids[0] in mr_white_ids:
                swap_candidates = [i for i in range(1, len(alive_ids)) if alive_ids[i] not in mr_white_ids]
                if swap_candidates:
                    swap_idx = rng.choice(swap_candidates)
                    alive_ids[0], alive_ids[swap_idx] = alive_ids[swap_idx], alive_ids[0]

        return alive_ids

    async def create_and_start(self, room_id: UUID, user_id: UUID) -> GameStartResponse:
        """Start a new Undercover game in the given room. Host only."""
        async with get_game_lock(f"room:{room_id}", self.session):
            # Undercover needs 3 players. MIN_PLAYERS_FOR_GAME existed but was
            # never passed, leaving the base default of 1 in force — so a lone
            # host could start a game that _compute_roles filled with a single
            # undercover and ZERO civilians (instantly won, unplayable: the only
            # player cannot vote, and voting for yourself is rejected), and a
            # 2-player game was a pure coin flip on the first tie-break.
            db_room, player_users = await self._prepare_game_start(
                room_id, min_players=MIN_PLAYERS_FOR_GAME, max_players=MAX_PLAYERS_UNDERCOVER
            )
            self._require_room_host(db_room, user_id)

            num_players = len(player_users)
            room_settings = getattr(db_room, "settings", None) or {}
            mr_white_enabled = room_settings.get("enable_mr_white", True)
            roles = self._compute_roles(num_players, mr_white_enabled)

            players = [
                {
                    "user_id": str(u.id),
                    "username": u.username,
                    "role": role,
                    "is_alive": True,
                    "is_mayor": False,
                }
                for u, role in zip(player_users, roles, strict=True)
            ]
            players[rng.randint(0, len(players) - 1)]["is_mayor"] = True

            civilian_word, undercover_word = await self._get_civilian_and_undercover_words()
            civilian_word_hint = civilian_word.hint
            undercover_word_hint = undercover_word.hint

            db_game = await self._game_controller.create_game(
                GameCreate(
                    room_id=db_room.id,
                    number_of_players=num_players,
                    type=GameType.UNDERCOVER,
                    game_configurations={
                        "civilian_word": civilian_word.word,
                        "undercover_word": undercover_word.word,
                        "civilian_word_id": str(civilian_word.id),
                        "undercover_word_id": str(undercover_word.id),
                    },
                ),
                # Keep the whole start in one transaction so the room advisory lock
                # is held until active_game_id is committed (prevents concurrent
                # double-start). The final commit below persists everything.
                commit=False,
            )

            # Build initial live_state
            description_order = self._generate_description_order(players)
            first_turn = {
                "votes": {},
                "words": {},
                "description_order": description_order,
                "current_describer_index": 0,
                "phase": "describing",
            }

            # Read timer settings from room settings if available
            room_settings = getattr(db_room, "settings", None) or {}
            desc_timer = room_settings.get("description_timer", DEFAULT_DESCRIPTION_TIMER_SECONDS)
            vote_timer = room_settings.get("voting_timer", DEFAULT_VOTING_TIMER_SECONDS)

            live_state = {
                "civilian_word": civilian_word.word,
                "undercover_word": undercover_word.word,
                "civilian_word_hint": civilian_word_hint,
                "undercover_word_hint": undercover_word_hint,
                "hint_usage": {},
                "players": players,
                "eliminated_players": [],
                "turns": [first_turn],
                "timer_config": {
                    "description_seconds": desc_timer,
                    "voting_seconds": vote_timer,
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

            # Create turn record (commit=False — the single commit below is atomic with the lock)
            turn = await self._game_controller.create_turn(game_id=db_game.id, commit=False)
            await self._game_controller.create_turn_event(
                game_id=db_game.id,
                event_create=EventCreate(
                    name="start_turn",
                    data={"game_id": str(db_game.id), "turn_id": str(turn.id), "message": "Turn started."},
                    user_id=db_room.owner_id,
                ),
                commit=False,
            )

            await self.session.commit()

            return GameStartResponse(
                game_id=str(db_game.id),
                room_id=str(db_room.id),
            )

    async def start_next_round(self, game_id: UUID, room_id: UUID, user_id: UUID) -> StartNextRoundResponse:
        """Start a new round (turn) in an existing game. Host only, game must be in progress."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            if game.room_id != room_id:
                raise GameNotInRoomError(game_id=game_id, room_id=room_id)
            room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
            if room:
                self._require_room_host(room, user_id)
            state = require_state(game)
            self._ensure_not_paused(game, state)

            # Only a resolved round may be followed by a new one. Without this guard a
            # host could append a turn in the middle of describing or voting — or
            # while an eliminated Mr. White still owes his guess — discarding the
            # round in progress; and two concurrent calls both appended a turn.
            current_turn = state["turns"][-1] if state["turns"] else None
            if (
                current_turn is None
                or not current_turn.get("resolved")
                or current_turn.get("phase") == "mr_white_guessing"
            ):
                raise RoundNotResolvedError(game_id=game_id)

            description_order = self._generate_description_order(state["players"])
            new_turn = {
                "votes": {},
                "words": {},
                "description_order": description_order,
                "current_describer_index": 0,
                "phase": "describing",
            }
            state["turns"].append(new_turn)
            state["timer_started_at"] = datetime.now(UTC).isoformat()
            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)

            # Create DB turn record. commit=False on both: these ran with the
            # default commit=True, i.e. two commits inside the game lock. On
            # PostgreSQL the lock is pg_try_advisory_xact_lock — transaction
            # scoped — so the first commit RELEASED it and the rest of this block
            # ran unprotected, letting two concurrent next-round calls each append
            # a turn. One commit per locked block.
            turn = await self._game_controller.create_turn(game_id=game.id, commit=False)
            await self._game_controller.create_turn_event(
                game_id=game.id,
                event_create=EventCreate(
                    name="start_turn",
                    data={"game_id": str(game.id), "turn_id": str(turn.id), "message": "Turn started."},
                    user_id=user_id,
                ),
                commit=False,
            )

            await self.session.commit()

            description_order_with_names = []
            for uid in description_order:
                p = next((p for p in state["players"] if p["user_id"] == uid), None)
                if p:
                    description_order_with_names.append({"user_id": uid, "username": p["username"]})

        return StartNextRoundResponse(
            game_id=str(game_id),
            turn_number=len(state["turns"]),
            description_order=description_order_with_names,
        )

    async def submit_description(self, game_id: UUID, user_id: UUID, word: str) -> SubmitDescriptionResponse:
        """Submit a single-word description for the current turn."""
        logger.info("Undercover description: game={} user={}", game_id, user_id)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)
            self._ensure_not_paused(game, state)
            current_turn = state["turns"][-1]

            if current_turn["phase"] != "describing":
                raise NotDescribingPhaseError()

            if current_turn["current_describer_index"] >= len(current_turn["description_order"]):
                raise AllDescriptionsSubmittedError()

            if current_turn["description_order"][current_turn["current_describer_index"]] != str(user_id):
                raise NotYourTurnToDescribeError()

            word = word.strip()
            if not word or " " in word or len(word) > UNDERCOVER_WORD_MAX_LENGTH:
                raise InvalidDescriptionWordError(max_length=UNDERCOVER_WORD_MAX_LENGTH)

            current_turn["words"][str(user_id)] = word
            current_turn["current_describer_index"] += 1
            all_done = current_turn["current_describer_index"] >= len(current_turn["description_order"])

            if all_done:
                current_turn["phase"] = "voting"
                state["timer_started_at"] = datetime.now(UTC).isoformat()

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return SubmitDescriptionResponse(
            game_id=str(game_id),
            all_described=all_done,
            word=word,
        )

    async def submit_vote(self, game_id: UUID, user_id: UUID, voted_for: UUID) -> SubmitVoteResponse:  # noqa: C901
        """Submit a vote for a player."""
        logger.info("Undercover vote: game={} user={} target={}", game_id, user_id, voted_for)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)
            self._ensure_not_paused(game, state)

            if state["turns"] and state["turns"][-1]["phase"] != "voting":
                raise DescriptionsNotCompleteError()

            player_to_vote = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
            if not player_to_vote:
                raise NotAGamePlayerError(message="Player not in game.", status_code=400)
            if not player_to_vote["is_alive"]:
                raise CantVoteBecauseYouDeadError(user_id=user_id)

            voted_player = next((p for p in state["players"] if p["user_id"] == str(voted_for)), None)
            if not voted_player:
                raise VoteTargetNotInGameError()
            if not voted_player["is_alive"]:
                raise CantVoteForDeadPersonError(user_id=user_id, dead_user_id=voted_for)
            if str(user_id) == str(voted_for):
                raise CantVoteForYourselfError(user_id=user_id)

            if str(user_id) in state["turns"][-1]["votes"]:
                raise AlreadyVotedError()

            state["turns"][-1]["votes"][str(user_id)] = str(voted_for)

            alive_count = sum(1 for p in state["players"] if p["is_alive"])
            all_voted = len(state["turns"][-1]["votes"]) == alive_count

            result = SubmitVoteResponse(game_id=str(game_id), all_voted=all_voted)

            if all_voted:
                eliminated_player, number_of_votes = self._eliminate_player_based_on_votes(state)

                result.eliminated_player = eliminated_player["user_id"]
                result.eliminated_player_role = eliminated_player["role"]
                result.eliminated_player_username = eliminated_player["username"]
                result.number_of_votes = number_of_votes

                # If the eliminated player is Mr. White, give them a chance to guess
                if eliminated_player["role"] == UndercoverRole.MR_WHITE.value:
                    enter_mr_white_guess(state, eliminated_player)
                    result.winner = None
                else:
                    winner = self._get_winning_team(state)
                    if winner:
                        await self._finish_game(game, state, winner)
                        result.winner = "civilians" if winner == UndercoverRole.CIVILIAN.value else "undercovers"
                    else:
                        result.winner = None

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return result

    async def _finish_game(self, game, state: dict, winner: str) -> None:
        """Finish the game: set status, record the winner, clear active_game_id, process stats."""
        winner_label = "civilians" if winner == UndercoverRole.CIVILIAN.value else "undercovers"
        game.game_status = GameStatus.FINISHED
        game.end_time = datetime.now(UTC)
        # Persist the decided winner. Undercover used to leave live_state["winner"]
        # unset, so game history and the post-game summary — which both read
        # state["winner"] — showed no winner and left `user_won` null for EVERY
        # undercover game. It is also the only correct source once the game is
        # over: recomputing from alive counts (see _get_winner_label) can't
        # express "Mr. White guessed the civilian word", where undercovers win
        # even though civilians still outnumber them.
        state["winner"] = winner_label
        room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
        if room:
            room.active_game_id = None
            self.session.add(room)
        newly_unlocked = await self._process_game_end_stats(state, winner_label)
        if newly_unlocked:
            state["newly_unlocked_achievements"] = newly_unlocked

    async def submit_mr_white_guess(self, game_id: UUID, user_id: UUID, guess_word: str) -> MrWhiteGuessResponse:
        """Mr. White submits a guess for the civilian word after being eliminated."""
        logger.info("Mr. White guess: game={} user={}", game_id, user_id)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)
            self._ensure_not_paused(game, state)
            current_turn = state["turns"][-1]

            if current_turn["phase"] != "mr_white_guessing":
                raise NotMrWhiteGuessingPhaseError()

            if state.get("mr_white_guesser") != str(user_id):
                raise NotTheMrWhiteGuesserError()

            # The civilian word is accepted in Latin or in Arabic script: an
            # Arabic-speaking Mr. White sees "صبر" on the civilians' cards, and
            # typing it used to be rejected as a wrong guess.
            civilian_word = state["civilian_word"]
            civilian_script = (await self._term_script_controller.get_forms([civilian_word])).get(civilian_word)
            correct = matches_any(guess_word, [civilian_word, civilian_script.ar if civilian_script else None])

            state.pop("mr_white_guesser", None)
            # The table hears the guess: the round's verdict says what he guessed and
            # whether it was the word (it used to reach the guesser alone, as a toast).
            current_turn["mr_white_guess"] = {"word": guess_word.strip(), "correct": correct}

            if correct:
                # Undercovers win — Mr. White guessed correctly
                winner = UndercoverRole.UNDERCOVER.value
                await self._finish_game(game, state, winner)
                current_turn["phase"] = "game_over"
            else:
                # Wrong guess — check normal win conditions
                current_turn["phase"] = "voting"  # Reset phase for next round flow
                winner_raw = self._get_winning_team(state)
                if winner_raw:
                    await self._finish_game(game, state, winner_raw)
                    current_turn["phase"] = "game_over"

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        winner_label = None
        if correct:
            winner_label = "undercovers"
        elif game.game_status == GameStatus.FINISHED:
            winner_raw = self._get_winning_team(state)
            winner_label = "civilians" if winner_raw == UndercoverRole.CIVILIAN.value else "undercovers"

        return MrWhiteGuessResponse(game_id=str(game_id), correct=correct, winner=winner_label)

    @staticmethod
    def _auto_fill_missing_votes(state: dict) -> None:
        """Fill in random votes for alive players who haven't voted yet."""
        current_turn = state["turns"][-1]
        alive_players = [p for p in state["players"] if p["is_alive"]]
        alive_ids = [p["user_id"] for p in alive_players]
        for p in alive_players:
            if p["user_id"] not in current_turn["votes"]:
                candidates = [pid for pid in alive_ids if pid != p["user_id"]]
                if candidates:
                    current_turn["votes"][p["user_id"]] = rng.choice(candidates)

    def _is_timer_actually_expired(self, state: dict) -> bool:
        """Check if the game timer has actually elapsed server-side."""
        timer_config = state.get("timer_config", {})
        timer_started_at = state.get("timer_started_at")
        if not timer_started_at:
            return True
        current_phase = state["turns"][-1]["phase"]
        if current_phase == "describing":
            allowed = timer_config.get("description_seconds", DEFAULT_DESCRIPTION_TIMER_SECONDS)
        else:
            allowed = timer_config.get("voting_seconds", DEFAULT_VOTING_TIMER_SECONDS)
        if allowed == 0:
            return False  # No time limit — timer never expires
        started = datetime.fromisoformat(timer_started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return elapsed >= allowed - TIMER_EXPIRATION_TOLERANCE_SECONDS

    def _phase_timer(self, state: dict) -> PhaseTimer | None:
        """The running phase's timer: describing, an open vote, or Mr. White's guess.

        Same durations as ``_is_timer_actually_expired``. A resolved vote is waiting on
        the host's next round, not on a clock, so it has none.
        """
        started_at = state.get("timer_started_at")
        turns = state.get("turns") or []
        if not started_at or not turns:
            return None
        turn = turns[-1]
        timer_config = state.get("timer_config") or {}
        if turn["phase"] == "describing":
            seconds = timer_config.get("description_seconds", DEFAULT_DESCRIPTION_TIMER_SECONDS)
        elif turn["phase"] == "mr_white_guessing" or (turn["phase"] == "voting" and not turn.get("resolved")):
            seconds = timer_config.get("voting_seconds", DEFAULT_VOTING_TIMER_SECONDS)
        else:
            return None
        if not seconds:
            return None  # 0 means no time limit
        return PhaseTimer(started_at=parse_instant(started_at), duration_seconds=seconds)

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> TimerExpiredResponse:
        """Handle timer expiration — auto-skip description, auto-random-vote, or mr_white guess timeout."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)

            # No clock runs while the host has paused the game for the prayer. Not an
            # error: clients fire this from their own local timers.
            if is_paused(state):
                return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.PAUSED)

            # Any player may trigger timer expiration (consistent with the other
            # games); the server only acts if the timer has actually elapsed, so
            # a game can still advance when the host is absent.
            if not self._is_timer_actually_expired(state):
                return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.TIMER_NOT_EXPIRED)

            current_turn = state["turns"][-1]
            action = TimerExpiredAction.NONE

            if current_turn["phase"] == "describing":
                # Auto-skip remaining describers by setting index to end
                current_turn["current_describer_index"] = len(current_turn["description_order"])
                current_turn["phase"] = "voting"
                state["timer_started_at"] = datetime.now(UTC).isoformat()
                action = TimerExpiredAction.SKIP_TO_VOTING

            elif current_turn["phase"] == "voting":
                # A round whose votes have already produced an elimination stays in
                # the "voting" phase until the host starts the next round, and
                # `timer_started_at` still points at the voting deadline — so the
                # timer reads as expired for the whole gap. Without this guard every
                # timer-expired call in that window re-ran the tally over the SAME
                # votes: another player died, `eliminated_players` grew a duplicate
                # entry (which desynchronises vote history), and the client's timer
                # callback kept the cycle going, one DB write and one broadcast per
                # tick. Re-resolving is never correct: a round has exactly one
                # elimination.
                if current_turn.get("resolved"):
                    return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.ROUND_ALREADY_RESOLVED)

                self._auto_fill_missing_votes(state)
                # Now eliminate
                eliminated_player, _ = self._eliminate_player_based_on_votes(state)
                action = TimerExpiredAction.AUTO_VOTE

                # If Mr. White was eliminated, enter guessing phase
                if eliminated_player["role"] == UndercoverRole.MR_WHITE.value:
                    enter_mr_white_guess(state, eliminated_player)
                else:
                    winner = self._get_winning_team(state)
                    if winner:
                        await self._finish_game(game, state, winner)

            elif current_turn["phase"] == "mr_white_guessing":
                # Timer expired during Mr. White guessing — treat as wrong guess
                state.pop("mr_white_guesser", None)
                current_turn["mr_white_guess"] = {"word": None, "correct": False}
                action = TimerExpiredAction.MR_WHITE_GUESS_TIMEOUT
                winner = self._get_winning_team(state)
                if winner:
                    await self._finish_game(game, state, winner)
                    current_turn["phase"] = "game_over"
                else:
                    # Leave the turn in the same phase a *wrong guess* leaves it
                    # (see submit_mr_white_guess). Staying in "mr_white_guessing"
                    # with no `mr_white_guesser` wedged the game: guessing 403s
                    # (nobody matches the guesser), voting and describing both
                    # reject the phase, and only the host's next-round call could
                    # rescue it.
                    current_turn["phase"] = "voting"

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return TimerExpiredResponse(game_id=str(game_id), action=action)

    def _eliminate_player_based_on_votes(self, state: dict) -> tuple[dict, int]:
        """Eliminate the alive player with the most votes. See ``undercover_rules``.

        Kept as a method because the disconnect path needs the same rule and
        cannot import a controller (``base_game`` → ``room`` → ``disconnect``).
        """
        return eliminate_player_based_on_votes(state)

    def _get_winning_team(self, state: dict) -> str | None:
        """Determine if a team has won based on alive player counts. See ``undercover_rules``."""
        return winning_team(state)

    async def get_state(
        self, game_id: UUID, user_id: UUID, sid: str | None = None, lang: str = "en", update_heartbeat: bool = True
    ) -> UndercoverGameState:
        """Get full game state for a player or spectator. Used for polling and initial page load."""
        game = await self._get_game(game_id)
        state = require_state(game)

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        is_spectator = await self._check_spectator(game, user_id, player)

        # Update heartbeat (throttled: skip if last_seen_at is recent to reduce write contention)
        if update_heartbeat:
            await self._update_heartbeat_throttled(game.room_id, user_id)

        winner = self._get_winner_label(state)
        owner_id, host_username = await self._get_room_host(game.room_id)
        is_host = owner_id == user_id
        colophon = self._build_colophon(game, state, host_username)
        vote_history = self._build_vote_history(state)

        if is_spectator:
            # Spectators see descriptions/votes but NOT roles/words until game ends
            my_role = "spectator"
            my_word = ""
            my_word_hint = None
            own_term = None
            turn_state = self._build_turn_state(state, "")
        else:
            if player is None:
                # Unreachable: _check_spectator above raises unless the caller is
                # either a player or a spectator, and this is the not-a-spectator
                # branch. Stated rather than assumed, so the invariant is checked.
                raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game.id))
            my_role = player["role"]
            my_word = self._get_player_word(player, state)
            my_word_hint = self._get_player_word_hint(player, state, lang)
            own_term = self._get_player_term(player, state)
            turn_state = self._build_turn_state(state, str(user_id))

        # ONE lookup for every term this caller may see: their own word (none for
        # Mr. White or a spectator) and, once the game is over, both words. The
        # Arabic form follows exactly the same rule as the Latin one — the other
        # side's word is never looked up while the game is running.
        visible_terms = [own_term]
        if winner:
            visible_terms += [state["civilian_word"], state["undercover_word"]]
        scripts = await self._term_script_controller.get_forms(visible_terms)
        own_script = scripts.get(own_term) if own_term else None
        word_explanations = self._build_word_explanations(state, lang, scripts) if winner else None

        return UndercoverGameState(
            game_id=str(game.id),
            room_id=str(game.room_id),
            is_host=is_host,
            is_spectator=is_spectator,
            my_role=my_role,
            my_word=my_word,
            my_word_ar=own_script.ar if own_script else None,
            my_word_ar_vocalized=own_script.ar_vocalized if own_script else None,
            my_word_hint=my_word_hint,
            is_alive=player["is_alive"] if player else False,
            players=[
                UndercoverPlayerState(
                    user_id=p["user_id"],
                    username=p["username"],
                    is_alive=p["is_alive"],
                    is_mayor=p.get("is_mayor", False),
                )
                for p in state["players"]
            ],
            eliminated_players=[
                EliminatedPlayer(user_id=p["user_id"], username=p["username"], role=p["role"])
                for p in state["eliminated_players"]
            ],
            turn_number=len(state["turns"]),
            winner=winner,
            vote_history=vote_history,
            timer_config=state.get("timer_config"),
            timer_started_at=state.get("timer_started_at"),
            word_explanations=word_explanations,
            mr_white_guesser=state.get("mr_white_guesser"),
            newly_unlocked_achievements=state.get("newly_unlocked_achievements"),
            paused=self._build_pause(game, state),
            can_pause=self._can_pause(game, state, user_id, owner_id, is_spectator=is_spectator),
            can_resume=self._can_resume(game, state, user_id, owner_id),
            host_username=colophon.host_username,
            started_at=colophon.started_at,
            ended_at=colophon.ended_at,
            **turn_state,
        )

    def _build_word_explanations(self, state: dict, lang: str, scripts: dict[str, TermScriptForms]) -> WordExplanations:
        """Both words of the pair, for the game-over screen. Only call once the game is over."""
        civilian = scripts.get(state["civilian_word"])
        undercover = scripts.get(state["undercover_word"])
        return WordExplanations(
            civilian_word=state["civilian_word"],
            civilian_word_ar=civilian.ar if civilian else None,
            civilian_word_ar_vocalized=civilian.ar_vocalized if civilian else None,
            civilian_word_hint=self._resolve_multilingual(state.get("civilian_word_hint"), lang),
            undercover_word=state["undercover_word"],
            undercover_word_ar=undercover.ar if undercover else None,
            undercover_word_ar_vocalized=undercover.ar_vocalized if undercover else None,
            undercover_word_hint=self._resolve_multilingual(state.get("undercover_word_hint"), lang),
        )

    @staticmethod
    def _get_player_term(player: dict, state: dict) -> str | None:
        """The secret term dealt to this player, or None for Mr. White (who has none)."""
        if player["role"] == UndercoverRole.MR_WHITE.value:
            return None
        if player["role"] == UndercoverRole.UNDERCOVER.value:
            return state["undercover_word"]
        return state["civilian_word"]

    def _get_player_word(self, player: dict, state: dict) -> str:
        """Get the word to display for a player based on their role."""
        if player["role"] == UndercoverRole.MR_WHITE.value:
            return "You are Mr. White. You have to guess the word."
        if player["role"] == UndercoverRole.UNDERCOVER.value:
            return state["undercover_word"]
        return state["civilian_word"]

    def _get_player_word_hint(self, player: dict, state: dict, lang: str) -> str | None:
        """Get the hint for the player's word, resolved to the requested language."""
        if player["role"] == UndercoverRole.MR_WHITE.value:
            return None
        if player["role"] == UndercoverRole.UNDERCOVER.value:
            return self._resolve_multilingual(state.get("undercover_word_hint"), lang)
        return self._resolve_multilingual(state.get("civilian_word_hint"), lang)

    async def record_hint_view(self, game_id: UUID, user_id: UUID, word: str) -> HintRecordResponse:
        """Record that a player viewed a hint for a word (deduplicated)."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            # Hint views feed achievements ("won without hints"), so they must not
            # be accepted after the game has ended — the end-of-game stats have
            # already been computed from hint_usage.
            self._check_game_in_progress(game)
            state = require_state(game)

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

    @staticmethod
    def _visible_votes(state: dict, current_turn: dict, user_id: str) -> dict[str, str]:
        """The votes this caller is allowed to see.

        While the round is open, only the caller's own choice is returned; every
        other voter is reported as having voted, with no target. The UI has only
        ever used this to render "who has voted" (``deriveVotedPlayers`` keys the
        dict), but the raw payload named every target — so anyone with the network
        tab open could watch the tally build and vote last with perfect
        information. In a social-deduction round that is the whole game.

        Targets become public once the round is ``resolved`` or the game is over:
        the elimination has already happened, and the end-of-round overlay and the
        vote-history panel show them anyway.
        """
        votes: dict[str, str] = current_turn.get("votes", {})
        if current_turn.get("resolved") or state.get("winner"):
            return votes
        return {voter: (target if voter == user_id else "") for voter, target in votes.items()}

    def _build_turn_state(self, state: dict, user_id: str) -> dict:
        """Build the turn-specific state dict."""
        if not state["turns"]:
            return {
                "votes": {},
                "has_voted": False,
                "turn_phase": "describing",
                "description_order": [],
                "current_describer_index": 0,
                "descriptions": {},
                "round_resolved": False,
            }
        current_turn = state["turns"][-1]
        return {
            "votes": self._visible_votes(state, current_turn, user_id),
            "has_voted": user_id in current_turn["votes"],
            "turn_phase": current_turn["phase"],
            # A resolved turn stays in phase "voting" until the host starts the next
            # round; without this flag the client cannot tell "still voting" from
            # "someone was just eliminated" and never offered the next round.
            "round_resolved": bool(current_turn.get("resolved")),
            "description_order": [
                {
                    "user_id": uid,
                    "username": next((p["username"] for p in state["players"] if p["user_id"] == uid), "Unknown"),
                }
                for uid in current_turn["description_order"]
            ],
            "current_describer_index": current_turn["current_describer_index"],
            "descriptions": current_turn["words"],
        }

    async def _process_game_end_stats(self, state: dict, winner_label: str) -> list[dict]:
        """Stage the end-of-game stat and achievement writes. See game_end_stats."""
        return await record_game_end(
            self.session,
            state,
            game_type="undercover",
            winners=undercover_winners(state, winner_label),
            default_role="civilian",
        )

    def _get_winner_label(self, state: dict) -> str | None:
        """Get the winner label string, or None if game is still in progress.

        Prefers the winner recorded by ``_finish_game``. Falling back to
        recomputing from alive counts is only for games that predate that write:
        the derived value is wrong after a correct Mr. White guess (undercovers
        win while civilians are still alive and ahead), which made the game-over
        screen report no winner and hide the word explanations.
        """
        recorded = state.get("winner")
        if recorded:
            return recorded
        winner = self._get_winning_team(state)
        if winner == UndercoverRole.CIVILIAN.value:
            return "civilians"
        if winner == UndercoverRole.UNDERCOVER.value:
            return "undercovers"
        return None

    def _build_vote_history(self, state: dict) -> list[dict]:
        """Build vote history from completed turns (all turns except the current one if still in progress)."""
        players_map = {p["user_id"]: p["username"] for p in state["players"]}
        eliminated_list = state.get("eliminated_players", [])
        history = []

        last_index = len(state["turns"]) - 1
        game_over = bool(state.get("winner"))
        for i, turn in enumerate(state["turns"]):
            votes = turn.get("votes", {})
            if not votes:
                continue
            # The docstring has always claimed this excludes the round still in
            # progress; the code did not. An open round's entries name every
            # target, so this was the second door onto the leak `_visible_votes`
            # closes — and it is the one the client actually reads. A round is
            # finished when it is `resolved`; once the game is over everything is
            # public anyway.
            if not game_over and i == last_index and not turn.get("resolved"):
                continue

            vote_entries = []
            for voter_id, target_id in votes.items():
                vote_entries.append(
                    {
                        "voter": players_map.get(voter_id, "Unknown"),
                        "voter_id": voter_id,
                        "target": players_map.get(target_id, "Unknown"),
                        "target_id": target_id,
                    }
                )

            eliminated_info = None
            ep = next((e for e in eliminated_list if e.get("round") == i + 1), None)
            if ep is None and i < len(eliminated_list) and "round" not in eliminated_list[i]:
                ep = eliminated_list[i]  # pre-"round" rows: fall back to position
            if ep is not None:
                eliminated_info = {
                    "username": ep["username"],
                    "role": ep["role"],
                    "user_id": ep["user_id"],
                }

            history.append(
                {
                    "round": i + 1,
                    "votes": vote_entries,
                    "eliminated": eliminated_info,
                    "mr_white_guess": turn.get("mr_white_guess"),
                }
            )

        return history
