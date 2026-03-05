"""Test configuration and fixtures for IPG backend."""

from datetime import datetime

import pytest
import pytest_asyncio
from faker import Faker
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.achievement import AchievementController
from ipg.api.controllers.auth import AuthController
from ipg.api.controllers.codenames import CodenamesController
from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.controllers.game import GameController
from ipg.api.controllers.room import RoomController
from ipg.api.controllers.shared import get_password_hash
from ipg.api.controllers.stats import StatsController
from ipg.api.controllers.undercover import UndercoverController
from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.controllers.user import UserController
from ipg.api.models.codenames import CodenamesWord, CodenamesWordPack, CodenamesWordPackCreate
from ipg.api.models.game import GameCreate, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.room import RoomCreate, RoomStatus
from ipg.api.models.table import Room, User
from ipg.api.models.undercover import TermPair, Word, WordCreate
from ipg.settings import Settings

# ========== Core Infrastructure ==========


@pytest.fixture(name="faker", scope="function")
def get_faker() -> Faker:
    """Get a Faker instance configured for French locale."""
    return Faker("fr_FR")


@pytest.fixture(name="test_settings", scope="function")
def get_test_settings() -> Settings:
    """Get test settings with safe defaults."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-for-unit-tests",
        jwt_encryption_algorithm="HS256",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        environment="test",
        log_level="WARNING",
        logfire_token="fake",
        frontend_url="http://localhost:3000",
        cors_origins="http://localhost:3000",
    )


@pytest_asyncio.fixture(name="engine", scope="function")
async def get_engine():
    """Create an in-memory SQLite async engine for testing.

    Uses StaticPool to ensure all connections share the same in-memory database.
    Enables foreign key enforcement via PRAGMA.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):  # noqa: ARG001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(name="session", scope="function")
