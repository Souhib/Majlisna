#!/usr/bin/env python3
"""Remove the seed data that ``generate_fake_data.py --create-db`` left on a server.

NEVER run this before a dump. It deletes accounts, and there is no undo but a restore.

What it removes (and only that):
- the seeded users, with every row that references them, through
  ``UserController._purge_user_references``: stats, achievements, challenges, chat,
  friendships, notebook, daily-word plays, room and game links, tokens, sessions, the
  bans and the host's removal records OF them (those BY them stay, ``banned_by`` /
  ``removed_by`` nulled), and their owned rooms orphaned.
  A seeded user is at @test.com / @example.com / @example.org / @example.net, never
  linked to Google (``google_sub`` null), not named by ``--keep``, and either one of
  TEST_USERS (their passwords are public: they go whatever they did) or an account with
  no sign of real use — no finished game, no session. The address alone is not enough:
  registration needs no verification, so a real player may have signed up with a
  throwaway @test.com address (review INT-04). Those are kept, and the dry run lists
  them as KEPT; ``--keep EMAIL`` (repeatable) keeps any other account the operator
  recognises in the listing;
- the seeded games: no room (``room_id IS NULL``), ``live_state`` null, nobody linked
  to them, and no room pointing at them;
- the seeded rooms: no settings, no member, no game, no active game, and OWNED by a
  seeded user (a real player's old room may have no settings either); with their bans,
  their removal records, their invites and their chat.

A dry run by default: it lists every account and room it would delete (and the accounts
at a seed domain it keeps) and changes nothing. ``--apply`` is refused while a seeded
account is seated in a running game: purging the seat would leave a ghost player in it
(let the game end, or remove the player through the app, first). ``--apply`` also needs
``--dump-taken PATH``, a ``pg_dump -Fc`` archive (it starts with PGDMP) written less than
an hour ago, readable by this process. The deletes run in ONE transaction: an error
anywhere rolls all of them back. Run it with the release that has the ``room_ban`` and
``auth_session`` tables (the backend creates them at startup).

Usage (production: the operator only, after a verified backup). The dump is streamed into
the backend so the app user owns it (a `docker cp` keeps the host's owner and mode, which
the app user cannot read), and removed afterwards: it is the database, unencrypted.
    docker exec -w /app majlisna-backend env PYTHONPATH=/app python scripts/purge_seed_data.py
    docker exec majlisna-db pg_dump -U majlisna -Fc majlisna \\
        | docker exec -i majlisna-backend sh -c 'umask 077; cat > /tmp/majlisna.dump'
    docker exec -w /app majlisna-backend env PYTHONPATH=/app python scripts/purge_seed_data.py \\
        --apply --dump-taken /tmp/majlisna.dump
    docker exec majlisna-backend rm -f /tmp/majlisna.dump

Then restart the backend: the leaderboard is cached per uvicorn worker.
"""

import argparse
import asyncio
import sys
from collections.abc import Collection
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import Text, cast, delete, exists, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import PRODUCTION_REFUSAL_EXIT_CODE, SEED_EMAIL_DOMAINS
from majlisna.api.controllers.user import UserController
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.game import GameStatus
from majlisna.api.models.relationship import RoomGameLink, RoomUserLink, UserGameLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.room_invite import RoomInvite
from majlisna.api.models.room_removal import RoomRemoval
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.shared import BaseModel
from majlisna.database import create_app_engine
from majlisna.settings import Settings
from scripts.generate_fake_data import TEST_USERS, dump_problem

# The seed's own fixed accounts, lowercased: the anchor of its batch.
TEST_USER_EMAILS = frozenset(user["email_address"].lower() for user in TEST_USERS)

# The JSON encoding of null: what a Python None becomes in a JSON column (none_as_null
# is off), as opposed to SQL NULL. Both mean "nothing" here.
JSON_NULL_TEXT = "null"


