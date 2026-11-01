"""BR-04, BDP-11, PD-12 on PostgreSQL: departures read the game under its lock, and one sweep per tick.

**BR-04.** ``_handle_permanent_disconnect`` read the Game before taking the game lock,
and the "re-read under the lock" returned the same session's identity-mapped copy (no
``populate_existing``, ``expire_on_commit=False``). A kick, a leave or a grace removal
that waited behind another move of the same game therefore committed the live_state it
had read BEFORE that move: the committed vote vanished, and a game decided by the vote
was left FINISHED with no winner in its live_state and the eliminated player alive.

**BDP-11 / PD-12.** Every uvicorn worker ran the whole sweep every tick, so four
workers handled the same expired link: four room broadcasts for one change, and the
losers' DELETE warned "expected to delete 1 row(s); 0 were matched".

Every test here uses one ``AsyncSession`` per concurrent task (root CLAUDE.md), like
one request each in production.
"""

import asyncio
import warnings
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SAWarning
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.disconnect import disconnect_checker_loop
from majlisna.api.controllers.game_lock import _game_id_to_lock_key
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomStatus, RoomType
from majlisna.api.models.table import Game, Room, User
from majlisna.api.models.undercover import TermPair, Word

pytestmark = pytest.mark.postgres

# How long the kick is left spinning on the lock before the vote goes in: long enough
# for it to have read whatever it reads before taking the lock (several lock retries).
LOCK_WAIT_SECONDS = 0.6


# ─── Helpers ──────────────────────────────────────────────────


async def _fresh_game(engine: AsyncEngine, game_id: str) -> Game:
    """The game as committed, read in a session of its own."""
    async with AsyncSession(engine, expire_on_commit=False) as fresh:
        return (await fresh.exec(select(Game).where(Game.id == UUID(game_id)))).one()


async def _undercover_at_the_vote(engine: AsyncEngine, tag: str, num_players: int) -> tuple[list[User], Room, str]:
    """A started Undercover game (no Mr. White) whose describing phase is over: everyone may vote."""
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        users = [
            User(username=f"lk{tag}_{i}", email_address=f"lk{tag}_{i}@test.com", password="x")
            for i in range(num_players)
        ]
        setup.add_all(users)
        await setup.commit()
        room = await RoomController(setup).create_room(users[0].id, GameType.UNDERCOVER)
        setup.add_all(
            [
                RoomUserLink(room_id=room.id, user_id=u.id, connected=True, last_seen_at=datetime.now())
                for u in users[1:]
            ]
        )
        db_room = (await setup.exec(select(Room).where(Room.id == room.id))).one()
        db_room.settings = {**(db_room.settings or {}), "enable_mr_white": False}
        flag_modified(db_room, "settings")
        setup.add(db_room)
        word1 = Word(word=f"a{tag}", category="c", short_description="a", long_description="b")
        word2 = Word(word=f"b{tag}", category="c", short_description="a", long_description="b")
        setup.add_all([word1, word2])
        await setup.commit()
        setup.add(TermPair(word1_id=word1.id, word2_id=word2.id))
        await setup.commit()

        controller = UndercoverGameController(setup)
        started = await controller.create_and_start(room.id, users[0].id)
        game = (await setup.exec(select(Game).where(Game.id == UUID(started.game_id)))).one()
        for describer in game.live_state["turns"][0]["description_order"]:
            await controller.submit_description(UUID(started.game_id), UUID(describer), "word")
        return users, room, started.game_id


