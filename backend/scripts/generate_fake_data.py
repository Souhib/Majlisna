#!/usr/bin/env python3
"""Script to generate fake data for Majlisna platform testing.

This script can be used to:
1. Create database tables and generate fake users, rooms, games, and seed data
2. Delete all data from the database (drop and recreate tables)
3. Seed Undercover word pairs (30+ Islamic term pairs)
4. Seed Codenames word packs (100+ Islamic terms in categories)
5. Seed achievement/challenge definitions
6. Create UserStats, UserAchievements, UserChallenges for test users
7. Create friendships and chat messages

Usage:
    # Create database tables and generate fake data
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -c

    # Delete all data from the database
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -d

    # Seed game content only (safe for production)
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --seed
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -s

    # Custom data volumes
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -c --users 50 --games 100

Options:
    --delete, -d         Delete all data by dropping and recreating tables
    --create-db, -c      Create tables and generate fake data
    --seed, -s           Seed game content only (safe for production)
    --users N            Number of additional random users to generate (default: 15)
    --games N            Number of games to generate (default: 30)

Note:
    You must use exactly ONE of: --delete or --create-db.
    These flags are mutually exclusive.
"""

import argparse
import asyncio
import random
import string
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.models.challenge import ChallengeDefinition, ChallengeType, UserChallenge
from majlisna.api.models.chat import ChatMessage
from majlisna.api.models.friendship import Friendship, FriendshipStatus
from majlisna.api.models.game import GameType
from majlisna.api.models.room import RoomStatus, RoomType
from majlisna.api.models.stats import AchievementDefinition, UserAchievement, UserStats
from majlisna.api.models.table import Game, Room, User
from majlisna.database import create_app_engine, create_db_and_tables
from majlisna.settings import Settings
from scripts.seed_data.codenames_data import seed_codenames_words
from scripts.seed_data.mcqquiz_data import seed_mcq_questions
from scripts.seed_data.undercover_data import seed_undercover_pairs, seed_undercover_words
from scripts.seed_data.wordquiz_data import seed_quiz_words

# Lazy imports for dev-only dependencies (not in production image)
fake = None  # type: ignore[assignment]


# ── Test user accounts ──────────────────────────────────────────────────────

TEST_USERS = [
    {
        "username": "admin",
        "email_address": "admin@test.com",
        "password": "admin123",
        "country": "SAU",
        "bio": "Platform admin. Love organizing game nights!",
    },
    {
        "username": "user",
        "email_address": "user@test.com",
        "password": "user1234",
        "country": "ARE",
        "bio": "Casual player, always up for a round.",
    },
    {
        "username": "player",
        "email_address": "player@test.com",
        "password": "player123",
        "country": "MAR",
    },
    {
        "username": "ali",
        "email_address": "ali@test.com",
        "password": "ali12345",
        "country": "EGY",
        "bio": "Undercover champion. Try to catch me!",
    },
    {
        "username": "fatima",
        "email_address": "fatima@test.com",
        "password": "fatima12",
        "country": "TUN",
        "bio": "Spymaster extraordinaire.",
    },
    {
        "username": "omar",
        "email_address": "omar@test.com",
        "password": "omar1234",
        "country": "DZA",
    },
    {
        "username": "aisha",
        "email_address": "aisha@test.com",
        "password": "aisha123",
        "country": "JOR",
        "bio": "Here for the fun and the community.",
    },
    {
        "username": "yusuf",
        "email_address": "yusuf@test.com",
        "password": "yusuf123",
        "country": "TUR",
    },
    {
        "username": "maryam",
        "email_address": "maryam@test.com",
        "password": "maryam12",
        "country": "MYS",
        "bio": "Codenames is my favourite!",
    },
    {
        "username": "hamza",
        "email_address": "hamza@test.com",
        "password": "hamza123",
        "country": "PAK",
    },
    # Pool B accounts (for parallel E2E test execution)
    {
        "username": "user_b",
        "email_address": "user_b@test.com",
        "password": "user1234",
        "country": "ARE",
    },
    {
        "username": "player_b",
        "email_address": "player_b@test.com",
        "password": "player123",
        "country": "MAR",
    },
    {
        "username": "ali_b",
        "email_address": "ali_b@test.com",
        "password": "ali12345",
        "country": "EGY",
    },
    {
        "username": "fatima_b",
        "email_address": "fatima_b@test.com",
        "password": "fatima12",
        "country": "TUN",
    },
    {
        "username": "omar_b",
        "email_address": "omar_b@test.com",
        "password": "omar1234",
        "country": "DZA",
    },
    {
        "username": "aisha_b",
        "email_address": "aisha_b@test.com",
        "password": "aisha123",
        "country": "JOR",
    },
]


