"""Tests for the UndercoverGameController."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import MAX_PLAYERS_UNDERCOVER, UNDERCOVER_MR_WHITE_MIN_PLAYERS
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.models.game import GameStatus
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.error import (
    BaseError,
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
    NotEnoughPlayersError,
    PlayerRemovedFromGameError,
    TooManyPlayersError,
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
    """5 players: 1 mr_white, 1 undercover, 3 civilians.

    This test used to assert 2 civilians against 3 impostors — a deal the win rule
    (impostors win at parity) had already decided before the first description.
    """
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
    assert roles.count(UndercoverRole.UNDERCOVER.value) == 1
    assert roles.count(UndercoverRole.CIVILIAN.value) == 3


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


async def _resolve_round_eliminating_a_civilian(controller, result, session):
    """Describe, then have every alive player vote out the same civilian (a civilian
    who is not the victim votes for another civilian), so the round resolves and the
    game continues. Requires a deal with at least three civilians."""
    game_uuid = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    for uid in game.live_state["turns"][-1]["description_order"]:
        await controller.submit_description(game_uuid, UUID(uid), "word")
    game = await _get_game(session, result.game_id)
    civilians = [p["user_id"] for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value]
    victim, fallback = civilians[0], civilians[1]
    for p in _alive_players(game.live_state):
        target = fallback if p["user_id"] == victim else victim
        await controller.submit_vote(game_uuid, UUID(p["user_id"]), UUID(target))
    return victim


@pytest.mark.asyncio
async def test_next_round_appends_turn(undercover_game_controller, setup_undercover_game, session):
    """Once a round is resolved, start_next_round adds a describing turn and the
    state stops reporting the round as resolved."""
    # Prepare — 4 players, Mr. White cannot be dealt below 5: 3 civilians / 1 undercover
    setup = await setup_undercover_game(4)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    await _resolve_round_eliminating_a_civilian(undercover_game_controller, result, session)
    resolved_state = await undercover_game_controller.get_state(game_uuid, setup["users"][0].id)
    assert resolved_state.round_resolved is True
    assert resolved_state.turn_phase == "voting"

    # Act
    round_result = await undercover_game_controller.start_next_round(game_uuid, setup["room"].id, setup["users"][0].id)

    # Assert
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["turns"]) == 2
    assert game.live_state["turns"][1]["phase"] == "describing"
    assert round_result.turn_number == 2
    assert game.game_status == GameStatus.IN_PROGRESS
    next_state = await undercover_game_controller.get_state(game_uuid, setup["users"][0].id)
    assert next_state.round_resolved is False
    assert next_state.turn_number == 2


@pytest.mark.asyncio
async def test_next_round_rejected_while_round_is_open(undercover_game_controller, setup_undercover_game, session):
    """A host cannot skip the round in progress: the call is rejected and no turn is added."""
    # Prepare
    setup = await setup_undercover_game(4)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)

    # Act / Assert
    with pytest.raises(BaseError) as exc_info:
        await undercover_game_controller.start_next_round(game_uuid, setup["room"].id, setup["users"][0].id)
    assert exc_info.value.status_code == 409
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["turns"]) == 1
    assert game.live_state["turns"][0]["phase"] == "describing"


@pytest.mark.asyncio
async def test_next_round_rejected_while_mr_white_guesses(undercover_game_controller, setup_undercover_game, session):
    """An eliminated Mr. White owes a guess: the round is resolved but cannot be followed yet."""
    # Prepare
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    mr_white = _find_player_by_role(game.live_state, UndercoverRole.MR_WHITE.value)
    for p in _alive_players(game.live_state):
        target = mr_white["user_id"] if p["user_id"] != mr_white["user_id"] else setup["users"][1].id
        await undercover_game_controller.submit_vote(game_uuid, UUID(p["user_id"]), UUID(str(target)))
    game = await _get_game(session, result.game_id)
    assert game.live_state["turns"][-1]["phase"] == "mr_white_guessing"

    # Act / Assert
    with pytest.raises(BaseError) as exc_info:
        await undercover_game_controller.start_next_round(game_uuid, setup["room"].id, setup["users"][0].id)
    assert exc_info.value.status_code == 409
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["turns"]) == 1


@pytest.mark.parametrize("mr_white_enabled", [True, False])
@pytest.mark.parametrize("num_players", range(3, MAX_PLAYERS_UNDERCOVER + 1))
def test_compute_roles_civilians_always_outnumber_impostors(num_players, mr_white_enabled):
    """Every deal starts with civilians strictly ahead of undercover + Mr. White.

    The win rule hands the impostors the game at parity, so a deal that starts at
    or past parity is decided before anyone speaks — the old table did exactly that
    for every 4-6 player game with Mr. White on.
    """
    # Act
    roles = UndercoverGameController._compute_roles(num_players, mr_white_enabled)

    # Assert
    civilians = roles.count(UndercoverRole.CIVILIAN.value)
    undercovers = roles.count(UndercoverRole.UNDERCOVER.value)
    mr_whites = roles.count(UndercoverRole.MR_WHITE.value)
    assert len(roles) == num_players
    assert undercovers >= 1
    assert civilians > undercovers + mr_whites
    if not mr_white_enabled or num_players < UNDERCOVER_MR_WHITE_MIN_PLAYERS:
        assert mr_whites == 0
    else:
        assert mr_whites >= 1


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

    # Run repeatedly to exercise different draws. Game draws come from
    # SystemRandom (see api/utils/rng.py), so there is no seed to set — the
    # assertion below is an invariant that must hold for every draw.
    for seed in range(10):
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
async def test_timer_expired_non_host_allowed_gated_by_elapsed(undercover_game_controller, setup_undercover_game):
    """A non-host may call handle_timer_expired; the server gates on the timer, not on host."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    non_host = setup["users"][1]

    # Act — non-host triggers before the timer has actually elapsed
    timer_result = await undercover_game_controller.handle_timer_expired(UUID(result.game_id), non_host.id)

    # Assert — not rejected for being non-host; the server declines only because
    # the timer has not elapsed yet
    assert timer_result.action == "timer_not_expired"


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
    """4 players with Mr. White enabled: no Mr. White (he needs 5), 1 undercover, 3 civilians.

    One undercover plus one Mr. White would already tie two civilians, and the win
    rule gives the impostors the game at parity.
    """
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
    assert len(players) == 4
    assert roles.count(UndercoverRole.MR_WHITE.value) == 0
    assert roles.count(UndercoverRole.UNDERCOVER.value) == 1
    assert roles.count(UndercoverRole.CIVILIAN.value) == 3


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
async def test_start_next_round_non_host_rejected(undercover_game_controller, setup_undercover_game):
    """Non-host calling start_next_round is rejected with 403."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    non_host = setup["users"][1]

    # Act / Assert — non-host is rejected
    with pytest.raises(BaseError) as exc_info:
        await undercover_game_controller.start_next_round(game_uuid, setup["room"].id, non_host.id)
    assert exc_info.value.status_code == 403


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

    # The winner must also be persisted in live_state and surface through
    # get_state. Regression guard: the winner used to be recomputed from alive
    # counts, which cannot express this outcome — undercovers win while civilians
    # are still alive and outnumber them. get_state therefore reported
    # winner=None, the frontend's deriveUndercoverPhase never reached
    # "game_over", word_explanations stayed hidden, and because the backend had
    # already set game_status=FINISHED every further action 400'd: the game
    # soft-locked on the voting screen.
    assert game.live_state["winner"] == "undercovers"
    civilian = next(p for p in game.live_state["players"] if p["role"] == "civilian")
    player_state = await undercover_game_controller.get_state(game_uuid, UUID(civilian["user_id"]))
    assert player_state.winner == "undercovers"
    assert player_state.word_explanations is not None
    assert player_state.word_explanations.civilian_word == civilian_word


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

    # The whole table learns what he guessed, through the round's history (it used to
    # reach the guesser alone, as a toast).
    civilian = next(p for p in state["players"] if p["role"] == "civilian")
    seen = await undercover_game_controller.get_state(game_uuid, UUID(civilian["user_id"]))
    this_round = next(r for r in seen.vote_history if r.round == len(state["turns"]))
    assert this_round.mr_white_guess is not None
    assert this_round.mr_white_guess.word == "completely_wrong_word"
    assert this_round.mr_white_guess.correct is False


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


# ─── Regression: a round resolves exactly once ────────────────


async def _expire_timer(session: AsyncSession, game_id_str: str) -> None:
    """Give the game a real timer and push its start far enough into the past.

    The default room settings use 0 (= no time limit), for which
    _is_timer_actually_expired always answers False — so a timer test has to
    configure one.
    """
    game = await _get_game(session, game_id_str)
    state = game.live_state
    state["timer_config"] = {"description_seconds": 30, "voting_seconds": 30}
    state["timer_started_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()


@pytest.mark.asyncio
async def test_timer_expired_does_not_re_resolve_a_finished_round(
    undercover_game_controller, setup_undercover_game, session
):
    """A second timer-expired call on an already-resolved round changes nothing.

    Once every alive player has voted, the turn keeps phase "voting" until the host
    starts the next round, and `timer_started_at` still points at the voting
    deadline — so the timer reads as expired for that whole gap. The handler used to
    re-run the tally over the SAME votes on every call: one more player died,
    `eliminated_players` grew a duplicate entry (which desynchronises vote history),
    and the client's timer callback kept firing, so it repeated indefinitely — one
    DB write and one Socket.IO broadcast per cycle.
    """
    # Prepare — 5 players with forced roles (1 undercover, 4 civilians) so that
    # voting out a civilian leaves the game running: 1 undercover vs 3 civilians
    # is not a win for either side.
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    state["players"][0]["role"] = UndercoverRole.UNDERCOVER.value
    for player in state["players"][1:]:
        player["role"] = UndercoverRole.CIVILIAN.value
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    game = await _get_game(session, result.game_id)
    for uid in game.live_state["turns"][0]["description_order"]:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    target = players[4]["user_id"]  # a civilian
    for player in players:
        vote_for = target if player["user_id"] != target else players[0]["user_id"]
        await undercover_game_controller.submit_vote(game_uuid, UUID(player["user_id"]), UUID(vote_for))

    game = await _get_game(session, result.game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    alive_after_vote = len(_alive_players(game.live_state))
    eliminated_after_vote = len(game.live_state["eliminated_players"])
    assert eliminated_after_vote == 1
    await _expire_timer(session, result.game_id)

    # Act — the (already resolved) round's timer expires, twice.
    first = await undercover_game_controller.handle_timer_expired(game_uuid, setup["users"][0].id)
    second = await undercover_game_controller.handle_timer_expired(game_uuid, setup["users"][0].id)

    # Assert
    assert first.action == "round_already_resolved"
    assert second.action == "round_already_resolved"
    game = await _get_game(session, result.game_id)
    assert len(_alive_players(game.live_state)) == alive_after_vote
    assert len(game.live_state["eliminated_players"]) == eliminated_after_vote


@pytest.mark.asyncio
async def test_mr_white_guess_timeout_leaves_a_playable_phase(
    undercover_game_controller, setup_undercover_game, session
):
    """Timing out the Mr. White guess must not wedge the turn.

    The handler dropped `mr_white_guesser` but left the phase on
    "mr_white_guessing", so guessing 403'd (nobody matched the guesser) while
    voting and describing both rejected the phase — only the host's next-round call
    could rescue the game.
    """
    # Prepare — reach the mr_white_guessing phase by voting Mr. White out.
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    mr_white = _find_player_by_role(game.live_state, UndercoverRole.MR_WHITE.value)
    voters = [p["user_id"] for p in game.live_state["players"] if p["is_alive"]]
    for voter in voters:
        target = mr_white["user_id"] if voter != mr_white["user_id"] else voters[1]
        await undercover_game_controller.submit_vote(game_uuid, UUID(voter), UUID(target))

    game = await _get_game(session, result.game_id)
    assert game.live_state["turns"][-1]["phase"] == "mr_white_guessing"
    await _expire_timer(session, result.game_id)

    # Act — the guess timer expires.
    response = await undercover_game_controller.handle_timer_expired(game_uuid, setup["users"][0].id)

    # Assert — no dangling guesser, and the phase is one the game can leave.
    assert response.action == "mr_white_guess_timeout"
    game = await _get_game(session, result.game_id)
    state = game.live_state
    assert "mr_white_guesser" not in state
    assert state["turns"][-1]["phase"] in ("voting", "game_over")
    # the round records that his time ran out: no word, not the word
    assert state["turns"][-1]["mr_white_guess"] == {"word": None, "correct": False}

    # And landing there does not re-open the elimination.
    eliminated_count = len(state["eliminated_players"])
    await _expire_timer(session, result.game_id)
    await undercover_game_controller.handle_timer_expired(game_uuid, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    assert len(game.live_state["eliminated_players"]) == eliminated_count


@pytest.mark.asyncio
async def test_cannot_start_undercover_with_one_player(undercover_game_controller, setup_undercover_game):
    """A lone host cannot start Undercover.

    MIN_PLAYERS_FOR_GAME existed but was never passed to _prepare_game_start, so the
    base default of 1 applied and _compute_roles produced one undercover and ZERO
    civilians — won on paper the moment anyone checked, and unplayable in practice
    since the only player may not vote for themselves.
    """
    setup = await setup_undercover_game(1)
    with pytest.raises(NotEnoughPlayersError):
        await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)


@pytest.mark.asyncio
async def test_cannot_start_undercover_with_two_players(undercover_game_controller, setup_undercover_game):
    """Two players is a coin flip on the first tie-break, not a game of Undercover."""
    setup = await setup_undercover_game(2)
    with pytest.raises(NotEnoughPlayersError):
        await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)


@pytest.mark.asyncio
async def test_cannot_start_undercover_above_the_supported_player_count(
    undercover_game_controller, setup_undercover_game
):
    """Undercover is designed for at most 12 players.

    Only the minimum was enforced. Role distribution scales past 12 without erroring,
    so a 20-player room quietly produced a game nobody had played or tested.
    """
    setup = await setup_undercover_game(MAX_PLAYERS_UNDERCOVER + 1)
    with pytest.raises(TooManyPlayersError):
        await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)


@pytest.mark.asyncio
async def test_vote_history_pairs_each_round_with_its_own_elimination(
    undercover_game_controller, setup_undercover_game, session
):
    """Each elimination carries the round that produced it.

    Vote history and the post-game summary used to pair `eliminated_players[i]` with
    `turns[i]` by POSITION — an implicit invariant that produced a wrong history as
    soon as anything appended out of step (a duplicate elimination, or a drop-out,
    which is not a round result at all).
    """
    # Prepare — 5 players, forced roles so the first elimination doesn't end the game
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game_uuid = UUID(result.game_id)
    game = await _get_game(session, result.game_id)
    state = game.live_state
    state["players"][0]["role"] = UndercoverRole.UNDERCOVER.value
    for player in state["players"][1:]:
        player["role"] = UndercoverRole.CIVILIAN.value
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    game = await _get_game(session, result.game_id)
    for uid in game.live_state["turns"][0]["description_order"]:
        await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    target = players[4]["user_id"]
    for player in players:
        vote_for = target if player["user_id"] != target else players[0]["user_id"]
        await undercover_game_controller.submit_vote(game_uuid, UUID(player["user_id"]), UUID(vote_for))

    # Assert
    game = await _get_game(session, result.game_id)
    eliminated = game.live_state["eliminated_players"]
    assert len(eliminated) == 1
    assert eliminated[0]["round"] == 1
    assert eliminated[0]["user_id"] == target

    history = undercover_game_controller._build_vote_history(game.live_state)
    assert len(history) == 1
    assert history[0]["round"] == 1
    assert history[0]["eliminated"]["user_id"] == target


# ========== Vote targets stay secret until the round is decided ==========


@pytest.mark.asyncio
async def test_open_round_hides_who_everyone_else_voted_for(undercover_game_controller, setup_undercover_game, session):
    """The payload must not name a target other players have not committed against yet.

    The UI has only ever rendered "who has voted" out of this dict, but it carried
    every target — so anyone with the network tab open watched the tally build and
    voted last with perfect information. In a social-deduction round that is the game.
    """
    # Prepare — 5 players in the voting phase, two votes already cast
    setup, result, game = await _setup_mr_white_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    alive = _alive_players(game.live_state)
    voter, other_voter, target = alive[2], alive[3], alive[4]

    await undercover_game_controller.submit_vote(game_uuid, UUID(voter["user_id"]), UUID(target["user_id"]))
    await undercover_game_controller.submit_vote(game_uuid, UUID(other_voter["user_id"]), UUID(target["user_id"]))

    # Act — the first voter reads the state back
    state = await undercover_game_controller.get_state(game_uuid, UUID(voter["user_id"]))

    # Assert — both voters are visibly done, but only the caller's own choice is named
    assert set(state.votes) == {voter["user_id"], other_voter["user_id"]}
    assert state.votes[voter["user_id"]] == target["user_id"]
    assert state.votes[other_voter["user_id"]] == ""
    # ...and the history panel does not publish the open round through the back door
    assert all(entry["round"] != state.turn_number for entry in state.vote_history)


@pytest.mark.asyncio
async def test_resolved_round_publishes_every_vote(undercover_game_controller, setup_undercover_game, session):
    """Once the elimination has happened the targets are public — the recap shows them."""
    # Prepare — 3 players, everyone votes so the round resolves
    setup, result, game = await _setup_voting_phase(undercover_game_controller, setup_undercover_game, session)
    game_uuid = UUID(result.game_id)
    alive = _alive_players(game.live_state)

    await undercover_game_controller.submit_vote(game_uuid, UUID(alive[0]["user_id"]), UUID(alive[1]["user_id"]))
    await undercover_game_controller.submit_vote(game_uuid, UUID(alive[1]["user_id"]), UUID(alive[0]["user_id"]))
    await undercover_game_controller.submit_vote(game_uuid, UUID(alive[2]["user_id"]), UUID(alive[0]["user_id"]))

    # Act
    state = await undercover_game_controller.get_state(game_uuid, UUID(alive[2]["user_id"]))

    # Assert — every target is named now
    assert state.votes[alive[0]["user_id"]] == alive[1]["user_id"]
    assert state.votes[alive[1]["user_id"]] == alive[0]["user_id"]


# ─── Arabic term forms (TermScript) ───────────────────────────
#
# The Arabic form follows exactly the visibility rule of the Latin word: a player
# gets their OWN word's forms, Mr. White and spectators get none, and both words
# only appear once the game is over. Every get_state does one batched lookup.

MOSQUE_AR = ("مسجد", "مَسْجِد")
CHURCH_AR = ("كنيسة", "كَنِيسَة")
FIXTURE_SCRIPTS = {"mosque": MOSQUE_AR, "church": CHURCH_AR}


def _arabic_forms_in(payload: str) -> set[str]:
    """Which of the fixture's Arabic forms appear anywhere in a serialised state."""
    return {form for forms in FIXTURE_SCRIPTS.values() for form in forms if form and form in payload}