async def _hold_the_game_lock(session: AsyncSession, game_id: str) -> None:
    """Take the game's advisory lock in ``session``'s transaction, as a slow request would."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _game_id_to_lock_key(game_id)})  # ty: ignore[deprecated]


async def _kick_in_its_own_request(engine: AsyncEngine, room_id: UUID, host_id: UUID, kicked_id: str) -> None:
    """The kick as one request: its own session, closed (rolled back) if it fails.

    A failing kick must end its transaction like a request does, or a row lock it took
    would hold the vote below forever instead of making the test fail.
    """
    async with AsyncSession(engine, expire_on_commit=False) as kick_session:
        await RoomController(kick_session).kick_player(room_id, host_id, UUID(kicked_id))


# ─── BR-04: a departure never overwrites a move committed while it waited ──


@pytest.mark.asyncio
async def test_a_kick_waiting_for_the_lock_keeps_the_vote_committed_meanwhile(engine: AsyncEngine):
    """The vote holds the lock, the kick waits on it, the vote commits, the kick finishes: the vote is still there."""
    # Prepare
    users, room, game_id = await _undercover_at_the_vote(engine, "keep", num_players=5)
    host = users[0]
    players = (await _fresh_game(engine, game_id)).live_state["players"]
    others = [p for p in players if p["user_id"] != str(host.id)]
    kicked, voter, voted_for = others[0], others[1], others[2]

    # Act
    async with AsyncSession(engine, expire_on_commit=False) as vote_session:
        await _hold_the_game_lock(vote_session, game_id)
        kick = asyncio.create_task(_kick_in_its_own_request(engine, room.id, host.id, kicked["user_id"]))
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not kick.done(), "the kick must be waiting for the game lock"
        await UndercoverGameController(vote_session).submit_vote(
            UUID(game_id), UUID(voter["user_id"]), UUID(voted_for["user_id"])
        )
        await kick

    # Assert — both landed: the vote AND the departure
    final = (await _fresh_game(engine, game_id)).live_state
    assert final["turns"][-1]["votes"].get(voter["user_id"]) == voted_for["user_id"]
    assert next(p for p in final["players"] if p["user_id"] == kicked["user_id"])["is_alive"] is False
    assert kicked["user_id"] in final["left_player_ids"]


@pytest.mark.asyncio
async def test_a_kick_waiting_behind_the_deciding_vote_keeps_the_result(engine: AsyncEngine):
    """The vote that decides the game commits while a kick waits: the game stays FINISHED with its winner."""
    # Prepare — 1 undercover, 3 civilians; everyone but one voter has voted the undercover out
    users, room, game_id = await _undercover_at_the_vote(engine, "fin", num_players=4)
    host = users[0]
    players = (await _fresh_game(engine, game_id)).live_state["players"]
    undercover = next(p for p in players if p["role"] == "undercover")
    civilians = [p for p in players if p["role"] == "civilian"]
    kicked = next(c for c in civilians if c["user_id"] != str(host.id))
    last_voter = next(p for p in civilians if p["user_id"] not in (kicked["user_id"],))
    async with AsyncSession(engine, expire_on_commit=False) as votes_session:
        controller = UndercoverGameController(votes_session)
        for p in players:
            if p["user_id"] == last_voter["user_id"]:
                continue
            target = undercover if p["user_id"] != undercover["user_id"] else last_voter
            await controller.submit_vote(UUID(game_id), UUID(p["user_id"]), UUID(target["user_id"]))

    # Act
    async with AsyncSession(engine, expire_on_commit=False) as vote_session:
        await _hold_the_game_lock(vote_session, game_id)
        kick = asyncio.create_task(_kick_in_its_own_request(engine, room.id, host.id, kicked["user_id"]))
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not kick.done(), "the kick must be waiting for the game lock"
        decided = await UndercoverGameController(vote_session).submit_vote(
            UUID(game_id), UUID(last_voter["user_id"]), UUID(undercover["user_id"])
        )
        await kick

    # Assert — the finished game keeps the result its deciding vote wrote
    assert decided.winner == "civilians"
    final = await _fresh_game(engine, game_id)
    assert final.game_status == GameStatus.FINISHED
    assert final.live_state["winner"] == "civilians"
    assert next(p for p in final.live_state["players"] if p["user_id"] == undercover["user_id"])["is_alive"] is False


@pytest.mark.asyncio
async def test_a_vote_burst_with_a_kick_loses_no_vote(engine: AsyncEngine):
    """9 players, 7 concurrent votes and 1 kick, 15 times: every committed vote is in the final state.

    Before the fix 10 runs in 15 lost votes (41 in all): the kick read the game, waited
    behind the burst, then wrote back what it had read.
    """
    lost: list[tuple[int, str]] = []
    for run in range(15):
        # Prepare
        users, room, game_id = await _undercover_at_the_vote(engine, f"burst{run}", num_players=9)
        host = users[0]
        players = (await _fresh_game(engine, game_id)).live_state["players"]
        kicked = next(p for p in players if p["user_id"] != str(host.id))
        staying = [p for p in players if p["user_id"] != kicked["user_id"]]
        voters, target = staying[:-1], staying[-1]  # one abstains, so the round stays open

        async def vote(player: dict, game_id: str = game_id, target: dict = target) -> str:
            async with AsyncSession(engine, expire_on_commit=False) as vote_session:
                await UndercoverGameController(vote_session).submit_vote(
                    UUID(game_id), UUID(player["user_id"]), UUID(target["user_id"])
                )
            return player["user_id"]

        async def kick(room_id: UUID = room.id, host_id: UUID = host.id, kicked_id: str = kicked["user_id"]) -> None:
            async with AsyncSession(engine, expire_on_commit=False) as kick_session:
                await RoomController(kick_session).kick_player(room_id, host_id, UUID(kicked_id))

        # Act
        results = await asyncio.gather(kick(), *(vote(p) for p in voters), return_exceptions=True)

        # Assert (collected, then checked once)
        assert not [r for r in results if isinstance(r, BaseException)], results
        final = (await _fresh_game(engine, game_id)).live_state
        lost.extend((run, voter) for voter in results[1:] if voter not in final["turns"][-1]["votes"])
        assert next(p for p in final["players"] if p["user_id"] == kicked["user_id"])["is_alive"] is False
    assert lost == []


# ─── BDP-11 / PD-12: one sweeper per tick ─────────────────────


async def _lobby_with_one_expired_and_one_stale(engine: AsyncEngine, tag: str) -> UUID:
    """A lobby: the host present, one member away past the lobby grace, one silent past the heartbeat."""
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        users = [User(username=f"sw{tag}_{i}", email_address=f"sw{tag}_{i}@test.com", password="x") for i in range(3)]
        setup.add_all(users)
        await setup.commit()
        room = Room(
            public_id=f"S{tag}"[:5],
            owner_id=users[0].id,
            status=RoomStatus.ONLINE,
            password="1234",
            type=RoomType.ACTIVE,
            settings={"game_type": "undercover"},
        )
        setup.add(room)
        await setup.commit()
        now = datetime.now()
        setup.add_all(
            [
                RoomUserLink(room_id=room.id, user_id=users[0].id, last_seen_at=now, connected=True),
                RoomUserLink(
                    room_id=room.id,
                    user_id=users[1].id,
                    last_seen_at=now - timedelta(minutes=12),
                    connected=False,
                    disconnected_at=now - timedelta(minutes=11),
                ),
                RoomUserLink(
                    room_id=room.id, user_id=users[2].id, last_seen_at=now - timedelta(seconds=60), connected=True
                ),
            ]
        )
        await setup.commit()
        return room.id


async def _wait_for_the_sweep(engine: AsyncEngine, room_id: UUID, timeout: float = 20.0) -> list[RoomUserLink]:
    """The room's links once a tick has removed the expired member and marked the silent one away."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        async with AsyncSession(engine, expire_on_commit=False) as check:
            links = list((await check.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all())
        if len(links) == 2 and sum(1 for link in links if not link.connected) == 1:
            return links
        if asyncio.get_running_loop().time() > deadline:
            return links
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_four_workers_sweeping_at_once_handle_each_link_once(engine: AsyncEngine):
    """4 checker loops starting together (4 uvicorn workers): one removal, one broadcast, no SAWarning."""
    for attempt in range(3):
        # Prepare
        room_id = await _lobby_with_one_expired_and_one_stale(engine, f"{attempt}")
        broadcasts: list[str] = []

        # Act — four workers' loops started together; each runs its first tick at once,
        # then sleeps DISCONNECT_CHECK_INTERVAL_SECONDS
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            loops = [
                asyncio.create_task(disconnect_checker_loop(engine, on_room_changed=broadcasts.append))
                for _ in range(4)
            ]
            links = await _wait_for_the_sweep(engine, room_id)
            # every other worker's first tick has run by now too
            await asyncio.sleep(1.5)
            for loop in loops:
                loop.cancel()
            await asyncio.gather(*loops, return_exceptions=True)

        # Assert
        assert len(links) == 2, "the expired member is removed, the two others stay"
        assert sum(1 for link in links if not link.connected) == 1, "the silent member is marked away"
        assert broadcasts.count(str(room_id)) == 1
        assert not [w for w in caught if issubclass(w.category, SAWarning)], [str(w.message) for w in caught]
