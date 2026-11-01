"""purge_seed_data.py removes what --create-db left on a server, and nothing else.

BDP-02 / INFRA-03 / PD-03: production ran on the fake dataset. 16 @test.com accounts
whose passwords are in this public repository, 15 Faker accounts (@example.com/.org/.net),
30 orphan WAITING games (no room, ``live_state`` JSON null) and 10 seeded rooms (no
settings, no member). The public leaderboard was entirely made of them.

The script is a dry run by default (counts only). ``--apply`` needs ``--dump-taken`` (the
same fresh pg_dump check as generate_fake_data's production guard) and deletes in ONE
transaction: the users through ``UserController._purge_user_references`` (their stats,
chat, friendships, achievements, challenges, sessions, bans…), the orphan games, then the
seeded rooms' bans and the rooms. These tests run on SQLite and, with --use-postgres, on
PostgreSQL: each FK is enforced on both.
"""

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import PG_DUMP_CUSTOM_FORMAT_MAGIC, PRODUCTION_DUMP_MAX_AGE_SECONDS
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.challenge import ChallengeDefinition, ChallengeType, UserChallenge
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.friendship import Friendship, FriendshipStatus
from majlisna.api.models.game import GameStatus, GameType
from majlisna.api.models.relationship import RoomGameLink, RoomUserLink, UserGameLink
from majlisna.api.models.room import RoomStatus, RoomType
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.stats import AchievementCategory, AchievementDefinition, UserAchievement, UserStats
from majlisna.api.models.table import Activity, Game, Room, User
from scripts import purge_seed_data

PG_DUMP_HEADER = PG_DUMP_CUSTOM_FORMAT_MAGIC + b"\x01\x0f\x00\x04\x08\x01\x01\x01"


class World:
    """The ids of a small production-like database: seed residue next to one real player."""

    def __init__(self) -> None:
        self.seeded_admin = uuid4()  # admin@test.com
        self.seeded_user = uuid4()  # user@TEST.com (any case is still the seed domain)
        self.faker_user = uuid4()  # a Faker safe email
        self.real_user = uuid4()  # a real Google account
        self.near_miss_user = uuid4()  # fan@latest.com: ends in "test.com", not "@test.com"
        self.real_room = uuid4()
        self.seeded_room = uuid4()
        self.real_game = uuid4()
        self.orphan_game = uuid4()


def _user(user_id: UUID, username: str, email: str) -> User:
    return User(id=user_id, username=username, email_address=email, password="not-a-real-hash", email_verified=True)