async def _vote_out_mr_white(controller, setup, game_uuid, mr_white) -> None:
    """Everyone votes for Mr. White (who votes for someone else) — enters the guessing phase."""
    users = setup["users"]
    for voter in users:
        if str(voter.id) == mr_white["user_id"]:
            other = next(u for u in users if str(u.id) != mr_white["user_id"])
            await controller.submit_vote(game_uuid, voter.id, other.id)
        else:
            await controller.submit_vote(game_uuid, voter.id, UUID(mr_white["user_id"]))


async def _reach_mr_white_guess_with_civilian_church(controller, setup_undercover_game, session):
    """5-player game where the civilians hold "church", voted to Mr. White's guess."""
    setup, result, game = await _setup_mr_white_voting_phase(controller, setup_undercover_game, session)
    state = game.live_state
    state["civilian_word"], state["undercover_word"] = "church", "mosque"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    game_uuid = UUID(result.game_id)
    mr_white = state["players"][0]
    await _vote_out_mr_white(controller, setup, game_uuid, mr_white)
    return setup, game_uuid, mr_white


@pytest.mark.asyncio
async def test_get_state_gives_each_player_only_their_own_word_in_arabic(
    undercover_game_controller, setup_undercover_game, session, create_term_scripts, count_statements
):
    """Civilians get the civilian word's Arabic, the undercover theirs — never the other's."""
    # Prepare
    await create_term_scripts(FIXTURE_SCRIPTS)
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    players = game.live_state["players"]
    counter = count_statements("term_script")

    # Act
    states = [await undercover_game_controller.get_state(UUID(result.game_id), UUID(p["user_id"])) for p in players]

    # Assert
    assert counter.count == len(players)  # one batched lookup per request
    for player_state in states:
        own_ar, own_vocalized = FIXTURE_SCRIPTS[player_state.my_word]
        assert player_state.my_word_ar == own_ar
        assert player_state.my_word_ar_vocalized == own_vocalized
        assert player_state.word_explanations is None
        assert _arabic_forms_in(player_state.model_dump_json()) == {own_ar, own_vocalized}


