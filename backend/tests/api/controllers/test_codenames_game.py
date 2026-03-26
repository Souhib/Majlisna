"""Tests for the CodenamesGameController."""

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import CODENAMES_BOARD_SIZE
from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.controllers.codenames_helpers import (
    CodenamesCardType,
    CodenamesGameStatus,
    CodenamesRole,
    CodenamesTeam,
)
from ipg.api.models.game import GameStatus
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room, User
from ipg.api.schemas.error import (
    BaseError,
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


def _find_all_operatives(state, team):
    """Find all operatives for a given team."""
    return [p for p in state["players"] if p["role"] == CodenamesRole.OPERATIVE.value and p["team"] == team]


def _find_card_of_type(board, card_type, exclude_revealed=True):
    """Find the index of a card of the given type."""
    for i, card in enumerate(board):
        if card["card_type"] == card_type and (not exclude_revealed or not card["revealed"]):
            return i
    return None


async def _give_clue_first(controller, session, result):
    """Helper: give a clue so guessing is allowed."""
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)
    await controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 3)
    return await _get_game(session, result.game_id)


# ─── Create & Start Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_25_card_board(codenames_game_controller, setup_codenames_game, session):
    """Board has exactly 25 cards."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    game = await _get_game(session, result.game_id)
    assert len(game.live_state["board"]) == 25
    assert game.game_status == GameStatus.IN_PROGRESS
    assert game.live_state["status"] == CodenamesGameStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_create_teams_assigned_balanced(codenames_game_controller, setup_codenames_game, session):
    """At least 2 per team, 1 spymaster each."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]

    red_players = [p for p in players if p["team"] == CodenamesTeam.RED.value]
    blue_players = [p for p in players if p["team"] == CodenamesTeam.BLUE.value]

    assert len(red_players) >= 2
    assert len(blue_players) >= 2
    assert sum(1 for p in red_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1
    assert sum(1 for p in blue_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1


@pytest.mark.asyncio
async def test_create_not_enough_players(codenames_game_controller, setup_codenames_game):
    """Less than 4 players raises NotEnoughPlayersError."""
    setup = await setup_codenames_game(3)

    with pytest.raises(NotEnoughPlayersError):
        await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)


# ─── Give Clue Tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_clue_valid(codenames_game_controller, setup_codenames_game, session):
    """Clue stored in current_turn."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    clue_result = await codenames_game_controller.give_clue(
        UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 2
    )

    assert clue_result.clue_word == "testclue"
    assert clue_result.clue_number == 2

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_turn"]["clue_word"] == "testclue"
    assert game.live_state["current_turn"]["max_guesses"] == 3  # clue_number + 1


@pytest.mark.asyncio
async def test_clue_not_spymaster(codenames_game_controller, setup_codenames_game, session):
    """Operative tries to give clue → NotSpymasterError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)

    with pytest.raises(NotSpymasterError):
        await codenames_game_controller.give_clue(UUID(result.game_id), UUID(operative["user_id"]), "testclue", 2)


@pytest.mark.asyncio
async def test_clue_wrong_team(codenames_game_controller, setup_codenames_game, session):
    """Spymaster of wrong team → NotYourTurnError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    wrong_spymaster = _find_spymaster(state, other_team)

    with pytest.raises(NotYourTurnError):
        await codenames_game_controller.give_clue(UUID(result.game_id), UUID(wrong_spymaster["user_id"]), "testclue", 2)


@pytest.mark.asyncio
async def test_clue_word_on_board(codenames_game_controller, setup_codenames_game, session):
    """Clue word that is on the board → ClueWordIsOnBoardError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)
    board_word = state["board"][0]["word"]

    with pytest.raises(ClueWordIsOnBoardError):
        await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), board_word, 2)


@pytest.mark.asyncio
async def test_clue_after_game_finished(codenames_game_controller, setup_codenames_game, session):
    """Clue after game finished → GameNotInProgressError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
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
        await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 2)


# ─── Guess Card Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_guess_correct_team_card(codenames_game_controller, setup_codenames_game, session):
    """Guessing own team's card: card revealed, remaining decremented."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)
    team_card_idx = _find_card_of_type(state["board"], current_team)

    remaining_key = f"{current_team}_remaining"
    before = state[remaining_key]

    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), team_card_idx
    )

    assert guess_result.result == "correct"
    game = await _get_game(session, result.game_id)
    assert game.live_state["board"][team_card_idx]["revealed"] is True
    assert game.live_state[remaining_key] == before - 1


