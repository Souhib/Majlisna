import random
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.game import GameController
from ipg.api.controllers.game_lock import cleanup_game_lock, get_game_lock
from ipg.api.controllers.room import RoomController
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
        db_room = await self._room_controller.get_room_by_id(room_id)

        if db_room.active_game_id:
            raise BaseError(
                message=f"Room {room_id} already has an active game",
                frontend_message="A game is already in progress.",
                status_code=400,
            )

        # Get connected players from RoomUserLink
        links = (
            await self.session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == db_room.id).where(RoomUserLink.connected == True)  # noqa: E712
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
        if num_players == 3:
            num_mr_white = 0
            num_undercover = 1
            num_civilians = 2
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

        live_state = {
            "civilian_word": civilian_word.word,
            "undercover_word": undercover_word.word,
            "players": players,
            "eliminated_players": [],
            "turns": [first_turn],
        }

        db_game.live_state = live_state
        db_game.game_status = GameStatus.IN_PROGRESS
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
        async with get_game_lock(str(game_id)):
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
        async with get_game_lock(str(game_id)):
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

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return {
            "game_id": str(game_id),
            "all_described": all_done,
            "word": word,
        }

    async def submit_vote(self, game_id: UUID, user_id: UUID, voted_for: UUID) -> dict:
        """Submit a vote for a player."""
        async with get_game_lock(str(game_id)):
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
                    cleanup_game_lock(str(game_id))
                else:
                    result["winner"] = None

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return result

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

    async def get_state(self, game_id: UUID, user_id: UUID, sid: str | None = None) -> dict:
        """Get full game state for a player. Used for polling and initial page load."""
        game = await self._get_game(game_id)
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        if not player:
            raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game_id))

        # Update heartbeat
        link = (
            await self.session.exec(
                select(RoomUserLink).where(RoomUserLink.room_id == game.room_id).where(RoomUserLink.user_id == user_id)
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
        turn_state = self._build_turn_state(state, str(user_id))
        winner = self._get_winner_label(state)
        is_host = await self._check_is_host(game.room_id, user_id)

        return {
            "game_id": str(game.id),
            "room_id": str(game.room_id),
            "is_host": is_host,
            "my_role": player["role"],
            "my_word": my_word,
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
            **turn_state,
        }

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

    def _get_winner_label(self, state: dict) -> str | None:
        """Get the winner label string, or None if game is still in progress."""
        winner = self._get_winning_team(state)
        if winner == UndercoverRole.CIVILIAN.value:
            return "civilians"
        if winner == UndercoverRole.UNDERCOVER.value:
            return "undercovers"
        return None

    async def _check_is_host(self, room_id: UUID, user_id: UUID) -> bool:
        """Check if the user is the host of the room."""
        room = (await self.session.exec(select(Room).where(Room.id == room_id))).first()
        if room:
            return room.owner_id == user_id
        return False
