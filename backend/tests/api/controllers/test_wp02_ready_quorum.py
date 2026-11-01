"""Undercover between rounds: the ready quorum (owner rule (d), BR-23, SEC F05).

The next round used to be the host's call alone, so a host whose tab stayed open but
who stopped playing held the table indefinitely (host transfer only happens after 180 s
DISconnected), and a room whose host deleted their account (``owner_id`` NULL) could
never start another round at all. Now, like the quizzes: every alive non-host player
marks ready through the same ``next-round`` call, and the round opens when the whole
quorum is in; the host still forces it at once.
"""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import UNDERCOVER_READY_PLAYERS_KEY
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.models.game import GameStatus
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.error import (
    GamePausedError,
    NotAGamePlayerError,
    NotAnAlivePlayerError,
    RoundNotResolvedError,
)

UNDERCOVER = UndercoverRole.UNDERCOVER.value
CIVILIAN = UndercoverRole.CIVILIAN.value


# ─── Helpers ──────────────────────────────────────────────────


async def _reread(session: AsyncSession, game_id: UUID) -> Game:
    """The game as committed (another session may have written it)."""
    statement = select(Game).where(Game.id == game_id).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


async def _resolved_round(controller: UndercoverGameController, setup_undercover_game, session: AsyncSession):
    """Six players (host = users[0]); users[5] is the only undercover, no Mr. White.

    Round 1 eliminates the civilian users[1], so the round is resolved and the game goes
    on with five alive: the host and four others (users[2..5]).
    """
    setup = await setup_undercover_game(6)
    users = setup["users"]
    result = await controller.create_and_start(setup["room"].id, users[0].id)
    game_id = UUID(result.game_id)

    game = await _reread(session, game_id)
    state = game.live_state
    for p in state["players"]:
        p["role"] = UNDERCOVER if p["user_id"] == str(users[5].id) else CIVILIAN
    game.live_state = state
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()

    for uid in state["turns"][0]["description_order"]:
        await controller.submit_description(game_id, UUID(uid), "word")
    victim = users[1]
    for voter in users:
        target = victim if voter.id != victim.id else users[2]
        await controller.submit_vote(game_id, voter.id, target.id)

    game = await _reread(session, game_id)
    assert game.live_state["turns"][-1].get("resolved") is True
    assert game.live_state.get("winner") is None
    return setup, game_id


async def _mutate(engine: AsyncEngine, method: str, *args):
    """One controller call in its own session, as production gives each request its own."""
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return await getattr(UndercoverGameController(own_session), method)(*args)