@pytest.mark.asyncio
async def test_guess_continues_under_max(codenames_game_controller, setup_codenames_game, session):
    """Correct guess with guesses < max_guesses: result is 'correct', turn stays."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)
    team_card_idx = _find_card_of_type(state["board"], current_team)

    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), team_card_idx
    )

    assert guess_result.result == "correct"
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == current_team  # same team


@pytest.mark.asyncio
async def test_guess_assassin_ends_game(codenames_game_controller, setup_codenames_game, session):
    """Guessing assassin: opponent wins, game finished."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)
    assassin_idx = _find_card_of_type(state["board"], CodenamesCardType.ASSASSIN.value)

    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), assassin_idx
    )

    assert guess_result.result == "assassin"
    game = await _get_game(session, result.game_id)
    assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    assert game.live_state["winner"] == other_team


@pytest.mark.asyncio
async def test_guess_opponent_card_ends_turn(codenames_game_controller, setup_codenames_game, session):
    """Guessing opponent's card: turn switches to other team."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    operative = _find_operative(state, current_team)
    opponent_card_idx = _find_card_of_type(state["board"], other_team)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), opponent_card_idx)

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team
    assert game.live_state["board"][opponent_card_idx]["revealed"] is True
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_guess_last_team_card_wins(codenames_game_controller, setup_codenames_game, session):
    """Guessing the last remaining team card: team wins."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    remaining_key = f"{current_team}_remaining"

    # Set remaining to 1 so next correct guess wins
    state[remaining_key] = 1
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    game = await _get_game(session, result.game_id)
    state = game.live_state
    operative = _find_operative(state, current_team)
    team_card_idx = _find_card_of_type(state["board"], current_team)

    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), team_card_idx
    )

    assert guess_result.result == "win"
    game = await _get_game(session, result.game_id)
    assert game.live_state["winner"] == current_team
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


@pytest.mark.asyncio
async def test_guess_not_operative(codenames_game_controller, setup_codenames_game, session):
    """Spymaster tries to guess → NotOperativeError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    with pytest.raises(NotOperativeError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(spymaster["user_id"]), 0)


@pytest.mark.asyncio
async def test_guess_wrong_team(codenames_game_controller, setup_codenames_game, session):
    """Operative on non-active team → NotYourTurnError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    wrong_operative = _find_operative(state, other_team)

    with pytest.raises(NotYourTurnError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(wrong_operative["user_id"]), 0)


@pytest.mark.asyncio
async def test_guess_no_clue_given(codenames_game_controller, setup_codenames_game, session):
    """Guessing before clue → NoClueGivenError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)

    with pytest.raises(NoClueGivenError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), 0)


@pytest.mark.asyncio
async def test_guess_invalid_card_index_negative(codenames_game_controller, setup_codenames_game, session):
    """card_index = -1 → InvalidCardIndexError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)

    with pytest.raises(InvalidCardIndexError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), -1)


@pytest.mark.asyncio
async def test_guess_invalid_card_index_25(codenames_game_controller, setup_codenames_game, session):
    """card_index = 25 → InvalidCardIndexError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)

    with pytest.raises(InvalidCardIndexError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), 25)


@pytest.mark.asyncio
async def test_guess_card_already_revealed(codenames_game_controller, setup_codenames_game, session):
    """Guessing already revealed card → CardAlreadyRevealedError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)
    team_card_idx = _find_card_of_type(state["board"], current_team)

    # Reveal first
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), team_card_idx)

    # Try again
    with pytest.raises(CardAlreadyRevealedError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), team_card_idx)


@pytest.mark.asyncio
async def test_guess_after_game_finished(codenames_game_controller, setup_codenames_game, session):
    """Guess after game over → GameNotInProgressError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    # Finish the game
    state["status"] = CodenamesGameStatus.FINISHED.value
    state["winner"] = CodenamesTeam.RED.value
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    game = await _get_game(session, result.game_id)
    current_team = game.live_state["current_team"]
    operative = _find_operative(game.live_state, current_team)

    with pytest.raises(GameNotInProgressError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), 0)


@pytest.mark.asyncio
async def test_guess_player_not_in_game(codenames_game_controller, setup_codenames_game, session):
    """Random user → BaseError from get_player_from_game."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    await _give_clue_first(codenames_game_controller, session, result)

    with pytest.raises(BaseError, match="not found"):
        await codenames_game_controller.guess_card(UUID(result.game_id), uuid4(), 0)