class SeedAccount(BaseModel):
    """One account at a seed domain, as the dry run lists it."""

    id: UUID
    username: str
    email_address: str
    auth_provider: str | None
    google_linked: bool
    finished_games: int = 0
    last_session_at: datetime | None = None


class SeedRoom(BaseModel):
    """One seeded room, as the dry run lists it."""

    id: UUID
    public_id: str
    created_at: datetime
    owner: str | None


class SeedDataSelection(BaseModel):
    """The ids of the seed residue, read once before anything is deleted."""

    user_ids: list[UUID]
    game_ids: list[UUID]
    room_ids: list[UUID]
    # For the listing: what goes, and the accounts at a seed domain that stay.
    accounts: list[SeedAccount] = []
    kept_accounts: list[SeedAccount] = []
    rooms: list[SeedRoom] = []
    # Seeded accounts seated in a running game: --apply is refused while there is one.
    seated_in_running_game: list[str] = []


class SeedDataCounts(BaseModel):
    """How much seed residue there is (a dry run) or was removed (--apply)."""

    # Seeded accounts per address domain, every SEED_EMAIL_DOMAINS entry present.
    users_by_domain: dict[str, int]
    games: int
    rooms: int

    @property
    def users(self) -> int:
        return sum(self.users_by_domain.values())


def _is_null_or_json_null(column):
    """SQL NULL, or the JSON value null — portable: the text of a JSON/JSONB null is 'null'."""
    return or_(column.is_(None), cast(column, Text) == JSON_NULL_TEXT)


def _address_at(domain: str):
    """The user's address is at ``domain``, in any case; 'fan@latest.com' is not at test.com."""
    return func.lower(User.email_address).endswith(f"@{domain}", autoescape=True)


def _seed_domain_users_query():
    """Every account at a seed domain — candidates only: ``_is_seed_account`` decides."""
    return select(User).where(or_(*(_address_at(domain) for domain in SEED_EMAIL_DOMAINS)))


def _is_seed_account(
    user: User, finished: dict[UUID, int], last_session: dict[UUID, datetime], keep: Collection[str]
) -> bool:
    """Seed data: never Google-linked, not kept by the operator, and one of TEST_USERS or never really used.

    "Used": a finished game, or a session (a sign-in since sessions exist). The seed's
    Faker accounts have neither — its games are orphans nobody is linked to.
    """
    email = user.email_address.lower()
    if user.google_sub is not None or email in keep:
        return False
    if email in TEST_USER_EMAILS:
        return True
    return finished.get(user.id, 0) == 0 and user.id not in last_session


def _seed_games_query():
    """Games the seed made: no room, no state, nobody played them, no room points at them.

    A real game always has a room (``GameCreate.room_id``), a ``live_state`` and its
    players' links; the last two conditions make sure a game somebody played is never
    taken for residue, whatever its other columns say.
    """
    return select(Game.id).where(
        col(Game.room_id).is_(None),
        _is_null_or_json_null(Game.live_state),
        # SQL expressions, not Python bools: ty does not model SQLModel column operators
        # (backend/CLAUDE.md, "ty: ignore discipline").
        ~exists().where(UserGameLink.game_id == Game.id),  # ty: ignore[invalid-argument-type]
        ~exists().where(Room.active_game_id == Game.id),  # ty: ignore[invalid-argument-type]
    )


def _seed_rooms_query(owner_ids: list[UUID]):
    """Rooms the seed made: owned by a seeded user, no settings, no member, no game.

    The owner matters: a real player's room made before rooms carried settings matches
    every other condition, and went with its chat (review INT-04).
    """
    return select(Room).where(
        col(Room.owner_id).in_(owner_ids),
        _is_null_or_json_null(Room.settings),
        col(Room.active_game_id).is_(None),
        # SQL expressions, as above.
        ~exists().where(RoomUserLink.room_id == Room.id),  # ty: ignore[invalid-argument-type]
        ~exists().where(Game.room_id == Room.id),  # ty: ignore[invalid-argument-type]
        ~exists().where(RoomGameLink.room_id == Room.id),  # ty: ignore[invalid-argument-type]
    )


