from datetime import UTC, datetime, timedelta

from sqlmodel import select

from majlisna.api.controllers.challenge import (
    CHALLENGE_DEFINITIONS,
    DAILY_CHALLENGE_COUNT,
    WEEKLY_CHALLENGE_COUNT,
    ChallengeController,
)
from majlisna.api.models.challenge import ChallengeDefinition, UserChallenge


async def test_seed_challenges(challenge_controller: ChallengeController):
    """Seeding challenges creates exactly as many definitions as CHALLENGE_DEFINITIONS contains."""

    # Arrange — no prior definitions in the database

    # Act
    await challenge_controller.seed_challenges()

    # Assert
    result = await challenge_controller.session.exec(select(ChallengeDefinition))
    definitions = result.all()
    assert len(definitions) == len(CHALLENGE_DEFINITIONS)

    # Verify each seeded definition has a matching code in the source data
    db_codes = {d.code for d in definitions}
    expected_codes = {d["code"] for d in CHALLENGE_DEFINITIONS}
    assert db_codes == expected_codes


async def test_seed_challenges_idempotent(challenge_controller: ChallengeController):
    """Seeding challenges twice does not duplicate any definition records."""

    # Arrange
    await challenge_controller.seed_challenges()

    # Act
    await challenge_controller.seed_challenges()

    # Assert
    result = await challenge_controller.session.exec(select(ChallengeDefinition))
    definitions = result.all()
    assert len(definitions) == len(CHALLENGE_DEFINITIONS)


async def test_get_active_challenges_assigns_new(challenge_controller: ChallengeController, create_user):
    """For a new user with no challenges, get_active_challenges auto-assigns daily and weekly challenges."""

    # Arrange
    user = await create_user(username="newchallenger", email="newchallenger@test.com")
    await challenge_controller.seed_challenges()

    # Act
    active = await challenge_controller.get_active_challenges(user.id)

    # Assert — correct total count returned
    assert len(active) == DAILY_CHALLENGE_COUNT + WEEKLY_CHALLENGE_COUNT

    # Assert — correct split between daily and weekly
    daily = [c for c in active if c.challenge_type == "daily"]
    weekly = [c for c in active if c.challenge_type == "weekly"]
    assert len(daily) == DAILY_CHALLENGE_COUNT
    assert len(weekly) == WEEKLY_CHALLENGE_COUNT

    # Assert — all are incomplete with zero progress
    assert all(c.progress == 0 for c in active)
    assert all(not c.completed for c in active)

    # Assert — database state: UserChallenge rows were persisted
    db_result = await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.user_id == user.id))
    db_challenges = db_result.all()
    assert len(db_challenges) == DAILY_CHALLENGE_COUNT + WEEKLY_CHALLENGE_COUNT


async def test_get_active_challenges_returns_existing(challenge_controller: ChallengeController, create_user):
    """Already assigned challenges are returned without creating duplicates on subsequent calls."""

    # Arrange
    user = await create_user(username="existing", email="existing@test.com")
    await challenge_controller.seed_challenges()
    first_active = await challenge_controller.get_active_challenges(user.id)
    first_ids = {c.id for c in first_active}

    # Act
    second_active = await challenge_controller.get_active_challenges(user.id)
    second_ids = {c.id for c in second_active}

    # Assert — same challenges returned
    assert first_ids == second_ids
    assert len(second_active) == DAILY_CHALLENGE_COUNT + WEEKLY_CHALLENGE_COUNT

    # Assert — no extra rows in DB
    db_result = await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.user_id == user.id))
    db_challenges = db_result.all()
    assert len(db_challenges) == DAILY_CHALLENGE_COUNT + WEEKLY_CHALLENGE_COUNT


async def test_check_progress_play_condition(challenge_controller: ChallengeController, create_user):
    """Playing a game increments progress on challenges with the 'play' condition."""

    # Arrange — manually assign a known play-condition challenge
    user = await create_user(username="player", email="player@test.com")
    await challenge_controller.seed_challenges()

    defn_result = await challenge_controller.session.exec(
        select(ChallengeDefinition).where(ChallengeDefinition.code == "daily_play_any")
    )
    play_any_defn = defn_result.one()

    now = datetime.now(UTC)
    uc = UserChallenge(
        user_id=user.id,
        challenge_id=play_any_defn.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(days=1),
    )
    challenge_controller.session.add(uc)
    await challenge_controller.session.commit()
    await challenge_controller.session.refresh(uc)

    # Act
    await challenge_controller.check_progress(user_id=user.id, game_type="undercover", won=False, role=None)

    # Assert — the play challenge had its progress incremented
    db_result = await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.id == uc.id))
    refreshed = db_result.one()
    assert refreshed.progress == 1


