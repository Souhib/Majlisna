#!/usr/bin/env python3
"""Script to generate fake data for IPG platform testing.

This script can be used to:
1. Create database tables and generate fake users, rooms, games, and seed data
2. Delete all data from the database (drop and recreate tables)
3. Seed Undercover word pairs (30+ Islamic term pairs)
4. Seed Codenames word packs (100+ Islamic terms in categories)
5. Seed achievement definitions
6. Create UserStats entries for test users

Usage:
    # Create database tables and generate fake data
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -c

    # Delete all data from the database
    PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -d

    # Custom data volumes
    PYTHONPATH=. uv run python scripts/generate_fake_data.py -c --users 50 --games 100

Options:
    --delete, -d         Delete all data by dropping and recreating tables
    --create-db, -c      Create tables and generate fake data
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
from datetime import datetime, timedelta
from uuid import uuid4

import pycountry
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.achievement import AchievementController
from ipg.api.controllers.shared import get_password_hash
from ipg.api.models.codenames import CodenamesWord, CodenamesWordPack
from ipg.api.models.game import GameType
from ipg.api.models.room import RoomStatus, RoomType
from ipg.api.models.stats import UserStats
from ipg.api.models.table import Game, Room, User
from ipg.api.models.undercover import TermPair, Word
from ipg.database import create_app_engine, create_db_and_tables
from ipg.settings import Settings

fake = Faker()


# ── Test user accounts ──────────────────────────────────────────────────────

TEST_USERS = [
    {
        "username": "admin",
        "email_address": "admin@test.com",
        "password": "admin123",
        "country": "SAU",
    },
    {
        "username": "user",
        "email_address": "user@test.com",
        "password": "user1234",
        "country": "ARE",
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
    },
    {
        "username": "fatima",
        "email_address": "fatima@test.com",
        "password": "fatima12",
        "country": "TUN",
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


# ── Undercover word pairs (30+ Islamic term pairs) ──────────────────────────

UNDERCOVER_WORDS = [
    # Pillars of Islam
    {"word": "Hajj", "category": "Pillars of Islam", "short_description": "Pilgrimage to Mecca", "long_description": "The fifth pillar of Islam requiring able Muslims to make a pilgrimage to Mecca at least once."},
    {"word": "Umrah", "category": "Islamic Rituals", "short_description": "Minor pilgrimage to Mecca", "long_description": "A voluntary pilgrimage to Mecca that can be performed at any time of the year."},
    {"word": "Salah", "category": "Pillars of Islam", "short_description": "Islamic ritual prayer", "long_description": "The second pillar of Islam consisting of five daily prayers obligatory for all adult Muslims."},
    {"word": "Sawm", "category": "Pillars of Islam", "short_description": "Fasting during Ramadan", "long_description": "The fourth pillar of Islam observed during Ramadan where Muslims fast from dawn until sunset."},
    {"word": "Zakat", "category": "Pillars of Islam", "short_description": "Compulsory charity", "long_description": "The third pillar of Islam requiring Muslims to give a fixed portion of their wealth to the needy."},
    {"word": "Sadaqah", "category": "Charitable Practices", "short_description": "Voluntary charity", "long_description": "Voluntary charitable acts extending beyond monetary donations to include acts of kindness."},
    {"word": "Shahada", "category": "Pillars of Islam", "short_description": "Declaration of faith", "long_description": "The first pillar of Islam expressing faith in the oneness of Allah and prophethood of Muhammad."},
    {"word": "Tawhid", "category": "Islamic Beliefs", "short_description": "Oneness of God", "long_description": "The principle of monotheism in Islam affirming the oneness and absolute sovereignty of God."},
    # Prophets and figures
    {"word": "Ibrahim", "category": "Prophets", "short_description": "Prophet Abraham in Islam", "long_description": "Prophet Ibrahim (Abraham) is considered the father of monotheism and a key prophet in Islam."},
    {"word": "Ismail", "category": "Prophets", "short_description": "Prophet Ishmael in Islam", "long_description": "Prophet Ismail (Ishmael), son of Ibrahim, is regarded as a prophet and ancestor of the Arab people."},
    {"word": "Musa", "category": "Prophets", "short_description": "Prophet Moses in Islam", "long_description": "Prophet Musa (Moses) is one of the most frequently mentioned prophets in the Quran."},
    {"word": "Isa", "category": "Prophets", "short_description": "Prophet Jesus in Islam", "long_description": "Prophet Isa (Jesus) is a revered prophet in Islam, born miraculously to Maryam."},
    {"word": "Maryam", "category": "Islamic Figures", "short_description": "Mother of Prophet Isa", "long_description": "Maryam (Mary) is the only woman mentioned by name in the Quran, revered for her piety."},
    {"word": "Khadijah", "category": "Islamic Figures", "short_description": "First wife of the Prophet", "long_description": "Khadijah bint Khuwaylid was the first wife of Prophet Muhammad and the first person to accept Islam."},
    # Places
    {"word": "Masjid", "category": "Islamic Places", "short_description": "Place of worship", "long_description": "A masjid (mosque) is a place of worship for Muslims, used for daily prayers and community gatherings."},
    {"word": "Mihrab", "category": "Islamic Architecture", "short_description": "Prayer niche in a mosque", "long_description": "The mihrab is a semicircular niche in the wall of a mosque that indicates the direction of Mecca."},
    {"word": "Minbar", "category": "Islamic Architecture", "short_description": "Pulpit in a mosque", "long_description": "The minbar is a raised platform or pulpit in a mosque where the imam delivers the Friday sermon."},
    {"word": "Minaret", "category": "Islamic Architecture", "short_description": "Tower of a mosque", "long_description": "A minaret is a tower from which the call to prayer (adhan) is traditionally broadcast."},
    {"word": "Kaaba", "category": "Islamic Places", "short_description": "Sacred cube structure in Mecca", "long_description": "The Kaaba is the most sacred site in Islam, located in the center of Masjid al-Haram in Mecca."},
    {"word": "Medina", "category": "Islamic Places", "short_description": "City of the Prophet", "long_description": "Medina is the second holiest city in Islam where Prophet Muhammad migrated to and is buried."},
    # Concepts
    {"word": "Tawakkul", "category": "Islamic Concepts", "short_description": "Trust in God", "long_description": "Tawakkul is the Islamic concept of placing complete trust and reliance in God's plan."},
    {"word": "Sabr", "category": "Islamic Concepts", "short_description": "Patience", "long_description": "Sabr is the virtue of patience and perseverance in the face of hardship, a core Islamic concept."},
    {"word": "Shukr", "category": "Islamic Concepts", "short_description": "Gratitude", "long_description": "Shukr is the practice of showing gratitude to Allah for blessings, both in words and actions."},
    {"word": "Taqwa", "category": "Islamic Concepts", "short_description": "God-consciousness", "long_description": "Taqwa is the awareness of God in all aspects of life, often translated as piety or mindfulness."},
    {"word": "Ihsan", "category": "Islamic Concepts", "short_description": "Excellence in worship", "long_description": "Ihsan means to worship Allah as if you see Him, and if you cannot see Him, He sees you."},
    {"word": "Iman", "category": "Islamic Beliefs", "short_description": "Faith", "long_description": "Iman encompasses belief in God, His angels, His books, His messengers, the Last Day, and divine decree."},
    {"word": "Jihad", "category": "Islamic Concepts", "short_description": "Struggle in God's way", "long_description": "Jihad represents struggle against evil inclinations and effort in the way of God."},
    {"word": "Hijrah", "category": "Islamic History", "short_description": "Migration to Medina", "long_description": "The Hijrah is the migration of Prophet Muhammad from Mecca to Medina in 622 CE."},
    # Practices
    {"word": "Wudu", "category": "Islamic Practices", "short_description": "Ablution before prayer", "long_description": "Wudu is the ritual washing performed by Muslims before prayer to achieve physical and spiritual purity."},
    {"word": "Tayammum", "category": "Islamic Practices", "short_description": "Dry ablution", "long_description": "Tayammum is the Islamic act of dry ablution using clean earth when water is unavailable."},
    {"word": "Adhan", "category": "Islamic Practices", "short_description": "Call to prayer", "long_description": "The adhan is the Islamic call to prayer recited by the muezzin from the mosque five times daily."},
    {"word": "Iqamah", "category": "Islamic Practices", "short_description": "Second call to prayer", "long_description": "The iqamah is the second call to prayer given immediately before the congregational prayer begins."},
    {"word": "Dhikr", "category": "Islamic Practices", "short_description": "Remembrance of God", "long_description": "Dhikr is the devotional act of remembering God through phrases, prayers, or meditation."},
    {"word": "Dua", "category": "Islamic Practices", "short_description": "Supplication", "long_description": "Dua is the act of supplication or personal prayer where Muslims directly communicate with God."},
    {"word": "Quran", "category": "Islamic Texts", "short_description": "Holy book of Islam", "long_description": "The Quran is the central religious text of Islam believed to be the direct word of God."},
    {"word": "Hadith", "category": "Islamic Texts", "short_description": "Prophetic traditions", "long_description": "Hadiths are records of the sayings, actions, and approvals of Prophet Muhammad."},
    {"word": "Sunnah", "category": "Islamic Practices", "short_description": "Prophetic tradition and way of life", "long_description": "The Sunnah refers to the practices and teachings of Prophet Muhammad as a model for Muslims."},
    {"word": "Fiqh", "category": "Islamic Sciences", "short_description": "Islamic jurisprudence", "long_description": "Fiqh is the body of Islamic jurisprudence dealing with the observance of rituals, morals, and social legislation."},
    # Food and daily life
    {"word": "Halal", "category": "Islamic Law", "short_description": "Permissible", "long_description": "Halal refers to what is permissible under Islamic law, commonly used in reference to food."},
    {"word": "Haram", "category": "Islamic Law", "short_description": "Forbidden", "long_description": "Haram refers to anything that is forbidden under Islamic law."},
    {"word": "Iftar", "category": "Ramadan", "short_description": "Breaking the fast", "long_description": "Iftar is the meal eaten by Muslims after sunset during Ramadan to break the daily fast."},
    {"word": "Suhoor", "category": "Ramadan", "short_description": "Pre-dawn meal", "long_description": "Suhoor is the pre-dawn meal consumed by Muslims before beginning the fast during Ramadan."},
    # Special times and events
    {"word": "Laylat al-Qadr", "category": "Islamic Events", "short_description": "Night of Power", "long_description": "Laylat al-Qadr is the most sacred night in Islam, believed to be when the Quran was first revealed."},
    {"word": "Eid al-Fitr", "category": "Islamic Holidays", "short_description": "Festival of breaking the fast", "long_description": "Eid al-Fitr marks the end of Ramadan and is celebrated with prayers, feasts, and giving."},
    {"word": "Eid al-Adha", "category": "Islamic Holidays", "short_description": "Festival of sacrifice", "long_description": "Eid al-Adha commemorates Ibrahim's willingness to sacrifice his son and concludes the Hajj."},
    {"word": "Jummah", "category": "Islamic Practices", "short_description": "Friday congregational prayer", "long_description": "Jummah is the congregational prayer held every Friday, the most important prayer of the week."},
]

# Word pairs (each pair contains two related but different Islamic terms)
UNDERCOVER_WORD_PAIRS = [
    ("Hajj", "Umrah"),
    ("Salah", "Sawm"),
    ("Zakat", "Sadaqah"),
    ("Shahada", "Tawhid"),
    ("Jihad", "Hijrah"),
    ("Ibrahim", "Ismail"),
    ("Musa", "Isa"),
    ("Maryam", "Khadijah"),
    ("Masjid", "Mihrab"),
    ("Minbar", "Minaret"),
    ("Kaaba", "Medina"),
    ("Tawakkul", "Sabr"),
    ("Shukr", "Taqwa"),
    ("Ihsan", "Iman"),
    ("Wudu", "Tayammum"),
    ("Adhan", "Iqamah"),
    ("Dhikr", "Dua"),
    ("Quran", "Hadith"),
    ("Sunnah", "Fiqh"),
    ("Halal", "Haram"),
    ("Iftar", "Suhoor"),
    ("Eid al-Fitr", "Eid al-Adha"),
    ("Laylat al-Qadr", "Jummah"),
    ("Salah", "Dua"),
    ("Zakat", "Hajj"),
    ("Quran", "Sunnah"),
    ("Sabr", "Shukr"),
    ("Taqwa", "Ihsan"),
    ("Masjid", "Kaaba"),
    ("Wudu", "Salah"),
    ("Ibrahim", "Musa"),
    ("Adhan", "Jummah"),
]


# ── Codenames word packs (100+ Islamic terms in categories) ─────────────────

CODENAMES_WORD_PACKS = {
    "Prophets & Messengers": [
        "Adam", "Nuh", "Ibrahim", "Ismail", "Ishaq",
        "Yaqub", "Yusuf", "Musa", "Harun", "Dawud",
        "Sulayman", "Isa", "Muhammad", "Ayyub", "Yunus",
        "Idris", "Hud", "Salih", "Shuayb", "Lut",
    ],
    "Quran & Surahs": [
        "Fatiha", "Baqarah", "Yasin", "Rahman", "Mulk",
        "Kahf", "Maryam", "Taha", "Naba", "Ikhlas",
        "Falaq", "Nas", "Ayah", "Juz", "Hizb",
        "Tanzil", "Tafsir", "Tajweed", "Tilawah", "Mushaf",
    ],
    "Islamic History": [
        "Hijrah", "Badr", "Uhud", "Khandaq", "Hudaybiyyah",
        "Mecca", "Medina", "Abyssinia", "Taif", "Tabuk",
        "Khaybar", "Caliphate", "Umayyad", "Abbasid", "Ottoman",
        "Andalusia", "Baghdad", "Damascus", "Cordoba", "Jerusalem",
    ],
    "Worship & Rituals": [
        "Salah", "Zakat", "Sawm", "Hajj", "Shahada",
        "Wudu", "Adhan", "Iqamah", "Qiyam", "Sujud",
        "Ruku", "Tashahhud", "Tasleem", "Takbir", "Tahmid",
        "Tasbih", "Istighfar", "Tawaf", "Sai", "Ihram",
    ],
    "Islamic Values": [
        "Tawakkul", "Sabr", "Shukr", "Taqwa", "Ihsan",
        "Iman", "Adl", "Rahma", "Hikmah", "Ilm",
        "Amanah", "Sidq", "Haya", "Tawbah", "Ikhlas",
        "Birr", "Husn", "Khushu", "Wara", "Zuhd",
    ],
    "Islamic Sciences": [
        "Fiqh", "Hadith", "Tafsir", "Aqeedah", "Usul",
        "Seerah", "Tajweed", "Nahw", "Sarf", "Balagha",
        "Mantiq", "Falsafa", "Kalam", "Tasawwuf", "Ijtihad",
    ],
}


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


async def seed_undercover_words(session: AsyncSession) -> dict[str, Word]:
    """Seed all Undercover words and return a mapping of word text to Word object.

    Args:
        session: The database session.

    Returns:
        Dictionary mapping word text to Word objects.
    """
    word_map: dict[str, Word] = {}

    for word_data in UNDERCOVER_WORDS:
        word = Word(
            id=uuid4(),
            word=word_data["word"],
            category=word_data["category"],
            short_description=word_data["short_description"],
            long_description=word_data["long_description"],
        )
        session.add(word)
        word_map[word_data["word"]] = word

    await session.commit()
    for word in word_map.values():
        await session.refresh(word)

    print(f"  Seeded {len(word_map)} Undercover words")
    return word_map


async def seed_undercover_pairs(session: AsyncSession, word_map: dict[str, Word]) -> None:
    """Seed Undercover word pairs.

    Args:
        session: The database session.
        word_map: Dictionary mapping word text to Word objects.
    """
    count = 0
    for word1_text, word2_text in UNDERCOVER_WORD_PAIRS:
        w1 = word_map.get(word1_text)
        w2 = word_map.get(word2_text)
        if w1 is None or w2 is None:
            print(f"    Warning: Skipping pair ({word1_text}, {word2_text}) - word not found")
            continue

        pair = TermPair(
            id=uuid4(),
            word1_id=w1.id,
            word2_id=w2.id,
        )
        session.add(pair)
        count += 1

    await session.commit()
    print(f"  Seeded {count} Undercover word pairs")


async def seed_codenames_words(session: AsyncSession) -> None:
    """Seed Codenames word packs and words.

    Args:
        session: The database session.
    """
    total_words = 0

    for pack_name, words in CODENAMES_WORD_PACKS.items():
        pack = CodenamesWordPack(
            id=uuid4(),
            name=pack_name,
            description=f"Islamic terms related to {pack_name.lower()}",
            is_active=True,
        )
        session.add(pack)
        await session.flush()

        for word_text in words:
            word = CodenamesWord(
                id=uuid4(),
                word=word_text,
                word_pack_id=pack.id,
            )
            session.add(word)
            total_words += 1

    await session.commit()
    print(f"  Seeded {len(CODENAMES_WORD_PACKS)} Codenames word packs with {total_words} words")


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
        print("\n[1/7] Creating test users...")
        test_users = await create_test_users(session)

        # 2. Create random users
        print(f"\n[2/7] Creating {num_users} random users...")
        random_users = await create_random_users(session, num_users)
        all_users = test_users + random_users

        # 3. Create rooms
        print("\n[3/7] Creating rooms...")
        await create_rooms(session, all_users, count=max(5, len(all_users) // 3))

        # 4. Seed Undercover words and pairs
        print("\n[4/7] Seeding Undercover words and pairs...")
        word_map = await seed_undercover_words(session)
        await seed_undercover_pairs(session, word_map)

        # 5. Seed Codenames words
        print("\n[5/7] Seeding Codenames word packs...")
        await seed_codenames_words(session)

        # 6. Seed achievements
        print("\n[6/7] Seeding achievement definitions...")
        await seed_achievements(session)

        # 7. Create games and stats
        print(f"\n[7/7] Creating {num_games} games and user stats...")
        await create_games(session, all_users, count=num_games)
        await create_user_stats(session, test_users)

    print("\nFake data generation complete!")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate fake data for IPG platform testing",
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
    args = parse_args()

    settings = Settings()  # type: ignore[call-arg]
    engine = await create_app_engine(settings)

    try:
        if args.delete:
            await delete_all_data(engine)
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
