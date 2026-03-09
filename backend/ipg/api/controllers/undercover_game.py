import random
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import (
    DEFAULT_DESCRIPTION_TIMER_SECONDS,
    DEFAULT_VOTING_TIMER_SECONDS,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
)
from ipg.api.controllers.achievement import AchievementController
from ipg.api.controllers.game import GameController
from ipg.api.controllers.game_lock import get_game_lock
from ipg.api.controllers.room import RoomController
from ipg.api.controllers.stats import StatsController
from ipg.api.controllers.undercover import UndercoverController
from ipg.api.models.error import (
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
    GameNotFoundError,
    PlayerRemovedFromGameError,
    RoomNotFoundError,
)
from ipg.api.models.event import EventCreate
from ipg.api.models.game import GameCreate, GameStatus, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room, User
from ipg.api.models.undercover import UndercoverRole
from ipg.api.schemas.error import BaseError


class UndercoverGameController:
    """REST controller for Undercover game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses asyncio.Lock per game_id for concurrency control.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._room_controller = RoomController(session)
        self._game_controller = GameController(session)
        self._undercover_controller = UndercoverController(session)
        self._stats_controller = StatsController(session)
        self._achievement_controller = AchievementController(session)

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
            num_mr_white = 1 if num_players < 10 else (2 if num_players <= 15 else 3)
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
        random.shuffle(roles)
        return roles

    async def _get_civilian_and_undercover_words(self) -> tuple:
        """Get the civilian and undercover words for the game."""
        term_pair = await self._undercover_controller.get_random_term_pair()
        civilian_word_id = term_pair.word1_id
        undercover_word_id = term_pair.word2_id
        if random.choice([True, False]):
            civilian_word_id, undercover_word_id = term_pair.word2_id, term_pair.word1_id
        civilian_word = await self._undercover_controller.get_word_by_id(civilian_word_id)
        undercover_word = await self._undercover_controller.get_word_by_id(undercover_word_id)
        return civilian_word, undercover_word

    def _generate_description_order(self, players: list[dict]) -> list[str]:
        """Generate a randomized description order for alive players.

        Mr. White is never placed first.
        """
        alive_ids = [p["user_id"] for p in players if p["is_alive"]]
        random.shuffle(alive_ids)

        if len(alive_ids) > 1:
            mr_white_ids = {
                p["user_id"] for p in players if p["role"] == UndercoverRole.MR_WHITE.value and p["is_alive"]
            }
            if alive_ids[0] in mr_white_ids:
                swap_candidates = [i for i in range(1, len(alive_ids)) if alive_ids[i] not in mr_white_ids]
                if swap_candidates:
                    swap_idx = random.choice(swap_candidates)
                    alive_ids[0], alive_ids[swap_idx] = alive_ids[swap_idx], alive_ids[0]

        return alive_ids

    async def create_and_start(self, room_id: UUID, user_id: UUID) -> dict:
        """Start a new Undercover game in the given room."""
        async with get_game_lock(f"room:{room_id}", self.session):
            db_room = await self._room_controller.get_room_by_id(room_id)

            if db_room.active_game_id:
                raise BaseError(
                    message=f"Room {room_id} already has an active game",
                    frontend_message="A game is already in progress.",
                    status_code=400,
                )

            # Get connected non-spectator players from RoomUserLink
            links = (
                await self.session.exec(
                    select(RoomUserLink).where(
                        RoomUserLink.room_id == db_room.id,
                        RoomUserLink.connected == True,  # noqa: E712
                        RoomUserLink.is_spectator == False,  # noqa: E712
                    )
                )
            ).all()

            if not links:
                raise RoomNotFoundError(room_id=room_id)

            # Get user info for each linked player
            player_users = []
            for link in links:
                u = (await self.session.exec(select(User).where(User.id == link.user_id))).first()
                if u:
                    player_users.append(u)

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
            players[random.randint(0, len(players) - 1)]["is_mayor"] = True

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
                )
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

            # Create turn record
            turn = await self._game_controller.create_turn(game_id=db_game.id)
            await self._game_controller.create_turn_event(
                game_id=db_game.id,
                event_create=EventCreate(
                    name="start_turn",
                    data={"game_id": str(db_game.id), "turn_id": str(turn.id), "message": "Turn started."},
                    user_id=db_room.owner_id,
                ),
            )

            await self.session.commit()

            return {
                "game_id": str(db_game.id),
                "room_id": str(db_room.id),
            }

    async def start_next_round(self, game_id: UUID, room_id: UUID, user_id: UUID) -> dict:
        """Start a new round (turn) in an existing game."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
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

            # Create DB turn record
            turn = await self._game_controller.create_turn(game_id=game.id)
            await self._game_controller.create_turn_event(
                game_id=game.id,
                event_create=EventCreate(
                    name="start_turn",
                    data={"game_id": str(game.id), "turn_id": str(turn.id), "message": "Turn started."},
                    user_id=user_id,
                ),
            )

            await self.session.commit()

            description_order_with_names = []
            for uid in description_order:
                p = next((p for p in state["players"] if p["user_id"] == uid), None)
                if p:
                    description_order_with_names.append({"user_id": uid, "username": p["username"]})

        return {
            "game_id": str(game_id),
            "turn_number": len(state["turns"]),
            "description_order": description_order_with_names,
        }

    async def submit_description(self, game_id: UUID, user_id: UUID, word: str) -> dict:
        """Submit a single-word description for the current turn."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
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
            if not word or " " in word or len(word) > 50:
                raise BaseError(
                    message="Word must be a single word (no spaces), max 50 characters.",
                    frontend_message="Word must be a single word (no spaces), max 50 characters.",
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

        return {
            "game_id": str(game_id),
            "all_described": all_done,
            "word": word,
        }

    async def submit_vote(self, game_id: UUID, user_id: UUID, voted_for: UUID) -> dict:  # noqa: C901
        """Submit a vote for a player."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
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

            result: dict = {"game_id": str(game_id), "all_voted": all_voted}

            if all_voted:
                eliminated_player, number_of_votes = self._eliminate_player_based_on_votes(state)
                winner = self._get_winning_team(state)

                result["eliminated_player"] = eliminated_player["user_id"]
                result["eliminated_player_role"] = eliminated_player["role"]
                result["eliminated_player_username"] = eliminated_player["username"]
                result["number_of_votes"] = number_of_votes

                if winner:
                    winner_label = "civilians" if winner == UndercoverRole.CIVILIAN.value else "undercovers"
                    result["winner"] = winner_label
                    game.game_status = GameStatus.FINISHED
                    game.end_time = datetime.now()
                    # Clear active game on room
                    room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
                    if room:
                        room.active_game_id = None
                        self.session.add(room)
                    # Process stats and achievements
                    newly_unlocked = await self._process_game_end_stats(state, winner_label)
                    if newly_unlocked:
                        state["newly_unlocked_achievements"] = newly_unlocked
                else:
                    result["winner"] = None

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return result

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
                    current_turn["votes"][p["user_id"]] = random.choice(candidates)

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

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> dict:
        """Handle timer expiration — auto-skip description or auto-random-vote."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            # Verify caller is host
            is_host = await self._check_is_host(game.room_id, user_id)
            if not is_host:
                raise BaseError(
                    message="Only the host can trigger timer expiration.",
                    frontend_message="Only the host can trigger timer expiration.",
                    status_code=403,
                )

            if not self._is_timer_actually_expired(state):
                return {"game_id": str(game_id), "action": "timer_not_expired"}

            current_turn = state["turns"][-1]
            action = "none"

            if current_turn["phase"] == "describing":
                # Auto-skip remaining describers by setting index to end
                current_turn["current_describer_index"] = len(current_turn["description_order"])
                current_turn["phase"] = "voting"
                state["timer_started_at"] = datetime.now(UTC).isoformat()
                action = "skip_to_voting"

            elif current_turn["phase"] == "voting":
                self._auto_fill_missing_votes(state)
                # Now eliminate
                self._eliminate_player_based_on_votes(state)
                winner = self._get_winning_team(state)
                action = "auto_vote"

                if winner:
                    winner_label = "civilians" if winner == UndercoverRole.CIVILIAN.value else "undercovers"
                    game.game_status = GameStatus.FINISHED
                    game.end_time = datetime.now()
                    room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
                    if room:
                        room.active_game_id = None
                        self.session.add(room)
                    # Process stats and achievements
                    newly_unlocked = await self._process_game_end_stats(state, winner_label)
                    if newly_unlocked:
                        state["newly_unlocked_achievements"] = newly_unlocked

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return {"game_id": str(game_id), "action": action}

    def _eliminate_player_based_on_votes(self, state: dict) -> tuple[dict, int]:
        """Eliminate the player with the most votes. Returns (eliminated_player, vote_count)."""
        votes = state["turns"][-1]["votes"]
        vote_counts: dict[str, int] = {}
        for p in state["players"]:
            vote_counts[p["user_id"]] = 0
        for voted_id in votes.values():
            if voted_id in vote_counts:
                vote_counts[voted_id] += 1

        max_votes = max(vote_counts.values())
        players_with_max_votes = [pid for pid, count in vote_counts.items() if count == max_votes]

        if len(players_with_max_votes) > 1:
            # Mayor breaks tie
            mayor = next((p for p in state["players"] if p.get("is_mayor")), None)
            mayor_vote = votes.get(mayor["user_id"]) if mayor else None
            player_with_most_vote = mayor_vote if mayor_vote in players_with_max_votes else players_with_max_votes[0]
        else:
            player_with_most_vote = players_with_max_votes[0]

        eliminated_player = next(p for p in state["players"] if p["user_id"] == player_with_most_vote)
        eliminated_player["is_alive"] = False
        state["eliminated_players"].append(
            {
                "user_id": eliminated_player["user_id"],
                "username": eliminated_player["username"],
                "role": eliminated_player["role"],
            }
        )

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
    ) -> dict:
        """Get full game state for a player. Used for polling and initial page load."""
        game = await self._get_game(game_id)
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        if not player:
            raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game_id))

        # Update heartbeat
        if update_heartbeat:
            link = (
                await self.session.exec(
                    select(RoomUserLink)
                    .where(RoomUserLink.room_id == game.room_id)
                    .where(RoomUserLink.user_id == user_id)
                )
            ).first()
            if link:
                link.last_seen_at = datetime.now()
                link.connected = True
                if link.disconnected_at is not None:
                    link.disconnected_at = None
                self.session.add(link)
                await self.session.commit()

        my_word = self._get_player_word(player, state)
        my_word_hint = self._get_player_word_hint(player, state, lang)
        turn_state = self._build_turn_state(state, str(user_id))
        winner = self._get_winner_label(state)
        is_host = await self._check_is_host(game.room_id, user_id)
        vote_history = self._build_vote_history(state)

        result = {
            "game_id": str(game.id),
            "room_id": str(game.room_id),
            "is_host": is_host,
            "my_role": player["role"],
            "my_word": my_word,
            "my_word_hint": my_word_hint,
            "is_alive": player["is_alive"],
            "players": [
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "is_alive": p["is_alive"],
                    "is_mayor": p.get("is_mayor", False),
                }
                for p in state["players"]
            ],
            "eliminated_players": [
                {"user_id": p["user_id"], "username": p["username"], "role": p["role"]}
                for p in state["eliminated_players"]
            ],
            "turn_number": len(state["turns"]),
            "winner": winner,
            "vote_history": vote_history,
            "timer_config": state.get("timer_config"),
            "timer_started_at": state.get("timer_started_at"),
            **turn_state,
        }

        # When game is over, include word explanations for educational reveal
        if winner:
            result["word_explanations"] = {
                "civilian_word": state["civilian_word"],
                "civilian_word_hint": self._resolve_hint(state.get("civilian_word_hint"), lang),
                "undercover_word": state["undercover_word"],
                "undercover_word_hint": self._resolve_hint(state.get("undercover_word_hint"), lang),
            }

        return result

    async def _get_game(self, game_id: UUID) -> Game:
        """Fetch a Game from PostgreSQL or raise GameNotFoundError."""
        game = (await self.session.exec(select(Game).where(Game.id == game_id))).first()
        if not game or not game.live_state:
            raise GameNotFoundError(game_id=game_id)
        return game

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
            return self._resolve_hint(state.get("undercover_word_hint"), lang)
        return self._resolve_hint(state.get("civilian_word_hint"), lang)

    @staticmethod
    def _resolve_hint(hint_dict: dict | None, lang: str) -> str | None:
        """Resolve a multilingual hint dict to a single string for the given language."""
        if not hint_dict:
            return None
        return hint_dict.get(lang) or hint_dict.get("en") or next(iter(hint_dict.values()), None)

    async def record_hint_view(self, game_id: UUID, user_id: UUID, word: str) -> dict:
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

        return {"game_id": str(game_id), "recorded": True}

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
        """Update stats and check achievements for all players after game ends.

        Returns a list of {user_id, achievements: [{code, name, icon, tier}]} for newly unlocked.
        """
        hint_usage = state.get("hint_usage", {})
        newly_unlocked_all: list[dict] = []
        for player in state["players"]:
            user_id = UUID(player["user_id"])
            role = player.get("role", "civilian")
            won = (winner_label == "civilians" and role == "civilian") or (
                winner_label == "undercovers" and role in ("undercover", "mr_white")
            )
            try:
                stats = await self._stats_controller.update_stats_after_game(
                    user_id=user_id, game_type="undercover", won=won, role=role
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
            except Exception:
                logger.exception("Failed to update stats/achievements for user {user_id}", user_id=user_id)
        return newly_unlocked_all

    def _get_winner_label(self, state: dict) -> str | None:
        """Get the winner label string, or None if game is still in progress."""
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
            if i < len(eliminated_list):
                ep = eliminated_list[i]
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

    async def _check_is_host(self, room_id: UUID, user_id: UUID) -> bool:
        """Check if the user is the host of the room."""
        room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
        if room:
            return room.owner_id == user_id
        return False
