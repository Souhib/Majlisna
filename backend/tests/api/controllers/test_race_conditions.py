"""Tests for race condition scenarios across all game types."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.codenames_helpers import CodenamesRole
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import Game
from majlisna.api.schemas.error import (
    BaseError,
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
    NoClueGivenError,
    NotYourTurnError,
    RoundNotPlayingError,
)

# ─── Helpers ──────────────────────────────────────────────────


async def _start_game(controller, room_id, user_id):
    """Start a game and return the result dict."""
    return await controller.create_and_start(room_id, user_id)


async def _start_game_own_session(engine: AsyncEngine, room_id, user_id):
    """create_and_start in a fresh session — for concurrent gather() (see _mutate rationale).

    Concurrent tasks must not share one AsyncSession; production gives each
    request its own, and the room's advisory lock serializes across connections.
    """
    async with AsyncSession(engine, expire_on_commit=False) as concurrent_session:
        return await UndercoverGameController(concurrent_session).create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    """Fetch a game by its string ID."""
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


def _alive_players(state):
    """Get alive players from state."""
    return [p for p in state["players"] if p["is_alive"]]


async def _advance_to_voting(controller, session, game_id_str):
    """Submit all descriptions to reach voting phase."""
    game = await _get_game(session, game_id_str)
    order = game.live_state["turns"][0]["description_order"]
    game_uuid = UUID(game_id_str)
    for uid in order:
        await controller.submit_description(game_uuid, UUID(uid), "word")
    return await _get_game(session, game_id_str)


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


# ─── Test 1: Vote after game manually set to FINISHED ─────────


@pytest.mark.asyncio
async def test_vote_after_phase_reverted_to_describing(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
):
    """Voting when the phase has been changed back to 'describing' should raise an error."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    # Manually revert the phase to 'describing' (simulating a race where phase changed)
    state = game.live_state
    state["turns"][-1]["phase"] = "describing"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Act & Assert — submit_vote should fail because phase is not 'voting'
    alive = _alive_players(game.live_state)
    voter = alive[0]
    target = alive[1]

    with pytest.raises(BaseError, match="not complete"):
        await undercover_game_controller.submit_vote(
            UUID(result.game_id),
            UUID(voter["user_id"]),
            UUID(target["user_id"]),
        )


# ─── Test 2: Vote for a manually killed player ────────────────


@pytest.mark.asyncio
async def test_vote_for_just_eliminated_player(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
):
    """Voting for a player who has been marked as dead should raise CantVoteForDeadPersonError."""
    # Prepare
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    state = game.live_state
    alive = _alive_players(state)

    # Manually mark one player as dead (simulating a prior elimination)
    dead_target = alive[0]
    for p in state["players"]:
        if p["user_id"] == dead_target["user_id"]:
            p["is_alive"] = False
            break
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Pick a voter who is still alive
    voter = alive[1]

    # Act & Assert
    with pytest.raises(CantVoteForDeadPersonError):
        await undercover_game_controller.submit_vote(
            UUID(result.game_id),
            UUID(voter["user_id"]),
            UUID(dead_target["user_id"]),
        )


# ─── Test 3: Description after phase changed to voting ────────


@pytest.mark.asyncio
async def test_description_after_phase_changed_to_voting(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
):
    """Submitting a description after all descriptions are done (phase=voting) should raise."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    # Advance to voting phase — all descriptions submitted
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)
    assert game.live_state["turns"][-1]["phase"] == "voting"

    # Try to submit another description
    any_user_id = UUID(game.live_state["players"][0]["user_id"])

    # Act & Assert
    with pytest.raises(BaseError, match="Not in description phase"):
        await undercover_game_controller.submit_description(
            UUID(result.game_id),
            any_user_id,
            "extra",
        )


# ─── Test 4: Concurrent game starts in the same room ──────────


@pytest.mark.asyncio
async def test_concurrent_game_starts_same_room(
    setup_undercover_game,
    engine: AsyncEngine,
):
    """Starting two games simultaneously in the same room — exactly one succeeds."""
    # Prepare
    setup = await setup_undercover_game(3)
    room_id = setup["room"].id
    host_id = setup["users"][0].id

    # Act — fire two concurrent create_and_start calls, each in its own session
    results = await asyncio.gather(
        _start_game_own_session(engine, room_id, host_id),
        _start_game_own_session(engine, room_id, host_id),
        return_exceptions=True,
    )

    # Assert — exactly one succeeds, the other raises BaseError
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, BaseError)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
    assert "already has an active game" in failures[0].message.lower()


# ─── Test 5: Rematch while game is still in progress ──────────


@pytest.mark.asyncio
async def test_rematch_while_game_in_progress(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,  # noqa: ARG001
):
    """Starting a new game in a room that already has an active game should raise."""
    # Prepare
    setup = await setup_undercover_game(3)
    room_id = setup["room"].id
    host_id = setup["users"][0].id

    await _start_game(undercover_game_controller, room_id, host_id)

    # Act & Assert — second start should fail
    with pytest.raises(BaseError, match="already has an active game"):
        await _start_game(undercover_game_controller, room_id, host_id)


# ─── Test 6: Codenames guess without a clue ───────────────────


@pytest.mark.asyncio
async def test_codenames_guess_without_clue(
    codenames_game_controller: CodenamesGameController,
    setup_codenames_game,
    session: AsyncSession,
):
    """An operative guessing before the spymaster gives a clue should raise NoClueGivenError."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    operative = _find_operative(state, current_team)
    assert operative is not None, "No operative found for the current team"

    # Act & Assert — guess without a clue
    with pytest.raises(NoClueGivenError):
        await codenames_game_controller.guess_card(
            UUID(result.game_id),
            UUID(operative["user_id"]),
            0,
        )


