"""Tests for the CodenamesGameController."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.controllers.codenames_helpers import (
    CodenamesCardType,
    CodenamesGameStatus,
    CodenamesRole,
    CodenamesTeam,
)
from ipg.api.models.game import GameStatus
from ipg.api.models.table import Game, Room
from ipg.api.schemas.error import (
    CardAlreadyRevealedError,
    ClueWordIsOnBoardError,
    GameNotInProgressError,
    InvalidCardIndexError,
    NoClueGivenError,
    NotEnoughPlayersError,
    NotOperativeError,
    NotSpymasterError,
    NotYourTurnError,
)

# ─── Helpers ──────────────────────────────────────────────────


async def _start_game(controller: CodenamesGameController, room_id, user_id):
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


def _find_player(state, role_value, team_value):
    """Find a player with given role and team."""
    return next(
        (p for p in state["players"] if p["role"] == role_value and p["team"] == team_value),
        None,
    )


def _find_spymaster(state, team):
    return _find_player(state, CodenamesRole.SPYMASTER.value, team)


def _find_operative(state, team):
    return _find_player(state, CodenamesRole.OPERATIVE.value, team)


def _find_card_of_type(board, card_type, exclude_revealed=True):
    """Find the index of a card of the given type."""
    for i, card in enumerate(board):
        if card["card_type"] == card_type and (not exclude_revealed or not card["revealed"]):
            return i
    return None


# ─── Happy Path Tests ─────────────────────────────────────────


class TestCreateAndStart:
    @pytest.mark.asyncio
    async def test_creates_25_card_board(self, codenames_game_controller, setup_codenames_game, session):
        """Board has exactly 25 cards."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

        game = await _get_game(session, result["game_id"])
        assert len(game.live_state["board"]) == 25

    @pytest.mark.asyncio
    async def test_teams_assigned_balanced(self, codenames_game_controller, setup_codenames_game, session):
        """At least 2 per team, 1 spymaster each."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

        game = await _get_game(session, result["game_id"])
        players = game.live_state["players"]

        red_players = [p for p in players if p["team"] == CodenamesTeam.RED.value]
        blue_players = [p for p in players if p["team"] == CodenamesTeam.BLUE.value]

        assert len(red_players) >= 2
        assert len(blue_players) >= 2
        assert sum(1 for p in red_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1
        assert sum(1 for p in blue_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1

    @pytest.mark.asyncio
    async def test_not_enough_players(self, codenames_game_controller, setup_codenames_game, session):
        """Less than 4 players raises NotEnoughPlayersError."""
        setup = await setup_codenames_game(3)

        with pytest.raises(NotEnoughPlayersError):
            await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)


class TestGiveClue:
    @pytest.mark.asyncio
    async def test_valid_clue(self, codenames_game_controller, setup_codenames_game, session):
        """Clue stored in current_turn."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)

        clue_result = await codenames_game_controller.give_clue(
            UUID(result["game_id"]), UUID(spymaster["user_id"]), "testclue", 2
        )

        assert clue_result["clue_word"] == "testclue"
        assert clue_result["clue_number"] == 2

        game = await _get_game(session, result["game_id"])
        assert game.live_state["current_turn"]["clue_word"] == "testclue"
        assert game.live_state["current_turn"]["max_guesses"] == 3  # clue_number + 1

    @pytest.mark.asyncio
    async def test_not_spymaster(self, codenames_game_controller, setup_codenames_game, session):
        """Operative tries to give clue → NotSpymasterError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)

        with pytest.raises(NotSpymasterError):
            await codenames_game_controller.give_clue(
                UUID(result["game_id"]), UUID(operative["user_id"]), "testclue", 2
            )

    @pytest.mark.asyncio
    async def test_wrong_team(self, codenames_game_controller, setup_codenames_game, session):
        """Spymaster of wrong team → NotYourTurnError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        current_team = state["current_team"]
        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        wrong_spymaster = _find_spymaster(state, other_team)

        with pytest.raises(NotYourTurnError):
            await codenames_game_controller.give_clue(
                UUID(result["game_id"]), UUID(wrong_spymaster["user_id"]), "testclue", 2
            )

    @pytest.mark.asyncio
    async def test_clue_word_on_board(self, codenames_game_controller, setup_codenames_game, session):
        """Clue word that is on the board → ClueWordIsOnBoardError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)
        board_word = state["board"][0]["word"]

        with pytest.raises(ClueWordIsOnBoardError):
            await codenames_game_controller.give_clue(
                UUID(result["game_id"]), UUID(spymaster["user_id"]), board_word, 2
            )

    @pytest.mark.asyncio
    async def test_after_game_finished(self, codenames_game_controller, setup_codenames_game, session):
        """Clue after game finished → GameNotInProgressError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        # Finish the game manually
        state["status"] = CodenamesGameStatus.FINISHED.value
        state["winner"] = CodenamesTeam.RED.value
        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()

        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)

        with pytest.raises(GameNotInProgressError):
            await codenames_game_controller.give_clue(
                UUID(result["game_id"]), UUID(spymaster["user_id"]), "testclue", 2
            )


