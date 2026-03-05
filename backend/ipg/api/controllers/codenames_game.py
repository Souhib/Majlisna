import random
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import CODENAMES_BOARD_SIZE
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
from ipg.api.controllers.game import GameController
from ipg.api.controllers.game_lock import cleanup_game_lock, get_game_lock
from ipg.api.controllers.room import RoomController
from ipg.api.models.error import (
    CardAlreadyRevealedError,
    ClueWordIsOnBoardError,
    GameNotFoundError,
    GameNotInProgressError,
    InvalidCardIndexError,
    NoClueGivenError,
    NotEnoughPlayersError,
    NotOperativeError,
    NotSpymasterError,
    NotYourTurnError,
)
from ipg.api.models.game import GameCreate, GameStatus, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room, User
from ipg.api.schemas.error import BaseError


class CodenamesGameController:
    """REST controller for Codenames game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses asyncio.Lock per game_id for concurrency control.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._room_controller = RoomController(session)
        self._game_controller = GameController(session)
        self._codenames_controller = CodenamesController(session)

    async def create_and_start(
        self,
        room_id: UUID,
        user_id: UUID,
        word_pack_ids: list[UUID] | None = None,
    ) -> dict:
        """Start a new Codenames game in the given room."""
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

        if len(links) < 4:
            raise NotEnoughPlayersError(player_count=len(links))

        # Get user info for each linked player
        room_user_dicts = []
        for link in links:
            u = (await self.session.exec(select(User).where(User.id == link.user_id))).first()
            if u:
                room_user_dicts.append({"user_id": str(u.id), "username": u.username})

        if len(room_user_dicts) < 4:
            raise NotEnoughPlayersError(player_count=len(room_user_dicts))

        random_words = await self._codenames_controller.get_random_words(
            count=CODENAMES_BOARD_SIZE,
            pack_ids=word_pack_ids,
        )
        word_strings = [w.word for w in random_words]

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
            },
            "red_remaining": red_remaining,
            "blue_remaining": blue_remaining,
            "status": CodenamesGameStatus.IN_PROGRESS.value,
            "winner": None,
        }

        db_game.live_state = live_state
        db_game.game_status = GameStatus.IN_PROGRESS
        self.session.add(db_game)

        # Set active game on room
        db_room.active_game_id = db_game.id
        self.session.add(db_room)
        await self.session.commit()

        return {
            "game_id": str(db_game.id),
            "room_id": str(db_room.id),
        }

    async def give_clue(self, game_id: UUID, user_id: UUID, clue_word: str, clue_number: int) -> dict:
        """Process a spymaster giving a clue."""
        async with get_game_lock(str(game_id)):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["status"] != CodenamesGameStatus.IN_PROGRESS.value:
                raise GameNotInProgressError(game_id=str(game_id))

            player = get_player_from_game(state["players"], str(user_id))

            if player["team"] != state["current_team"]:
                raise NotYourTurnError(user_id=str(user_id))
            if player["role"] != CodenamesRole.SPYMASTER.value:
                raise NotSpymasterError(user_id=str(user_id))

            board_words_lower = [card["word"].lower() for card in state["board"]]
            if clue_word.lower() in board_words_lower:
                raise ClueWordIsOnBoardError(clue_word=clue_word)

            state["current_turn"] = {
                "team": state["current_team"],
                "clue_word": clue_word,
                "clue_number": clue_number,
                "guesses_made": 0,
                "max_guesses": clue_number + 1,
            }

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return {
            "game_id": str(game_id),
            "clue_word": clue_word,
            "clue_number": clue_number,
        }

    async def guess_card(self, game_id: UUID, user_id: UUID, card_index: int) -> dict:
        """Process an operative guessing a card."""
        async with get_game_lock(str(game_id)):
            game = await self._get_game(game_id)
            state = game.live_state

            self._validate_guess(state, str(user_id), card_index)

            card = state["board"][card_index]
            card["revealed"] = True
            state["current_turn"]["guesses_made"] += 1

            result = self._resolve_card(state, card)

            if (
                result in ("opponent_card", "neutral", "max_guesses")
                and state["status"] == CodenamesGameStatus.IN_PROGRESS.value
            ):
                self._switch_turn(state)

            if state["status"] == CodenamesGameStatus.FINISHED.value:
                game.game_status = GameStatus.FINISHED
                game.end_time = datetime.now()
                # Clear active game on room
                room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
                if room:
                    room.active_game_id = None
                    self.session.add(room)
                cleanup_game_lock(str(game_id))

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return {
            "game_id": str(game_id),
            "card_index": card_index,
            "card_type": card["card_type"],
            "result": result,
        }

    async def end_turn(self, game_id: UUID, user_id: UUID) -> dict:
        """Allow an operative to voluntarily end their turn."""
        async with get_game_lock(str(game_id)):
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

        return {
            "game_id": str(game_id),
            "current_team": state["current_team"],
        }

    async def get_board(self, game_id: UUID, user_id: UUID, sid: str | None = None) -> dict:
        """Get the current board state for a player. Used for polling."""
        game = await self._get_game(game_id)
        state = game.live_state

        player = get_player_from_game(state["players"], str(user_id))
        board_view = get_board_for_player(state["board"], player)

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

        return {
            "game_id": str(game.id),
            "room_id": str(game.room_id),
            "team": player["team"],
            "role": player["role"],
            "board": board_view,
            "current_team": state["current_team"],
            "red_remaining": state["red_remaining"],
            "blue_remaining": state["blue_remaining"],
            "status": state["status"],
            "current_turn": state["current_turn"],
            "winner": state["winner"],
            "players": [
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "team": p["team"],
                    "role": p["role"],
                }
                for p in state["players"]
            ],
        }

    async def _get_game(self, game_id: UUID) -> Game:
        """Fetch a Game from PostgreSQL or raise GameNotFoundError."""
        game = (await self.session.exec(select(Game).where(Game.id == game_id))).first()
        if not game or not game.live_state:
            raise GameNotFoundError(game_id=game_id)
        return game

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
        }