async def test_check_progress_win_condition(challenge_controller: ChallengeController, create_user):
    """Winning a game increments 'win' challenges; losing does not increment them."""

    # Arrange — manually assign a known win-condition challenge
    user = await create_user(username="winner", email="winner@test.com")
    await challenge_controller.seed_challenges()

    defn_result = await challenge_controller.session.exec(
        select(ChallengeDefinition).where(ChallengeDefinition.code == "daily_win_any")
    )
    win_any_defn = defn_result.one()

    now = datetime.now(UTC)
    uc = UserChallenge(
        user_id=user.id,
        challenge_id=win_any_defn.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(days=1),
    )
    challenge_controller.session.add(uc)
    await challenge_controller.session.commit()
    await challenge_controller.session.refresh(uc)

    # Act — play a game but lose
    await challenge_controller.check_progress(user_id=user.id, game_type="undercover", won=False, role=None)

    # Assert — win challenge was NOT incremented
    db_result = await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.id == uc.id))
    refreshed = db_result.one()
    assert refreshed.progress == 0

    # Act — now play a game and win
    await challenge_controller.check_progress(user_id=user.id, game_type="undercover", won=True, role=None)

    # Assert — win challenge was incremented this time
    db_result_after_win = await challenge_controller.session.exec(
        select(UserChallenge).where(UserChallenge.id == uc.id)
    )
    refreshed_after_win = db_result_after_win.one()
    assert refreshed_after_win.progress == 1


async def test_check_progress_completes_challenge(challenge_controller: ChallengeController, create_user):
    """When progress reaches target_count, the challenge is marked as completed."""

    # Arrange — seed definitions and manually assign daily_play_any (target_count=1, condition="play")
    user = await create_user(username="completer", email="completer@test.com")
    await challenge_controller.seed_challenges()

    defn_result = await challenge_controller.session.exec(
        select(ChallengeDefinition).where(ChallengeDefinition.code == "daily_play_any")
    )
    play_any_defn = defn_result.one()

    now = datetime.now(UTC)
    uc = UserChallenge(
        user_id=user.id,
        challenge_id=play_any_defn.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(days=1),
    )
    challenge_controller.session.add(uc)
    await challenge_controller.session.commit()
    await challenge_controller.session.refresh(uc)

    # Act
    newly_completed = await challenge_controller.check_progress(
        user_id=user.id, game_type="undercover", won=False, role=None
    )

    # Assert — the challenge was newly completed (returned by check_progress)
    assert len(newly_completed) == 1
    assert newly_completed[0].completed is True
    assert newly_completed[0].code == "daily_play_any"
    assert newly_completed[0].progress >= play_any_defn.target_count

    # Assert — database state: the challenge is marked completed
    db_uc = await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.id == uc.id))
    refreshed = db_uc.one()
    assert refreshed.completed is True
    assert refreshed.progress == 1


async def test_check_progress_game_type_filter(challenge_controller: ChallengeController, create_user):
    """Game-type-specific challenges only match when the played game type matches."""

    # Arrange — manually assign one codenames-specific and one any-game challenge
    user = await create_user(username="typefilter", email="typefilter@test.com")
    await challenge_controller.seed_challenges()

    codenames_defn = (
        await challenge_controller.session.exec(
            select(ChallengeDefinition).where(ChallengeDefinition.code == "daily_play_codenames")
        )
    ).one()
    any_defn = (
        await challenge_controller.session.exec(
            select(ChallengeDefinition).where(ChallengeDefinition.code == "daily_play_any")
        )
    ).one()

    now = datetime.now(UTC)
    uc_codenames = UserChallenge(
        user_id=user.id,
        challenge_id=codenames_defn.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(days=1),
    )
    uc_any = UserChallenge(
        user_id=user.id,
        challenge_id=any_defn.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(days=1),
    )
    challenge_controller.session.add(uc_codenames)
    challenge_controller.session.add(uc_any)
    await challenge_controller.session.commit()
    await challenge_controller.session.refresh(uc_codenames)
    await challenge_controller.session.refresh(uc_any)

    # Act — play an "undercover" game (not codenames)
    await challenge_controller.check_progress(user_id=user.id, game_type="undercover", won=False, role=None)

    # Assert — codenames-specific challenge was NOT incremented
    refreshed_codenames = (
        await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.id == uc_codenames.id))
    ).one()
    assert refreshed_codenames.progress == 0, "Codenames challenge should not be incremented by an undercover game"

    # Assert — any-game challenge WAS incremented
    refreshed_any = (
        await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.id == uc_any.id))
    ).one()
    assert refreshed_any.progress == 1, "Any-game challenge should be incremented by an undercover game"