class TestGuessCard:
    async def _give_clue_first(self, controller, session, result):
        """Helper: give a clue so guessing is allowed."""
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)
        await controller.give_clue(UUID(result["game_id"]), UUID(spymaster["user_id"]), "testclue", 3)
        return await _get_game(session, result["game_id"])

    @pytest.mark.asyncio
    async def test_guess_correct_team_card(self, codenames_game_controller, setup_codenames_game, session):
        """Guessing own team's card: card revealed, remaining decremented."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)
        team_card_idx = _find_card_of_type(state["board"], current_team)

        remaining_key = f"{current_team}_remaining"
        before = state[remaining_key]

        guess_result = await codenames_game_controller.guess_card(
            UUID(result["game_id"]), UUID(operative["user_id"]), team_card_idx
        )

        assert guess_result["result"] == "correct"
        game = await _get_game(session, result["game_id"])
        assert game.live_state["board"][team_card_idx]["revealed"] is True
        assert game.live_state[remaining_key] == before - 1

    @pytest.mark.asyncio
    async def test_guess_continues_under_max(self, codenames_game_controller, setup_codenames_game, session):
        """Correct guess with guesses < max_guesses: result is 'correct', turn stays."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)
        team_card_idx = _find_card_of_type(state["board"], current_team)

        guess_result = await codenames_game_controller.guess_card(
            UUID(result["game_id"]), UUID(operative["user_id"]), team_card_idx
        )

        assert guess_result["result"] == "correct"
        game = await _get_game(session, result["game_id"])
        assert game.live_state["current_team"] == current_team  # same team

    @pytest.mark.asyncio
    async def test_guess_assassin_ends_game(self, codenames_game_controller, setup_codenames_game, session):
        """Guessing assassin: opponent wins, game finished."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)
        assassin_idx = _find_card_of_type(state["board"], CodenamesCardType.ASSASSIN.value)

        guess_result = await codenames_game_controller.guess_card(
            UUID(result["game_id"]), UUID(operative["user_id"]), assassin_idx
        )

        assert guess_result["result"] == "assassin"
        game = await _get_game(session, result["game_id"])
        assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
        assert game.game_status == GameStatus.FINISHED
        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        assert game.live_state["winner"] == other_team

    @pytest.mark.asyncio
    async def test_guess_opponent_card_ends_turn(self, codenames_game_controller, setup_codenames_game, session):
        """Guessing opponent's card: turn switches to other team."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        operative = _find_operative(state, current_team)
        opponent_card_idx = _find_card_of_type(state["board"], other_team)

        await codenames_game_controller.guess_card(
            UUID(result["game_id"]), UUID(operative["user_id"]), opponent_card_idx
        )

        game = await _get_game(session, result["game_id"])
        assert game.live_state["current_team"] == other_team

    @pytest.mark.asyncio
    async def test_guess_last_team_card_wins(self, codenames_game_controller, setup_codenames_game, session):
        """Guessing the last remaining team card: team wins."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        remaining_key = f"{current_team}_remaining"

        # Set remaining to 1 so next correct guess wins
        state[remaining_key] = 1
        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()

        game = await _get_game(session, result["game_id"])
        state = game.live_state
        operative = _find_operative(state, current_team)
        team_card_idx = _find_card_of_type(state["board"], current_team)

        guess_result = await codenames_game_controller.guess_card(
            UUID(result["game_id"]), UUID(operative["user_id"]), team_card_idx
        )

        assert guess_result["result"] == "win"
        game = await _get_game(session, result["game_id"])
        assert game.live_state["winner"] == current_team
        assert game.game_status == GameStatus.FINISHED

    @pytest.mark.asyncio
    async def test_not_operative(self, codenames_game_controller, setup_codenames_game, session):
        """Spymaster tries to guess → NotOperativeError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)

        with pytest.raises(NotOperativeError):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(spymaster["user_id"]), 0)

    @pytest.mark.asyncio
    async def test_wrong_team_guess(self, codenames_game_controller, setup_codenames_game, session):
        """Operative on non-active team → NotYourTurnError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        wrong_operative = _find_operative(state, other_team)

        with pytest.raises(NotYourTurnError):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(wrong_operative["user_id"]), 0)

    @pytest.mark.asyncio
    async def test_no_clue_given(self, codenames_game_controller, setup_codenames_game, session):
        """Guessing before clue → NoClueGivenError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)

        with pytest.raises(NoClueGivenError):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), 0)

    @pytest.mark.asyncio
    async def test_invalid_card_index_negative(self, codenames_game_controller, setup_codenames_game, session):
        """card_index = -1 → InvalidCardIndexError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)

        with pytest.raises(InvalidCardIndexError):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), -1)

    @pytest.mark.asyncio
    async def test_invalid_card_index_25(self, codenames_game_controller, setup_codenames_game, session):
        """card_index = 25 → InvalidCardIndexError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)

        with pytest.raises(InvalidCardIndexError):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), 25)

    @pytest.mark.asyncio
    async def test_card_already_revealed(self, codenames_game_controller, setup_codenames_game, session):
        """Guessing already revealed card → CardAlreadyRevealedError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)
        team_card_idx = _find_card_of_type(state["board"], current_team)

        # Reveal first
        await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), team_card_idx)

        # Try again
        with pytest.raises(CardAlreadyRevealedError):
            await codenames_game_controller.guess_card(
                UUID(result["game_id"]), UUID(operative["user_id"]), team_card_idx
            )

    @pytest.mark.asyncio
    async def test_guess_after_game_finished(self, codenames_game_controller, setup_codenames_game, session):
        """Guess after game over → GameNotInProgressError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await self._give_clue_first(codenames_game_controller, session, result)
        state = game.live_state

        # Finish the game
        state["status"] = CodenamesGameStatus.FINISHED.value
        state["winner"] = CodenamesTeam.RED.value
        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()

        game = await _get_game(session, result["game_id"])
        current_team = game.live_state["current_team"]
        operative = _find_operative(game.live_state, current_team)

        with pytest.raises(GameNotInProgressError):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), 0)

    @pytest.mark.asyncio
    async def test_player_not_in_game(self, codenames_game_controller, setup_codenames_game, session):
        """Random user → ValueError from get_player_from_game."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        await self._give_clue_first(codenames_game_controller, session, result)

        with pytest.raises(ValueError, match="not found"):
            await codenames_game_controller.guess_card(UUID(result["game_id"]), uuid4(), 0)


class TestEndTurn:
    @pytest.mark.asyncio
    async def test_switches_team(self, codenames_game_controller, setup_codenames_game, session):
        """end_turn switches current_team."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]

        # Give clue first (otherwise operative has nothing to end)
        spymaster = _find_spymaster(state, current_team)
        await codenames_game_controller.give_clue(UUID(result["game_id"]), UUID(spymaster["user_id"]), "testclue", 2)

        operative = _find_operative(state, current_team)
        end_result = await codenames_game_controller.end_turn(UUID(result["game_id"]), UUID(operative["user_id"]))

        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        assert end_result["current_team"] == other_team

    @pytest.mark.asyncio
    async def test_spymaster_tries_end_turn(self, codenames_game_controller, setup_codenames_game, session):
        """Spymaster tries end_turn → NotOperativeError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)

        with pytest.raises(NotOperativeError):
            await codenames_game_controller.end_turn(UUID(result["game_id"]), UUID(spymaster["user_id"]))

    @pytest.mark.asyncio
    async def test_wrong_team_end_turn(self, codenames_game_controller, setup_codenames_game, session):
        """Wrong team operative tries end_turn → NotYourTurnError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]
        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        wrong_operative = _find_operative(state, other_team)

        with pytest.raises(NotYourTurnError):
            await codenames_game_controller.end_turn(UUID(result["game_id"]), UUID(wrong_operative["user_id"]))

    @pytest.mark.asyncio
    async def test_after_game_finished(self, codenames_game_controller, setup_codenames_game, session):
        """end_turn after game over → GameNotInProgressError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        state["status"] = CodenamesGameStatus.FINISHED.value
        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()

        current_team = state["current_team"]
        operative = _find_operative(state, current_team)

        with pytest.raises(GameNotInProgressError):
            await codenames_game_controller.end_turn(UUID(result["game_id"]), UUID(operative["user_id"]))


class TestGetBoard:
    @pytest.mark.asyncio
    async def test_spymaster_sees_all_types(self, codenames_game_controller, setup_codenames_game, session):
        """Spymaster sees card_type for all cards."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)

        board_result = await codenames_game_controller.get_board(UUID(result["game_id"]), UUID(spymaster["user_id"]))

        assert all(c["card_type"] is not None for c in board_result["board"])

    @pytest.mark.asyncio
    async def test_operative_hides_unrevealed(self, codenames_game_controller, setup_codenames_game, session):
        """Operative sees card_type=None for unrevealed cards."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]
        operative = _find_operative(state, current_team)

        board_result = await codenames_game_controller.get_board(UUID(result["game_id"]), UUID(operative["user_id"]))

        unrevealed = [c for c in board_result["board"] if not c["revealed"]]
        assert all(c["card_type"] is None for c in unrevealed)

    @pytest.mark.asyncio
    async def test_room_active_game_cleared_on_finish(self, codenames_game_controller, setup_codenames_game, session):
        """After game ends, room.active_game_id is None."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

        # Give clue and guess assassin to end game
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)
        await codenames_game_controller.give_clue(UUID(result["game_id"]), UUID(spymaster["user_id"]), "testclue", 1)

        game = await _get_game(session, result["game_id"])
        operative = _find_operative(game.live_state, current_team)
        assassin_idx = _find_card_of_type(game.live_state["board"], CodenamesCardType.ASSASSIN.value)

        await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), assassin_idx)

        # Assert
        room = (await session.exec(select(Room).where(Room.id == setup["room"].id))).first()
        assert room.active_game_id is None

    @pytest.mark.asyncio
    async def test_guess_max_guesses_ends_turn(self, codenames_game_controller, setup_codenames_game, session):
        """When guesses_made >= max_guesses, turn switches."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        current_team = state["current_team"]
        spymaster = _find_spymaster(state, current_team)

        # Give clue with number 1 → max_guesses = 2
        await codenames_game_controller.give_clue(UUID(result["game_id"]), UUID(spymaster["user_id"]), "testclue", 1)

        game = await _get_game(session, result["game_id"])
        state = game.live_state
        operative = _find_operative(state, current_team)

        # Find two team cards
        team_cards = [i for i, c in enumerate(state["board"]) if c["card_type"] == current_team and not c["revealed"]]

        # First guess (correct, guesses_made=1, max=2)
        await codenames_game_controller.guess_card(UUID(result["game_id"]), UUID(operative["user_id"]), team_cards[0])

        # Second guess (correct but max reached, guesses_made=2, max=2)
        result2 = await codenames_game_controller.guess_card(
            UUID(result["game_id"]), UUID(operative["user_id"]), team_cards[1]
        )

        assert result2["result"] == "max_guesses"
        game = await _get_game(session, result["game_id"])
        other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
        assert game.live_state["current_team"] == other_team

    @pytest.mark.asyncio
    async def test_player_not_in_game_clue(self, codenames_game_controller, setup_codenames_game, session):
        """Random user tries give_clue → ValueError."""
        setup = await setup_codenames_game(4)
        result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

        with pytest.raises(ValueError, match="not found"):
            await codenames_game_controller.give_clue(UUID(result["game_id"]), uuid4(), "testclue", 2)