async def _build_world(session: AsyncSession) -> World:
    world = World()
    now = datetime.now(UTC)
    achievement = AchievementDefinition(
        code="first_win", category=AchievementCategory.BEGINNER, name="First win", description="Win a game"
    )
    challenge = ChallengeDefinition(code="play_one", description="Play a game", challenge_type=ChallengeType.DAILY)
    session.add_all(
        [
            achievement,
            challenge,
            _user(world.seeded_admin, "admin", "admin@test.com"),
            _user(world.seeded_user, "user", "user@TEST.com"),
            _user(world.faker_user, "jdupont", "jdupont@example.org"),
            _user(world.real_user, "souhib", "real.player@gmail.com"),
            _user(world.near_miss_user, "fan", "fan@latest.com"),
        ]
    )
    await session.flush()

    # The rooms: the real one went through create_room (settings), the seeded one did not.
    session.add_all(
        [
            Room(
                id=world.real_room,
                public_id="REAL1",
                owner_id=world.real_user,
                status=RoomStatus.ONLINE,
                password="1234",
                type=RoomType.ACTIVE,
                settings={"game_type": "undercover"},
            ),
            Room(
                id=world.seeded_room,
                public_id="SEED1",
                owner_id=world.seeded_admin,
                status=RoomStatus.ONLINE,
                password="4321",
                type=RoomType.ACTIVE,
                settings=None,
            ),
        ]
    )
    await session.flush()

    # The games: the real player's finished game (a seeded account played in it too),
    # and the seed's orphan: no room, live_state JSON null, nobody linked.
    session.add_all(
        [
            Game(
                id=world.real_game,
                room_id=world.real_room,
                user_id=world.real_user,
                number_of_players=3,
                type=GameType.UNDERCOVER,
                live_state={"players": [], "winner": "civilians"},
                game_status=GameStatus.FINISHED,
                end_time=now,
            ),
            Game(
                id=world.orphan_game,
                room_id=None,
                user_id=world.seeded_admin,
                number_of_players=5,
                type=GameType.CODENAMES,
                live_state=None,
                game_status=GameStatus.WAITING,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            RoomGameLink(room_id=world.real_room, game_id=world.real_game),
            UserGameLink(user_id=world.real_user, game_id=world.real_game),
            UserGameLink(user_id=world.seeded_user, game_id=world.real_game),
            RoomUserLink(room_id=world.real_room, user_id=world.real_user),
            # Stats, achievements, a challenge
            UserStats(user_id=world.seeded_admin, total_games_played=100, total_games_won=91),
            UserStats(user_id=world.seeded_user, total_games_played=40, total_games_won=12),
            UserStats(user_id=world.real_user, total_games_played=1, total_games_won=1),
            UserAchievement(user_id=world.seeded_admin, achievement_id=achievement.id, progress=1, unlocked_at=now),
            UserAchievement(user_id=world.real_user, achievement_id=achievement.id, progress=1, unlocked_at=now),
            UserChallenge(user_id=world.seeded_user, challenge_id=challenge.id, expires_at=now + timedelta(days=1)),
            # Chat: the seed's in the seeded room, the real player's in theirs
            ChatMessage(room_id=world.seeded_room, user_id=world.seeded_admin, username="admin", message="Salam"),
            ChatMessage(room_id=world.real_room, user_id=world.seeded_user, username="user", message="Bismillah"),
            ChatMessage(room_id=world.real_room, user_id=world.real_user, username="souhib", message="Yalla"),
            # Friendships: between two seeds, and a seed's request to the real player
            Friendship(
                requester_id=world.seeded_admin, addressee_id=world.seeded_user, status=FriendshipStatus.ACCEPTED
            ),
            Friendship(requester_id=world.seeded_user, addressee_id=world.real_user),
            Friendship(requester_id=world.real_user, addressee_id=world.near_miss_user),
            # Sessions: one per side
            AuthSession(user_id=world.seeded_admin, expires_at=now + timedelta(days=30), current_refresh_jti="seed"),
            AuthSession(user_id=world.real_user, expires_at=now + timedelta(days=30), current_refresh_jti="real"),
            # Bans: a seed banned from the real room; the real player banned from the seeded
            # room BY a seed (only the room step can remove that one before the room)
            RoomBan(room_id=world.real_room, user_id=world.seeded_user, banned_by=world.real_user),
            RoomBan(room_id=world.seeded_room, user_id=world.real_user, banned_by=world.seeded_admin),
        ]
    )
    await session.commit()
    return world


async def _row_counts(engine: AsyncEngine) -> dict[str, int]:
    """Rows per table, read on a fresh session."""
    async with AsyncSession(engine) as reader:
        counts: dict[str, int] = {}
        for table in SQLModel.metadata.sorted_tables:
            counts[table.name] = (await reader.exec(select(func.count()).select_from(table))).one()
        return counts


def _fresh_dump(tmp_path: Path, *, age_seconds: float = 0) -> Path:
    dump = tmp_path / "majlisna.dump"
    dump.write_bytes(PG_DUMP_HEADER + b"\x00" * 64)
    if age_seconds:
        instant = time.time() - age_seconds
        os.utime(dump, (instant, instant))
    return dump


# ── Counting ─────────────────────────────────────────────────────────────────


async def test_counts_find_exactly_the_seed_residue(session: AsyncSession):
    # Prepare
    await _build_world(session)

    # Act
    counts = await purge_seed_data.count_seed_data(session)

    # Assert: the 2 @test.com (any case) + 1 Faker account, never fan@latest.com or the
    # gmail one; the orphan game, never the real one; the seeded room, never the real one
    assert counts.users_by_domain == {"test.com": 2, "example.com": 0, "example.org": 1, "example.net": 0}
    assert counts.users == 3
    assert counts.games == 1
    assert counts.rooms == 1


async def test_a_dry_run_changes_no_row(session: AsyncSession, engine: AsyncEngine, capsys: pytest.CaptureFixture):
    # Prepare
    await _build_world(session)
    before = await _row_counts(engine)

    # Act
    exit_code = await purge_seed_data.run(engine, apply=False, dump_taken=None)

    # Assert
    assert exit_code == 0
    assert await _row_counts(engine) == before
    output = capsys.readouterr().out
    assert "dry run" in output.lower()
    assert "@test.com" in output


# ── Refused ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "dump_kind",
    ["none", "missing", "stale", "not-a-pg-dump"],
)
async def test_apply_without_a_fresh_dump_is_refused_and_changes_nothing(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path, dump_kind: str
):
    # Prepare
    await _build_world(session)
    before = await _row_counts(engine)
    dump: Path | None
    if dump_kind == "none":
        dump = None
    elif dump_kind == "missing":
        dump = tmp_path / "never-taken.dump"
    elif dump_kind == "stale":
        dump = _fresh_dump(tmp_path, age_seconds=PRODUCTION_DUMP_MAX_AGE_SECONDS + 60)
    else:
        dump = tmp_path / "plain.sql"
        dump.write_text("--\n-- PostgreSQL database dump\n--\n")

    # Act
    exit_code = await purge_seed_data.run(engine, apply=True, dump_taken=dump)

    # Assert
    assert exit_code == 2
    assert await _row_counts(engine) == before