# ─── End Turn Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_turn_switches_team(codenames_game_controller, setup_codenames_game, session):
    """end_turn switches current_team."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]

    # Give clue first (otherwise operative has nothing to end)
    spymaster = _find_spymaster(state, current_team)
    await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 2)

    operative = _find_operative(state, current_team)
    end_result = await codenames_game_controller.end_turn(UUID(result.game_id), UUID(operative["user_id"]))

    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    assert end_result.current_team == other_team

    # Verify DB state
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team
    assert game.live_state["current_turn"]["clue_word"] is None
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_end_turn_spymaster_rejected(codenames_game_controller, setup_codenames_game, session):
    """Spymaster tries end_turn → NotOperativeError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    with pytest.raises(NotOperativeError):
        await codenames_game_controller.end_turn(UUID(result.game_id), UUID(spymaster["user_id"]))


@pytest.mark.asyncio
async def test_end_turn_wrong_team(codenames_game_controller, setup_codenames_game, session):
    """Wrong team operative tries end_turn → NotYourTurnError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    wrong_operative = _find_operative(state, other_team)

    with pytest.raises(NotYourTurnError):
        await codenames_game_controller.end_turn(UUID(result.game_id), UUID(wrong_operative["user_id"]))


@pytest.mark.asyncio
async def test_end_turn_after_game_finished(codenames_game_controller, setup_codenames_game, session):
    """end_turn after game over → GameNotInProgressError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    state["status"] = CodenamesGameStatus.FINISHED.value
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)

    with pytest.raises(GameNotInProgressError):
        await codenames_game_controller.end_turn(UUID(result.game_id), UUID(operative["user_id"]))


# ─── Board Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_board_spymaster_sees_all_types(codenames_game_controller, setup_codenames_game, session):
    """Spymaster sees card_type for all cards."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    board_result = await codenames_game_controller.get_board(UUID(result.game_id), UUID(spymaster["user_id"]))

    assert all(c.card_type is not None for c in board_result.board)


@pytest.mark.asyncio
async def test_board_operative_hides_unrevealed(codenames_game_controller, setup_codenames_game, session):
    """Operative sees card_type=None for unrevealed cards."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    operative = _find_operative(state, current_team)

    board_result = await codenames_game_controller.get_board(UUID(result.game_id), UUID(operative["user_id"]))

    unrevealed = [c for c in board_result.board if not c.revealed]
    assert all(c.card_type is None for c in unrevealed)


@pytest.mark.asyncio
async def test_board_room_active_game_cleared_on_finish(codenames_game_controller, setup_codenames_game, session):
    """After game ends, room.active_game_id is None."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    # Give clue and guess assassin to end game
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)
    await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 1)

    game = await _get_game(session, result.game_id)
    operative = _find_operative(game.live_state, current_team)
    assassin_idx = _find_card_of_type(game.live_state["board"], CodenamesCardType.ASSASSIN.value)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), assassin_idx)

    # Assert
    room = (await session.exec(select(Room).where(Room.id == setup["room"].id))).first()
    assert room.active_game_id is None
    game = await _get_game(session, result.game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


@pytest.mark.asyncio
async def test_guess_max_guesses_ends_turn(codenames_game_controller, setup_codenames_game, session):
    """When guesses_made >= max_guesses, turn switches."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    # Give clue with number 1 → max_guesses = 2
    await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 1)

    game = await _get_game(session, result.game_id)
    state = game.live_state
    operative = _find_operative(state, current_team)

    # Find two team cards
    team_cards = [i for i, c in enumerate(state["board"]) if c["card_type"] == current_team and not c["revealed"]]

    # First guess (correct, guesses_made=1, max=2)
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), team_cards[0])

    # Second guess (correct but max reached, guesses_made=2, max=2)
    result2 = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), team_cards[1]
    )

    assert result2.result == "max_guesses"
    game = await _get_game(session, result.game_id)
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    assert game.live_state["current_team"] == other_team


@pytest.mark.asyncio
async def test_clue_player_not_in_game(codenames_game_controller, setup_codenames_game):
    """Random user tries give_clue → BaseError."""
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    with pytest.raises(BaseError, match="not found"):
        await codenames_game_controller.give_clue(UUID(result.game_id), uuid4(), "testclue", 2)


# ─── Vote Tests (multi-operative) ────────────────────────────