@pytest.mark.asyncio
async def test_get_state_gives_mr_white_no_arabic_word(
    undercover_game_controller, setup_undercover_game, session, create_term_scripts
):
    """Mr. White has no word, so no Arabic form either — not even the civilians'."""
    # Prepare
    await create_term_scripts(FIXTURE_SCRIPTS)
    _setup, result, game = await _setup_mr_white_voting_phase(
        undercover_game_controller, setup_undercover_game, session
    )
    mr_white = game.live_state["players"][0]

    # Act
    state = await undercover_game_controller.get_state(UUID(result.game_id), UUID(mr_white["user_id"]))

    # Assert
    assert state.my_role == UndercoverRole.MR_WHITE.value
    assert state.my_word_ar is None
    assert state.my_word_ar_vocalized is None
    assert _arabic_forms_in(state.model_dump_json()) == set()


@pytest.mark.asyncio
async def test_get_state_gives_a_spectator_no_arabic_word_mid_game(
    undercover_game_controller, setup_undercover_game, session, create_term_scripts, count_statements
):
    """A spectator sees no word in any script until the game is over — and costs no lookup."""
    # Prepare
    await create_term_scripts(FIXTURE_SCRIPTS)
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    spectator = User(
        username="arabic_spectator", email_address="arabic_spectator@test.com", password=get_password_hash("pw123456")
    )
    session.add(spectator)
    await session.commit()
    await session.refresh(spectator)
    session.add(RoomUserLink(room_id=setup["room"].id, user_id=spectator.id, connected=True, is_spectator=True))
    await session.commit()
    counter = count_statements("term_script")

    # Act
    state = await undercover_game_controller.get_state(UUID(result.game_id), spectator.id)

    # Assert
    assert state.is_spectator is True
    assert state.my_word_ar is None
    assert _arabic_forms_in(state.model_dump_json()) == set()
    assert counter.count == 0


