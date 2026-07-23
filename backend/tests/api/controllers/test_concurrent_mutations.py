"""Tests that concurrent game mutations (via asyncio.gather) produce correct final state."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.codenames_helpers import CodenamesRole, CodenamesTeam
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import Game
from majlisna.api.schemas.error import AlreadyAnsweredError, BaseError, NotYourTurnError

# ─── Helpers ──────────────────────────────────────────────────


async def _mutate(engine: AsyncEngine, controller_cls, method: str, *args):
    """Run ONE mutating controller call in its own fresh session.

    A single AsyncSession (and its underlying asyncpg connection) must not be
    driven by several asyncio tasks at once — doing so raises errors like
    "this transaction is closed". Production gives every request its own session
    via the get_session dependency, so the game's advisory lock serializes the
    mutations across *distinct* connections. Concurrency tests must replicate
    that (a session per task) instead of sharing one session across gather().
    """
    async with AsyncSession(engine, expire_on_commit=False) as concurrent_session:
        controller = controller_cls(concurrent_session)
        return await getattr(controller, method)(*args)


async def _start_game(controller, room_id, user_id):
    """Start a game and return the result."""
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    """Fetch a game by its string ID (expires the session first to avoid a stale snapshot)."""
    # After concurrent tasks committed on other connections, the passed-in
    # session may still hold their pre-mutation snapshot / cached instances.
    await session.rollback()
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


async def _advance_to_voting(controller, session, game_id_str):
    """Submit all descriptions to reach voting phase."""
    game = await _get_game(session, game_id_str)
    order = game.live_state["turns"][0]["description_order"]
    game_uuid = UUID(game_id_str)
    for uid in order:
        await controller.submit_description(game_uuid, UUID(uid), "word")
    return await _get_game(session, game_id_str)


def _alive_players(state):
    """Get alive players from state."""
    return [p for p in state["players"] if p["is_alive"]]


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


# ─── Undercover: Concurrent Votes ────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_votes_all_recorded(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """All 4 non-target players vote for the same target simultaneously — all votes recorded."""
    # Prepare
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    state = game.live_state
    alive = _alive_players(state)
    target = alive[0]
    voters = [p for p in alive if p["user_id"] != target["user_id"]]
    game_uuid = UUID(result.game_id)

    # Act — all 4 voters vote simultaneously, each in its own session
    tasks = [
        _mutate(engine, UndercoverGameController, "submit_vote", game_uuid, UUID(v["user_id"]), UUID(target["user_id"]))
        for v in voters
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert — no exceptions, all votes recorded
    for r in results:
        assert not isinstance(r, Exception), f"Vote raised unexpected exception: {r}"

    game = await _get_game(session, result.game_id)
    current_turn = game.live_state["turns"][-1]
    votes = current_turn.get("votes", {})
    # All 4 voters should have their vote recorded
    for v in voters:
        assert v["user_id"] in votes, f"Vote for {v['user_id']} not recorded"


@pytest.mark.asyncio
async def test_concurrent_votes_trigger_elimination_exactly_once(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """All vote for same target simultaneously — target eliminated exactly once."""
    # Prepare
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    state = game.live_state
    alive = _alive_players(state)
    target = alive[0]
    voters = [p for p in alive if p["user_id"] != target["user_id"]]
    game_uuid = UUID(result.game_id)

    # Act — all alive players must vote (target votes for someone else, rest vote for target)
    # Target votes for a random other player first
    other = next(p for p in alive if p["user_id"] != target["user_id"])
    tasks = [
        _mutate(
            engine, UndercoverGameController, "submit_vote", game_uuid, UUID(target["user_id"]), UUID(other["user_id"])
        ),
    ] + [
        _mutate(engine, UndercoverGameController, "submit_vote", game_uuid, UUID(v["user_id"]), UUID(target["user_id"]))
        for v in voters
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Assert — target eliminated exactly once
    game = await _get_game(session, result.game_id)
    state = game.live_state
    target_player = next(p for p in state["players"] if p["user_id"] == target["user_id"])
    assert target_player["is_alive"] is False

    # Count how many times target appears in eliminated_players list
    eliminated_entries = [e for e in state["eliminated_players"] if e["user_id"] == target["user_id"]]
    assert len(eliminated_entries) == 1, f"Target eliminated {len(eliminated_entries)} times, expected exactly 1"


# ─── Undercover: Concurrent Descriptions ─────────────────────


@pytest.mark.asyncio
async def test_concurrent_descriptions_only_current_describer_succeeds(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """All 5 players submit description simultaneously — only the current describer succeeds."""
    # Prepare
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

    game = await _get_game(session, result.game_id)
    state = game.live_state
    order = state["turns"][0]["description_order"]
    current_describer = order[0]
    game_uuid = UUID(result.game_id)

    # Act — all 5 players try to describe simultaneously, each in its own session
    all_player_ids = [p["user_id"] for p in state["players"]]
    tasks = [
        _mutate(engine, UndercoverGameController, "submit_description", game_uuid, UUID(uid), "testword")
        for uid in all_player_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert — exactly one success (the current describer), others raise BaseError
    successes = []
    errors = []
    for uid, r in zip(all_player_ids, results, strict=False):
        if isinstance(r, BaseError):
            errors.append(uid)
        elif isinstance(r, Exception):
            pytest.fail(f"Unexpected exception type from {uid}: {type(r).__name__}: {r}")
        else:
            successes.append(uid)

    assert current_describer in successes, "Current describer should have succeeded"
    assert len(successes) >= 1, f"Expected at least 1 success but got {len(successes)}"
    assert len(errors) >= 1, "At least one non-describer should have failed"
    # Every success must be a player in the description order (sequentially valid)
    for s in successes:
        assert s in order, f"Successful describer {s} not in description order"


# ─── Word Quiz: Concurrent Answers ───────────────────────────


@pytest.mark.asyncio
async def test_concurrent_quiz_answers_all_recorded(
    wordquiz_game_controller: WordQuizGameController,
    setup_wordquiz_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """3 players submit the correct answer simultaneously — all answers stored, scores correct."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=3)
    result = await _start_game(wordquiz_game_controller, setup["room"].id, setup["users"][0].id)

    game = await _get_game(session, result.game_id)
    state = game.live_state
    correct_answer = state["current_word"]["word_en"]
    game_uuid = UUID(result.game_id)
    player_ids = [p["user_id"] for p in state["players"]]

    # Act — all 3 players submit correct answer simultaneously, each in its own session
    tasks = [
        _mutate(engine, WordQuizGameController, "submit_answer", game_uuid, UUID(uid), correct_answer)
        for uid in player_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert — no unexpected exceptions
    for uid, r in zip(player_ids, results, strict=False):
        assert not isinstance(r, Exception), f"Player {uid} raised: {type(r).__name__}: {r}"

    # All answers should be stored in live_state
    game = await _get_game(session, result.game_id)
    answers = game.live_state["answers"]
    for uid in player_ids:
        assert uid in answers, f"Answer for {uid} not recorded"
        assert answers[uid]["correct"] is True
        assert answers[uid]["points"] > 0


# ─── MCQ Quiz: Concurrent Double Submit ──────────────────────


@pytest.mark.asyncio
async def test_concurrent_mcq_answers_one_per_player(
    mcqquiz_game_controller: McqQuizGameController,
    setup_mcqquiz_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """One player submits the same MCQ answer twice simultaneously — only first counts."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=2)
    result = await _start_game(mcqquiz_game_controller, setup["room"].id, setup["users"][0].id)

    game = await _get_game(session, result.game_id)
    state = game.live_state
    correct_index = state["current_question"]["correct_answer_index"]
    game_uuid = UUID(result.game_id)
    double_submitter = state["players"][0]["user_id"]

    # Act — same player submits twice simultaneously, each in its own session
    tasks = [
        _mutate(engine, McqQuizGameController, "submit_answer", game_uuid, UUID(double_submitter), correct_index),
        _mutate(engine, McqQuizGameController, "submit_answer", game_uuid, UUID(double_submitter), correct_index),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert — one succeeds, one raises AlreadyAnsweredError
    successes = [r for r in results if not isinstance(r, Exception)]
    already_answered = [r for r in results if isinstance(r, AlreadyAnsweredError)]
    other_errors = [r for r in results if isinstance(r, Exception) and not isinstance(r, AlreadyAnsweredError)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(already_answered) == 1, f"Expected 1 AlreadyAnsweredError, got {len(already_answered)}"
    assert len(other_errors) == 0, f"Unexpected errors: {other_errors}"

    # Verify only one answer is stored
    game = await _get_game(session, result.game_id)
    answers = game.live_state["answers"]
    assert double_submitter in answers
    assert answers[double_submitter]["correct"] is True


# ─── Codenames: Concurrent Guesses ───────────────────────────


@pytest.mark.asyncio
async def test_concurrent_codenames_guesses(
    codenames_game_controller: CodenamesGameController,
    setup_codenames_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """After a clue, the non-current-team operative is rejected while the current team operative succeeds."""
    # Prepare
    setup = await setup_codenames_game(4)
    result = await _start_game(codenames_game_controller, setup["room"].id, setup["users"][0].id)

    # Give a clue first
    game = await _get_game(session, result.game_id)
    state = game.live_state
    current_team = state["current_team"]
    other_team = CodenamesTeam.BLUE.value if current_team == CodenamesTeam.RED.value else CodenamesTeam.RED.value

    spymaster = _find_spymaster(state, current_team)
    await codenames_game_controller.give_clue(UUID(result.game_id), UUID(spymaster["user_id"]), "testclue", 2)

    # Find operatives from each team
    current_operative = _find_operative(state, current_team)
    other_operative = _find_operative(state, other_team)
    game_uuid = UUID(result.game_id)

    # Find an unrevealed card index to guess
    game = await _get_game(session, result.game_id)
    board = game.live_state["board"]
    unrevealed_index = next(i for i, card in enumerate(board) if not card["revealed"])

    # Act — both operatives try to guess simultaneously, each in its own session
    tasks = [
        _mutate(
            engine,
            CodenamesGameController,
            "guess_card",
            game_uuid,
            UUID(current_operative["user_id"]),
            unrevealed_index,
        ),
        _mutate(
            engine, CodenamesGameController, "guess_card", game_uuid, UUID(other_operative["user_id"]), unrevealed_index
        ),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert — one succeeds (current team), one is rejected (not your turn)
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) >= 1, "At least the current team operative should succeed"
    assert any(isinstance(r, (NotYourTurnError, BaseError)) for r in results), (
        "The other team's operative should be rejected"
    )


# ─── Cross-Game: No Deadlock ─────────────────────────────────


@pytest.mark.asyncio
async def test_lock_contention_no_deadlock(
    undercover_game_controller: UndercoverGameController,
    setup_undercover_game,
    session: AsyncSession,
    engine: AsyncEngine,
):
    """Submit all 5 votes simultaneously with asyncio.wait_for — completes within timeout (no deadlock)."""
    # Prepare — single game, all concurrent votes on the same lock
    setup = await setup_undercover_game(5)
    result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
    game = await _advance_to_voting(undercover_game_controller, session, result.game_id)

    alive = _alive_players(game.live_state)
    target = alive[0]
    game_uuid = UUID(result.game_id)

    # Build vote tasks — target votes for someone else, rest vote for target — each in its own session
    other = next(p for p in alive if p["user_id"] != target["user_id"])
    tasks = [
        _mutate(
            engine, UndercoverGameController, "submit_vote", game_uuid, UUID(target["user_id"]), UUID(other["user_id"])
        ),
    ] + [
        _mutate(engine, UndercoverGameController, "submit_vote", game_uuid, UUID(p["user_id"]), UUID(target["user_id"]))
        for p in alive
        if p["user_id"] != target["user_id"]
    ]

    # Should complete within 10 seconds — no deadlock despite all 5 contending for same lock
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=10.0,
    )

    # Assert — all tasks completed (no timeout), no unexpected exceptions
    for r in results:
        assert not isinstance(r, asyncio.TimeoutError), "Deadlock detected — operation timed out"
        assert not isinstance(r, Exception), f"Unexpected exception: {type(r).__name__}: {r}"

    # All votes should be recorded
    game = await _get_game(session, result.game_id)
    votes = game.live_state["turns"][-1].get("votes", {})
    assert len(votes) == len(alive)
