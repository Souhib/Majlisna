"""WP-03: what a game end writes, and for whom.

* one winner list (``live_state[WINNER_IDS_KEY]``) for every game type;
* a leaver gets neither a win nor a loss (owner rule (b)), an Undercover drop-out
  never shares the win;
* the daily and weekly challenges advance at every game end (owner rule (g)) —
  ``check_progress`` had no caller, so the whole /challenges page sat at 0/N;
* the counters that had no writer: ``games_hosted``, ``mr_white_correct_guesses``,
  ``codenames_perfect_rounds``;
* nothing inside commits: every caller runs it inside ``get_game_lock``.

Most tests drive ``record_game_end`` with a hand-built final ``live_state``, which is
what every caller hands it. The challenge and quiz ones play real games.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    HOST_USERNAME_STATE_KEY,
    LEFT_PLAYER_IDS_KEY,
    MR_WHITE_GUESS_RESULT_KEY,
    WINNER_IDS_KEY,
)
from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.controllers.game_end_stats import (
    codenames_winners,
    record_game_end,
    top_score_winners,
    undercover_winners,
)
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.challenge import ChallengeDefinition, ChallengeType, UserChallenge
from majlisna.api.models.game import GameStatus
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room, User

# ── helpers ────────────────────────────────────────────────────────────────


async def _make_users(create_user, count: int, prefix: str) -> list[User]:
    return [await create_user(username=f"{prefix}{i}", email=f"{prefix}{i}@test.com") for i in range(count)]


async def _stats(session: AsyncSession, user_id: UUID) -> UserStats | None:
    return (
        await session.exec(
            select(UserStats).where(UserStats.user_id == user_id).execution_options(populate_existing=True)
        )
    ).first()


async def _game(session: AsyncSession, game_id: str | UUID) -> Game:
    return (
        await session.exec(select(Game).where(Game.id == UUID(str(game_id))).execution_options(populate_existing=True))
    ).one()


def _undercover_player(user: User, role: str, *, alive: bool = True) -> dict:
    return {"user_id": str(user.id), "username": user.username, "role": role, "is_alive": alive, "is_mayor": False}


def _codenames_player(user: User, team: str, role: str) -> dict:
    return {"user_id": str(user.id), "username": user.username, "team": team, "role": role}


def _quiz_player(user: User, score: int) -> dict:
    return {"user_id": str(user.id), "username": user.username, "total_score": score}


async def _assign(session: AsyncSession, user_id: UUID, *codes: str) -> None:
    """Give ``user_id`` these exact challenges (assignment is random otherwise)."""
    challenge_controller = ChallengeController(session)
    await challenge_controller.seed_challenges()
    definitions = (
        await session.exec(select(ChallengeDefinition).where(ChallengeDefinition.code.in_(codes)))  # ty: ignore[unresolved-attribute]
    ).all()
    assert {d.code for d in definitions} == set(codes)
    now = datetime.now(UTC)
    for definition in definitions:
        lifetime = timedelta(hours=12) if definition.challenge_type == ChallengeType.DAILY else timedelta(days=7)
        session.add(
            UserChallenge(
                user_id=user_id,
                challenge_id=definition.id,
                progress=0,
                completed=False,
                assigned_at=now,
                expires_at=now + lifetime,
            )
        )
    await session.commit()


async def _progress(session: AsyncSession, user_id: UUID) -> dict[str, int]:
    """``{challenge code: progress}`` for the user's challenges, re-read from the DB."""
    rows = (
        await session.exec(
            select(ChallengeDefinition.code, UserChallenge.progress)
            .join(UserChallenge, UserChallenge.challenge_id == ChallengeDefinition.id)  # ty: ignore[invalid-argument-type]
            .where(UserChallenge.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).all()
    return dict(rows)


async def _play_undercover_to_civilian_win(session: AsyncSession, room_id: UUID, host_id: UUID) -> str:
    """Start an Undercover game, everyone describes, the table votes the undercover out."""
    controller = UndercoverGameController(session)
    started = await controller.create_and_start(room_id, host_id)
    game = await _game(session, started.game_id)
    for user_id in game.live_state["turns"][0]["description_order"]:
        await controller.submit_description(UUID(started.game_id), UUID(user_id), "w")
    game = await _game(session, started.game_id)
    players = game.live_state["players"]
    undercover = next(p for p in players if p["role"] == "undercover")
    for player in players:
        target = (
            undercover
            if player["user_id"] != undercover["user_id"]
            else next(p for p in players if p["user_id"] != player["user_id"])
        )
        await controller.submit_vote(UUID(started.game_id), UUID(player["user_id"]), UUID(target["user_id"]))
    return started.game_id


# ── one winner list, for every game type ──────────────────────────────────


async def test_winner_ids_are_written_for_an_undercover_game(session: AsyncSession, create_user):
    """The resolver (did_user_win) reads this list; Undercover only had a side label."""
    # Prepare
    users = await _make_users(create_user, 4, "wiu")
    roles = ["civilian", "civilian", "civilian", "undercover"]
    state = {"players": [_undercover_player(u, r) for u, r in zip(users, roles, strict=True)], "winner": "civilians"}

    # Act
    await record_game_end(
        session, state, game_type="undercover", winners=undercover_winners(state, "civilians"), default_role="civilian"
    )
    await session.commit()

    # Assert
    assert state[WINNER_IDS_KEY] == sorted(str(u.id) for u in users[:3])


async def test_winner_ids_are_written_for_a_codenames_game(session: AsyncSession, create_user):
    # Prepare
    users = await _make_users(create_user, 4, "wic")
    state = {
        "players": [
            _codenames_player(users[0], "red", "spymaster"),
            _codenames_player(users[1], "red", "operative"),
            _codenames_player(users[2], "blue", "spymaster"),
            _codenames_player(users[3], "blue", "operative"),
        ],
        "winner": "blue",
    }

    # Act
    await record_game_end(
        session, state, game_type="codenames", winners=codenames_winners(state, "blue"), default_role="operative"
    )
    await session.commit()

    # Assert
    assert state[WINNER_IDS_KEY] == sorted([str(users[2].id), str(users[3].id)])


@pytest.mark.parametrize("game_type", ["word_quiz", "mcq_quiz"])
async def test_winner_ids_name_every_top_scorer_of_a_quiz(session: AsyncSession, create_user, game_type: str):
    """Owner rule (a): a tie is a shared win, and the list names both."""
    # Prepare
    users = await _make_users(create_user, 3, f"wiq{game_type[0]}")
    state = {"players": [_quiz_player(users[0], 6), _quiz_player(users[1], 6), _quiz_player(users[2], 2)]}

    # Act
    await record_game_end(
        session, state, game_type=game_type, winners=top_score_winners(state["players"]), track_hints=False
    )
    await session.commit()

    # Assert
    assert state[WINNER_IDS_KEY] == sorted([str(users[0].id), str(users[1].id)])
    won = [(await _stats(session, u.id)).total_games_won for u in users]
    assert won == [1, 1, 0]


async def test_winner_ids_leave_out_an_undercover_drop_out_of_the_winning_side(session: AsyncSession, create_user):
    """BR-12 / owner rule (b): the civilian who walked out in round 1 is still in
    ``players`` (dead) and has the winning role, yet is neither a winner nor a loser."""
    # Prepare
    users = await _make_users(create_user, 4, "wid")
    leaver = users[1]
    players = [
        _undercover_player(users[0], "civilian"),
        _undercover_player(leaver, "civilian", alive=False),
        _undercover_player(users[2], "civilian"),
        _undercover_player(users[3], "undercover", alive=False),
    ]
    state = {"players": players, "winner": "civilians", LEFT_PLAYER_IDS_KEY: [str(leaver.id)]}

    # Act
    await record_game_end(
        session, state, game_type="undercover", winners=undercover_winners(state, "civilians"), default_role="civilian"
    )
    await session.commit()

    # Assert
    assert state[WINNER_IDS_KEY] == sorted([str(users[0].id), str(users[2].id)])
    assert await _stats(session, leaver.id) is None
    stayer = await _stats(session, users[0].id)
    assert (stayer.total_games_played, stayer.total_games_won) == (1, 1)


async def test_a_game_whose_others_all_left_has_no_winner(session: AsyncSession, create_user):
    """A final roster below MIN_PLAYERS_FOR_A_WIN is never a win, whatever the caller passed."""
    # Prepare
    users = await _make_users(create_user, 2, "wis")
    state = {
        "players": [_quiz_player(users[0], 9), _quiz_player(users[1], 3)],
        LEFT_PLAYER_IDS_KEY: [str(users[1].id)],
    }

    # Act
    await record_game_end(session, state, game_type="mcq_quiz", winners={str(users[0].id)}, track_hints=False)
    await session.commit()

    # Assert
    assert state[WINNER_IDS_KEY] == []
    stays = await _stats(session, users[0].id)
    assert (stays.total_games_played, stays.total_games_won, stays.current_win_streak) == (1, 0, 0)
    assert await _stats(session, users[1].id) is None


# ── the counters nothing wrote ────────────────────────────────────────────


async def test_the_host_gets_games_hosted(session: AsyncSession, create_user):
    """PD-05: the stats page showed 'Games hosted: 0' to every host."""
    # Prepare
    users = await _make_users(create_user, 3, "hst")
    state = {
        "players": [_quiz_player(users[0], 4), _quiz_player(users[1], 2), _quiz_player(users[2], 0)],
        HOST_USERNAME_STATE_KEY: users[1].username,
    }

    # Act
    await record_game_end(
        session, state, game_type="word_quiz", winners=top_score_winners(state["players"]), track_hints=False
    )
    await session.commit()

    # Assert
    hosted = [(await _stats(session, u.id)).games_hosted for u in users]
    assert hosted == [0, 1, 0]


async def test_a_host_who_left_gets_no_games_hosted(session: AsyncSession, create_user):
    """Owner rule (b): the game is not counted in a leaver's stats at all."""
    # Prepare
    users = await _make_users(create_user, 3, "hsl")
    state = {
        "players": [_quiz_player(users[0], 4), _quiz_player(users[1], 2), _quiz_player(users[2], 1)],
        HOST_USERNAME_STATE_KEY: users[0].username,
        LEFT_PLAYER_IDS_KEY: [str(users[0].id)],
    }

    # Act
    await record_game_end(session, state, game_type="mcq_quiz", winners=set(), track_hints=False)
    await session.commit()

    # Assert
    assert await _stats(session, users[0].id) is None
    assert (await _stats(session, users[1].id)).games_hosted == 0


async def test_a_correct_mr_white_guess_is_counted(session: AsyncSession, create_user):
    """PD-05: mr_white_guess_1 / mr_white_guess_5 had no writer."""
    # Prepare
    users = await _make_users(create_user, 5, "mwg")
    roles = ["civilian", "civilian", "civilian", "undercover", "mr_white"]
    players = [_undercover_player(u, r) for u, r in zip(users, roles, strict=True)]
    players[4]["is_alive"] = False
    state = {
        "players": players,
        "winner": "undercovers",
        MR_WHITE_GUESS_RESULT_KEY: {"user_id": str(users[4].id), "correct": True},
    }

    # Act
    await record_game_end(
        session,
        state,
        game_type="undercover",
        winners=undercover_winners(state, "undercovers"),
        default_role="civilian",
    )
    await session.commit()

    # Assert
    guesses = [(await _stats(session, u.id)).mr_white_correct_guesses for u in users]
    assert guesses == [0, 0, 0, 0, 1]


async def test_a_wrong_mr_white_guess_is_not_counted(session: AsyncSession, create_user):
    # Prepare
    users = await _make_users(create_user, 5, "mww")
    roles = ["civilian", "civilian", "civilian", "undercover", "mr_white"]
    players = [_undercover_player(u, r) for u, r in zip(users, roles, strict=True)]
    players[3]["is_alive"] = False
    players[4]["is_alive"] = False
    state = {
        "players": players,
        "winner": "civilians",
        MR_WHITE_GUESS_RESULT_KEY: {"user_id": str(users[4].id), "correct": False},
    }

    # Act
    await record_game_end(
        session, state, game_type="undercover", winners=undercover_winners(state, "civilians"), default_role="civilian"
    )
    await session.commit()

    # Assert
    assert (await _stats(session, users[4].id)).mr_white_correct_guesses == 0


def _codenames_end_state(users: list[User], clue_history: list[dict]) -> dict:
    return {
        "players": [
            _codenames_player(users[0], "red", "spymaster"),
            _codenames_player(users[1], "red", "operative"),
            _codenames_player(users[2], "blue", "spymaster"),
            _codenames_player(users[3], "blue", "operative"),
        ],
        "winner": "red",
        "clue_history": clue_history,
    }


def _clue(team: str, number: int, *card_types: str) -> dict:
    return {
        "team": team,
        "clue_word": "x",
        "clue_number": number,
        "guesses": [{"word": f"w{i}", "card_type": t, "correct": t == team} for i, t in enumerate(card_types)],
    }


async def test_codenames_perfect_rounds_count_each_flawless_clue_of_the_team(session: AsyncSession, create_user):
    """PD-05: a clue turn whose operatives found exactly ``clue_number`` own cards and
    nothing else is a perfect round — for every member of that team."""
    # Prepare
    users = await _make_users(create_user, 4, "cpr")
    state = _codenames_end_state(
        users,
        [
            _clue("red", 2, "red", "red"),  # perfect
            _clue("blue", 2, "blue", "neutral"),  # a wrong card
            _clue("red", 3, "red", "red"),  # stopped one short
            _clue("blue", 1, "blue"),  # perfect, for blue
            _clue("red", 1, "red"),  # perfect
            _clue("red", 0, "red"),  # an unlimited clue is never "exactly N"
            _clue("red", 1, "red", "blue"),  # the bonus guess went wrong
        ],
    )

    # Act
    await record_game_end(
        session, state, game_type="codenames", winners=codenames_winners(state, "red"), default_role="operative"
    )
    await session.commit()

    # Assert
    perfect = [(await _stats(session, u.id)).codenames_perfect_rounds for u in users]
    assert perfect == [2, 2, 1, 1]


# ── nothing commits inside the game lock ──────────────────────────────────


async def test_record_game_end_stages_everything_without_committing(session: AsyncSession, create_user):
    """The callers hold ``pg_try_advisory_xact_lock``: a commit in here would release
    the game lock mid-block. Rolling back must leave no trace — stats, achievements
    or challenge progress."""
    # Prepare
    users = await _make_users(create_user, 3, "nci")
    for user in users:
        await _assign(session, user.id, "daily_play_any")
    state = {
        "players": [_quiz_player(users[0], 5), _quiz_player(users[1], 1), _quiz_player(users[2], 0)],
        HOST_USERNAME_STATE_KEY: users[0].username,
    }

    user_ids = [u.id for u in users]  # read before the rollback expires the rows

    # Act
    await record_game_end(
        session, state, game_type="mcq_quiz", winners=top_score_winners(state["players"]), track_hints=False
    )
    await session.rollback()

    # Assert
    for user_id in user_ids:
        assert await _stats(session, user_id) is None
        assert await _progress(session, user_id) == {"daily_play_any": 0}


# ── challenges, wired to every game end (owner rule (g)) ──────────────────


async def test_finishing_an_undercover_game_advances_every_players_challenges(
    session: AsyncSession, setup_undercover_game
):
    """BR-03 / PD-04, the auditor's probe: check_progress had no caller at all."""
    # Prepare
    setup = await setup_undercover_game(3)
    users = setup["users"]
    for user in users:
        await _assign(session, user.id, "daily_play_any", "daily_play_undercover", "daily_play_codenames")

    # Act
    game_id = await _play_undercover_to_civilian_win(session, setup["room"].id, users[0].id)

    # Assert
    game = await _game(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    for user in users:
        progress = await _progress(session, user.id)
        assert progress["daily_play_any"] == 1
        assert progress["daily_play_undercover"] == 1
        assert progress["daily_play_codenames"] == 0


async def test_win_challenges_advance_for_the_winners_only(session: AsyncSession, setup_undercover_game):
    # Prepare
    setup = await setup_undercover_game(3)
    users = setup["users"]
    for user in users:
        await _assign(session, user.id, "daily_win_any")

    # Act
    game_id = await _play_undercover_to_civilian_win(session, setup["room"].id, users[0].id)

    # Assert
    game = await _game(session, game_id)
    winners = set(game.live_state[WINNER_IDS_KEY])
    for user in users:
        assert (await _progress(session, user.id))["daily_win_any"] == (1 if str(user.id) in winners else 0)


async def test_a_players_first_game_assigns_challenges_and_counts(session: AsyncSession, setup_undercover_game):
    """Assignment only happened when /challenges was opened, so a player's first
    games — before they ever looked — counted for nothing."""
    # Prepare
    setup = await setup_undercover_game(3)
    users = setup["users"]
    challenge_controller = ChallengeController(session)
    await challenge_controller.seed_challenges()

    # Act
    game_id = await _play_undercover_to_civilian_win(session, setup["room"].id, users[0].id)

    # Assert
    game = await _game(session, game_id)
    roles = {p["user_id"]: p["role"] for p in game.live_state["players"]}
    winners = set(game.live_state[WINNER_IDS_KEY])
    for user in users:
        rows = (
            await session.exec(
                select(UserChallenge, ChallengeDefinition)
                .join(ChallengeDefinition, ChallengeDefinition.id == UserChallenge.challenge_id)  # ty: ignore[invalid-argument-type]
                .where(UserChallenge.user_id == user.id)
                .execution_options(populate_existing=True)
            )
        ).all()
        assert len(rows) == 5  # 3 daily + 2 weekly, assigned by the game end itself
        for row, definition in rows:
            in_game = definition.game_type in (None, "undercover")
            won = str(user.id) in winners
            matches = in_game and (
                # an Undercover game is one of the types both distinct-games challenges count
                definition.condition in {"play", "play_distinct_types"}
                or (definition.condition == "win" and won)
                or (definition.condition == "play_as_role" and definition.role == roles[str(user.id)])
                or (definition.condition == "win_as_role" and won and definition.role == roles[str(user.id)])
            )
            assert row.progress == (1 if matches else 0), definition.code


async def test_a_disconnect_end_advances_the_challenges_of_the_players_who_stayed(
    session: AsyncSession, setup_undercover_game
):
    """The disconnect path calls record_game_end too: the undercover closing the tab
    decides the game, and the civilians who stayed see their challenges move."""
    # Prepare
    setup = await setup_undercover_game(4)
    users = setup["users"]
    room_id = setup["room"].id
    room = (await session.exec(select(Room).where(Room.id == room_id))).one()
    room.settings = {**(room.settings or {}), "enable_mr_white": False}
    flag_modified(room, "settings")
    session.add(room)
    await session.commit()
    for user in users:
        await _assign(session, user.id, "daily_play_any")
    started = await UndercoverGameController(session).create_and_start(room_id, users[0].id)
    game = await _game(session, started.game_id)
    undercover = next(p for p in game.live_state["players"] if p["role"] == "undercover")
    stayers = [u for u in users if str(u.id) != undercover["user_id"]]

    # Act
    await RoomController(session).leave_room(room_id, UUID(undercover["user_id"]))

    # Assert
    game = await _game(session, started.game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == "civilians"
    for user in stayers:
        assert (await _progress(session, user.id))["daily_play_any"] == 1


async def test_a_leavers_challenges_do_not_move(session: AsyncSession, create_user):
    """Owner rule (b): no stats, no achievements, no challenge progress for a leaver."""
    # Prepare
    users = await _make_users(create_user, 4, "lcm")
    leaver = users[3]
    for user in users:
        await _assign(session, user.id, "daily_play_any", "daily_play_undercover")
    players = [
        _undercover_player(users[0], "civilian"),
        _undercover_player(users[1], "civilian"),
        _undercover_player(users[2], "civilian"),
        _undercover_player(leaver, "undercover", alive=False),
    ]
    state = {"players": players, "winner": "civilians", LEFT_PLAYER_IDS_KEY: [str(leaver.id)]}

    # Act
    await record_game_end(
        session, state, game_type="undercover", winners=undercover_winners(state, "civilians"), default_role="civilian"
    )
    await session.commit()

    # Assert
    assert await _progress(session, leaver.id) == {"daily_play_any": 0, "daily_play_undercover": 0}
    for user in users[:3]:
        progress = await _progress(session, user.id)
        assert (progress["daily_play_any"], progress["daily_play_undercover"]) == (1, 1)


# ── the quizzes, by owner rule (a), through real games ────────────────────


async def _one_round(session: AsyncSession, room_id: UUID, key: str) -> None:
    room = (await session.exec(select(Room).where(Room.id == room_id))).one()
    room.settings = {**(room.settings or {}), key: 1}
    flag_modified(room, "settings")
    session.add(room)
    await session.commit()


async def test_a_zero_zero_zero_mcq_game_records_no_win(session: AsyncSession, setup_mcqquiz_game):
    """BR-11 probe: 0-0-0 used to hand the first seat a win."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=3, num_questions=3)
    users = setup["users"]
    await _one_round(session, setup["room"].id, "mcq_quiz_rounds")
    controller = McqQuizGameController(session)
    started = await controller.create_and_start(setup["room"].id, users[0].id)
    game = await _game(session, started.game_id)
    wrong = (game.live_state["current_question"]["correct_answer_index"] + 1) % 4
    for user in users:
        await controller.submit_answer(UUID(started.game_id), user.id, wrong)

    # Act
    await controller.advance_to_next_round(UUID(started.game_id), users[0].id)

    # Assert
    game = await _game(session, started.game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state[WINNER_IDS_KEY] == []
    assert [(await _stats(session, u.id)).total_games_won for u in users] == [0, 0, 0]


async def test_a_six_six_word_quiz_tie_is_a_shared_win(session: AsyncSession, setup_wordquiz_game):
    """BR-11 probe: the second of two tied players was recorded as a loss."""
    # Prepare
    setup = await setup_wordquiz_game(num_players=2, num_words=3)
    users = setup["users"]
    await _one_round(session, setup["room"].id, "word_quiz_rounds")
    controller = WordQuizGameController(session)
    started = await controller.create_and_start(setup["room"].id, users[0].id)
    game = await _game(session, started.game_id)
    word = game.live_state["current_word"]["word_en"]
    for user in users:
        assert (await controller.submit_answer(UUID(started.game_id), user.id, word)).correct

    # Act
    await controller.advance_to_next_round(UUID(started.game_id), users[0].id)

    # Assert
    game = await _game(session, started.game_id)
    assert [p["total_score"] for p in game.live_state["players"]] == [6, 6]
    assert game.live_state[WINNER_IDS_KEY] == sorted(str(u.id) for u in users)
    rows = [await _stats(session, u.id) for u in users]
    assert [r.total_games_won for r in rows] == [1, 1]
    assert [r.total_games_lost for r in rows] == [0, 0]


async def test_three_solo_quizzes_answered_wrong_are_no_wins(session: AsyncSession, setup_mcqquiz_game):
    """BR-11 / PD-10 probe: three solo 1-question games answered WRONG gave wins 3, streak 3."""
    # Prepare
    setup = await setup_mcqquiz_game(num_players=1, num_questions=3)
    user = setup["users"][0]
    await _one_round(session, setup["room"].id, "mcq_quiz_rounds")
    controller = McqQuizGameController(session)

    # Act
    for _ in range(3):
        started = await controller.create_and_start(setup["room"].id, user.id)
        game = await _game(session, started.game_id)
        wrong = (game.live_state["current_question"]["correct_answer_index"] + 1) % 4
        await controller.submit_answer(UUID(started.game_id), user.id, wrong)
        await controller.advance_to_next_round(UUID(started.game_id), user.id)

    # Assert — played, never won, and never charged a loss either (reviews R4 / INT-03)
    row = await _stats(session, user.id)
    assert (row.total_games_played, row.total_games_won, row.total_games_lost) == (3, 0, 0)
    assert row.current_win_streak == 0


async def test_a_solo_game_is_no_result_in_the_stats_like_in_history(session: AsyncSession, create_user):
    """Owner rule (a): a solo game is never a win. It was recorded as a LOSS (losses +1, the
    streak reset), while ``did_user_win`` answers None for it and the chart skips it."""
    # Prepare — a player on a two-game win streak plays alone
    (user,) = await _make_users(create_user, 1, "solo")
    stats = UserStats(
        user_id=user.id, total_games_played=2, total_games_won=2, current_win_streak=2, longest_win_streak=2
    )
    session.add(stats)
    await session.commit()
    state = {"players": [_quiz_player(user, 6)]}

    # Act
    await record_game_end(session, state, game_type="word_quiz", winners=top_score_winners(state["players"]))
    await session.commit()

    # Assert
    row = await _stats(session, user.id)
    assert (row.total_games_played, row.total_games_won, row.total_games_lost) == (3, 2, 0)
    assert (row.current_win_streak, row.longest_win_streak) == (2, 2)
    assert state[WINNER_IDS_KEY] == []


async def test_the_player_who_stays_when_the_other_walks_out_is_charged_nothing(session: AsyncSession, create_user):
    """Rule (b) spares the leaver; the one who stayed was charged a loss because the other left."""
    # Prepare
    stayer, leaver = await _make_users(create_user, 2, "stay")
    session.add(UserStats(user_id=stayer.id, total_games_played=1, total_games_won=1, current_win_streak=1))
    await session.commit()
    state = {
        "players": [_quiz_player(stayer, 0), _quiz_player(leaver, 4)],
        LEFT_PLAYER_IDS_KEY: [str(leaver.id)],
    }

    # Act
    await record_game_end(session, state, game_type="mcq_quiz", winners=top_score_winners(state["players"]))
    await session.commit()

    # Assert
    row = await _stats(session, stayer.id)
    assert (row.total_games_played, row.total_games_won, row.total_games_lost) == (2, 1, 0)
    assert row.current_win_streak == 1
    assert await _stats(session, leaver.id) is None


# ── one read per table, whatever the size of the table of players (BDP-07) ──


async def test_a_game_end_reads_each_table_once_for_twelve_players(
    session: AsyncSession, create_user, count_statements
):
    """It ran inside the game lock one SELECT per player per table — userstats,
    userachievement, userchallenge: ~110 statements for a 12-player game end."""
    # Prepare
    users = await _make_users(create_user, 12, "bat")
    await ChallengeController(session).seed_challenges()
    await AchievementController(session).seed_achievements()
    state = {"players": [_quiz_player(u, 3 if i == 0 else 0) for i, u in enumerate(users)]}
    counters = {table: count_statements(f"FROM {table}") for table in ("userstats", "userachievement", "userchallenge")}
    everything = count_statements("")

    # Act
    await record_game_end(
        session, state, game_type="mcq_quiz", winners=top_score_winners(state["players"]), track_hints=False
    )
    await session.commit()

    # Assert
    assert {table: c.count for table, c in counters.items()} == {
        "userstats": 1,
        "userachievement": 1,
        "userchallenge": 1,
    }
    assert everything.count <= 20
    for user in users:
        assert (await _stats(session, user.id)).total_games_played == 1
        assert len(await _progress(session, user.id)) == 5


# ── the counters, through real games ──────────────────────────────────────


async def test_mr_whites_right_guess_counts_through_the_real_game(session: AsyncSession, setup_undercover_game):
    """End to end: Mr. White voted out in round 1 names the civilian word, the
    undercovers win, and his guess is counted (mr_white_guess_1 then unlocks)."""
    # Prepare
    setup = await setup_undercover_game(5)
    users = setup["users"]
    await AchievementController(session).seed_achievements()
    controller = UndercoverGameController(session)
    started = await controller.create_and_start(setup["room"].id, users[0].id)
    game_id = UUID(started.game_id)
    game = await _game(session, game_id)
    for user_id in game.live_state["turns"][0]["description_order"]:
        await controller.submit_description(game_id, UUID(user_id), "w")
    game = await _game(session, game_id)
    players = game.live_state["players"]
    mr_white = next(p for p in players if p["role"] == "mr_white")
    for player in players:
        target = (
            mr_white
            if player["user_id"] != mr_white["user_id"]
            else next(p for p in players if p["user_id"] != mr_white["user_id"])
        )
        await controller.submit_vote(game_id, UUID(player["user_id"]), UUID(target["user_id"]))

    # Act
    await controller.submit_mr_white_guess(game_id, UUID(mr_white["user_id"]), game.live_state["civilian_word"])

    # Assert
    game = await _game(session, game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == "undercovers"
    assert str(mr_white["user_id"]) in game.live_state[WINNER_IDS_KEY]
    stats = await _stats(session, UUID(mr_white["user_id"]))
    assert (stats.mr_white_correct_guesses, stats.mr_white_wins) == (1, 1)
    host = await _stats(session, users[0].id)
    assert host.games_hosted == 1
    unlocked = {a["code"] for e in game.live_state["newly_unlocked_achievements"] for a in e["achievements"]}
    assert "mr_white_guess_1" in unlocked