@pytest.mark.asyncio
async def test_word_explanations_carry_both_arabic_forms_once_the_game_is_over(
    undercover_game_controller, setup_undercover_game, session, create_term_scripts
):
    """The game-over screen names both words, so it gets both Arabic forms."""
    # Prepare
    await create_term_scripts(FIXTURE_SCRIPTS)
    _setup, game_uuid, mr_white = await _reach_mr_white_guess_with_civilian_church(
        undercover_game_controller, setup_undercover_game, session
    )
    await undercover_game_controller.submit_mr_white_guess(game_uuid, UUID(mr_white["user_id"]), "church")
    game = await _get_game(session, str(game_uuid))
    civilian = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value)

    # Act
    state = await undercover_game_controller.get_state(game_uuid, UUID(civilian["user_id"]))

    # Assert
    assert state.winner == "undercovers"
    explanations = state.word_explanations
    assert explanations is not None
    assert (explanations.civilian_word, explanations.civilian_word_ar) == ("church", CHURCH_AR[0])
    assert explanations.civilian_word_ar_vocalized == CHURCH_AR[1]
    assert (explanations.undercover_word, explanations.undercover_word_ar) == ("mosque", MOSQUE_AR[0])
    assert explanations.undercover_word_ar_vocalized == MOSQUE_AR[1]


