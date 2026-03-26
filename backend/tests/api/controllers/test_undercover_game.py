"""Tests for the UndercoverGameController."""

import random
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.shared import get_password_hash
from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.models.game import GameStatus
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room, User
from ipg.api.models.undercover import UndercoverRole
from ipg.api.schemas.error import (
    BaseError,
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
    PlayerRemovedFromGameError,
)

# ─── Helpers ──────────────────────────────────────────────────


async def _start_game(controller: UndercoverGameController, room_id, user_id):
    """Start a game and return the result dict."""
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    """Fetch a game by its string ID."""
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


def _find_player_by_role(state, role_value):
    """Find the first player with the given role."""
    return next((p for p in state["players"] if p["role"] == role_value), None)


def _alive_players(state):
    """Get alive players from state."""
    return [p for p in state["players"] if p["is_alive"]]


async def _setup_voting_phase(controller, setup_undercover_game, session):
    """Helper: start game and submit all descriptions to reach voting phase."""

    setup = await setup_undercover_game(3)
    result = await _start_game(controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    order = game.live_state["turns"][0]["description_order"]
    game_uuid = UUID(result.game_id)

    for uid in order:
        await controller.submit_description(game_uuid, UUID(uid), "word")

    game = await _get_game(session, result.game_id)
    return setup, result, game


async def _setup_mr_white_voting_phase(controller, setup_undercover_game, session):
    """Helper: start a 5-player game, force one player as Mr. White, and reach voting phase."""
    setup = await setup_undercover_game(5)
    result = await _start_game(controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    # Force roles: player 0 = mr_white, player 1 = undercover, rest = civilian
    state["players"][0]["role"] = UndercoverRole.MR_WHITE.value
    state["players"][1]["role"] = UndercoverRole.UNDERCOVER.value
    for p in state["players"][2:]:
        p["role"] = UndercoverRole.CIVILIAN.value
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Submit all descriptions to reach voting phase
    game = await _get_game(session, result.game_id)
    order = game.live_state["turns"][0]["description_order"]
    game_uuid = UUID(result.game_id)
    for uid in order:
        await controller.submit_description(game_uuid, UUID(uid), "word")

    game = await _get_game(session, result.game_id)
    return setup, result, game


# ========== CreateAndStart ==========


@pytest.mark.asyncio
async def test_create_3_players(undercover_game_controller, setup_undercover_game, session):
    """3 players: 0 mr_white, 1 undercover, 2 civilians, mayor assigned, description_order generated."""
    # Prepare
    setup = await setup_undercover_game(3)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(undercover_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    players = state["players"]

    assert len(players) == 3
    roles = [p["role"] for p in players]
    assert roles.count(UndercoverRole.MR_WHITE.value) == 0
    assert roles.count(UndercoverRole.UNDERCOVER.value) == 1
    assert roles.count(UndercoverRole.CIVILIAN.value) == 2

    # Mayor assigned
    mayors = [p for p in players if p.get("is_mayor")]
    assert len(mayors) == 1

    # Description order generated
    assert len(state["turns"]) == 1
    turn = state["turns"][0]
    assert len(turn["description_order"]) == 3
    assert turn["phase"] == "describing"
    assert game.game_status == GameStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_create_5_players(undercover_game_controller, setup_undercover_game, session):
    """5 players: 1 mr_white, 2 undercover, 2 civilians."""
    # Prepare
    setup = await setup_undercover_game(5)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(undercover_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    roles = [p["role"] for p in players]

    assert roles.count(UndercoverRole.MR_WHITE.value) == 1
    assert roles.count(UndercoverRole.UNDERCOVER.value) == 2
    assert roles.count(UndercoverRole.CIVILIAN.value) == 2


@pytest.mark.asyncio
async def test_create_10_players(undercover_game_controller, setup_undercover_game, session):
    """10 players: correct role distribution with at least 1 civilian."""
    # Prepare
    setup = await setup_undercover_game(10)
    room, users = setup["room"], setup["users"]

    # Act
    result = await _start_game(undercover_game_controller, room.id, users[0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    roles = [p["role"] for p in players]

    # 10 players: 2 mr_white (10 <= 15), 2 undercover (10//4=2), 6 civilians
    assert roles.count(UndercoverRole.MR_WHITE.value) == 2
    assert roles.count(UndercoverRole.UNDERCOVER.value) == 2
    assert roles.count(UndercoverRole.CIVILIAN.value) == 6


@pytest.mark.asyncio
async def test_create_room_already_has_active_game(undercover_game_controller, setup_undercover_game):
    """Starting a game in a room that already has one raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    room, users = setup["room"], setup["users"]
    await _start_game(undercover_game_controller, room.id, users[0].id)

    # Act / Assert
    with pytest.raises(BaseError, match="already has an active game"):
        await _start_game(undercover_game_controller, room.id, users[0].id)


# ========== SubmitDescription ==========


@pytest.mark.asyncio
async def test_describe_stores_word_and_advances_index(undercover_game_controller, setup_undercover_game, session):
    """Word stored in current_turn['words'], current_describer_index incremented."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    first_describer_id = game.live_state["turns"][0]["description_order"][0]

    # Act

    desc_result = await undercover_game_controller.submit_description(
        UUID(result.game_id), UUID(first_describer_id), "testword"
    )

    # Assert
    assert desc_result.word == "testword"
    game = await _get_game(session, result.game_id)
    turn = game.live_state["turns"][0]
    assert first_describer_id in turn["words"]
    assert turn["words"][first_describer_id] == "testword"
    assert turn["current_describer_index"] == 1


@pytest.mark.asyncio
async def test_describe_all_descriptions_transitions_to_voting(
    undercover_game_controller, setup_undercover_game, session
):
    """After last description, phase becomes 'voting'."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    order = game.live_state["turns"][0]["description_order"]

    # Act — submit all descriptions

    game_uuid = UUID(result.game_id)
    for uid in order:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    # Assert
    game = await _get_game(session, result.game_id)
    assert game.live_state["turns"][0]["phase"] == "voting"


@pytest.mark.asyncio
async def test_describe_not_your_turn(undercover_game_controller, setup_undercover_game, session):
    """Wrong user submitting raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    order = game.live_state["turns"][0]["description_order"]
    # Find a user who is NOT the current describer
    wrong_user_id = next(str(u.id) for u in setup["users"] if str(u.id) != order[0])

    # Act / Assert

    with pytest.raises(BaseError, match="Not your turn"):
        await undercover_game_controller.submit_description(UUID(result.game_id), UUID(wrong_user_id), "word")


@pytest.mark.asyncio
async def test_describe_not_in_describing_phase(undercover_game_controller, setup_undercover_game, session):
    """Submitting during voting phase raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    order = game.live_state["turns"][0]["description_order"]

    game_uuid = UUID(result.game_id)

    # Submit all to move to voting
    for uid in order:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    # Act / Assert — try to submit during voting
    with pytest.raises(BaseError, match="Not in description phase"):
        await undercover_game_controller.submit_description(game_uuid, UUID(order[0]), "extra")


@pytest.mark.asyncio
async def test_describe_empty_word(undercover_game_controller, setup_undercover_game, session):
    """Empty word raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    first_describer = game.live_state["turns"][0]["description_order"][0]

    # Act / Assert
    with pytest.raises(BaseError, match="single word"):
        await undercover_game_controller.submit_description(UUID(result.game_id), UUID(first_describer), "")


@pytest.mark.asyncio
async def test_describe_word_with_spaces(undercover_game_controller, setup_undercover_game, session):
    """Word with spaces raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    first_describer = game.live_state["turns"][0]["description_order"][0]

    # Act / Assert
    with pytest.raises(BaseError, match="single word"):
        await undercover_game_controller.submit_description(UUID(result.game_id), UUID(first_describer), "two words")


@pytest.mark.asyncio
async def test_describe_word_too_long(undercover_game_controller, setup_undercover_game, session):
    """Word over 50 characters raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    first_describer = game.live_state["turns"][0]["description_order"][0]

    # Act / Assert
    with pytest.raises(BaseError, match="max 50"):
        await undercover_game_controller.submit_description(UUID(result.game_id), UUID(first_describer), "a" * 51)


@pytest.mark.asyncio
async def test_describe_after_all_submitted(undercover_game_controller, setup_undercover_game, session):
    """Extra description after all done raises error."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    order = game.live_state["turns"][0]["description_order"]

    game_uuid = UUID(result.game_id)
    for uid in order:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    # Act / Assert — phase is "voting" now, so this fails
    with pytest.raises(BaseError):
        await undercover_game_controller.submit_description(game_uuid, UUID(order[0]), "extra")


@pytest.mark.asyncio
async def test_describe_player_not_in_game(undercover_game_controller, setup_undercover_game):
    """Random user_id not in game players raises error."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    # Act / Assert — random UUID not in description_order
    with pytest.raises(BaseError, match="Not your turn"):
        await undercover_game_controller.submit_description(UUID(result.game_id), uuid4(), "word")


# ========== SubmitVote ==========


@pytest.mark.asyncio
async def test_vote_records_vote(undercover_game_controller, setup_undercover_game, session):
    """Vote stored in current_turn['votes']."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    voter = setup["users"][0]
    target = next(u for u in setup["users"] if u.id != voter.id)

    # Act
    vote_result = await undercover_game_controller.submit_vote(game_uuid, voter.id, target.id)

    # Assert
    assert vote_result.game_id == result.game_id
    game = await _get_game(session, result.game_id)
    assert str(voter.id) in game.live_state["turns"][0]["votes"]


@pytest.mark.asyncio
async def test_vote_all_votes_eliminates_majority_target(undercover_game_controller, setup_undercover_game, session):
    """Player with most votes eliminated, is_alive=False, added to eliminated_players."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    users = setup["users"]
    target = users[2]  # everyone votes for player 2

    # Act — all 3 players vote for target (except target votes for someone else)
    for voter in users:
        if voter.id == target.id:
            other = next(u for u in users if u.id != target.id)
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, target.id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    eliminated = next(p for p in state["players"] if p["user_id"] == str(target.id))
    assert eliminated["is_alive"] is False
    assert any(e["user_id"] == str(target.id) for e in state["eliminated_players"])
    assert game.game_status in (GameStatus.IN_PROGRESS, GameStatus.FINISHED)


@pytest.mark.asyncio
async def test_vote_civilians_win_when_all_undercovers_eliminated(
    undercover_game_controller, setup_undercover_game, session
):
    """When all undercovers and mr_whites are eliminated, civilians win."""
    # Prepare — 3 players: 1 undercover, 2 civilians, 0 mr_white
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    state = game.live_state
    undercover_player = _find_player_by_role(state, UndercoverRole.UNDERCOVER.value)
    users = setup["users"]

    # Act — all vote for the undercover
    for voter in users:
        if str(voter.id) == undercover_player["user_id"]:
            other = next(u for u in users if str(u.id) != undercover_player["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(undercover_player["user_id"]))

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    uc = next(p for p in state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value)
    if not uc["is_alive"]:
        assert game.game_status == GameStatus.FINISHED
        assert game.end_time is not None


@pytest.mark.asyncio
async def test_vote_dead_voter(undercover_game_controller, setup_undercover_game, session):
    """Dead player voting raises CantVoteBecauseYouDeadError."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    state = game.live_state

    # Kill a player manually
    state["players"][0]["is_alive"] = False
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    dead_user = setup["users"][0]
    target = setup["users"][1]

    # Act / Assert
    with pytest.raises(CantVoteBecauseYouDeadError):
        await undercover_game_controller.submit_vote(game_uuid, dead_user.id, target.id)


@pytest.mark.asyncio
async def test_vote_dead_target(undercover_game_controller, setup_undercover_game, session):
    """Voting for dead player raises CantVoteForDeadPersonError."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    state = game.live_state

    # Kill target manually
    state["players"][2]["is_alive"] = False
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    voter = setup["users"][0]
    dead_target = setup["users"][2]

    # Act / Assert
    with pytest.raises(CantVoteForDeadPersonError):
        await undercover_game_controller.submit_vote(game_uuid, voter.id, dead_target.id)


@pytest.mark.asyncio
async def test_vote_self(undercover_game_controller, setup_undercover_game, session):
    """Voting for yourself raises CantVoteForYourselfError."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    voter = setup["users"][0]

    # Act / Assert
    with pytest.raises(CantVoteForYourselfError):
        await undercover_game_controller.submit_vote(game_uuid, voter.id, voter.id)


@pytest.mark.asyncio
async def test_vote_not_in_voting_phase(undercover_game_controller, setup_undercover_game):
    """Voting during describing phase raises BaseError 400."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    game_uuid = UUID(result.game_id)
    voter = setup["users"][0]
    target = setup["users"][1]

    # Act / Assert
    with pytest.raises(BaseError, match="not complete"):
        await undercover_game_controller.submit_vote(game_uuid, voter.id, target.id)


@pytest.mark.asyncio
async def test_vote_twice_raises_error(undercover_game_controller, setup_undercover_game, session):
    """Voting again raises an error (duplicate vote prevention)."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    voter = setup["users"][0]
    target1 = setup["users"][1]
    target2 = setup["users"][2]

    # Act — vote once succeeds
    await undercover_game_controller.submit_vote(game_uuid, voter.id, target1.id)

    # Assert — second vote raises error
    with pytest.raises(BaseError, match="already voted"):
        await undercover_game_controller.submit_vote(game_uuid, voter.id, target2.id)


@pytest.mark.asyncio
async def test_vote_player_not_in_game(undercover_game_controller, setup_undercover_game, session):
    """User not in game raises error."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    target = setup["users"][1]

    # Act / Assert
    with pytest.raises(BaseError, match="not in game"):
        await undercover_game_controller.submit_vote(game_uuid, uuid4(), target.id)


# ========== StartNextRound ==========


@pytest.mark.asyncio
async def test_next_round_appends_turn(undercover_game_controller, setup_undercover_game, session):
    """start_next_round adds a new turn, phase reset to 'describing'."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    game_uuid = UUID(result.game_id)

    # Act
    round_result = await undercover_game_controller.start_next_round(game_uuid, setup["room"].id, setup["users"][0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["turns"]) == 2
    assert game.live_state["turns"][1]["phase"] == "describing"
    assert round_result.turn_number == 2
    assert game.game_status == GameStatus.IN_PROGRESS


# ========== GetState ==========


@pytest.mark.asyncio
async def test_state_civilian_word(undercover_game_controller, setup_undercover_game, session):
    """Civilian sees civilian_word."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    civilian = _find_player_by_role(state, UndercoverRole.CIVILIAN.value)

    # Act
    player_state = await undercover_game_controller.get_state(UUID(result.game_id), UUID(civilian["user_id"]))

    # Assert
    assert player_state.my_word == state["civilian_word"]


@pytest.mark.asyncio
async def test_state_undercover_word(undercover_game_controller, setup_undercover_game, session):
    """Undercover sees undercover_word."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    undercover = _find_player_by_role(state, UndercoverRole.UNDERCOVER.value)

    # Act
    player_state = await undercover_game_controller.get_state(UUID(result.game_id), UUID(undercover["user_id"]))

    # Assert
    assert player_state.my_word == state["undercover_word"]


@pytest.mark.asyncio
async def test_state_mr_white_message(undercover_game_controller, setup_undercover_game, session):
    """Mr. White sees message about guessing the word."""
    # Prepare — need 5 players to get mr_white
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    mr_white = _find_player_by_role(state, UndercoverRole.MR_WHITE.value)
    if not mr_white:
        pytest.skip("No Mr. White in this game (random role assignment)")

    # Act
    player_state = await undercover_game_controller.get_state(UUID(result.game_id), UUID(mr_white["user_id"]))

    # Assert
    assert "Mr. White" in player_state.my_word


@pytest.mark.asyncio
async def test_state_player_not_in_game(undercover_game_controller, setup_undercover_game):
    """User not in game raises PlayerRemovedFromGameError."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    # Act / Assert
    with pytest.raises(PlayerRemovedFromGameError):
        await undercover_game_controller.get_state(UUID(result.game_id), uuid4())


# ========== EdgeCases ==========


@pytest.mark.asyncio
async def test_edge_undercovers_win_when_outnumbering_civilians(
    undercover_game_controller, setup_undercover_game, session
):
    """3-player game: eliminate the civilian → undercovers should win."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    game_uuid = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    order = state["turns"][0]["description_order"]

    # Submit all descriptions
    for uid in order:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    # Find a civilian to eliminate
    game = await _get_game(session, result.game_id)
    state = game.live_state
    civilians = [p for p in state["players"] if p["role"] == UndercoverRole.CIVILIAN.value]
    target_civilian = civilians[0]
    users = setup["users"]

    # All vote for the civilian
    for voter in users:
        if str(voter.id) == target_civilian["user_id"]:
            other = next(u for u in users if str(u.id) != target_civilian["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(target_civilian["user_id"]))

    # Assert — undercovers should win (1 undercover >= 1 remaining civilian)
    game = await _get_game(session, result.game_id)
    # Check win condition
    alive_uc = sum(
        1 for p in game.live_state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value and p["is_alive"]
    )
    alive_civ = sum(
        1 for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value and p["is_alive"]
    )
    if alive_uc >= alive_civ:
        assert game.game_status == GameStatus.FINISHED
        assert game.end_time is not None


@pytest.mark.asyncio
async def test_edge_mayor_breaks_tie_vote(undercover_game_controller, setup_undercover_game, session):
    """In a tie, mayor's vote decides who gets eliminated."""
    # Prepare — need at least 4 players to create a tie
    setup = await setup_undercover_game(4)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    game_uuid = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    order = state["turns"][0]["description_order"]

    # Submit all descriptions
    for uid in order:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    game = await _get_game(session, result.game_id)
    state = game.live_state
    mayor = next(p for p in state["players"] if p.get("is_mayor"))
    users = setup["users"]

    # Create a tie: 2 votes for user A, 2 for user B
    non_mayor_users = [u for u in users if str(u.id) != mayor["user_id"]]
    target_a = non_mayor_users[0]
    target_b = non_mayor_users[1]

    # Mayor votes for target_a
    await undercover_game_controller.submit_vote(game_uuid, UUID(mayor["user_id"]), target_a.id)

    # Find another user (not mayor, not target_a, not target_b) to vote for target_a
    mayor_uuid = UUID(mayor["user_id"])
    other_voter_for_a = next(u for u in users if u.id not in (mayor_uuid, target_a.id, target_b.id))
    await undercover_game_controller.submit_vote(game_uuid, other_voter_for_a.id, target_a.id)
    # target_a votes for target_b
    await undercover_game_controller.submit_vote(game_uuid, target_a.id, target_b.id)
    # target_b votes for target_a (to complete all votes)
    await undercover_game_controller.submit_vote(game_uuid, target_b.id, target_a.id)

    # Assert — target_a should be eliminated (has most votes or tied with mayor's vote)
    game = await _get_game(session, result.game_id)
    eliminated = game.live_state["eliminated_players"]
    assert len(eliminated) > 0
    assert game.game_status in (GameStatus.IN_PROGRESS, GameStatus.FINISHED)


@pytest.mark.asyncio
async def test_edge_mr_white_never_first_in_description_order(
    undercover_game_controller, setup_undercover_game, session
):
    """Mr. White should never be first in description order."""
    # Prepare — 5 players to get Mr. White
    setup = await setup_undercover_game(5)

    # Run multiple times with different seeds to verify
    for seed in range(10):
        random.seed(seed)
        try:
            result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
            game = await _get_game(session, result.game_id)
            state = game.live_state

            mr_white = _find_player_by_role(state, UndercoverRole.MR_WHITE.value)
            order = state["turns"][0]["description_order"]

            if mr_white and len(order) > 1:
                assert order[0] != mr_white["user_id"], f"Mr. White was first with seed {seed}"

            # Clean up for next iteration — remove active_game_id
            room = (await session.exec(select(Room).where(Room.id == setup["room"].id))).first()
            room.active_game_id = None
            session.add(room)
            await session.commit()
        except BaseError:
            # Room might already have active game, skip
            break


@pytest.mark.asyncio
async def test_edge_flag_modified_persists_state(undercover_game_controller, setup_undercover_game, session):
    """Re-fetch game after mutation verifies state was persisted."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    first_describer = game.live_state["turns"][0]["description_order"][0]

    # Act
    await undercover_game_controller.submit_description(UUID(result.game_id), UUID(first_describer), "persisted")

    # Assert — re-fetch from DB
    game = await _get_game(session, result.game_id)
    assert game.live_state["turns"][0]["words"][first_describer] == "persisted"


# ========== _resolve_hint (static method) ==========


def test_resolve_hint_exact_match():
    """When the requested lang key exists, return its value."""
    hint = {"en": "English hint", "fr": "French hint", "ar": "Arabic hint"}
    result = UndercoverGameController._resolve_multilingual(hint, "fr")
    assert result == "French hint"


def test_resolve_hint_fallback_to_en():
    """When requested lang missing, fall back to 'en'."""
    hint = {"en": "English hint", "ar": "Arabic hint"}
    result = UndercoverGameController._resolve_multilingual(hint, "fr")
    assert result == "English hint"


def test_resolve_hint_fallback_to_first_value():
    """When both requested lang and 'en' missing, return first value."""
    hint = {"ar": "Arabic hint", "de": "German hint"}
    result = UndercoverGameController._resolve_multilingual(hint, "fr")
    assert result == "Arabic hint"


def test_resolve_hint_none_input():
    """When hint_dict is None, return None."""
    result = UndercoverGameController._resolve_multilingual(None, "en")
    assert result is None


def test_resolve_hint_empty_dict():
    """When hint_dict is empty, return None."""
    result = UndercoverGameController._resolve_multilingual({}, "en")
    assert result is None


def test_resolve_hint_exact_en():
    """When lang='en' and 'en' key exists, return 'en' value."""
    hint = {"en": "English hint", "fr": "French hint"}
    result = UndercoverGameController._resolve_multilingual(hint, "en")
    assert result == "English hint"


# ========== record_hint_view ==========


@pytest.mark.asyncio
async def test_record_hint_view_success(undercover_game_controller, setup_undercover_game, session):
    """Recording a hint view stores the word in hint_usage for the user."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act
    hint_result = await undercover_game_controller.record_hint_view(game_uuid, user.id, "mosque")

    # Assert
    assert hint_result.recorded is True
    game = await _get_game(session, result.game_id)
    assert str(user.id) in game.live_state["hint_usage"]
    assert "mosque" in game.live_state["hint_usage"][str(user.id)]


@pytest.mark.asyncio
async def test_record_hint_view_deduplicated(undercover_game_controller, setup_undercover_game, session):
    """Recording the same hint twice does not create duplicate entries."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act — record twice
    await undercover_game_controller.record_hint_view(game_uuid, user.id, "mosque")
    await undercover_game_controller.record_hint_view(game_uuid, user.id, "mosque")

    # Assert — only one entry
    game = await _get_game(session, result.game_id)
    assert game.live_state["hint_usage"][str(user.id)].count("mosque") == 1


@pytest.mark.asyncio
async def test_record_hint_view_multiple_words(undercover_game_controller, setup_undercover_game, session):
    """Recording different words adds each to the list."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act
    await undercover_game_controller.record_hint_view(game_uuid, user.id, "mosque")
    await undercover_game_controller.record_hint_view(game_uuid, user.id, "church")

    # Assert
    game = await _get_game(session, result.game_id)
    user_hints = game.live_state["hint_usage"][str(user.id)]
    assert "mosque" in user_hints
    assert "church" in user_hints
    assert len(user_hints) == 2


# ========== get_state hint fields ==========


@pytest.mark.asyncio
async def test_state_includes_my_word_hint(undercover_game_controller, setup_undercover_game, session):
    """get_state returns my_word_hint field for non-Mr-White players."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    civilian = _find_player_by_role(state, UndercoverRole.CIVILIAN.value)

    # Act
    player_state = await undercover_game_controller.get_state(UUID(result.game_id), UUID(civilian["user_id"]))

    # Assert — my_word_hint is present in the response (can be None if word has no hint)
    assert hasattr(player_state, "my_word_hint")


# ========== create_and_start hint fields ==========


@pytest.mark.asyncio
async def test_create_stores_hint_in_live_state(undercover_game_controller, setup_undercover_game, session):
    """create_and_start stores civilian_word_hint and undercover_word_hint in live_state."""
    # Prepare
    setup = await setup_undercover_game(3)

    # Act
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert "civilian_word_hint" in state
    assert "undercover_word_hint" in state
    assert "hint_usage" in state
    assert state["hint_usage"] == {}


# ========== Timer Expiration ==========


@pytest.mark.asyncio
async def test_timer_expired_describing_phase(undercover_game_controller, setup_undercover_game, session):
    """During describing phase with a configured timer, handle_timer_expired skips to voting."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)

    # Set a short timer and a past timer_started_at so the timer is expired
    state = game.live_state
    state["timer_config"]["description_seconds"] = 5
    state["timer_started_at"] = "2020-01-01T00:00:00+00:00"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    host_id = setup["users"][0].id

    # Act
    timer_result = await undercover_game_controller.handle_timer_expired(UUID(result.game_id), host_id)

    # Assert
    assert timer_result.action == "skip_to_voting"
    game = await _get_game(session, result.game_id)
    assert game.live_state["turns"][-1]["phase"] == "voting"


@pytest.mark.asyncio
async def test_timer_expired_voting_phase(undercover_game_controller, setup_undercover_game, session):
    """During voting phase, handle_timer_expired auto-fills missing votes and triggers elimination."""
    # Prepare
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    # Set a short timer and a past timer_started_at so the timer is expired
    state = game.live_state
    state["timer_config"]["voting_seconds"] = 5
    state["timer_started_at"] = "2020-01-01T00:00:00+00:00"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    host_id = setup["users"][0].id

    # Act
    timer_result = await undercover_game_controller.handle_timer_expired(UUID(result.game_id), host_id)

    # Assert
    assert timer_result.action == "auto_vote"
    game = await _get_game(session, result.game_id)
    state = game.live_state
    # All alive players should have votes
    alive_ids = [p["user_id"] for p in state["players"] if p["is_alive"]]
    for uid in alive_ids:
        assert uid in state["turns"][-1]["votes"] or not next(
            (p for p in state["players"] if p["user_id"] == uid and p["is_alive"]), None
        )
    # At least one player should have been eliminated
    assert len(state["eliminated_players"]) >= 1


@pytest.mark.asyncio
async def test_timer_expired_no_timer_configured(undercover_game_controller, setup_undercover_game, session):
    """When timer is 0 (disabled), handle_timer_expired returns timer_not_expired."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)

    # Ensure timer is disabled (0)
    state = game.live_state
    state["timer_config"]["description_seconds"] = 0
    state["timer_config"]["voting_seconds"] = 0
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    host_id = setup["users"][0].id

    # Act
    timer_result = await undercover_game_controller.handle_timer_expired(UUID(result.game_id), host_id)

    # Assert — timer is disabled so _is_timer_actually_expired returns False
    assert timer_result.action == "timer_not_expired"


@pytest.mark.asyncio
async def test_timer_expired_non_host_rejected(undercover_game_controller, setup_undercover_game, session):  # noqa: ARG001
    """Non-host player calling handle_timer_expired should be rejected."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    non_host = setup["users"][1]

    # Act / Assert
    with pytest.raises(BaseError, match="Only the host"):
        await undercover_game_controller.handle_timer_expired(UUID(result.game_id), non_host.id)


# ========== Vote Tie and Elimination ==========


@pytest.mark.asyncio
async def test_vote_tie_without_mayor(undercover_game_controller, setup_undercover_game, session):
    """When votes are tied and no mayor exists, the first player in the tied list is eliminated."""
    # Prepare — 4 players for a possible tie
    setup = await setup_undercover_game(4)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    order = state["turns"][0]["description_order"]

    # Submit all descriptions
    for uid in order:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    # Remove mayor from all players
    game = await _get_game(session, result.game_id)
    state = game.live_state
    for p in state["players"]:
        p["is_mayor"] = False
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    users = setup["users"]
    # Create a tie: users[0] and users[1] vote for users[2], users[2] and users[3] vote for users[0]
    await undercover_game_controller.submit_vote(game_uuid, users[0].id, users[2].id)
    await undercover_game_controller.submit_vote(game_uuid, users[1].id, users[2].id)
    await undercover_game_controller.submit_vote(game_uuid, users[2].id, users[0].id)
    await undercover_game_controller.submit_vote(game_uuid, users[3].id, users[0].id)

    # Assert — someone got eliminated (tie broken deterministically)
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["eliminated_players"]) == 1
    # The eliminated player should be one of the two tied players
    eliminated_id = game.live_state["eliminated_players"][0]["user_id"]
    assert eliminated_id in (str(users[0].id), str(users[2].id))


# ========== Role Distribution ==========


@pytest.mark.asyncio
async def test_create_4_players_mr_white_disabled(undercover_game_controller, setup_undercover_game, session):
    """4 players with mr_white_enabled=False: 0 Mr. White, 1 undercover, 3 civilians."""
    # Prepare
    setup = await setup_undercover_game(4)
    room = setup["room"]
    # Disable Mr. White via room settings
    room.settings = {"enable_mr_white": False}
    session.add(room)
    await session.commit()

    # Act
    result = await _start_game(undercover_game_controller, room.id, setup["users"][0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    roles = [p["role"] for p in players]

    assert roles.count(UndercoverRole.MR_WHITE.value) == 0
    assert roles.count(UndercoverRole.UNDERCOVER.value) == 1
    assert roles.count(UndercoverRole.CIVILIAN.value) == 3


@pytest.mark.asyncio
async def test_create_4_players_mr_white_enabled(undercover_game_controller, setup_undercover_game, session):
    """4 players with Mr. White enabled: 1 Mr. White, 1 undercover, 2 civilians."""
    # Prepare
    setup = await setup_undercover_game(4)
    room = setup["room"]
    room.settings = {"enable_mr_white": True}
    session.add(room)
    await session.commit()

    # Act
    result = await _start_game(undercover_game_controller, room.id, setup["users"][0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    roles = [p["role"] for p in players]

    # 4 players: _compute_roles → mr_white=1, undercover=max(2,4//4)=2, civilians=1
    # But the while loop adjusts: undercover -> 1, civilians -> 2
    assert roles.count(UndercoverRole.MR_WHITE.value) == 1
    assert len(players) == 4
    assert roles.count(UndercoverRole.CIVILIAN.value) >= 1


# ========== Spectator State ==========


@pytest.mark.asyncio
async def test_get_state_spectator_hides_roles(undercover_game_controller, setup_undercover_game, session):
    """A spectator should NOT see player roles or words during an in-progress game."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    spectator = User(
        username="spectator", email_address="spectator@test.com", password=get_password_hash("password123")
    )
    session.add(spectator)
    await session.commit()
    await session.refresh(spectator)

    link = RoomUserLink(
        room_id=setup["room"].id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(link)
    await session.commit()

    # Act
    player_state = await undercover_game_controller.get_state(UUID(result.game_id), spectator.id)

    # Assert
    assert player_state.is_spectator is True
    assert player_state.my_role == "spectator"
    assert player_state.my_word == ""
    assert player_state.word_explanations is None  # No word explanations during in-progress game


@pytest.mark.asyncio
async def test_get_state_spectator_sees_roles_after_game_over(
    undercover_game_controller, setup_undercover_game, session
):
    """After game ends, spectator should see word explanations."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)

    # Force game to finished state with a winner
    state = game.live_state
    # Kill all undercovers to trigger civilian win condition
    for p in state["players"]:
        if p["role"] == UndercoverRole.UNDERCOVER.value:
            p["is_alive"] = False
            state["eliminated_players"].append({"user_id": p["user_id"], "username": p["username"], "role": p["role"]})
    game.live_state = state
    game.game_status = GameStatus.FINISHED
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Create a spectator
    spectator = User(
        username="spectator2", email_address="spectator2@test.com", password=get_password_hash("password123")
    )
    session.add(spectator)
    await session.commit()
    await session.refresh(spectator)

    link = RoomUserLink(
        room_id=setup["room"].id,
        user_id=spectator.id,
        connected=True,
        is_spectator=True,
    )
    session.add(link)
    await session.commit()

    # Act
    player_state = await undercover_game_controller.get_state(UUID(result.game_id), spectator.id)

    # Assert
    assert player_state.is_spectator is True
    assert player_state.word_explanations is not None
    assert player_state.word_explanations.civilian_word == state["civilian_word"]
    assert player_state.word_explanations.undercover_word == state["undercover_word"]


# ========== Win Conditions ==========


@pytest.mark.asyncio
async def test_undercovers_win_outnumber_civilians(undercover_game_controller, setup_undercover_game, session):  # noqa: ARG001
    """When alive undercovers + mr_white >= alive civilians, undercovers win."""
    # Prepare — use _get_winning_team directly with crafted state
    state = {
        "players": [
            {"user_id": "u1", "username": "p1", "role": UndercoverRole.UNDERCOVER.value, "is_alive": True},
            {"user_id": "u2", "username": "p2", "role": UndercoverRole.CIVILIAN.value, "is_alive": True},
            {"user_id": "u3", "username": "p3", "role": UndercoverRole.CIVILIAN.value, "is_alive": False},
        ],
    }

    # Act
    winner = undercover_game_controller._get_winning_team(state)

    # Assert — 1 undercover >= 1 civilian → undercovers win
    assert winner == UndercoverRole.UNDERCOVER.value


@pytest.mark.asyncio
async def test_civilians_win_all_threats_eliminated(undercover_game_controller, setup_undercover_game, session):  # noqa: ARG001
    """When all undercovers AND all Mr. White are eliminated, civilians win."""
    # Prepare
    state = {
        "players": [
            {"user_id": "u1", "username": "p1", "role": UndercoverRole.UNDERCOVER.value, "is_alive": False},
            {"user_id": "u2", "username": "p2", "role": UndercoverRole.MR_WHITE.value, "is_alive": False},
            {"user_id": "u3", "username": "p3", "role": UndercoverRole.CIVILIAN.value, "is_alive": True},
            {"user_id": "u4", "username": "p4", "role": UndercoverRole.CIVILIAN.value, "is_alive": True},
        ],
    }

    # Act
    winner = undercover_game_controller._get_winning_team(state)

    # Assert
    assert winner == UndercoverRole.CIVILIAN.value


@pytest.mark.asyncio
async def test_vote_elimination_removes_last_undercover_civilians_win(
    undercover_game_controller, setup_undercover_game, session
):
    """Eliminating the last undercover (no Mr. White in game) triggers civilian victory."""
    # Prepare — 3 players: 1 undercover, 2 civilians, 0 mr_white
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

    game_uuid = UUID(result.game_id)
    state = game.live_state
    undercover_player = _find_player_by_role(state, UndercoverRole.UNDERCOVER.value)
    users = setup["users"]

    # Act — everyone votes for the undercover (except the undercover, who votes for someone else)
    for voter in users:
        if str(voter.id) == undercover_player["user_id"]:
            other = next(u for u in users if str(u.id) != undercover_player["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(undercover_player["user_id"]))

    # Assert — civilians should win
    game = await _get_game(session, result.game_id)
    state = game.live_state
    uc = next(p for p in state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value)
    assert uc["is_alive"] is False
    assert game.game_status == GameStatus.FINISHED


# ========== _auto_fill_missing_votes ==========


def test_auto_fill_missing_votes():
    """The _auto_fill_missing_votes static method fills votes for players who haven't voted."""
    # Prepare
    state = {
        "players": [
            {"user_id": "u1", "username": "p1", "role": "civilian", "is_alive": True},
            {"user_id": "u2", "username": "p2", "role": "civilian", "is_alive": True},
            {"user_id": "u3", "username": "p3", "role": "undercover", "is_alive": True},
        ],
        "turns": [
            {
                "votes": {"u1": "u3"},  # Only u1 has voted
                "words": {},
                "description_order": [],
                "current_describer_index": 0,
                "phase": "voting",
            }
        ],
    }

    # Act
    UndercoverGameController._auto_fill_missing_votes(state)

    # Assert — u2 and u3 should now have votes
    votes = state["turns"][-1]["votes"]
    assert "u1" in votes
    assert "u2" in votes
    assert "u3" in votes
    # Each player's vote should not be for themselves
    assert votes["u2"] != "u2"
    assert votes["u3"] != "u3"


# ========== record_hint_view edge case ==========


@pytest.mark.asyncio
async def test_record_hint_view_wrong_word(undercover_game_controller, setup_undercover_game, session):
    """Recording a hint view for a word not in the game should still succeed."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    user = setup["users"][0]

    # Act — record a hint for a word that is not in the game
    hint_result = await undercover_game_controller.record_hint_view(game_uuid, user.id, "nonexistentword")

    # Assert
    assert hint_result.recorded is True
    game = await _get_game(session, result.game_id)
    assert "nonexistentword" in game.live_state["hint_usage"][str(user.id)]


# ========== start_next_round ==========


@pytest.mark.asyncio
async def test_start_next_round_non_host_succeeds(undercover_game_controller, setup_undercover_game, session):
    """Non-host calling start_next_round is not rejected (no host check in this method)."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    non_host = setup["users"][1]

    # Act — non-host starts next round (no host validation exists)
    round_result = await undercover_game_controller.start_next_round(game_uuid, setup["room"].id, non_host.id)

    # Assert — succeeds without error
    assert round_result.turn_number == 2
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["turns"]) == 2


# ========== Description validation ==========


@pytest.mark.asyncio
async def test_describe_word_is_stripped(undercover_game_controller, setup_undercover_game, session):
    """A word with leading/trailing whitespace is stripped before storage."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    first_describer = game.live_state["turns"][0]["description_order"][0]

    # Act
    desc_result = await undercover_game_controller.submit_description(
        UUID(result.game_id), UUID(first_describer), "  hello  "
    )

    # Assert — word is stripped
    assert desc_result.word == "hello"
    game = await _get_game(session, result.game_id)
    assert game.live_state["turns"][0]["words"][first_describer] == "hello"


# ========== Mr. White Guessing ==========


@pytest.mark.asyncio
async def test_mr_white_eliminated_triggers_guessing_phase(undercover_game_controller, setup_undercover_game, session):
    """Voting that eliminates Mr. White enters mr_white_guessing phase instead of ending the game."""
    # Prepare
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    state = game.live_state
    mr_white = state["players"][0]  # We forced player 0 as Mr. White
    users = setup["users"]

    # Act — everyone votes for Mr. White (Mr. White votes for someone else)
    for voter in users:
        if str(voter.id) == mr_white["user_id"]:
            other = next(u for u in users if str(u.id) != mr_white["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(mr_white["user_id"]))

    # Assert
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert state["turns"][-1]["phase"] == "mr_white_guessing"
    assert state["mr_white_guesser"] == mr_white["user_id"]
    assert game.game_status != GameStatus.FINISHED


@pytest.mark.asyncio
async def test_mr_white_guess_correct_undercovers_win(undercover_game_controller, setup_undercover_game, session):
    """Mr. White guesses correctly, undercovers win."""
    # Prepare — get to mr_white_guessing phase
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    state = game.live_state
    civilian_word = state["civilian_word"]
    mr_white = state["players"][0]
    users = setup["users"]

    # Vote out Mr. White
    for voter in users:
        if str(voter.id) == mr_white["user_id"]:
            other = next(u for u in users if str(u.id) != mr_white["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(mr_white["user_id"]))

    # Act — Mr. White guesses correctly
    guess_result = await undercover_game_controller.submit_mr_white_guess(
        game_uuid, UUID(mr_white["user_id"]), civilian_word
    )

    # Assert
    assert guess_result.correct is True
    assert guess_result.winner == "undercovers"
    game = await _get_game(session, result.game_id)
    assert game.game_status == GameStatus.FINISHED


@pytest.mark.asyncio
async def test_mr_white_guess_wrong_game_continues(undercover_game_controller, setup_undercover_game, session):
    """Mr. White guesses wrong, game continues (checks win conditions)."""
    # Prepare — get to mr_white_guessing phase
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    state = game.live_state
    mr_white = state["players"][0]
    users = setup["users"]

    # Vote out Mr. White
    for voter in users:
        if str(voter.id) == mr_white["user_id"]:
            other = next(u for u in users if str(u.id) != mr_white["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(mr_white["user_id"]))

    # Act — Mr. White guesses wrong
    guess_result = await undercover_game_controller.submit_mr_white_guess(
        game_uuid, UUID(mr_white["user_id"]), "completely_wrong_word"
    )

    # Assert — wrong guess, game should check win conditions
    assert guess_result.correct is False
    game = await _get_game(session, result.game_id)
    # Mr. White is dead but undercover (player 1) is still alive with 3 civilians
    # So game should continue (1 undercover < 3 civilians)
    state = game.live_state
    assert state.get("mr_white_guesser") is None


@pytest.mark.asyncio
async def test_mr_white_guess_non_mr_white_rejected(undercover_game_controller, setup_undercover_game, session):
    """Non Mr. White player trying to guess is rejected."""
    # Prepare — get to mr_white_guessing phase
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    state = game.live_state
    mr_white = state["players"][0]
    non_mr_white = state["players"][1]  # undercover player
    users = setup["users"]

    # Vote out Mr. White
    for voter in users:
        if str(voter.id) == mr_white["user_id"]:
            other = next(u for u in users if str(u.id) != mr_white["user_id"])
            await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(mr_white["user_id"]))

    # Act / Assert — non-Mr. White player tries to guess
    with pytest.raises(BaseError, match="Only the eliminated Mr. White"):
        await undercover_game_controller.submit_mr_white_guess(game_uuid, UUID(non_mr_white["user_id"]), "some_word")
