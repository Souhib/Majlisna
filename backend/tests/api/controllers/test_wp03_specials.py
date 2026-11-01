"""WP-03, owner rule (f): the five special achievements are implemented, not hidden.

``perfect_undercover``, ``sweep_victory``, ``assassin_finder``, ``unanimous_vote`` and
``last_survivor`` had ``stat_field: None`` ("checked via custom logic") and no logic
anywhere: ``check_achievements`` skipped them and nothing else referenced the codes,
so 5 of the 45 badges could never unlock (PD-05; 12 counting the stat fields nothing
wrote). They are now computed by ``record_game_end`` from the final ``live_state``,
for scorable players only, and unlocked through ``AchievementController.unlock_special``.

One hand-built final state per achievement, each with its positive case and the
negative the rule exists for. Plus the introspection: no badge without a writer.
"""

import re
from pathlib import Path
from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import CODENAMES_REVEAL_LOG_KEY, LEFT_PLAYER_IDS_KEY, UNDERCOVER_AUTO_VOTERS_KEY
from majlisna.api.controllers.achievement import ACHIEVEMENT_DEFINITIONS, AchievementController
from majlisna.api.controllers.game_end_stats import (
    SPECIAL_ACHIEVEMENT_RULES,
    codenames_winners,
    record_game_end,
    undercover_winners,
)
from majlisna.api.models.stats import AchievementDefinition, UserAchievement
from majlisna.api.models.table import User

CONTROLLERS = Path(__file__).resolve().parents[3] / "majlisna" / "api" / "controllers"


async def _make_users(create_user, count: int, prefix: str) -> list[User]:
    return [await create_user(username=f"{prefix}{i}", email=f"{prefix}{i}@test.com") for i in range(count)]


async def _unlocked(session: AsyncSession, user_id: UUID) -> set[str]:
    rows = (
        await session.exec(
            select(AchievementDefinition.code)
            .join(UserAchievement, UserAchievement.achievement_id == AchievementDefinition.id)  # ty: ignore[invalid-argument-type]
            .where(UserAchievement.user_id == user_id)
            .where(UserAchievement.unlocked_at.is_not(None))  # ty: ignore[unresolved-attribute]
            .execution_options(populate_existing=True)
        )
    ).all()
    return set(rows)


def _uc(user: User, role: str, *, alive: bool = True) -> dict:
    return {"user_id": str(user.id), "username": user.username, "role": role, "is_alive": alive, "is_mayor": False}


def _cn(user: User, team: str, role: str) -> dict:
    return {"user_id": str(user.id), "username": user.username, "team": team, "role": role}


def _turn(*votes: tuple[User, User], resolved: bool = True) -> dict:
    """A turn whose ``votes`` are the given (voter, target) pairs."""
    return {
        "votes": {str(voter.id): str(target.id) for voter, target in votes},
        "words": {},
        "phase": "voting",
        "resolved": resolved,
    }


def _reveal(card_index: int, team: str, card_type: str, voters: list[User], clue_turn: int = 1) -> dict:
    return {
        "card_index": card_index,
        "team": team,
        "card_type": card_type,
        "voter_ids": [str(v.id) for v in voters],
        "clue_turn": clue_turn,
    }


async def _end_undercover(session: AsyncSession, state: dict) -> list[dict]:
    unlocked = await record_game_end(
        session,
        state,
        game_type="undercover",
        winners=undercover_winners(state, state["winner"]),
        default_role="civilian",
    )
    await session.commit()
    return unlocked


async def _end_codenames(session: AsyncSession, state: dict) -> list[dict]:
    unlocked = await record_game_end(
        session,
        state,
        game_type="codenames",
        winners=codenames_winners(state, state["winner"]),
        default_role="operative",
    )
    await session.commit()
    return unlocked


@pytest.fixture(autouse=True)
async def _seeded(session: AsyncSession):
    await AchievementController(session).seed_achievements()


# ── perfect_undercover ────────────────────────────────────────────────────