# ========== staged inside the game lock (commit=False) ==========


async def _assign_play_any(challenge_controller: ChallengeController, user_id) -> UserChallenge:
    await challenge_controller.seed_challenges()
    definition = (
        await challenge_controller.session.exec(
            select(ChallengeDefinition).where(ChallengeDefinition.code == "daily_play_any")
        )
    ).one()
    now = datetime.now(UTC)
    row = UserChallenge(
        user_id=user_id,
        challenge_id=definition.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(hours=12),
    )
    challenge_controller.session.add(row)
    await challenge_controller.session.commit()
    return row


async def test_check_progress_without_commit_stages_only(challenge_controller: ChallengeController, create_user):
    """record_game_end runs it inside pg_try_advisory_xact_lock: it must not commit.
    A rollback after it leaves the progress where it was."""
    # Prepare
    user = await create_user(username="staged", email="staged@test.com")
    row = await _assign_play_any(challenge_controller, user.id)
    row_id = row.id  # read before the rollback expires the row

    # Act
    completed = await challenge_controller.check_progress(user.id, "undercover", False, None, commit=False)
    await challenge_controller.session.rollback()

    # Assert
    assert [c.code for c in completed] == ["daily_play_any"]
    fresh = (
        await challenge_controller.session.exec(
            select(UserChallenge).where(UserChallenge.id == row_id).execution_options(populate_existing=True)
        )
    ).one()
    assert (fresh.progress, fresh.completed) == (0, False)


async def test_assign_missing_challenges_fills_every_slot(challenge_controller: ChallengeController, create_user):
    """The game end assigns before it counts, so a first game is never lost."""
    # Prepare
    user = await create_user(username="newcomer", email="newcomer@test.com")
    await challenge_controller.seed_challenges()

    # Act
    await challenge_controller.assign_missing_challenges(user.id, commit=False)
    await challenge_controller.session.commit()

    # Assert
    rows = (
        await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.user_id == user.id))
    ).all()
    assert len(rows) == DAILY_CHALLENGE_COUNT + WEEKLY_CHALLENGE_COUNT


async def test_assign_missing_challenges_keeps_what_is_assigned(challenge_controller: ChallengeController, create_user):
    # Prepare
    user = await create_user(username="keeper", email="keeper@test.com")
    kept = await _assign_play_any(challenge_controller, user.id)

    # Act
    await challenge_controller.assign_missing_challenges(user.id)
    await challenge_controller.assign_missing_challenges(user.id)

    # Assert
    rows = (
        await challenge_controller.session.exec(select(UserChallenge).where(UserChallenge.user_id == user.id))
    ).all()
    assert len(rows) == DAILY_CHALLENGE_COUNT + WEEKLY_CHALLENGE_COUNT
    assert kept.id in {r.id for r in rows}


# ========== review R7: definitions that complete on the wrong games ==========


async def _assign(challenge_controller: ChallengeController, user_id, code: str) -> UserChallenge:
    await challenge_controller.seed_challenges()
    definition = (
        await challenge_controller.session.exec(select(ChallengeDefinition).where(ChallengeDefinition.code == code))
    ).one()
    now = datetime.now(UTC)
    row = UserChallenge(
        user_id=user_id,
        challenge_id=definition.id,
        progress=0,
        completed=False,
        assigned_at=now,
        expires_at=now + timedelta(days=7),
    )
    challenge_controller.session.add(row)
    await challenge_controller.session.commit()
    return row


async def _shown(challenge_controller: ChallengeController, user_id, code: str):
    """The challenge as /challenges shows it (progress and completion)."""
    active = await challenge_controller.get_active_challenges(user_id)
    return next(c for c in active if c.code == code)