async def test_main_refuses_apply_without_a_dump_before_opening_the_database(monkeypatch: pytest.MonkeyPatch):
    # Prepare: no engine may be created for a refused run
    create_app_engine = AsyncMock()
    monkeypatch.setattr(purge_seed_data, "create_app_engine", create_app_engine)

    # Act
    exit_code = await purge_seed_data.main(["--apply"])

    # Assert
    assert exit_code == 2
    assert create_app_engine.await_count == 0


def test_help_says_it_never_runs_before_a_dump(capsys: pytest.CaptureFixture):
    # Act
    with pytest.raises(SystemExit):
        purge_seed_data.parse_args(["--help"])

    # Assert
    assert "never" in capsys.readouterr().out.lower()


# ── Applied ──────────────────────────────────────────────────────────────────


async def test_apply_removes_only_the_seed_rows(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path, capsys: pytest.CaptureFixture
):
    # Prepare
    world = await _build_world(session)
    dump = _fresh_dump(tmp_path)

    # Act
    exit_code = await purge_seed_data.run(engine, apply=True, dump_taken=dump)

    # Assert: re-read everything on a fresh session
    assert exit_code == 0
    async with AsyncSession(engine) as reader:
        user_ids = set((await reader.exec(select(User.id))).all())
        assert user_ids == {world.real_user, world.near_miss_user}

        # The real player's rows are intact
        real_stats = (await reader.exec(select(UserStats).where(UserStats.user_id == world.real_user))).one()
        assert real_stats.total_games_won == 1
        assert (await reader.exec(select(UserStats.user_id))).all() == [world.real_user]
        assert (await reader.exec(select(UserAchievement.user_id))).all() == [world.real_user]
        assert (await reader.exec(select(AuthSession.user_id))).all() == [world.real_user]
        assert (await reader.exec(select(ChatMessage.user_id))).all() == [world.real_user]
        friendships = (await reader.exec(select(Friendship))).all()
        assert [(f.requester_id, f.addressee_id) for f in friendships] == [(world.real_user, world.near_miss_user)]
        real_room = (await reader.exec(select(Room).where(Room.id == world.real_room))).one()
        assert real_room.owner_id == world.real_user
        assert real_room.type == RoomType.ACTIVE
        assert real_room.settings == {"game_type": "undercover"}
        assert (await reader.exec(select(RoomUserLink.user_id))).all() == [world.real_user]
        real_game = (await reader.exec(select(Game).where(Game.id == world.real_game))).one()
        assert real_game.game_status == GameStatus.FINISHED
        assert real_game.user_id == world.real_user
        assert real_game.live_state == {"players": [], "winner": "civilians"}
        assert (await reader.exec(select(UserGameLink.user_id))).all() == [world.real_user]
        assert (await reader.exec(select(RoomGameLink.game_id))).all() == [world.real_game]

        # The seed residue is gone
        assert (await reader.exec(select(Game.id))).all() == [world.real_game]
        assert (await reader.exec(select(Room.id))).all() == [world.real_room]
        assert (await reader.exec(select(UserChallenge))).all() == []
        assert (await reader.exec(select(RoomBan))).all() == []

    # Counted again afterwards: nothing left, and the operator is told to restart
    output = capsys.readouterr().out
    assert "restart" in output.lower()
    async with AsyncSession(engine) as reader:
        after = await purge_seed_data.count_seed_data(reader)
    assert after.users == 0
    assert after.games == 0
    assert after.rooms == 0


