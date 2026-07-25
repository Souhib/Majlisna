import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DEFAULT_DESCRIPTION_TIMER_SECONDS,
    DEFAULT_VOTING_TIMER_SECONDS,
    MAX_PLAYERS_UNDERCOVER,
    MIN_PLAYERS_FOR_GAME,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
    UNDERCOVER_MR_WHITE_COUNT_LARGE,
    UNDERCOVER_MR_WHITE_COUNT_MEDIUM,
    UNDERCOVER_MR_WHITE_COUNT_SMALL,
    UNDERCOVER_MR_WHITE_THRESHOLD_MEDIUM,
    UNDERCOVER_MR_WHITE_THRESHOLD_SMALL,
    UNDERCOVER_WORD_MAX_LENGTH,
)
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.game_end_stats import record_game_end, undercover_winners
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.controllers.undercover import UndercoverController
from majlisna.api.models.error import (
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
)
from majlisna.api.models.event import EventCreate
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.table import Room
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.common import GameStartResponse, HintRecordResponse, TimerExpiredResponse
from majlisna.api.schemas.error import BaseError
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
from majlisna.api.utils.rng import rng


class UndercoverGameController(BaseGameController):
    """REST controller for Undercover game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses asyncio.Lock per game_id for concurrency control.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._undercover_controller = UndercoverController(session)

    @staticmethod
    def _compute_roles(num_players: int, mr_white_enabled: bool) -> list[str]:
        """Compute role distribution for the given number of players."""
        if num_players == 3:
            num_mr_white = 0
            num_undercover = 1
            num_civilians = 2
        elif not mr_white_enabled:
            num_mr_white = 0
            num_undercover = max(1, num_players // 4)
            num_civilians = num_players - num_undercover
        else:
            if num_players < UNDERCOVER_MR_WHITE_THRESHOLD_SMALL:
                num_mr_white = UNDERCOVER_MR_WHITE_COUNT_SMALL
            elif num_players <= UNDERCOVER_MR_WHITE_THRESHOLD_MEDIUM:
                num_mr_white = UNDERCOVER_MR_WHITE_COUNT_MEDIUM
            else:
                num_mr_white = UNDERCOVER_MR_WHITE_COUNT_LARGE
            num_undercover = max(2, num_players // 4)
            num_civilians = num_players - num_mr_white - num_undercover
            while num_civilians < 1 and num_undercover > 1:
                num_undercover -= 1
                num_civilians += 1
            while num_civilians < 1 and num_mr_white > 0:
                num_mr_white -= 1
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
            mr_white_enabled = room_settings.get("enable_mr_white", True) and num_players >= 4
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
                raise BaseError(
                    message=f"Game {game_id} does not belong to room {room_id}",
                    frontend_message="This game does not belong to this room.",
                    status_code=400,
                )
            room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
            if room:
                self._require_room_host(room, user_id)
            state = game.live_state

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
            state = game.live_state
            current_turn = state["turns"][-1]

            if current_turn["phase"] != "describing":
                raise BaseError(
                    message="Not in description phase.",
                    frontend_message="Not in description phase.",
                    status_code=400,
                )

            if current_turn["current_describer_index"] >= len(current_turn["description_order"]):
                raise BaseError(
                    message="All descriptions already submitted.",
                    frontend_message="All descriptions already submitted.",
                    status_code=400,
                )

            if current_turn["description_order"][current_turn["current_describer_index"]] != str(user_id):
                raise BaseError(
                    message="Not your turn to describe.",
                    frontend_message="Not your turn to describe.",
                    status_code=400,
                )

            word = word.strip()
            if not word or " " in word or len(word) > UNDERCOVER_WORD_MAX_LENGTH:
                raise BaseError(
                    message=f"Word must be a single word (no spaces), max {UNDERCOVER_WORD_MAX_LENGTH} characters.",
                    frontend_message=f"Word must be a single word (no spaces), max {UNDERCOVER_WORD_MAX_LENGTH} characters.",
                    status_code=400,
                )

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
            state = game.live_state

            if state["turns"] and state["turns"][-1]["phase"] != "voting":
                raise BaseError(
                    message="Descriptions are not complete yet.",
                    frontend_message="Descriptions are not complete yet.",
                    status_code=400,
                )

            player_to_vote = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
            if not player_to_vote:
                raise BaseError(message="Player not in game.", frontend_message="Player not in game.", status_code=400)
            if not player_to_vote["is_alive"]:
                raise CantVoteBecauseYouDeadError(user_id=user_id)

            voted_player = next((p for p in state["players"] if p["user_id"] == str(voted_for)), None)
            if not voted_player:
                raise BaseError(
                    message="Voted player not in game.", frontend_message="Voted player not in game.", status_code=400
                )
            if not voted_player["is_alive"]:
                raise CantVoteForDeadPersonError(user_id=user_id, dead_user_id=voted_for)
            if str(user_id) == str(voted_for):
                raise CantVoteForYourselfError(user_id=user_id)

            if str(user_id) in state["turns"][-1]["votes"]:
                raise BaseError(
                    message="You have already voted this round.",
                    frontend_message="You have already voted this round.",
                    status_code=400,
                )

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
                    state["turns"][-1]["phase"] = "mr_white_guessing"
                    state["mr_white_guesser"] = eliminated_player["user_id"]
                    state["timer_started_at"] = datetime.now(UTC).isoformat()
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

    @staticmethod
    def _normalize_guess(word: str) -> str:
        """Normalize a guess word for comparison: strip, lowercase, remove Arabic diacritics."""
        text = word.strip().lower()
        # Remove Arabic diacritics (tashkeel) — unicode category Mn (nonspacing marks)
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

    async def submit_mr_white_guess(self, game_id: UUID, user_id: UUID, guess_word: str) -> MrWhiteGuessResponse:
        """Mr. White submits a guess for the civilian word after being eliminated."""
        logger.info("Mr. White guess: game={} user={}", game_id, user_id)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = game.live_state
            current_turn = state["turns"][-1]

            if current_turn["phase"] != "mr_white_guessing":
                raise BaseError(
                    message="Not in Mr. White guessing phase.",
                    frontend_message="Not in Mr. White guessing phase.",
                    status_code=400,
                )

            if state.get("mr_white_guesser") != str(user_id):
                raise BaseError(
                    message="Only the eliminated Mr. White can guess.",
                    frontend_message="Only the eliminated Mr. White can guess.",
                    status_code=403,
                )

            normalized_guess = self._normalize_guess(guess_word)
            normalized_civilian_word = self._normalize_guess(state["civilian_word"])
            correct = normalized_guess == normalized_civilian_word

            state.pop("mr_white_guesser", None)

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

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> TimerExpiredResponse:
        """Handle timer expiration — auto-skip description, auto-random-vote, or mr_white guess timeout."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = game.live_state

            # Any player may trigger timer expiration (consistent with the other
            # games); the server only acts if the timer has actually elapsed, so
            # a game can still advance when the host is absent.
            if not self._is_timer_actually_expired(state):
                return TimerExpiredResponse(game_id=str(game_id), action="timer_not_expired")

            current_turn = state["turns"][-1]
            action = "none"

            if current_turn["phase"] == "describing":
                # Auto-skip remaining describers by setting index to end
                current_turn["current_describer_index"] = len(current_turn["description_order"])
                current_turn["phase"] = "voting"
                state["timer_started_at"] = datetime.now(UTC).isoformat()
                action = "skip_to_voting"

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
                    return TimerExpiredResponse(game_id=str(game_id), action="round_already_resolved")

                self._auto_fill_missing_votes(state)
                # Now eliminate
                eliminated_player, _ = self._eliminate_player_based_on_votes(state)
                action = "auto_vote"

                # If Mr. White was eliminated, enter guessing phase
                if eliminated_player["role"] == UndercoverRole.MR_WHITE.value:
                    current_turn["phase"] = "mr_white_guessing"
                    state["mr_white_guesser"] = eliminated_player["user_id"]
                    state["timer_started_at"] = datetime.now(UTC).isoformat()
                else:
                    winner = self._get_winning_team(state)
                    if winner:
                        await self._finish_game(game, state, winner)

            elif current_turn["phase"] == "mr_white_guessing":
                # Timer expired during Mr. White guessing — treat as wrong guess
                state.pop("mr_white_guesser", None)
                action = "mr_white_guess_timeout"
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
        """Eliminate the alive player with the most votes. Returns (eliminated_player, vote_count).

        Marks the turn ``resolved`` so the round can never be counted twice — see
        ``handle_timer_expired``.

        Candidates are restricted to ALIVE players. Seeding the tally with every
        player (dead included) meant a dead player could win the tally and be
        "eliminated" a second time: with one alive player left,
        ``_auto_fill_missing_votes`` cannot record a vote (no one to vote for), so
        every count was 0 and the tie-break picked at random from the whole
        roster, corpses included.
        """
        current_turn = state["turns"][-1]
        votes = current_turn["votes"]
        vote_counts: dict[str, int] = {p["user_id"]: 0 for p in state["players"] if p["is_alive"]}
        if not vote_counts:
            raise BaseError(
                message="No alive players left to eliminate.",
                frontend_message="This game is already over.",
                status_code=400,
            )
        for voted_id in votes.values():
            if voted_id in vote_counts:
                vote_counts[voted_id] += 1

        max_votes = max(vote_counts.values())
        players_with_max_votes = [pid for pid, count in vote_counts.items() if count == max_votes]

        if len(players_with_max_votes) > 1:
            # Mayor breaks tie
            mayor = next((p for p in state["players"] if p.get("is_mayor")), None)
            if mayor and mayor.get("is_alive"):
                mayor_vote = votes.get(mayor["user_id"])
                player_with_most_vote = (
                    mayor_vote if mayor_vote in players_with_max_votes else rng.choice(players_with_max_votes)
                )
            else:
                player_with_most_vote = rng.choice(players_with_max_votes)
        else:
            player_with_most_vote = players_with_max_votes[0]

        eliminated_player = next(p for p in state["players"] if p["user_id"] == player_with_most_vote)
        eliminated_player["is_alive"] = False
        state["eliminated_players"].append(
            {
                "user_id": eliminated_player["user_id"],
                "username": eliminated_player["username"],
                "role": eliminated_player["role"],
                # Which turn eliminated them. Vote history and the post-game summary
                # used to pair eliminated_players[i] with turns[i] by POSITION, an
                # implicit invariant that silently produced a wrong history the
                # moment anything appended out of step. Readers prefer this field
                # and fall back to the index for rows written before it existed.
                "round": len(state["turns"]),
            }
        )
        # This round's votes have now produced their elimination and must never
        # produce another one. See handle_timer_expired.
        current_turn["resolved"] = True

        return eliminated_player, vote_counts[player_with_most_vote]

    def _get_winning_team(self, state: dict) -> str | None:
        """Determine if a team has won based on alive player counts. Returns role value or None."""
        players = state["players"]
        num_alive_undercover = sum(1 for p in players if p["role"] == UndercoverRole.UNDERCOVER.value and p["is_alive"])
        num_alive_civilian = sum(1 for p in players if p["role"] == UndercoverRole.CIVILIAN.value and p["is_alive"])
        num_alive_mr_white = sum(1 for p in players if p["role"] == UndercoverRole.MR_WHITE.value and p["is_alive"])

        if num_alive_undercover == 0 and num_alive_mr_white == 0:
            return UndercoverRole.CIVILIAN.value
        if num_alive_civilian == 0:
            return UndercoverRole.UNDERCOVER.value
        if num_alive_undercover + num_alive_mr_white >= num_alive_civilian:
            return UndercoverRole.UNDERCOVER.value
        return None

    async def get_state(
        self, game_id: UUID, user_id: UUID, sid: str | None = None, lang: str = "en", update_heartbeat: bool = True
    ) -> UndercoverGameState:
        """Get full game state for a player or spectator. Used for polling and initial page load."""
        game = await self._get_game(game_id)
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        is_spectator = await self._check_spectator(game, user_id, player)

        # Update heartbeat (throttled: skip if last_seen_at is recent to reduce write contention)
        if update_heartbeat:
            await self._update_heartbeat_throttled(game.room_id, user_id)

        winner = self._get_winner_label(state)
        is_host = await self._check_is_host(game.room_id, user_id)
        vote_history = self._build_vote_history(state)

        if is_spectator:
            # Spectators see descriptions/votes but NOT roles/words until game ends
            word_explanations = None
            my_role = "spectator"
            my_word = ""
            my_word_hint = None
            if winner:
                word_explanations = WordExplanations(
                    civilian_word=state["civilian_word"],
                    civilian_word_hint=self._resolve_multilingual(state.get("civilian_word_hint"), lang),
                    undercover_word=state["undercover_word"],
                    undercover_word_hint=self._resolve_multilingual(state.get("undercover_word_hint"), lang),
                )
            turn_state = self._build_turn_state(state, "")
        else:
            my_role = player["role"]
            my_word = self._get_player_word(player, state)
            my_word_hint = self._get_player_word_hint(player, state, lang)
            turn_state = self._build_turn_state(state, str(user_id))
            word_explanations = None
            if winner:
                word_explanations = WordExplanations(
                    civilian_word=state["civilian_word"],
                    civilian_word_hint=self._resolve_multilingual(state.get("civilian_word_hint"), lang),
                    undercover_word=state["undercover_word"],
                    undercover_word_hint=self._resolve_multilingual(state.get("undercover_word_hint"), lang),
                )

        return UndercoverGameState(
            game_id=str(game.id),
            room_id=str(game.room_id),
            is_host=is_host,
            is_spectator=is_spectator,
            my_role=my_role,
            my_word=my_word,
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
            **turn_state,
        )

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
            }
        current_turn = state["turns"][-1]
        return {
            "votes": current_turn["votes"],
            "has_voted": user_id in current_turn["votes"],
            "turn_phase": current_turn["phase"],
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

        for i, turn in enumerate(state["turns"]):
            votes = turn.get("votes", {})
            if not votes:
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
                }
            )

        return history