@pytest.mark.asyncio
async def test_vote_first_returns_not_all_voted(codenames_game_controller, setup_codenames_game, session):
    """6p game, 1 op votes → all_voted=False, card NOT revealed."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2, "Need at least 2 operatives for vote tests"

    team_card_idx = _find_card_of_type(state["board"], current_team)

    # First operative votes
    vote_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[0]["user_id"]), team_card_idx
    )

    assert vote_result.all_voted is False
    # Card should NOT be revealed yet
    game = await _get_game(session, result.game_id)
    assert game.live_state["board"][team_card_idx]["revealed"] is False


@pytest.mark.asyncio
async def test_vote_second_resolves_and_reveals(codenames_game_controller, setup_codenames_game, session):
    """Both ops vote same card → all_voted=True, card revealed."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    team_card_idx = _find_card_of_type(state["board"], current_team)

    # First operative votes
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), team_card_idx)

    # Second operative votes same card
    vote_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[1]["user_id"]), team_card_idx
    )

    assert vote_result.all_voted is True
    assert vote_result.result == "correct"

    game = await _get_game(session, result.game_id)
    assert game.live_state["board"][team_card_idx]["revealed"] is True


@pytest.mark.asyncio
async def test_vote_change_before_all_voted(codenames_game_controller, setup_codenames_game, session):
    """Op re-votes different card → vote_changed=True, count=1."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    team_cards = [i for i, c in enumerate(state["board"]) if c["card_type"] == current_team and not c["revealed"]]
    assert len(team_cards) >= 2

    # First vote
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), team_cards[0])

    # Change vote to different card
    changed_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[0]["user_id"]), team_cards[1]
    )

    assert changed_result.all_voted is False
    assert changed_result.vote_changed is True
    assert changed_result.card_votes_count == 1


@pytest.mark.asyncio
async def test_vote_card_votes_cleared_after_resolution(codenames_game_controller, setup_codenames_game, session):
    """After resolution → card_votes == {} in DB."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    team_card_idx = _find_card_of_type(state["board"], current_team)

    # Both vote same card
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), team_card_idx)
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[1]["user_id"]), team_card_idx)

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_turn"]["card_votes"] == {}


@pytest.mark.asyncio
async def test_vote_resolve_unanimous(codenames_game_controller, setup_codenames_game, session):
    """Both vote same → tied=False."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    team_card_idx = _find_card_of_type(state["board"], current_team)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), team_card_idx)
    vote_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[1]["user_id"]), team_card_idx
    )

    assert vote_result.tied is False


@pytest.mark.asyncio
@patch("ipg.api.controllers.codenames_game.random.choice", side_effect=lambda x: x[0])
async def test_vote_resolve_two_way_tie(mock_choice, codenames_game_controller, setup_codenames_game, session):
    """Each votes different → tied=True (mock random.choice)."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    team_cards = [i for i, c in enumerate(state["board"]) if c["card_type"] == current_team and not c["revealed"]]
    assert len(team_cards) >= 2

    # Each operative votes for a different card
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), team_cards[0])
    vote_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[1]["user_id"]), team_cards[1]
    )

    assert vote_result.all_voted is True
    assert vote_result.tied is True
    mock_choice.assert_called()


@pytest.mark.asyncio
@patch("ipg.api.controllers.codenames_game.random.choice", side_effect=lambda x: x[0])
async def test_vote_resolve_three_way_tie(mock_choice, codenames_game_controller, setup_codenames_game, session):
    """8p game, 3 ops vote 3 different cards → tied=True (mock)."""
    setup = await setup_codenames_game(8)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 3, f"Need at least 3 operatives, got {len(operatives)}"

    team_cards = [i for i, c in enumerate(state["board"]) if c["card_type"] == current_team and not c["revealed"]]
    assert len(team_cards) >= 3

    # Each operative votes for a different card
    for i in range(len(operatives)):
        card_idx = team_cards[i % len(team_cards)]
        vote_result = await codenames_game_controller.guess_card(
            UUID(result.game_id), UUID(operatives[i]["user_id"]), card_idx
        )

    assert vote_result.all_voted is True
    assert vote_result.tied is True
    mock_choice.assert_called()