async def test_a_second_apply_finds_nothing_and_changes_nothing(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path
):
    # Prepare: already purged once
    await _build_world(session)
    dump = _fresh_dump(tmp_path)
    assert await purge_seed_data.run(engine, apply=True, dump_taken=dump) == 0
    before = await _row_counts(engine)

    # Act
    exit_code = await purge_seed_data.run(engine, apply=True, dump_taken=dump)

    # Assert
    assert exit_code == 0
    assert await _row_counts(engine) == before


async def test_apply_is_one_transaction_an_unexpected_reference_rolls_everything_back(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path
):
    # Prepare: a row the script does not know about still points at the seeded room,
    # so deleting that room (the last step) violates a foreign key
    world = await _build_world(session)
    session.add(Activity(room_id=world.seeded_room, user_id=None, name="unexpected", data={}))
    await session.commit()
    before = await _row_counts(engine)
    dump = _fresh_dump(tmp_path)

    # Act
    with pytest.raises(IntegrityError):
        await purge_seed_data.run(engine, apply=True, dump_taken=dump)

    # Assert: the users deleted earlier in the same transaction are all back
    assert await _row_counts(engine) == before
    async with AsyncSession(engine) as reader:
        assert world.seeded_admin in set((await reader.exec(select(User.id))).all())


# ── Review INT-04: the address alone does not make an account seed data ─────


async def _add_real_test_com_player(session: AsyncSession, world: World) -> tuple[UUID, UUID]:
    """A real player who registered with a throwaway @test.com address and played a game,
    and a real player's old empty room (no settings: rooms made before they existed)."""
    player = User(id=uuid4(), username="ahmed", email_address="ahmed@test.com", password="not-a-real-hash")
    old_room = Room(
        id=uuid4(),
        public_id="OLD42",
        owner_id=world.real_user,
        status=RoomStatus.ONLINE,
        password="9999",
        type=RoomType.ACTIVE,
        settings=None,
    )
    session.add_all([player, old_room])
    await session.flush()
    session.add(UserGameLink(user_id=player.id, game_id=world.real_game))
    await session.commit()
    return player.id, old_room.id