@pytest.mark.asyncio
async def test_arabic_forms_are_null_for_a_word_without_a_term_script(
    undercover_game_controller, setup_undercover_game, session
):
    """A word an admin added without an Arabic row still plays — its forms are just null."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    civilian = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value)

    # Act
    state = await undercover_game_controller.get_state(UUID(result.game_id), UUID(civilian["user_id"]))

    # Assert
    assert state.my_word in FIXTURE_SCRIPTS
    assert state.my_word_ar is None
    assert state.my_word_ar_vocalized is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guess", "expected_correct"),
    [
        # Latin
        ("church", True),
        ("  CHURCH ", True),
        # Arabic — plain, vocalised, with the article, with a folded taa marbuta
        ("كنيسة", True),
        ("كَنِيسَة", True),
        ("الكنيسة", True),
        ("كنيسه", True),
        # Wrong — including the undercover word, in either script
        ("mosque", False),
        ("مسجد", False),
        ("كنيس", False),
    ],
)
async def test_mr_white_guess_accepts_the_civilian_word_in_latin_or_arabic(
    undercover_game_controller, setup_undercover_game, session, create_term_scripts, guess, expected_correct
):
    """An Arabic-speaking Mr. White typing the civilian word in Arabic wins, like typing the Latin."""
    # Prepare
    await create_term_scripts(FIXTURE_SCRIPTS)
    _setup, game_uuid, mr_white = await _reach_mr_white_guess_with_civilian_church(
        undercover_game_controller, setup_undercover_game, session
    )

    # Act
    response = await undercover_game_controller.submit_mr_white_guess(game_uuid, UUID(mr_white["user_id"]), guess)

    # Assert
    assert response.correct is expected_correct
    game = await _get_game(session, str(game_uuid))
    if expected_correct:
        assert response.winner == "undercovers"
        assert game.game_status == GameStatus.FINISHED
        assert game.live_state["winner"] == "undercovers"
    else:
        assert game.game_status == GameStatus.IN_PROGRESS
        assert game.live_state["turns"][-1]["phase"] == "voting"
    assert "mr_white_guesser" not in game.live_state


@pytest.mark.asyncio
async def test_game_over_meanings_and_colophon_in_the_requested_language(
    undercover_game_controller, setup_undercover_game, session
):
    """At game over both meanings come back in `lang` (like my_word_hint), with who hosted and when.

    The host's name is the one who STARTED the game, kept in live_state, so a host
    transfer afterwards does not rename the majlis.
    """
    # Prepare
    setup, game_uuid, mr_white = await _reach_mr_white_guess_with_civilian_church(
        undercover_game_controller, setup_undercover_game, session
    )
    starter = setup["users"][0]
    await undercover_game_controller.submit_mr_white_guess(game_uuid, UUID(mr_white["user_id"]), "church")
    game = await _get_game(session, str(game_uuid))
    game.live_state["civilian_word_hint"] = {"en": "A church", "ar": "كنيسة", "fr": "Une église"}
    game.live_state["undercover_word_hint"] = {"en": "A mosque", "ar": "مسجد"}
    flag_modified(game, "live_state")
    session.add(game)
    room = (await session.exec(select(Room).where(Room.id == game.room_id))).one()
    room.owner_id = setup["users"][1].id  # the host moved on after the game
    session.add(room)
    await session.commit()
    civilian = next(p for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value)

    # Act
    state_ar = await undercover_game_controller.get_state(game_uuid, UUID(civilian["user_id"]), lang="ar")
    state_fr = await undercover_game_controller.get_state(game_uuid, UUID(civilian["user_id"]), lang="fr")

    # Assert
    assert state_ar.word_explanations is not None
    assert state_ar.word_explanations.civilian_word_hint == "كنيسة"
    assert state_ar.word_explanations.undercover_word_hint == "مسجد"
    assert state_ar.my_word_hint == "كنيسة"
    assert state_fr.word_explanations is not None
    assert state_fr.word_explanations.undercover_word_hint == "A mosque"  # no French → English
    assert state_ar.host_username == starter.username
    stored = await _get_game(session, str(game_uuid))
    assert stored.live_state["host_username"] == starter.username
    assert state_ar.started_at is not None and state_ar.ended_at is not None
    assert state_ar.started_at.utcoffset() is not None and state_ar.ended_at.utcoffset() is not None
    assert state_ar.ended_at >= state_ar.started_at


@pytest.mark.asyncio
async def test_colophon_falls_back_to_the_current_host_for_an_older_game(
    undercover_game_controller, setup_undercover_game, session
):
    """A game started before the host's name was stored reads the room's current host."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await undercover_game_controller.create_and_start(setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    del game.live_state["host_username"]
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act
    state = await undercover_game_controller.get_state(UUID(result.game_id), setup["users"][1].id)

    # Assert
    assert state.host_username == setup["users"][0].username
    assert state.ended_at is None