@pytest.mark.asyncio
async def test_vote_assassin_ends_game(codenames_game_controller, setup_codenames_game, session):
    """Both vote assassin → game finished, opponent wins."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    assassin_idx = _find_card_of_type(state["board"], CodenamesCardType.ASSASSIN.value)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), assassin_idx)
    vote_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[1]["user_id"]), assassin_idx
    )

    assert vote_result.result == "assassin"
    game = await _get_game(session, result.game_id)
    assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
    assert game.live_state["winner"] == other_team
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


@pytest.mark.asyncio
async def test_vote_last_card_wins(codenames_game_controller, setup_codenames_game, session):
    """Set remaining=1, both vote last card → team wins."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    remaining_key = f"{current_team}_remaining"

    # Set remaining to 1
    state[remaining_key] = 1
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    game = await _get_game(session, result.game_id)
    state = game.live_state
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    team_card_idx = _find_card_of_type(state["board"], current_team)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), team_card_idx)
    vote_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[1]["user_id"]), team_card_idx
    )

    assert vote_result.result == "win"
    game = await _get_game(session, result.game_id)
    assert game.live_state["winner"] == current_team
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


@pytest.mark.asyncio
async def test_vote_opponent_card_ends_turn(codenames_game_controller, setup_codenames_game, session):
    """Both vote opponent card → turn switches."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    opponent_card_idx = _find_card_of_type(state["board"], other_team)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), opponent_card_idx)
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[1]["user_id"]), opponent_card_idx)

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team


@pytest.mark.asyncio
async def test_vote_neutral_ends_turn(codenames_game_controller, setup_codenames_game, session):
    """Both vote neutral → turn switches."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) >= 2

    neutral_idx = _find_card_of_type(state["board"], CodenamesCardType.NEUTRAL.value)

    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[0]["user_id"]), neutral_idx)
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operatives[1]["user_id"]), neutral_idx)

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team


@pytest.mark.asyncio
async def test_vote_spymaster_cannot_vote(codenames_game_controller, setup_codenames_game, session):
    """Spymaster in 6p game → NotOperativeError."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)
    team_card_idx = _find_card_of_type(state["board"], current_team)

    with pytest.raises(NotOperativeError):
        await codenames_game_controller.guess_card(UUID(result.game_id), UUID(spymaster["user_id"]), team_card_idx)


@pytest.mark.asyncio
async def test_vote_wrong_team_cannot_vote(codenames_game_controller, setup_codenames_game, session):
    """Wrong team op in 6p → NotYourTurnError."""
    setup = await setup_codenames_game(6)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    wrong_operative = _find_operative(state, other_team)
    team_card_idx = _find_card_of_type(state["board"], current_team)

    with pytest.raises(NotYourTurnError):
        await codenames_game_controller.guess_card(
            UUID(result.game_id), UUID(wrong_operative["user_id"]), team_card_idx
        )


# ─── _resolve_hint (static method) ──────────────────────────


def test_resolve_hint_exact_match():
    """When the requested lang key exists, return its value."""
    hint = {"en": "English hint", "fr": "French hint", "ar": "Arabic hint"}
    result = CodenamesGameController._resolve_multilingual(hint, "fr")
    assert result == "French hint"


def test_resolve_hint_fallback_to_en():
    """When requested lang missing, fall back to 'en'."""
    hint = {"en": "English hint", "ar": "Arabic hint"}
    result = CodenamesGameController._resolve_multilingual(hint, "fr")
    assert result == "English hint"


def test_resolve_hint_fallback_to_first_value():
    """When both requested lang and 'en' missing, return first value."""
    hint = {"ar": "Arabic hint", "de": "German hint"}
    result = CodenamesGameController._resolve_multilingual(hint, "fr")
    assert result == "Arabic hint"


def test_resolve_hint_none_input():
    """When hint_dict is None, return None."""
    result = CodenamesGameController._resolve_multilingual(None, "en")
    assert result is None


def test_resolve_hint_empty_dict():
    """When hint_dict is empty, return None."""
    result = CodenamesGameController._resolve_multilingual({}, "en")
    assert result is None


def test_resolve_hint_exact_en():
    """When lang='en' and 'en' key exists, return 'en' value."""
    hint = {"en": "English hint", "fr": "French hint"}
    result = CodenamesGameController._resolve_multilingual(hint, "en")
    assert result == "English hint"


# ─── record_hint_view ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_hint_view_success(codenames_game_controller, setup_codenames_game, session):
    """Recording a hint view stores the word in hint_usage for the user."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act
    hint_result = await codenames_game_controller.record_hint_view(game_uuid, user.id, "Quran")

    # Assert
    assert hint_result.recorded is True
    game = await _get_game(session, result.game_id)
    assert str(user.id) in game.live_state["hint_usage"]
    assert "Quran" in game.live_state["hint_usage"][str(user.id)]