def _account(user: User, finished: dict[UUID, int], last_session: dict[UUID, datetime]) -> SeedAccount:
    return SeedAccount(
        id=user.id,
        username=user.username,
        email_address=user.email_address,
        auth_provider=user.auth_provider,
        google_linked=user.google_sub is not None,
        finished_games=finished.get(user.id, 0),
        last_session_at=last_session.get(user.id),
    )


async def _finished_games(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, int]:
    """How many FINISHED games each account took part in — one grouped query."""
    if not user_ids:
        return {}
    rows = (
        await session.exec(
            select(UserGameLink.user_id, func.count())
            .join(Game, col(Game.id) == col(UserGameLink.game_id))
            .where(col(UserGameLink.user_id).in_(user_ids))
            .where(Game.game_status == GameStatus.FINISHED)
            .group_by(col(UserGameLink.user_id))
        )
    ).all()
    return {user_id: count for user_id, count in rows}


async def _last_sessions(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, datetime]:
    """Each account's latest sign-in activity (its sessions' last refresh) — one grouped query."""
    if not user_ids:
        return {}
    rows = (
        await session.exec(
            select(AuthSession.user_id, func.max(AuthSession.last_refreshed_at))
            .where(col(AuthSession.user_id).in_(user_ids))
            .group_by(col(AuthSession.user_id))
        )
    ).all()
    return {user_id: instant for user_id, instant in rows if instant is not None}


async def _seated_in_running_game(session: AsyncSession, user_ids: list[UUID]) -> list[str]:
    """The seeded accounts holding a seat in an ACTIVE room whose game is running."""
    if not user_ids:
        return []
    rows = (
        await session.exec(
            select(User.email_address)
            .join(RoomUserLink, col(RoomUserLink.user_id) == col(User.id))
            .join(Room, col(Room.id) == col(RoomUserLink.room_id))
            .join(Game, col(Game.id) == col(Room.active_game_id))
            .where(col(User.id).in_(user_ids))
            .where(Room.type == RoomType.ACTIVE)
            .where(Game.game_status == GameStatus.IN_PROGRESS)
        )
    ).all()
    return sorted({str(address) for address in rows})


async def find_seed_data(session: AsyncSession, keep: Collection[str] = ()) -> SeedDataSelection:
    """Read every seeded user, game and room, and the accounts at a seed domain that stay.

    :param keep: addresses the operator keeps whatever the rules say (``--keep``).
    """
    kept_addresses = {address.strip().lower() for address in keep}
    candidates = list((await session.exec(_seed_domain_users_query())).all())
    candidate_ids = [user.id for user in candidates]
    finished = await _finished_games(session, candidate_ids)
    last_session = await _last_sessions(session, candidate_ids)
    seeded = [user for user in candidates if _is_seed_account(user, finished, last_session, kept_addresses)]
    kept = [user for user in candidates if user not in seeded]
    user_ids = [user.id for user in seeded]
    usernames = {user.id: user.username for user in seeded}
    rooms = list((await session.exec(_seed_rooms_query(user_ids))).all()) if user_ids else []
    return SeedDataSelection(
        user_ids=user_ids,
        game_ids=list((await session.exec(_seed_games_query())).all()),
        room_ids=[room.id for room in rooms],
        accounts=[_account(user, finished, last_session) for user in seeded],
        kept_accounts=[_account(user, finished, last_session) for user in kept],
        rooms=[
            SeedRoom(
                id=room.id, public_id=room.public_id, created_at=room.created_at, owner=usernames.get(room.owner_id)
            )
            for room in rooms
            if room.owner_id is not None
        ],
        seated_in_running_game=await _seated_in_running_game(session, user_ids),
    )