# ─── The quorum ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_host_marks_open_the_round_once_the_quorum_is_in(
    undercover_game_controller, setup_undercover_game, session
):
    """Five alive with the host: three non-host marks wait, the fourth opens round 2."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    users = setup["users"]

    # Act — three of the four
    responses = [await undercover_game_controller.start_next_round(game_id, room_id, u.id) for u in users[2:5]]

    # Assert
    last = responses[-1]
    assert [r.advanced for r in responses] == [False, False, False]
    assert last.ready_count == 3
    assert last.ready_quorum == 4
    assert sorted(last.ready_players) == sorted(str(u.id) for u in users[2:5])
    assert last.turn_number is None
    assert last.description_order == []
    game = await _reread(session, game_id)
    assert len(game.live_state["turns"]) == 1
    assert sorted(game.live_state["turns"][0][UNDERCOVER_READY_PLAYERS_KEY]) == sorted(str(u.id) for u in users[2:5])

    # The state everyone reads says so, and who is ready.
    view = await undercover_game_controller.get_state(game_id, users[2].id, update_heartbeat=False)
    assert view.round_resolved is True
    assert (view.ready_count, view.ready_quorum, view.is_ready) == (3, 4, True)
    assert sorted(view.ready_players) == sorted(str(u.id) for u in users[2:5])
    waiting = await undercover_game_controller.get_state(game_id, users[5].id, update_heartbeat=False)
    assert waiting.is_ready is False

    # Act — the fourth
    opened = await undercover_game_controller.start_next_round(game_id, room_id, users[5].id)

    # Assert
    assert opened.advanced is True
    assert opened.turn_number == 2
    assert sorted(e.user_id for e in opened.description_order) == sorted(str(u.id) for u in [users[0], *users[2:]])
    game = await _reread(session, game_id)
    turns = game.live_state["turns"]
    assert len(turns) == 2
    assert turns[-1]["phase"] == "describing"
    assert UNDERCOVER_READY_PLAYERS_KEY not in turns[-1]
    view = await undercover_game_controller.get_state(game_id, users[2].id, update_heartbeat=False)
    assert view.round_resolved is False
    assert (view.ready_players, view.ready_count, view.is_ready) == ([], 0, False)


@pytest.mark.asyncio
async def test_a_ready_mark_is_counted_once(undercover_game_controller, setup_undercover_game, session):
    """A double tap marks one player once."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    player = setup["users"][3]

    # Act
    await undercover_game_controller.start_next_round(game_id, setup["room"].id, player.id)
    again = await undercover_game_controller.start_next_round(game_id, setup["room"].id, player.id)

    # Assert
    assert again.advanced is False
    assert again.ready_count == 1
    game = await _reread(session, game_id)
    assert game.live_state["turns"][0][UNDERCOVER_READY_PLAYERS_KEY] == [str(player.id)]


@pytest.mark.asyncio
async def test_the_host_still_forces_the_next_round(undercover_game_controller, setup_undercover_game, session):
    """No mark needed: the host's call opens the round at once."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)

    # Act
    forced = await undercover_game_controller.start_next_round(game_id, setup["room"].id, setup["users"][0].id)

    # Assert
    assert forced.advanced is True
    assert forced.turn_number == 2
    game = await _reread(session, game_id)
    assert len(game.live_state["turns"]) == 2
    assert game.live_state["turns"][-1]["phase"] == "describing"


@pytest.mark.asyncio
async def test_an_eliminated_player_cannot_mark_ready(undercover_game_controller, setup_undercover_game, session):
    """The quorum is the living table's: the eliminated player gets NotAnAlivePlayerError."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)

    # Act / Assert
    with pytest.raises(NotAnAlivePlayerError):
        await undercover_game_controller.start_next_round(game_id, setup["room"].id, setup["users"][1].id)
    game = await _reread(session, game_id)
    assert UNDERCOVER_READY_PLAYERS_KEY not in game.live_state["turns"][0]


@pytest.mark.asyncio
async def test_a_stranger_cannot_mark_ready(undercover_game_controller, setup_undercover_game, session):
    """Someone outside the game gets NotAGamePlayerError."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    stranger = User(username="stranger", email_address="stranger@test.com", password=get_password_hash("password123"))
    session.add(stranger)
    await session.commit()
    await session.refresh(stranger)

    # Act / Assert
    with pytest.raises(NotAGamePlayerError):
        await undercover_game_controller.start_next_round(game_id, setup["room"].id, stranger.id)
    game = await _reread(session, game_id)
    assert UNDERCOVER_READY_PLAYERS_KEY not in game.live_state["turns"][0]


@pytest.mark.asyncio
async def test_no_mark_while_the_round_is_still_open(undercover_game_controller, setup_undercover_game, session):
    """Ready is for a resolved round; during describing it is RoundNotResolvedError, as for the host."""
    # Prepare
    setup = await setup_undercover_game(4)
    result = await undercover_game_controller.create_and_start(setup["room"].id, setup["users"][0].id)
    game_id = UUID(result.game_id)

    # Act / Assert
    with pytest.raises(RoundNotResolvedError):
        await undercover_game_controller.start_next_round(game_id, setup["room"].id, setup["users"][1].id)
    game = await _reread(session, game_id)
    assert UNDERCOVER_READY_PLAYERS_KEY not in game.live_state["turns"][0]


@pytest.mark.asyncio
async def test_no_mark_during_the_prayer_pause(undercover_game_controller, setup_undercover_game, session):
    """Like every move, a ready mark waits for the resume."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    await undercover_game_controller.pause_game(game_id, setup["users"][0].id)

    # Act / Assert
    with pytest.raises(GamePausedError):
        await undercover_game_controller.start_next_round(game_id, setup["room"].id, setup["users"][2].id)
    game = await _reread(session, game_id)
    assert UNDERCOVER_READY_PLAYERS_KEY not in game.live_state["turns"][0]