# ─── Test 7: Codenames guess after turn ended ─────────────────


@pytest.mark.asyncio
async def test_codenames_guess_after_turn_ended(
    codenames_game_controller: CodenamesGameController,
    setup_codenames_game,
    session: AsyncSession,
):
    """After ending a turn, the previous team's operative cannot guess (NotYourTurnError)."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)
    state = game.live_state

    current_team = state["current_team"]
    spymaster = _find_spymaster(state, current_team)
    operative = _find_operative(state, current_team)

    # Give a clue so the team can act
    await codenames_game_controller.give_clue(
        UUID(result.game_id),
        UUID(spymaster["user_id"]),
        "testclue",
        1,
    )

    # End the turn voluntarily
    await codenames_game_controller.end_turn(
        UUID(result.game_id),
        UUID(operative["user_id"]),
    )

    # Now the current team has switched — the old operative tries to guess
    # Act & Assert
    with pytest.raises(NotYourTurnError):
        await codenames_game_controller.guess_card(
            UUID(result.game_id),
            UUID(operative["user_id"]),
            0,
        )


# ─── Test 8: Vote for self rejected ───────────────────────────


@pytest.mark.asyncio
async def test_vote_for_self_rejected(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
):
    """A player voting for themselves should raise CantVoteForYourselfError."""
    # Prepare
    setup = await setup_undercover_game(3)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    alive = _alive_players(game.live_state)
    voter = alive[0]

    # Act & Assert
    with pytest.raises(CantVoteForYourselfError):
        await undercover_game_controller.submit_vote(
            UUID(result.game_id),
            UUID(voter["user_id"]),
            UUID(voter["user_id"]),
        )


# ─── Test 9: Dead player cannot vote ──────────────────────────


@pytest.mark.asyncio
async def test_dead_player_cannot_vote(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
):
    """A dead player attempting to vote should raise CantVoteBecauseYouDeadError."""
    # Prepare
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    state = game.live_state
    alive = _alive_players(state)

    # Manually mark one player as dead
    dead_voter = alive[0]
    for p in state["players"]:
        if p["user_id"] == dead_voter["user_id"]:
            p["is_alive"] = False
            break
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    # Pick a living target
    target = alive[1]

    # Act & Assert
    with pytest.raises(CantVoteBecauseYouDeadError):
        await undercover_game_controller.submit_vote(
            UUID(result.game_id),
            UUID(dead_voter["user_id"]),
            UUID(target["user_id"]),
        )


# ─── Test 10: Quiz answer after round phase changed ───────────


@pytest.mark.asyncio
async def test_quiz_answer_after_round_phase_changed(
    wordquiz_game_controller: WordQuizGameController,
    setup_wordquiz_game,
    session: AsyncSession,
):
    """Submitting an answer when round_phase is 'results' should raise RoundNotPlayingError."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2)
    result = await _start_game(wordquiz_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _get_game(session, result.game_id)

    # Manually set round_phase to "results"
    state = game.live_state
    state["round_phase"] = "results"
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    player_id = UUID(state["players"][0]["user_id"])

    # Act & Assert
    with pytest.raises(RoundNotPlayingError):
        await wordquiz_game_controller.submit_answer(
            UUID(result.game_id),
            player_id,
            "some answer",
        )