async def test_a_real_player_at_a_seed_domain_is_kept_and_listed_as_kept(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path, capsys: pytest.CaptureFixture
):
    """The purge picked accounts by domain alone, and the dry run said "17" instead of "16"."""
    # Prepare
    world = await _build_world(session)
    ahmed, old_room = await _add_real_test_com_player(session, world)

    # Act — the dry run first: it names who goes and who stays
    assert await purge_seed_data.run(engine, apply=False, dump_taken=None) == 0
    dry_run = capsys.readouterr().out
    exit_code = await purge_seed_data.run(engine, apply=True, dump_taken=_fresh_dump(tmp_path))

    # Assert
    assert exit_code == 0
    assert "admin@test.com" in dry_run
    assert "jdupont@example.org" in dry_run
    assert "ahmed@test.com" in dry_run
    assert "KEPT" in dry_run
    assert "SEED1" in dry_run
    assert "OLD42" not in dry_run
    async with AsyncSession(engine) as reader:
        user_ids = set((await reader.exec(select(User.id))).all())
        room_ids = set((await reader.exec(select(Room.id))).all())
    assert ahmed in user_ids
    assert old_room in room_ids
    assert world.seeded_admin not in user_ids
    assert world.seeded_room not in room_ids


async def test_a_google_linked_account_is_never_seed_data(session: AsyncSession):
    """An address Google verified belongs to a real mailbox, whatever its domain."""
    # Prepare
    await _build_world(session)
    admin = (await session.exec(select(User).where(User.email_address == "admin@test.com"))).one()
    admin.google_sub = "google-123"
    session.add(admin)
    await session.commit()

    # Act
    selection = await purge_seed_data.find_seed_data(session)

    # Assert
    assert admin.id not in selection.user_ids


async def test_apply_is_refused_while_a_seed_account_is_seated_in_a_running_game(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path, capsys: pytest.CaptureFixture
):
    """Purging a seat in a running game left a ghost player in it (the problem WP-27 fixed for account deletion)."""
    # Prepare
    world = await _build_world(session)
    running = Game(
        id=uuid4(),
        room_id=world.real_room,
        user_id=world.real_user,
        number_of_players=3,
        type=GameType.UNDERCOVER,
        live_state={"players": []},
        game_status=GameStatus.IN_PROGRESS,
    )
    session.add(running)
    await session.flush()
    room = (await session.exec(select(Room).where(Room.id == world.real_room))).one()
    room.active_game_id = running.id
    session.add_all([room, RoomUserLink(room_id=world.real_room, user_id=world.seeded_user)])
    await session.commit()
    before = await _row_counts(engine)

    # Act
    exit_code = await purge_seed_data.run(engine, apply=True, dump_taken=_fresh_dump(tmp_path))

    # Assert
    assert exit_code == 2
    assert await _row_counts(engine) == before
    assert "running game" in capsys.readouterr().err.lower()


async def test_keep_spares_an_account_the_operator_recognises(
    session: AsyncSession, engine: AsyncEngine, tmp_path: Path
):
    """An unused account at a seed domain goes by default; ``--keep`` spares it."""
    # Prepare
    world = await _build_world(session)
    newcomer = User(id=uuid4(), username="newcomer", email_address="newcomer@example.com", password="not-a-real-hash")
    session.add(newcomer)
    await session.commit()

    # Act
    exit_code = await purge_seed_data.run(
        engine, apply=True, dump_taken=_fresh_dump(tmp_path), keep=["Newcomer@Example.com"]
    )

    # Assert
    assert exit_code == 0
    async with AsyncSession(engine) as reader:
        user_ids = set((await reader.exec(select(User.id))).all())
    assert newcomer.id in user_ids
    assert world.faker_user not in user_ids


def test_keep_is_repeatable_on_the_command_line():
    # Act
    args = purge_seed_data.parse_args(["--keep", "a@test.com", "--keep", "b@example.org"])

    # Assert
    assert args.keep == ["a@test.com", "b@example.org"]