# ── Helper functions ────────────────────────────────────────────────────────


def create_random_public_id() -> str:
    """Create a random 5-character public ID for rooms."""
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(5))


async def create_test_users(session: AsyncSession) -> list[User]:
    """Create the three fixed test users with hashed passwords.

    Returns:
        List of created User objects.
    """
    users = []
    for user_data in TEST_USERS:
        user = User(
            id=uuid4(),
            username=user_data["username"],
            email_address=user_data["email_address"],
            password=get_password_hash(user_data["password"]),
            country=user_data["country"],
            email_verified=True,
            bio=user_data.get("bio"),
        )
        session.add(user)
        users.append(user)

    await session.commit()
    for user in users:
        await session.refresh(user)

    print(f"  Created {len(users)} test users:")
    for u in TEST_USERS:
        print(f"    - {u['email_address']} / {u['password']}")

    return users


async def create_random_users(session: AsyncSession, count: int) -> list[User]:
    """Create additional random users with hashed passwords.

    Args:
        session: The database session.
        count: Number of random users to create.

    Returns:
        List of created User objects.
    """
    import pycountry

    country_codes = [c.alpha_3 for c in pycountry.countries]
    users = []

    for _ in range(count):
        user = User(
            id=uuid4(),
            username=fake.user_name(),
            email_address=fake.email(),
            password=get_password_hash(fake.password()),
            country=random.choice(country_codes),
        )
        session.add(user)
        users.append(user)

    await session.commit()
    for user in users:
        await session.refresh(user)

    print(f"  Created {count} random users")
    return users


async def create_rooms(session: AsyncSession, users: list[User], count: int = 5) -> list[Room]:
    """Create rooms with various statuses.

    Args:
        session: The database session.
        users: List of users who can own rooms.
        count: Number of rooms to create.

    Returns:
        List of created Room objects.
    """
    rooms = []
    for i in range(count):
        owner = random.choice(users)
        room = Room(
            id=uuid4(),
            public_id=create_random_public_id(),
            owner_id=owner.id,
            status=random.choice(list(RoomStatus)),
            password="".join(random.choice(string.digits) for _ in range(4)),
            type=random.choice(list(RoomType)),
            created_at=fake.date_time_between(start_date="-30d", end_date="now"),
        )
        session.add(room)
        rooms.append(room)

    await session.commit()
    for room in rooms:
        await session.refresh(room)

    print(f"  Created {count} rooms")
    return rooms


async def create_games(
    session: AsyncSession, users: list[User], count: int = 30
) -> list[Game]:
    """Create games with various types and configurations.

    Args:
        session: The database session.
        users: List of users who can participate in games.
        count: Number of games to create.

    Returns:
        List of created Game objects.
    """
    games = []
    for _ in range(count):
        user = random.choice(users)
        start_time = fake.date_time_between(start_date="-30d", end_date="now")
        has_ended = random.choice([True, False])
        end_time = start_time + timedelta(minutes=random.randint(5, 45)) if has_ended else None
        game_type = random.choice(list(GameType))
        num_players = random.randint(3, 12) if game_type == GameType.UNDERCOVER else random.randint(4, 10)

        game = Game(
            id=uuid4(),
            user_id=user.id,
            start_time=start_time,
            end_time=end_time,
            number_of_players=num_players,
            type=game_type,
            game_configurations={
                "game_type": game_type.value,
                "created_by": str(user.id),
            },
        )
        session.add(game)
        games.append(game)

    await session.commit()
    for game in games:
        await session.refresh(game)

    print(f"  Created {count} games")
    return games