def _counts_of(selection: SeedDataSelection) -> SeedDataCounts:
    users_by_domain = {
        domain: sum(1 for account in selection.accounts if account.email_address.lower().endswith(f"@{domain}"))
        for domain in SEED_EMAIL_DOMAINS
    }
    return SeedDataCounts(users_by_domain=users_by_domain, games=len(selection.game_ids), rooms=len(selection.room_ids))


async def count_seed_data(session: AsyncSession, keep: Collection[str] = ()) -> SeedDataCounts:
    """Count the seed residue, per address domain for the users. Reads only."""
    return _counts_of(await find_seed_data(session, keep))


async def purge_seed_data(session: AsyncSession, keep: Collection[str] = ()) -> SeedDataCounts:
    """Delete the seed residue in ONE transaction, committed once at the end.

    Order matters for the foreign keys (none declares ON DELETE): every reference to a
    seeded user first (``_purge_user_references``, which also orphans the rooms they own
    and nulls ``Game.user_id`` on the games they made), then the users; then the games,
    which nothing references any more; then the seeded rooms' bans, removals, invites and chat, then
    the rooms. Any other row still pointing at one of them raises, and the caller's rollback
    undoes every delete before it.

    :return: what was removed.
    """
    selection = await find_seed_data(session, keep)
    counts = _counts_of(selection)
    users = UserController(session)
    for user_id in selection.user_ids:
        await users._purge_user_references(user_id)
    # The cleanup reaches the database before the rows it unblocks are deleted.
    await session.flush()
    if selection.user_ids:
        await session.exec(delete(User).where(col(User.id).in_(selection.user_ids)))
    if selection.game_ids:
        await session.exec(delete(Game).where(col(Game.id).in_(selection.game_ids)))
    if selection.room_ids:
        await session.exec(delete(RoomBan).where(col(RoomBan.room_id).in_(selection.room_ids)))
        await session.exec(delete(RoomRemoval).where(col(RoomRemoval.room_id).in_(selection.room_ids)))
        await session.exec(delete(RoomInvite).where(col(RoomInvite.room_id).in_(selection.room_ids)))
        await session.exec(delete(ChatMessage).where(col(ChatMessage.room_id).in_(selection.room_ids)))
        await session.exec(delete(Room).where(col(Room.id).in_(selection.room_ids)))
    await session.commit()
    return counts


def _print_selection(selection: SeedDataSelection) -> None:
    """Every account and room the purge deletes, and the accounts at a seed domain it keeps."""
    print("Accounts it deletes (username, email, provider, finished games, last session):")
    for account in selection.accounts:
        print(f"  - {_describe(account)}")
    if selection.kept_accounts:
        print("Accounts at a seed domain it KEEPS (Google-linked, used for real, or --keep):")
        for account in selection.kept_accounts:
            print(f"  - KEPT {_describe(account)}")
    print("Rooms it deletes (code, created, owner):")
    for room in selection.rooms:
        print(f"  - {room.public_id}  {room.created_at.isoformat()}  {room.owner}")


def _describe(account: SeedAccount) -> str:
    google = " google-linked" if account.google_linked else ""
    last = account.last_session_at.isoformat() if account.last_session_at else "never"
    return (
        f"{account.username}  {account.email_address}  "
        f"{account.auth_provider}{google}  games={account.finished_games}  last_session={last}"
    )


def _refuses_while_seated(selection: SeedDataSelection) -> bool:
    """Print why --apply is refused and return True while a seeded account sits in a running game."""
    if not selection.seated_in_running_game:
        return False
    print(
        "REFUSED: seeded accounts are seated in a running game; purging their seats would leave "
        "ghost players in it. Let the game end (or remove them through the app) and run again: "
        + ", ".join(selection.seated_in_running_game),
        file=sys.stderr,
    )
    return True