async def test_win_as_the_undercover_agent_needs_the_undercover_role(
    challenge_controller: ChallengeController, create_user
):
    """It completed on any Undercover win, a civilian's included."""
    # Prepare
    user = await create_user(username="agent", email="agent@test.com")
    await _assign(challenge_controller, user.id, "weekly_win_undercover_role")

    # Act
    await challenge_controller.check_progress(user.id, "undercover", True, "civilian")
    await challenge_controller.check_progress(user.id, "undercover", False, "undercover")

    # Assert
    shown = await _shown(challenge_controller, user.id, "weekly_win_undercover_role")
    assert (shown.progress, shown.completed) == (0, False)

    # Act
    completed = await challenge_controller.check_progress(user.id, "undercover", True, "undercover")

    # Assert
    assert "weekly_win_undercover_role" in [c.code for c in completed]
    shown = await _shown(challenge_controller, user.id, "weekly_win_undercover_role")
    assert (shown.progress, shown.completed) == (1, True)


async def test_play_both_undercover_and_codenames_needs_one_of_each(
    challenge_controller: ChallengeController, create_user
):
    """It completed after any two games, two quizzes included."""
    # Prepare
    user = await create_user(username="both", email="both@test.com")
    await _assign(challenge_controller, user.id, "weekly_play_both")

    # Act — two quizzes, then two Undercover games
    for game_type in ("word_quiz", "mcq_quiz", "undercover", "undercover"):
        await challenge_controller.check_progress(user.id, game_type, False, None)

    # Assert
    shown = await _shown(challenge_controller, user.id, "weekly_play_both")
    assert (shown.progress, shown.target_count, shown.completed) == (1, 2, False)

    # Act
    completed = await challenge_controller.check_progress(user.id, "codenames", False, "operative")

    # Assert — /challenges also assigned the day's own challenges, which may complete too
    done = next(c for c in completed if c.code == "weekly_play_both")
    assert done.progress == 2
    shown = await _shown(challenge_controller, user.id, "weekly_play_both")
    assert (shown.progress, shown.completed) == (2, True)


async def test_play_three_different_games_counts_each_game_once(challenge_controller: ChallengeController, create_user):
    """It completed after any three games, the same one three times included."""
    # Prepare
    user = await create_user(username="three", email="three@test.com")
    await _assign(challenge_controller, user.id, "weekly_play_all_3")

    # Act
    for game_type in ("undercover", "undercover", "undercover", "codenames"):
        await challenge_controller.check_progress(user.id, game_type, False, None)

    # Assert
    shown = await _shown(challenge_controller, user.id, "weekly_play_all_3")
    assert (shown.progress, shown.target_count, shown.completed) == (2, 3, False)

    # Act
    completed = await challenge_controller.check_progress(user.id, "mcq_quiz", False, None)

    # Assert
    assert "weekly_play_all_3" in [c.code for c in completed]
    shown = await _shown(challenge_controller, user.id, "weekly_play_all_3")
    assert (shown.progress, shown.completed) == (3, True)


async def test_seed_brings_a_stored_definition_up_to_date(challenge_controller: ChallengeController):
    """The seed only inserted missing codes, so a corrected definition never reached a database that had it."""
    # Prepare — the definition as an older seed wrote it
    challenge_controller.session.add(
        ChallengeDefinition(
            code="weekly_win_undercover_role",
            description="Win as the Undercover agent this week",
            challenge_type="weekly",
            target_count=1,
            game_type="undercover",
            condition="win",
            role=None,
        )
    )
    await challenge_controller.session.commit()

    # Act
    await challenge_controller.seed_challenges()

    # Assert
    stored = (
        await challenge_controller.session.exec(
            select(ChallengeDefinition)
            .where(ChallengeDefinition.code == "weekly_win_undercover_role")
            .execution_options(populate_existing=True)
        )
    ).one()
    expected = next(d for d in CHALLENGE_DEFINITIONS if d["code"] == "weekly_win_undercover_role")
    assert (stored.condition, stored.role, stored.game_type) == (expected["condition"], "undercover", "undercover")
    assert len((await challenge_controller.session.exec(select(ChallengeDefinition))).all()) == len(
        CHALLENGE_DEFINITIONS
    )