async def test_perfect_undercover_unlocks_for_an_undercover_who_won_with_no_vote_against(
    session: AsyncSession, create_user
):
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "pu")
    state = {
        "players": [
            _uc(civ_a, "civilian", alive=False),
            _uc(civ_b, "civilian", alive=False),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover"),
        ],
        "turns": [
            _turn((civ_a, civ_b), (civ_b, civ_a), (civ_c, civ_a), (under, civ_a)),
            _turn((civ_b, civ_c), (civ_c, civ_b), (under, civ_b)),
        ],
        "winner": "undercovers",
    }

    # Act
    unlocked = await _end_undercover(session, state)

    # Assert
    assert "perfect_undercover" in await _unlocked(session, under.id)
    assert "perfect_undercover" not in await _unlocked(session, civ_c.id)
    toasts = {entry["user_id"]: {a["code"] for a in entry["achievements"]} for entry in unlocked}
    assert "perfect_undercover" in toasts[str(under.id)]


async def test_one_vote_against_the_undercover_means_no_perfect_undercover(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "pun")
    state = {
        "players": [
            _uc(civ_a, "civilian", alive=False),
            _uc(civ_b, "civilian", alive=False),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover"),
        ],
        "turns": [
            _turn((civ_a, under), (civ_b, civ_a), (civ_c, civ_a), (under, civ_a)),
            _turn((civ_b, civ_c), (civ_c, civ_b), (under, civ_b)),
        ],
        "winner": "undercovers",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert "perfect_undercover" not in await _unlocked(session, under.id)


async def test_a_losing_undercover_never_gets_perfect_undercover(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "pul")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [_turn((civ_a, civ_b), (civ_b, civ_a), (civ_c, civ_a), (under, civ_a))],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert "perfect_undercover" not in await _unlocked(session, under.id)


# ── unanimous_vote ────────────────────────────────────────────────────────


async def test_unanimous_vote_unlocks_for_every_voter_but_the_target(session: AsyncSession, create_user):
    """Everyone but the target named the target: the target cannot vote for themselves,
    so their own ballot is not part of the table's verdict. Reading "every ballot" made
    the badge unreachable in play (every alive player votes, or is auto-voted)."""
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "uv")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [_turn((civ_a, under), (civ_b, under), (civ_c, under), (under, civ_a))],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    for voter in (civ_a, civ_b, civ_c):
        assert "unanimous_vote" in await _unlocked(session, voter.id), voter.username
    assert "unanimous_vote" not in await _unlocked(session, under.id)


async def test_a_split_vote_is_not_a_unanimous_vote(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "uvs")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [_turn((civ_a, under), (civ_b, under), (civ_c, civ_a), (under, civ_a))],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    for player in (civ_a, civ_b, civ_c, under):
        assert "unanimous_vote" not in await _unlocked(session, player.id), player.username


async def test_a_ballot_cast_by_the_timer_is_not_a_unanimous_vote(session: AsyncSession, create_user):
    """A silent player's vote is drawn at random when the clock runs out: a draw that
    happened to agree is not the table agreeing."""
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "uva")
    turn = _turn((civ_a, under), (civ_b, under), (civ_c, under), (under, civ_a))
    turn[UNDERCOVER_AUTO_VOTERS_KEY] = [str(civ_c.id)]
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [turn],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    for player in (civ_a, civ_b, civ_c):
        assert "unanimous_vote" not in await _unlocked(session, player.id), player.username