def _print_counts(title: str, counts: SeedDataCounts) -> None:
    print(title)
    for domain, count in counts.users_by_domain.items():
        print(f"  users @{domain:<12} {count}")
    print(f"  users (total)        {counts.users}")
    print(f"  seeded games         {counts.games}")
    print(f"  seeded rooms         {counts.rooms}")


def _refuses_without_fresh_dump(dump_taken: Path | None) -> bool:
    """Print why --apply is refused and return True, unless ``dump_taken`` is a fresh pg_dump."""
    problem = dump_problem(dump_taken)
    if problem is None:
        return False
    print(
        f"REFUSED: --apply needs a fresh dump: {problem}.\n"
        "         docker exec majlisna-db pg_dump -U majlisna -Fc majlisna > majlisna.dump",
        file=sys.stderr,
    )
    return True


async def run(engine: AsyncEngine, *, apply: bool, dump_taken: Path | None, keep: Collection[str] = ()) -> int:
    """Count the seed residue, and delete it when ``apply`` is set and the dump is fresh.

    :return: the process exit code (PRODUCTION_REFUSAL_EXIT_CODE when --apply is refused).
    :raises SQLAlchemyError: a delete failed; the whole transaction was rolled back.
    """
    if apply and _refuses_without_fresh_dump(dump_taken):
        return PRODUCTION_REFUSAL_EXIT_CODE

    async with AsyncSession(engine, expire_on_commit=False) as session:
        selection = await find_seed_data(session, keep)
        if not apply:
            _print_counts(
                "Seed residue (dry run, nothing changed; --apply --dump-taken PATH deletes it):",
                _counts_of(selection),
            )
            _print_selection(selection)
            if selection.seated_in_running_game:
                print("WARNING: --apply will be refused: " + ", ".join(selection.seated_in_running_game))
            return 0
        if _refuses_while_seated(selection):
            await session.rollback()
            return PRODUCTION_REFUSAL_EXIT_CODE
        try:
            removed = await purge_seed_data(session, keep)
        except SQLAlchemyError:
            await session.rollback()
            print("FAILED: rolled back, nothing was deleted.", file=sys.stderr)
            raise
        _print_counts(f"Removed (the dump {dump_taken} holds the previous state):", removed)

    async with AsyncSession(engine) as session:
        _print_counts("Seed residue left:", await count_seed_data(session, keep))
    print(
        "\nNow restart the backend: the leaderboard is cached per uvicorn worker and still "
        "lists the deleted accounts until its entries expire."
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments (``argv`` defaults to ``sys.argv[1:]``)."""
    parser = argparse.ArgumentParser(
        description=(
            "Remove the seed data (@test.com and @example.* accounts, orphan games, seeded "
            "rooms) from a database. NEVER run it before a dump: there is no undo but a "
            "restore. A dry run unless --apply is given."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the seed data (one transaction). Without it, only print the counts.",
    )
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="EMAIL",
        help=(
            "Keep this account whatever the rules say (repeatable): a real player the dry run lists among the deletions"
        ),
    )
    parser.add_argument(
        "--dump-taken",
        type=Path,
        metavar="PATH",
        help=(
            "Required with --apply: a `pg_dump -Fc` archive (starts with PGDMP) written less "
            "than an hour ago, at a path this process can read"
        ),
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    """Entry point: refuse a dumpless --apply before opening the database, then run."""
    args = parse_args(argv)
    if args.apply and _refuses_without_fresh_dump(args.dump_taken):
        return PRODUCTION_REFUSAL_EXIT_CODE

    settings = Settings()  # type: ignore[call-arg]
    # DML only, but the operator's other script goes direct too; one URL for both.
    if settings.direct_database_url:
        settings = settings.model_copy(update={"database_url": settings.direct_database_url})
    engine = await create_app_engine(settings)
    try:
        return await run(engine, apply=args.apply, dump_taken=args.dump_taken, keep=args.keep)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