async def seed_achievements(session: AsyncSession) -> None:
    """Seed achievement definitions using the AchievementController.

    Args:
        session: The database session.
    """
    controller = AchievementController(session)
    await controller.seed_achievements()
    print("  Seeded achievement definitions")


async def create_user_stats(session: AsyncSession, users: list[User]) -> None:
    """Create sample UserStats entries for test users.

    Args:
        session: The database session.
        users: List of users to create stats for.
    """
    roles_undercover = ["civilian", "undercover", "mr_white"]
    roles_codenames = ["spymaster", "operative"]

    for user in users:
        total_played = random.randint(5, 100)
        total_won = random.randint(1, total_played)
        total_lost = total_played - total_won

        uc_played = random.randint(2, total_played // 2 + 1)
        uc_won = random.randint(0, uc_played)
        cn_played = total_played - uc_played
        cn_won = total_won - uc_won if total_won > uc_won else random.randint(0, cn_played)

        times_civilian = random.randint(1, max(1, uc_played // 2))
        times_undercover = random.randint(1, max(1, uc_played // 3))
        times_mr_white = max(0, uc_played - times_civilian - times_undercover)

        civilian_wins = random.randint(0, times_civilian)
        undercover_wins = random.randint(0, times_undercover)
        mr_white_wins = random.randint(0, times_mr_white)

        times_spymaster = random.randint(1, max(1, cn_played // 2))
        times_operative = max(0, cn_played - times_spymaster)

        spymaster_wins = random.randint(0, times_spymaster)
        operative_wins = random.randint(0, times_operative)

        current_win_streak = random.randint(0, 5)
        longest_win_streak = random.randint(current_win_streak, 10)

        current_play_streak = random.randint(0, 7)
        longest_play_streak = random.randint(current_play_streak, 30)

        stats = UserStats(
            id=uuid4(),
            user_id=user.id,
            total_games_played=total_played,
            total_games_won=total_won,
            total_games_lost=total_lost,
            undercover_games_played=uc_played,
            undercover_games_won=uc_won,
            codenames_games_played=cn_played,
            codenames_games_won=cn_won,
            times_civilian=times_civilian,
            times_undercover=times_undercover,
            times_mr_white=times_mr_white,
            civilian_wins=civilian_wins,
            undercover_wins=undercover_wins,
            mr_white_wins=mr_white_wins,
            times_spymaster=times_spymaster,
            times_operative=times_operative,
            spymaster_wins=spymaster_wins,
            operative_wins=operative_wins,
            total_votes_cast=random.randint(10, 200),
            correct_votes=random.randint(5, 100),
            times_eliminated=random.randint(0, 30),
            times_survived=random.randint(0, 50),
            current_win_streak=current_win_streak,
            longest_win_streak=longest_win_streak,
            current_play_streak_days=current_play_streak,
            longest_play_streak_days=longest_play_streak,
            last_played_at=fake.date_time_between(start_date="-7d", end_date="now"),
            mr_white_correct_guesses=random.randint(0, 5),
            codenames_words_guessed=random.randint(5, 80),
            codenames_perfect_rounds=random.randint(0, 5),
            rooms_created=random.randint(0, 20),
            games_hosted=random.randint(0, 15),
        )
        session.add(stats)

    await session.commit()
    print(f"  Created UserStats for {len(users)} users")


async def seed_challenges(session: AsyncSession) -> None:
    """Seed challenge definitions using the ChallengeController.

    Args:
        session: The database session.
    """
    controller = ChallengeController(session)
    await controller.seed_challenges()
    print("  Seeded challenge definitions")


async def create_friendships(session: AsyncSession, users: list[User]) -> None:
    """Create sample friendship records between test users.

    Args:
        session: The database session.
        users: List of users to create friendships between.
    """
    if len(users) < 4:
        return

    count = 0
    # Create accepted friendships between first few users
    pairs_accepted = [(0, 1), (0, 2), (1, 3), (2, 4), (3, 5)]
    for i, j in pairs_accepted:
        if i < len(users) and j < len(users):
            friendship = Friendship(
                id=uuid4(),
                requester_id=users[i].id,
                addressee_id=users[j].id,
                status=FriendshipStatus.ACCEPTED,
            )
            session.add(friendship)
            count += 1

    # Create some pending requests
    pairs_pending = [(4, 0), (5, 1), (6, 2)]
    for i, j in pairs_pending:
        if i < len(users) and j < len(users):
            friendship = Friendship(
                id=uuid4(),
                requester_id=users[i].id,
                addressee_id=users[j].id,
                status=FriendshipStatus.PENDING,
            )
            session.add(friendship)
            count += 1

    await session.commit()
    print(f"  Created {count} friendships")


async def create_chat_messages(session: AsyncSession, users: list[User], rooms: list[Room]) -> None:
    """Create sample chat messages in rooms.

    Args:
        session: The database session.
        users: List of users who can send messages.
        rooms: List of rooms to add messages to.
    """
    if not rooms or not users:
        return

    count = 0
    messages_pool = [
        "Assalamu Alaikum!",
        "Who's ready to play?",
        "Let's go!",
        "Good game everyone",
        "That was close!",
        "MashaAllah, well played!",
        "Ready for another round?",
        "SubhanAllah, what a game!",
        "Who's the undercover?",
        "I think I know the word...",
        "Great clue!",
        "Let's vote!",
        "Bismillah, here we go",
        "AlhamduliLlah, good win",
        "JazakAllah khair for playing",
    ]

    for room in rooms[:5]:  # Only first 5 rooms
        num_messages = random.randint(3, 10)
        for _ in range(num_messages):
            user = random.choice(users[:10])  # Use first 10 test users
            msg = ChatMessage(
                id=uuid4(),
                room_id=room.id,
                user_id=user.id,
                username=user.username,
                message=random.choice(messages_pool),
            )
            session.add(msg)
            count += 1

    await session.commit()
    print(f"  Created {count} chat messages")


async def create_user_achievements(session: AsyncSession, users: list[User]) -> None:
    """Create sample UserAchievement records for test users.

    Some achievements are unlocked (with unlocked_at), some are in-progress.

    Args:
        session: The database session.
        users: List of users to create achievements for.
    """
    # Fetch all achievement definitions
    definitions = list((await session.exec(select(AchievementDefinition))).all())
    if not definitions:
        print("  No achievement definitions found — skipping")
        return

    count = 0
    for user in users[:10]:  # First 10 test users
        # Give each user 3-6 random achievements
        num_achievements = random.randint(3, min(6, len(definitions)))
        selected = random.sample(definitions, num_achievements)

        for defn in selected:
            is_unlocked = random.random() < 0.6  # 60% chance unlocked
            progress = defn.threshold if is_unlocked else random.randint(0, defn.threshold - 1)
            unlocked_at = (
                fake.date_time_between(start_date="-30d", end_date="now")
                if is_unlocked
                else None
            )

            achievement = UserAchievement(
                id=uuid4(),
                user_id=user.id,
                achievement_id=defn.id,
                progress=progress,
                unlocked_at=unlocked_at,
            )
            session.add(achievement)
            count += 1

    await session.commit()
    print(f"  Created {count} user achievements")


async def create_user_challenges(session: AsyncSession, users: list[User]) -> None:
    """Assign active challenges to test users.

    Each user gets 3 daily + 2 weekly challenges (matching the app's assignment logic).

    Args:
        session: The database session.
        users: List of users to assign challenges to.
    """
    # Fetch challenge definitions by type
    all_defs = list((await session.exec(select(ChallengeDefinition))).all())
    if not all_defs:
        print("  No challenge definitions found — skipping")
        return

    daily_defs = [d for d in all_defs if d.challenge_type == ChallengeType.DAILY]
    weekly_defs = [d for d in all_defs if d.challenge_type == ChallengeType.WEEKLY]

    now = datetime.now(UTC)
    daily_expires = now.replace(hour=23, minute=59, second=59) + timedelta(days=1)
    weekly_expires = now + timedelta(days=7 - now.weekday())  # Next Monday

    count = 0
    for user in users[:10]:  # First 10 test users
        # 3 daily challenges
        chosen_daily = random.sample(daily_defs, min(3, len(daily_defs)))
        for defn in chosen_daily:
            progress = random.randint(0, defn.target_count)
            challenge = UserChallenge(
                id=uuid4(),
                user_id=user.id,
                challenge_id=defn.id,
                progress=progress,
                completed=progress >= defn.target_count,
                assigned_at=now,
                expires_at=daily_expires,
            )
            session.add(challenge)
            count += 1

        # 2 weekly challenges
        chosen_weekly = random.sample(weekly_defs, min(2, len(weekly_defs)))
        for defn in chosen_weekly:
            progress = random.randint(0, defn.target_count)
            challenge = UserChallenge(
                id=uuid4(),
                user_id=user.id,
                challenge_id=defn.id,
                progress=progress,
                completed=progress >= defn.target_count,
                assigned_at=now,
                expires_at=weekly_expires,
            )
            session.add(challenge)
            count += 1

    await session.commit()
    print(f"  Created {count} user challenges")


# ── Main operations ─────────────────────────────────────────────────────────


async def delete_all_data(engine: AsyncEngine) -> None:
    """Delete all data by dropping and recreating tables.

    Args:
        engine: The database engine.
    """
    print("Dropping and recreating all tables...")
    await create_db_and_tables(engine, drop_all=True)
    print("All tables dropped and recreated successfully!")


async def generate_all_data(
    engine: AsyncEngine,
    num_users: int = 15,
    num_games: int = 30,
) -> None:
    """Create tables and generate all fake data.

    Args:
        engine: The database engine.
        num_users: Number of additional random users to generate.
        num_games: Number of games to generate.
    """
    print("Creating database tables...")
    await create_db_and_tables(engine)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # 1. Create test users
        print("\n[1/12] Creating test users...")
        test_users = await create_test_users(session)

        # 2. Create random users
        print(f"\n[2/12] Creating {num_users} random users...")
        random_users = await create_random_users(session, num_users)
        all_users = test_users + random_users

        # 3. Create rooms
        print("\n[3/12] Creating rooms...")
        rooms = await create_rooms(session, all_users, count=max(5, len(all_users) // 3))

        # 4. Seed Undercover words and pairs
        print("\n[4/12] Seeding Undercover words and pairs...")
        word_map = await seed_undercover_words(session)
        await seed_undercover_pairs(session, word_map)

        # 5. Seed Codenames words
        print("\n[5/12] Seeding Codenames word packs...")
        await seed_codenames_words(session)

        # 5b. Seed Word Quiz words
        print("\n[5b/12] Seeding Word Quiz words...")
        await seed_quiz_words(session)

        # 5c. Seed MCQ Quiz questions
        print("\n[5c/12] Seeding MCQ Quiz questions...")
        await seed_mcq_questions(session)

        # 6. Seed achievements
        print("\n[6/12] Seeding achievement definitions...")
        await seed_achievements(session)

        # 7. Seed challenges
        print("\n[7/12] Seeding challenge definitions...")
        await seed_challenges(session)

        # 8. Create games and stats
        print(f"\n[8/12] Creating {num_games} games and user stats...")
        await create_games(session, all_users, count=num_games)
        await create_user_stats(session, test_users)

        # 9. Create friendships
        print("\n[9/12] Creating friendships...")
        await create_friendships(session, test_users)

        # 10. Create chat messages
        print("\n[10/12] Creating chat messages...")
        await create_chat_messages(session, test_users, rooms)

        # 11. Create user achievements (earned/in-progress)
        print("\n[11/12] Creating user achievements...")
        await create_user_achievements(session, test_users)

        # 12. Create user challenges (assigned daily/weekly)
        print("\n[12/12] Creating user challenges...")
        await create_user_challenges(session, test_users)

    print("\nFake data generation complete!")


async def seed_game_content(engine: AsyncEngine) -> None:
    """Seed only game content (words, term pairs, codenames, achievements, challenges).

    Safe for production — does not create fake users, rooms, or games.

    Args:
        engine: The database engine.
    """
    print("Creating database tables (if not exist)...")
    await create_db_and_tables(engine)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        print("\n[1/4] Seeding Undercover words and pairs...")
        word_map = await seed_undercover_words(session)
        await seed_undercover_pairs(session, word_map)

        print("\n[2/4] Seeding Codenames word packs...")
        await seed_codenames_words(session)

        print("\n[3/6] Seeding Word Quiz words...")
        await seed_quiz_words(session)

        print("\n[4/6] Seeding MCQ Quiz questions...")
        await seed_mcq_questions(session)

        print("\n[5/6] Seeding achievement definitions...")
        await seed_achievements(session)

        print("\n[6/6] Seeding challenge definitions...")
        await seed_challenges(session)

    print("\nGame content seeding complete!")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate fake data for Majlisna platform testing",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--create-db", "-c",
        action="store_true",
        help="Create database tables and generate fake data",
    )
    group.add_argument(
        "--delete", "-d",
        action="store_true",
        help="Delete all data by dropping and recreating tables",
    )
    group.add_argument(
        "--seed", "-s",
        action="store_true",
        help="Seed game content only (words, term pairs, codenames, achievements, challenges). Safe for production.",
    )

    parser.add_argument(
        "--users",
        type=int,
        default=15,
        help="Number of additional random users to generate (default: 15)",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=30,
        help="Number of games to generate (default: 30)",
    )

    return parser.parse_args()


async def main() -> None:
    """Main entry point for the fake data generation script."""
    global fake
    args = parse_args()

    # Import dev-only dependencies only when needed (not in production image)
    if args.create_db:
        from faker import Faker

        fake = Faker()

    settings = Settings()  # type: ignore[call-arg]

    # This script runs DDL (drop/create every table) and then bulk-inserts, which
    # must NOT go through PgBouncer: asyncpg's per-connection type cache goes
    # stale after the DDL and the inserts fail with "could not resolve query
    # result and/or argument types in N attempts". Prefer DIRECT_DATABASE_URL.
    if settings.direct_database_url:
        settings = settings.model_copy(update={"database_url": settings.direct_database_url})
    elif "pgbouncer" in settings.database_url:
        print(
            "ERROR: DATABASE_URL points at PgBouncer and DIRECT_DATABASE_URL is not set.\n"
            "       This script runs DDL and cannot use PgBouncer's transaction pooling —\n"
            "       the bulk inserts will fail with an asyncpg type-resolution error.\n"
            "       Set DIRECT_DATABASE_URL to the PostgreSQL server itself, e.g.\n"
            "       postgresql+asyncpg://<user>:<pass>@db:5432/<db>",
            file=sys.stderr,
        )
        raise SystemExit(1)

    engine = await create_app_engine(settings)

    try:
        if args.delete:
            await delete_all_data(engine)
        elif args.seed:
            await seed_game_content(engine)
        elif args.create_db:
            await generate_all_data(
                engine,
                num_users=args.users,
                num_games=args.games,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