@pytest.mark.asyncio
async def test_record_hint_view_deduplicated(codenames_game_controller, setup_codenames_game, session):
    """Recording the same hint twice does not create duplicate entries."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act — record twice
    await codenames_game_controller.record_hint_view(game_uuid, user.id, "Quran")
    await codenames_game_controller.record_hint_view(game_uuid, user.id, "Quran")

    # Assert — only one entry
    game = await _get_game(session, result.game_id)
    assert game.live_state["hint_usage"][str(user.id)].count("Quran") == 1


@pytest.mark.asyncio
async def test_record_hint_view_multiple_words(codenames_game_controller, setup_codenames_game, session):
    """Recording different words adds each to the list."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act
    await codenames_game_controller.record_hint_view(game_uuid, user.id, "Quran")
    await codenames_game_controller.record_hint_view(game_uuid, user.id, "Salah")

    # Assert
    game = await _get_game(session, result.game_id)
    user_hints = game.live_state["hint_usage"][str(user.id)]
    assert "Quran" in user_hints
    assert "Salah" in user_hints
    assert len(user_hints) == 2


# ─── create_and_start hint fields ───────────────────────────


@pytest.mark.asyncio
async def test_create_stores_hint_usage_in_live_state(codenames_game_controller, setup_codenames_game, session):
    """create_and_start stores word_hints and hint_usage in live_state."""
    # Prepare
    setup = await setup_codenames_game(4)

    # Act
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert "word_hints" in state
    assert "hint_usage" in state
    assert state["hint_usage"] == {}


# ─── get_board hint fields ──────────────────────────────────


@pytest.mark.asyncio
async def test_board_includes_hint_field(codenames_game_controller, setup_codenames_game, session):
    """get_board returns 'hint' field on each card of the board view."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    # Act — spymaster sees hints
    board_result = await codenames_game_controller.get_board(UUID(result.game_id), UUID(spymaster["user_id"]))

    # Assert — each card has a 'hint' key
    for card in board_result.board:
        assert hasattr(card, "hint")


# ─── Timer Expired Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_timer_expired_clue_phase(codenames_game_controller, setup_codenames_game, session):
    """During clue-giving phase, timer expiration should auto-end the turn."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value

    # Set timer config with non-zero clue timer and push timer_started_at far in the past
    state["timer_config"] = {"clue_seconds": 60, "guess_seconds": 60}
    state["timer_started_at"] = "2020-01-01T00:00:00+00:00"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — host triggers timer expiration (no clue given, so it's clue phase)
    host_id = setup["users"][0].id
    timer_result = await codenames_game_controller.handle_timer_expired(UUID(result.game_id), host_id)

    # Assert — turn switched
    assert timer_result.action == "auto_end_turn"
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team


@pytest.mark.asyncio
async def test_timer_expired_guess_phase(codenames_game_controller, setup_codenames_game, session):
    """During guess phase, timer expiration should auto-end the turn and switch teams."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state
    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value

    # Set timer config with non-zero guess timer and push timer_started_at far in the past
    state["timer_config"] = {"clue_seconds": 60, "guess_seconds": 60}
    state["timer_started_at"] = "2020-01-01T00:00:00+00:00"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — host triggers timer expiration (clue already given, so it's guess phase)
    host_id = setup["users"][0].id
    timer_result = await codenames_game_controller.handle_timer_expired(UUID(result.game_id), host_id)

    # Assert — turn switched
    assert timer_result.action == "auto_end_turn"
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team


@pytest.mark.asyncio
async def test_timer_expired_non_host_allowed(codenames_game_controller, setup_codenames_game, session):
    """Any player can trigger timer expiration — not just host."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value

    # Set timer config so it doesn't short-circuit
    state["timer_config"] = {"clue_seconds": 60, "guess_seconds": 60}
    state["timer_started_at"] = "2020-01-01T00:00:00+00:00"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — non-host triggers timer expiration
    non_host_id = setup["users"][1].id
    timer_result = await codenames_game_controller.handle_timer_expired(UUID(result.game_id), non_host_id)

    # Assert — should succeed and switch turn
    assert timer_result.action == "auto_end_turn"
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team


@pytest.mark.asyncio
async def test_timer_expired_no_timer_configured(codenames_game_controller, setup_codenames_game, session):
    """When timer is 0 (disabled), timer expired should return without changing state."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]

    # Ensure timer is 0 (disabled) — this is the default
    state["timer_config"] = {"clue_seconds": 0, "guess_seconds": 0}
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act — host triggers timer expiration
    host_id = setup["users"][0].id
    timer_result = await codenames_game_controller.handle_timer_expired(UUID(result.game_id), host_id)

    # Assert — no action taken, team stays the same
    assert timer_result.action == "timer_not_expired"
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == current_team


# ─── Spectator Board Test ───────────────────────────────────


@pytest.mark.asyncio
async def test_board_spectator_hides_unrevealed(codenames_game_controller, setup_codenames_game, session):
    """A spectator should see the same view as an operative (no card types for unrevealed cards)."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    # Create a spectator user with RoomUserLink.is_spectator = True
    spectator = User(username="spectator_cn", email_address="spectator_cn@test.com", password="password123")
    session.add(spectator)
    await session.commit()
    await session.refresh(spectator)

    spectator_link = RoomUserLink(
        room_id=setup["room"].id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(spectator_link)
    await session.commit()

    # Act
    board_result = await codenames_game_controller.get_board(UUID(result.game_id), spectator.id)

    # Assert — unrevealed cards should have card_type=None
    unrevealed = [c for c in board_result.board if not c.revealed]
    assert len(unrevealed) > 0
    assert all(c.card_type is None for c in unrevealed)
    assert board_result.is_spectator is True


# ─── Single Operative Auto-Reveal Test ──────────────────────


@pytest.mark.asyncio
async def test_single_operative_auto_reveal(codenames_game_controller, setup_codenames_game, session):
    """When only 1 operative on a team, guess_card should auto-reveal (skip voting)."""
    # Prepare — 4 players means each team has 1 spymaster + 1 operative
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operatives = _find_all_operatives(state, current_team)
    assert len(operatives) == 1, "4-player game should have exactly 1 operative per team"

    team_card_idx = _find_card_of_type(state["board"], current_team)

    # Act — single operative guesses
    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operatives[0]["user_id"]), team_card_idx
    )

    # Assert — card revealed immediately (no voting), result is "correct"
    assert guess_result.result == "correct"
    game = await _get_game(session, result.game_id)
    assert game.live_state["board"][team_card_idx]["revealed"] is True