async def test_two_votes_are_not_a_unanimous_vote(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, under = await _make_users(create_user, 3, "uvn")
    state = {
        "players": [_uc(civ_a, "civilian"), _uc(civ_b, "civilian"), _uc(under, "undercover", alive=False)],
        "turns": [_turn((civ_a, under), (civ_b, under), (under, civ_a))],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert "unanimous_vote" not in await _unlocked(session, civ_a.id)
    assert "unanimous_vote" not in await _unlocked(session, civ_b.id)


async def test_an_open_round_is_not_a_unanimous_vote(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "uvo")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian"),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [_turn((civ_a, under), (civ_b, under), (civ_c, under), resolved=False)],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert "unanimous_vote" not in await _unlocked(session, civ_a.id)


# ── last_survivor ─────────────────────────────────────────────────────────


async def test_last_survivor_unlocks_for_the_only_living_member_of_the_winning_side(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, under, mr_white = await _make_users(create_user, 4, "ls")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian", alive=False),
            _uc(under, "undercover"),
            _uc(mr_white, "mr_white", alive=False),
        ],
        "turns": [],
        "winner": "undercovers",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert "last_survivor" in await _unlocked(session, under.id)
    assert "last_survivor" not in await _unlocked(session, mr_white.id)  # won, but dead
    assert "last_survivor" not in await _unlocked(session, civ_a.id)  # alive, but lost


async def test_two_living_winners_means_no_last_survivor(session: AsyncSession, create_user):
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "lsn")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian", alive=False),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [],
        "winner": "civilians",
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert "last_survivor" not in await _unlocked(session, civ_a.id)
    assert "last_survivor" not in await _unlocked(session, civ_b.id)


# ── sweep_victory ─────────────────────────────────────────────────────────


def _codenames_state(red_spy, red_op, blue_spy, blue_op, reveals: list[dict], winner: str = "red") -> dict:
    return {
        "players": [
            _cn(red_spy, "red", "spymaster"),
            _cn(red_op, "red", "operative"),
            _cn(blue_spy, "blue", "spymaster"),
            _cn(blue_op, "blue", "operative"),
        ],
        "winner": winner,
        "clue_history": [],
        CODENAMES_REVEAL_LOG_KEY: reveals,
    }


async def test_sweep_victory_unlocks_for_a_team_that_won_without_a_wrong_card(session: AsyncSession, create_user):
    # Prepare
    red_spy, red_op, blue_spy, blue_op = await _make_users(create_user, 4, "sv")
    state = _codenames_state(
        red_spy,
        red_op,
        blue_spy,
        blue_op,
        [
            _reveal(0, "red", "red", [red_op], 1),
            _reveal(1, "blue", "neutral", [blue_op], 2),  # the OTHER team's mistake
            _reveal(2, "red", "red", [red_op], 3),
        ],
    )

    # Act
    await _end_codenames(session, state)

    # Assert
    assert "sweep_victory" in await _unlocked(session, red_spy.id)
    assert "sweep_victory" in await _unlocked(session, red_op.id)
    assert "sweep_victory" not in await _unlocked(session, blue_op.id)


async def test_one_neutral_reveal_by_the_winning_team_means_no_sweep(session: AsyncSession, create_user):
    # Prepare
    red_spy, red_op, blue_spy, blue_op = await _make_users(create_user, 4, "svn")
    state = _codenames_state(
        red_spy,
        red_op,
        blue_spy,
        blue_op,
        [_reveal(0, "red", "red", [red_op], 1), _reveal(1, "red", "neutral", [red_op], 1)],
    )

    # Act
    await _end_codenames(session, state)

    # Assert
    assert "sweep_victory" not in await _unlocked(session, red_op.id)
    assert "sweep_victory" not in await _unlocked(session, red_spy.id)


async def test_a_team_that_never_guessed_did_not_sweep(session: AsyncSession, create_user):
    """Winning because the other side hit the assassin on their first guess is not a sweep."""
    # Prepare
    red_spy, red_op, blue_spy, blue_op = await _make_users(create_user, 4, "svz")
    state = _codenames_state(red_spy, red_op, blue_spy, blue_op, [_reveal(0, "blue", "assassin", [blue_op], 1)])

    # Act
    await _end_codenames(session, state)

    # Assert
    assert "sweep_victory" not in await _unlocked(session, red_op.id)


# ── assassin_finder ───────────────────────────────────────────────────────


async def test_assassin_finder_unlocks_for_the_operatives_who_pointed_at_the_assassin(
    session: AsyncSession, create_user
):
    """Whether or not their team lost: the badge is for finding it."""
    # Prepare
    red_spy, red_op, blue_spy, blue_op, blue_op_2 = await _make_users(create_user, 5, "af")
    state = _codenames_state(red_spy, red_op, blue_spy, blue_op, [_reveal(7, "blue", "assassin", [blue_op], 1)])
    state["players"].append(_cn(blue_op_2, "blue", "operative"))

    # Act
    await _end_codenames(session, state)

    # Assert
    assert "assassin_finder" in await _unlocked(session, blue_op.id)
    assert "assassin_finder" not in await _unlocked(session, blue_op_2.id)  # voted for another card
    assert "assassin_finder" not in await _unlocked(session, blue_spy.id)


async def test_a_voter_of_another_card_does_not_find_the_assassin(session: AsyncSession, create_user):
    # Prepare
    red_spy, red_op, blue_spy, blue_op = await _make_users(create_user, 4, "afn")
    state = _codenames_state(
        red_spy,
        red_op,
        blue_spy,
        blue_op,
        [_reveal(3, "red", "neutral", [red_op], 1), _reveal(7, "blue", "assassin", [], 2)],
    )

    # Act
    await _end_codenames(session, state)

    # Assert
    assert "assassin_finder" not in await _unlocked(session, red_op.id)
    assert "assassin_finder" not in await _unlocked(session, blue_op.id)


# ── a leaver never unlocks ────────────────────────────────────────────────


async def test_a_leaver_never_unlocks_a_special(session: AsyncSession, create_user):
    """Owner rule (b): the voter of a unanimous round who then walked out gets nothing."""
    # Prepare
    civ_a, civ_b, civ_c, under = await _make_users(create_user, 4, "lvr")
    state = {
        "players": [
            _uc(civ_a, "civilian"),
            _uc(civ_b, "civilian"),
            _uc(civ_c, "civilian", alive=False),
            _uc(under, "undercover", alive=False),
        ],
        "turns": [_turn((civ_a, under), (civ_b, under), (civ_c, under))],
        "winner": "civilians",
        LEFT_PLAYER_IDS_KEY: [str(civ_c.id)],
    }

    # Act
    await _end_undercover(session, state)

    # Assert
    assert await _unlocked(session, civ_c.id) == set()
    assert "unanimous_vote" in await _unlocked(session, civ_a.id)


async def test_an_operative_who_left_does_not_find_the_assassin(session: AsyncSession, create_user):
    # Prepare
    red_spy, red_op, blue_spy, blue_op, blue_op_2 = await _make_users(create_user, 5, "afl")
    state = _codenames_state(
        red_spy, red_op, blue_spy, blue_op, [_reveal(7, "blue", "assassin", [blue_op, blue_op_2], 1)]
    )
    state["players"].append(_cn(blue_op_2, "blue", "operative"))
    state[LEFT_PLAYER_IDS_KEY] = [str(blue_op_2.id)]

    # Act
    await _end_codenames(session, state)

    # Assert
    assert "assassin_finder" in await _unlocked(session, blue_op.id)
    assert await _unlocked(session, blue_op_2.id) == set()


async def test_a_special_unlocks_once(session: AsyncSession, create_user):
    """Two qualifying games: one UserAchievement row, and no second toast."""
    # Prepare
    red_spy, red_op, blue_spy, blue_op = await _make_users(create_user, 4, "once")

    # Act
    first = await _end_codenames(
        session, _codenames_state(red_spy, red_op, blue_spy, blue_op, [_reveal(7, "blue", "assassin", [blue_op], 1)])
    )
    second = await _end_codenames(
        session, _codenames_state(red_spy, red_op, blue_spy, blue_op, [_reveal(7, "blue", "assassin", [blue_op], 1)])
    )

    # Assert
    def codes(unlocked: list[dict]) -> set[str]:
        return {a["code"] for e in unlocked if e["user_id"] == str(blue_op.id) for a in e["achievements"]}

    assert "assassin_finder" in codes(first)
    assert "assassin_finder" not in codes(second)
    rows = (
        await session.exec(
            select(UserAchievement)
            .join(AchievementDefinition, AchievementDefinition.id == UserAchievement.achievement_id)  # ty: ignore[invalid-argument-type]
            .where(UserAchievement.user_id == blue_op.id, AchievementDefinition.code == "assassin_finder")
        )
    ).all()
    assert len(rows) == 1


# ── introspection: no badge without a writer ──────────────────────────────


def test_every_special_code_has_a_rule_and_every_rule_a_special_code():
    """``stat_field: None`` means "unlock_special handles it" — and nothing else does."""
    special_codes = {d["code"] for d in ACHIEVEMENT_DEFINITIONS if d["stat_field"] is None}

    assert special_codes == set(SPECIAL_ACHIEVEMENT_RULES)
    assert special_codes == {
        "perfect_undercover",
        "sweep_victory",
        "assassin_finder",
        "unanimous_vote",
        "last_survivor",
    }


@pytest.mark.parametrize(
    "stat_field", sorted({d["stat_field"] for d in ACHIEVEMENT_DEFINITIONS if d["stat_field"] is not None})
)
def test_every_stat_field_an_achievement_reads_has_a_writer(stat_field: str):
    """PD-05: 7 badges read a UserStats column nothing ever wrote (rooms_created,
    mr_white_correct_guesses, codenames_perfect_rounds). A controller must assign or
    increment it — on a game-end or room path, the only places stats move."""
    writer = re.compile(rf"\.{re.escape(stat_field)}\s*(\+=|=[^=])")
    sources = {path.name: path.read_text(encoding="utf-8") for path in CONTROLLERS.glob("*.py")}

    writers = [name for name, source in sources.items() if writer.search(source)]

    assert writers, f"no controller writes UserStats.{stat_field}"