# ─── A room without a host (SEC F05) ─────────────────────────


async def _orphan(session: AsyncSession, room_id: UUID) -> None:
    """What account deletion leaves behind: ``Room.owner_id`` is NULL (``_purge_user_references``)."""
    room = (await session.exec(select(Room).where(Room.id == room_id))).one()
    room.owner_id = None
    session.add(room)
    await session.commit()


@pytest.mark.asyncio
async def test_without_a_host_the_quorum_is_every_alive_player(
    undercover_game_controller, setup_undercover_game, session
):
    """``owner_id`` NULL: nobody forces, every alive player marks, and the last mark opens the round."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    await _orphan(session, room_id)
    alive = [setup["users"][0], *setup["users"][2:]]

    # Act — the former host is an ordinary player now: his call is a mark like the others
    first = [await undercover_game_controller.start_next_round(game_id, room_id, u.id) for u in alive[:-1]]

    # Assert
    assert [r.advanced for r in first] == [False] * 4
    assert (first[-1].ready_count, first[-1].ready_quorum) == (4, 5)
    assert len((await _reread(session, game_id)).live_state["turns"]) == 1

    # Act
    last = await undercover_game_controller.start_next_round(game_id, room_id, alive[-1].id)

    # Assert
    assert last.advanced is True
    game = await _reread(session, game_id)
    assert len(game.live_state["turns"]) == 2
    assert game.live_state["turns"][-1]["phase"] == "describing"


@pytest.mark.asyncio
async def test_f05_the_players_advance_after_the_host_deleted_their_account(
    undercover_game_controller, setup_undercover_game, session
):
    """Port of the security probe ``test_f05_host_deletes_account_and_no_one_can_start_next_round``.

    The host deleted their account: the room is orphaned and the host's seat is gone
    from the table (account deletion runs the departure path, WP-27). Every remaining
    player's next-round used to answer 403; now they advance by quorum.
    """
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    host = setup["users"][0]
    await RoomController(session).leave_room(room_id, host.id)
    await _orphan(session, room_id)
    game = await _reread(session, game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    remaining = setup["users"][2:]

    # Act
    responses = [await undercover_game_controller.start_next_round(game_id, room_id, u.id) for u in remaining]

    # Assert
    assert [r.advanced for r in responses] == [False, False, False, True]
    game = await _reread(session, game_id)
    assert len(game.live_state["turns"]) == 2
    assert str(host.id) not in game.live_state["turns"][-1]["description_order"]


# ─── Departures ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_departure_that_completes_the_quorum_opens_the_next_round(
    undercover_game_controller, setup_undercover_game, session
):
    """Three of the four non-host players are ready; the one they wait on (a civilian, so
    the departure decides nothing) leaves, and the next round opens without the host."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    users = setup["users"]
    for u in (users[2], users[4], users[5]):
        await undercover_game_controller.start_next_round(game_id, room_id, u.id)
    leaver = users[3]

    # Act
    await RoomController(session).leave_room(room_id, leaver.id)

    # Assert
    game = await _reread(session, game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    turns = game.live_state["turns"]
    assert len(turns) == 2
    assert turns[-1]["phase"] == "describing"
    assert sorted(turns[-1]["description_order"]) == sorted(str(u.id) for u in (users[0], users[2], users[4], users[5]))


@pytest.mark.asyncio
async def test_a_quorum_a_departure_completes_during_the_pause_opens_the_round_at_the_resume(
    undercover_game_controller, setup_undercover_game, session
):
    """Review R6: the departure leaves the round as the prayer found it, and the resume opened nothing.

    The ready players' button reads "You are ready" (they cannot mark again), so only the
    host could rescue the round — and in a room with no owner nobody could, for good.
    """
    # Prepare — three of four marked, the host pauses, the fourth leaves during the prayer
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    users = setup["users"]
    for u in (users[2], users[4], users[5]):
        await undercover_game_controller.start_next_round(game_id, room_id, u.id)
    await undercover_game_controller.pause_game(game_id, users[0].id)
    await RoomController(session).leave_room(room_id, users[3].id)
    assert len((await _reread(session, game_id)).live_state["turns"]) == 1

    # Act
    await undercover_game_controller.resume_game(game_id, users[0].id)

    # Assert
    game = await _reread(session, game_id)
    turns = game.live_state["turns"]
    assert len(turns) == 2
    assert turns[-1]["phase"] == "describing"
    assert sorted(turns[-1]["description_order"]) == sorted(str(u.id) for u in (users[0], users[2], users[4], users[5]))


@pytest.mark.asyncio
async def test_a_resume_with_the_quorum_incomplete_opens_nothing(
    undercover_game_controller, setup_undercover_game, session
):
    """The control: the resume opens the round only when everyone asked is ready."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    users = setup["users"]
    await undercover_game_controller.start_next_round(game_id, room_id, users[2].id)
    await undercover_game_controller.pause_game(game_id, users[0].id)

    # Act
    await undercover_game_controller.resume_game(game_id, users[0].id)

    # Assert
    assert len((await _reread(session, game_id)).live_state["turns"]) == 1


@pytest.mark.asyncio
async def test_a_ready_player_leaving_takes_their_mark_with_them(
    undercover_game_controller, setup_undercover_game, session
):
    """The leaver's mark must not count: the others still wait for the rest."""
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    users = setup["users"]
    for u in (users[2], users[3]):
        await undercover_game_controller.start_next_round(game_id, room_id, u.id)

    # Act
    await RoomController(session).leave_room(room_id, users[2].id)

    # Assert
    game = await _reread(session, game_id)
    assert len(game.live_state["turns"]) == 1
    assert game.live_state["turns"][0][UNDERCOVER_READY_PLAYERS_KEY] == [str(users[3].id)]
    view = await undercover_game_controller.get_state(game_id, users[3].id, update_heartbeat=False)
    assert (view.ready_count, view.ready_quorum) == (1, 3)


# ─── Concurrency ─────────────────────────────────────────────


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_two_last_marks_at_once_open_exactly_one_round(
    undercover_game_controller, setup_undercover_game, session, engine
):
    """The last two marks arrive together, each on its own connection: ONE new turn.

    An invariant, not a timing outcome: whichever is serialised first only marks, the
    second opens the round — or, if the order makes the second find the round already
    opened, it answers RoundNotResolvedError. Never two new turns.
    """
    # Prepare
    setup, game_id = await _resolved_round(undercover_game_controller, setup_undercover_game, session)
    room_id = setup["room"].id
    users = setup["users"]
    for u in users[2:4]:
        await undercover_game_controller.start_next_round(game_id, room_id, u.id)

    # Act
    outcomes = await asyncio.gather(
        _mutate(engine, "start_next_round", game_id, room_id, users[4].id),
        _mutate(engine, "start_next_round", game_id, room_id, users[5].id),
        return_exceptions=True,
    )

    # Assert
    for outcome in outcomes:
        assert not isinstance(outcome, Exception) or isinstance(outcome, RoundNotResolvedError), outcome
    advanced = [o for o in outcomes if not isinstance(o, Exception) and o.advanced]
    assert len(advanced) == 1
    await session.rollback()
    game = await _reread(session, game_id)
    turns = game.live_state["turns"]
    assert len(turns) == 2
    assert turns[-1]["phase"] == "describing"