# ─── Clue Case-Insensitive Board Match Test ─────────────────


@pytest.mark.asyncio
async def test_clue_case_insensitive_board_match(codenames_game_controller, setup_codenames_game, session):
    """Giving a clue that matches a board word case-insensitively should be rejected."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)
    # Get a board word and change its case
    board_word = state["board"][0]["word"]
    case_changed = board_word.upper() if board_word[0].islower() else board_word.lower()

    # Act & Assert — case-insensitive match should be rejected
    with pytest.raises(ClueWordIsOnBoardError):
        await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), case_changed, 2)


# ─── Guess Opponent Last Card Test ──────────────────────────


@pytest.mark.asyncio
async def test_guess_opponent_last_card_opponent_wins(codenames_game_controller, setup_codenames_game, session):
    """Guessing the opponent's last remaining card should make the opponent win."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value

    # Set opponent remaining to 1 so guessing their card wins for them
    other_remaining_key = f"{other_team}_remaining"
    state[other_remaining_key] = 1
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    game = await _get_game(session, result.game_id)
    state = game.live_state
    operative = _find_operative(state, current_team)
    opponent_card_idx = _find_card_of_type(state["board"], other_team)

    # Act
    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), opponent_card_idx
    )

    # Assert — opponent wins
    assert guess_result.result == "opponent_wins"
    game = await _get_game(session, result.game_id)
    assert game.live_state["status"] == CodenamesGameStatus.FINISHED.value
    assert game.live_state["winner"] == other_team
    assert game.game_status == GameStatus.FINISHED
    assert game.end_time is not None


# ─── Guess Neutral Switches Turn Test ───────────────────────


@pytest.mark.asyncio
async def test_guess_neutral_switches_turn(codenames_game_controller, setup_codenames_game, session):
    """Guessing a neutral card should end the turn and switch to the other team."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    operative = _find_operative(state, current_team)
    neutral_idx = _find_card_of_type(state["board"], CodenamesCardType.NEUTRAL.value)

    # Act
    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), neutral_idx
    )

    # Assert — turn switched
    assert guess_result.result == "neutral"
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team


# ─── End Turn Wrong Team Rejected Test ──────────────────────


@pytest.mark.asyncio
async def test_end_turn_wrong_team_rejected(codenames_game_controller, setup_codenames_game, session):
    """An operative from the non-active team calling end_turn should be rejected."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    wrong_operative = _find_operative(state, other_team)

    # Act & Assert
    with pytest.raises(NotYourTurnError):
        await codenames_game_controller.end_turn(UUID(result.game_id), UUID(wrong_operative["user_id"]))