async def get_session(engine: AsyncEngine) -> AsyncSession:
    """Create an async database session for testing."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


@pytest_asyncio.fixture(autouse=True, scope="function")
async def clear_database(engine: AsyncEngine):
    """Clear the database after each test function to prevent cross-test pollution."""
    yield
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = OFF;"))
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(lambda sync_engine: SQLModel.metadata.create_all(sync_engine, checkfirst=True))


# ========== Controller Fixtures ==========


@pytest_asyncio.fixture(name="auth_controller")
async def get_auth_controller(session: AsyncSession, test_settings: Settings) -> AuthController:
    """Create an AuthController instance for testing."""
    return AuthController(session, test_settings)


@pytest_asyncio.fixture(name="user_controller")
async def get_user_controller(session: AsyncSession) -> UserController:
    """Create a UserController instance for testing."""
    return UserController(session)


@pytest_asyncio.fixture(name="room_controller")
async def get_room_controller(session: AsyncSession) -> RoomController:
    """Create a RoomController instance for testing."""
    return RoomController(session)


@pytest_asyncio.fixture(name="game_controller")
async def get_game_controller(session: AsyncSession) -> GameController:
    """Create a GameController instance for testing."""
    return GameController(session)


@pytest_asyncio.fixture(name="undercover_controller")
async def get_undercover_controller(session: AsyncSession) -> UndercoverController:
    """Create an UndercoverController instance for testing."""
    return UndercoverController(session)


@pytest_asyncio.fixture(name="codenames_controller")
async def get_codenames_controller(session: AsyncSession) -> CodenamesController:
    """Create a CodenamesController instance for testing."""
    return CodenamesController(session)


@pytest_asyncio.fixture(name="stats_controller")
async def get_stats_controller(session: AsyncSession) -> StatsController:
    """Create a StatsController instance for testing."""
    return StatsController(session)


@pytest_asyncio.fixture(name="achievement_controller")
async def get_achievement_controller(session: AsyncSession) -> AchievementController:
    """Create an AchievementController instance for testing."""
    return AchievementController(session)


@pytest_asyncio.fixture(name="undercover_game_controller")
async def get_undercover_game_controller(session: AsyncSession) -> UndercoverGameController:
    """Create an UndercoverGameController instance for testing."""
    return UndercoverGameController(session)


@pytest_asyncio.fixture(name="codenames_game_controller")
async def get_codenames_game_controller(session: AsyncSession) -> CodenamesGameController:
    """Create a CodenamesGameController instance for testing."""
    return CodenamesGameController(session)


# ========== Factory Fixtures ==========


@pytest_asyncio.fixture(name="create_user")
async def get_create_user(session: AsyncSession):
    """Factory fixture for creating users in tests."""

    async def _create_user(
        username: str = "testuser",
        email: str = "test@example.com",
        password: str = "password123",
        country: str | None = None,
    ) -> User:
        hashed = get_password_hash(password)
        user = User(username=username, email_address=email, password=hashed, country=country)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    return _create_user


@pytest_asyncio.fixture(name="create_room")
async def get_create_room(room_controller: RoomController):
    """Factory fixture for creating rooms via the controller."""

    async def _create_room(
        owner: User,
        password: str = "1234",
        status: RoomStatus = RoomStatus.ONLINE,
    ) -> Room:
        room_create = RoomCreate(status=status, password=password, owner_id=owner.id)
        return await room_controller.create_room(room_create)

    return _create_room


@pytest_asyncio.fixture(name="create_word")
async def get_create_word(undercover_controller: UndercoverController):
    """Factory fixture for creating undercover words via the controller."""

    async def _create_word(
        word: str = "test_word",
        category: str = "test_category",
        short_description: str = "Short desc",
        long_description: str = "Long desc",
    ) -> Word:
        return await undercover_controller.create_word(
            WordCreate(
                word=word,
                category=category,
                short_description=short_description,
                long_description=long_description,
            )
        )

    return _create_word


@pytest_asyncio.fixture(name="create_codenames_word_pack")
async def get_create_codenames_word_pack(codenames_controller: CodenamesController):
    """Factory fixture for creating codenames word packs via the controller."""

    async def _create_pack(
        name: str = "Test Pack",
        description: str | None = "A test word pack",
    ) -> CodenamesWordPack:
        return await codenames_controller.create_word_pack(CodenamesWordPackCreate(name=name, description=description))

    return _create_pack


# ========== Sample Object Fixtures ==========
# Pre-created objects used across many tests to avoid repetition.


@pytest_asyncio.fixture(name="sample_user")
async def get_sample_user(create_user) -> User:
    """Create a sample user available for tests that need a pre-existing user."""
    return await create_user(username="sampleuser", email="sample@test.com", password="samplepass123")


@pytest_asyncio.fixture(name="sample_owner")
async def get_sample_owner(create_user) -> User:
    """Create a sample room owner for tests that need a room with an owner."""
    return await create_user(username="owner", email="owner@test.com", password="ownerpass123")


@pytest_asyncio.fixture(name="sample_room")
async def get_sample_room(sample_owner: User, create_room) -> Room:
    """Create a sample room with a sample owner for tests that need a pre-existing room."""
    return await create_room(owner=sample_owner, password="1234")


@pytest_asyncio.fixture(name="sample_game")
async def get_sample_game(sample_room: Room, game_controller: GameController):
    """Create a sample game inside the sample room."""
    game_create = GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=4)
    return await game_controller.create_game(game_create)


@pytest_asyncio.fixture(name="sample_word")
async def get_sample_word(create_word) -> Word:
    """Create a sample undercover word for tests that need a pre-existing word."""
    return await create_word(
        word="mosque",
        category="islamic",
        short_description="Place of worship",
        long_description="A place where Muslims gather for prayer",
    )


# ========== Game Setup Factories ==========


@pytest_asyncio.fixture(name="setup_undercover_game")
async def get_setup_undercover_game(session: AsyncSession, create_user, create_room):
    """Factory fixture that creates N users + room + RoomUserLinks + Word + TermPair.

    Returns a dict with users, room, word1, word2, term_pair.
    """

    async def _setup(num_players: int = 3) -> dict:
        users = []
        for i in range(num_players):
            user = await create_user(
                username=f"player{i}",
                email=f"player{i}@test.com",
                password="password123",
            )
            users.append(user)

        room = await create_room(owner=users[0])

        # Create RoomUserLinks for all players (connected=True)
        for user in users:
            existing = (
                await session.exec(
                    select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
                )
            ).first()
            if not existing:
                link = RoomUserLink(
                    room_id=room.id,
                    user_id=user.id,
                    connected=True,
                    last_seen_at=datetime.now(),
                )
                session.add(link)
        await session.commit()

        # Create words and term pair
        word1 = Word(word="mosque", category="islamic", short_description="A", long_description="B")
        word2 = Word(word="church", category="islamic", short_description="C", long_description="D")
        session.add(word1)
        session.add(word2)
        await session.commit()
        await session.refresh(word1)
        await session.refresh(word2)

        term_pair = TermPair(word1_id=word1.id, word2_id=word2.id)
        session.add(term_pair)
        await session.commit()
        await session.refresh(term_pair)

        return {
            "users": users,
            "room": room,
            "word1": word1,
            "word2": word2,
            "term_pair": term_pair,
        }

    return _setup


@pytest_asyncio.fixture(name="setup_codenames_game")
async def get_setup_codenames_game(session: AsyncSession, create_user, create_room):
    """Factory fixture that creates N users + room + RoomUserLinks + WordPack with 25+ words.

    Returns a dict with users, room, word_pack, words.
    """

    async def _setup(num_players: int = 4) -> dict:
        users = []
        for i in range(num_players):
            user = await create_user(
                username=f"cnplayer{i}",
                email=f"cnplayer{i}@test.com",
                password="password123",
            )
            users.append(user)

        room = await create_room(owner=users[0])

        # Create RoomUserLinks for all players (connected=True)
        for user in users:
            existing = (
                await session.exec(
                    select(RoomUserLink).where(RoomUserLink.room_id == room.id).where(RoomUserLink.user_id == user.id)
                )
            ).first()
            if not existing:
                link = RoomUserLink(
                    room_id=room.id,
                    user_id=user.id,
                    connected=True,
                    last_seen_at=datetime.now(),
                )
                session.add(link)
        await session.commit()

        # Create word pack with 30 words (more than the 25 needed)
        word_pack = CodenamesWordPack(name="Test Pack", description="Test")
        session.add(word_pack)
        await session.commit()
        await session.refresh(word_pack)

        words = []
        word_list = [
            "Quran",
            "Salah",
            "Zakat",
            "Hajj",
            "Sawm",
            "Iman",
            "Ihsan",
            "Taqwa",
            "Dua",
            "Dhikr",
            "Mosque",
            "Minaret",
            "Mihrab",
            "Minbar",
            "Wudu",
            "Adhan",
            "Iqama",
            "Sunnah",
            "Hadith",
            "Fiqh",
            "Sharia",
            "Ummah",
            "Hijab",
            "Sadaqah",
            "Dawah",
            "Barakah",
            "Jannat",
            "Tawhid",
            "Khalifah",
            "Makkah",
        ]
        for w in word_list:
            word = CodenamesWord(word=w, word_pack_id=word_pack.id)
            session.add(word)
            words.append(word)
        await session.commit()
        for w in words:
            await session.refresh(w)

        return {
            "users": users,
            "room": room,
            "word_pack": word_pack,
            "words": words,
        }

    return _setup