# ─── End Turn After Assassin Rejected Test ──────────────────


@pytest.mark.asyncio
async def test_end_turn_after_assassin_rejected(codenames_game_controller, setup_codenames_game, session):
    """Calling end_turn after game is finished should be rejected."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _give_clue_first(codenames_game_controller, session, result)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)
    assassin_idx = _find_card_of_type(state["board"], CodenamesCardType.ASSASSIN.value)

    # Guess assassin to finish the game
    await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), assassin_idx)

    # Act & Assert — end_turn on finished game
    with pytest.raises(GameNotInProgressError):
        await codenames_game_controller.end_turn(UUID(result.game_id), UUID(operative["user_id"]))


# ─── Create With Word Packs Test ────────────────────────────


@pytest.mark.asyncio
async def test_create_with_word_packs(codenames_game_controller, setup_codenames_game, session):
    """Creating a game with specific word pack IDs should use words from those packs."""
    # Prepare
    setup = await setup_codenames_game(4)
    word_pack = setup["word_pack"]

    # Act — pass word_pack_ids
    result = await codenames_game_controller.create_and_start(
        setup["room"].id, setup["users"][0].id, word_pack_ids=[word_pack.id]
    )

    # Assert — game created with board words from the pack
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["board"]) == 25
    board_words = {card["word"] for card in game.live_state["board"]}
    pack_words = {w.word for w in setup["words"]}
    # All board words should come from the pack
    assert board_words.issubset(pack_words)
    # game_configurations should record the word pack IDs
    assert str(word_pack.id) in game.game_configurations["word_pack_ids"]


# ─── Clue Number Zero Test ─────────────────────────────────


@pytest.mark.asyncio
async def test_clue_number_zero_max_guesses(codenames_game_controller, setup_codenames_game, session):
    """A clue with number=0 means unlimited guesses (max_guesses = BOARD_SIZE)."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)

    # Act — give clue with number=0 (unlimited)
    await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "zeroclue", 0)

    # Assert — max_guesses = CODENAMES_BOARD_SIZE (unlimited)
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_turn"]["clue_number"] == 0
    assert game.live_state["current_turn"]["max_guesses"] == CODENAMES_BOARD_SIZE

    # Guessing one correct card should NOT end the turn (unlimited guesses)
    operative = _find_operative(game.live_state, current_team)
    team_card_idx = _find_card_of_type(game.live_state["board"], current_team)
    guess_result = await codenames_game_controller.guess_card(
        UUID(result.game_id), UUID(operative["user_id"]), team_card_idx
    )
    assert guess_result.result == "correct"  # Turn continues
    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == current_team  # Still same team's turn


# ─── Guess Max Guesses Plus One Test ────────────────────────


@pytest.mark.asyncio
async def test_guess_max_guesses_plus_one(codenames_game_controller, setup_codenames_game, session):
    """After clue_number+1 correct guesses, the turn should automatically end."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value
    spymaster = _find_spymaster(state, current_team)

    # Give clue with number=2 → max_guesses = 3
    await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "threeguess", 2)

    game = await _get_game(session, result.game_id)
    state = game.live_state
    operative = _find_operative(state, current_team)

    # Find 3 team cards
    team_cards = [i for i, c in enumerate(state["board"]) if c["card_type"] == current_team and not c["revealed"]]
    assert len(team_cards) >= 3, "Need at least 3 team cards"

    # First guess (guesses_made=1, max=3) → correct
    r1 = await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), team_cards[0])
    assert r1.result == "correct"

    # Second guess (guesses_made=2, max=3) → correct
    r2 = await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), team_cards[1])
    assert r2.result == "correct"

    # Third guess (guesses_made=3, max=3) → max_guesses, turn switches
    r3 = await codenames_game_controller.guess_card(UUID(result.game_id), UUID(operative["user_id"]), team_cards[2])
    assert r3.result == "max_guesses"

    game = await _get_game(session, result.game_id)
    assert game.live_state["current_team"] == other_team
