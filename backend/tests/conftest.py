"""Test configuration and fixtures for Majlisna backend."""

import subprocess
from datetime import datetime

import pytest
import pytest_asyncio
from faker import Faker
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.controllers.chat import ChatController
from majlisna.api.controllers.codenames import CodenamesController
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.notebook import NotebookController
from majlisna.api.controllers.profile import ProfileController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.shared import get_password_hash
from majlisna.api.controllers.stats import StatsController
from majlisna.api.controllers.term_script import TermScriptController
from majlisna.api.controllers.undercover import UndercoverController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.user import UserController
from majlisna.api.controllers.wordquiz import WordQuizController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.codenames import CodenamesWord, CodenamesWordPack, CodenamesWordPackCreate
from majlisna.api.models.game import GameCreate, GameType
from majlisna.api.models.mcqquiz import McqQuestion
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Room, User
from majlisna.api.models.undercover import TermPair, Word, WordCreate
from majlisna.api.models.wordquiz import QuizWord
from majlisna.api.schemas.term_script import TermScriptEntry
from majlisna.api.utils.cache import cache
from majlisna.settings import Settings

# ========== PyTest Configuration ==========


def pytest_addoption(parser):
    """Add --use-postgres flag to run tests against a PostgreSQL testcontainer."""
    parser.addoption(
        "--use-postgres",
        action="store_true",
        default=False,
        help="Use PostgreSQL testcontainer instead of in-memory SQLite",
    )


def pytest_configure(config):
    """Register the 'postgres' marker and check Docker availability when --use-postgres is specified."""
    config.addinivalue_line("markers", "postgres: marks tests requiring PostgreSQL (skip without --use-postgres)")
    if config.getoption("--use-postgres", default=False):
        error_reason = None
        try:
            result = subprocess.run(["docker", "info"], check=False, capture_output=True, timeout=10)
            if result.returncode != 0:
                error_reason = "Docker is not running"
        except FileNotFoundError:
            error_reason = "Docker is not installed"
        except subprocess.TimeoutExpired:
            error_reason = "Docker is not responding (timed out)"

        if error_reason:
            raise pytest.UsageError(
                f"\n\n{error_reason}!\n\n"
                f"--use-postgres requires Docker to run PostgreSQL testcontainers.\n"
                f"Please start Docker and try again, or run without --use-postgres.\n"
            )


def pytest_collection_modifyitems(config, items):
    """Auto-skip @pytest.mark.postgres tests when running without --use-postgres."""
    if not config.getoption("--use-postgres"):
        skip_postgres = pytest.mark.skip(reason="Requires PostgreSQL (use --use-postgres flag)")
        for item in items:
            if "postgres" in item.keywords:
                item.add_marker(skip_postgres)


# ========== Cache Cleanup ==========


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the TTL cache before and after each test to prevent cross-test pollution."""
    cache.clear()
    yield
    cache.clear()


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


@pytest.fixture(name="use_postgres", scope="session")
def get_use_postgres(request):
    """Determine whether to use PostgreSQL or SQLite for tests."""
    return request.config.getoption("--use-postgres")


@pytest.fixture(name="postgres_container", scope="session")
def get_postgres_container(use_postgres):
    """Start a PostgreSQL testcontainer once for the entire test session."""
    if not use_postgres:
        yield None
        return

    from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest_asyncio.fixture(name="engine", scope="function")
async def get_engine(use_postgres, postgres_container):
    """Create a database engine for testing.

    SQLite (default): In-memory with StaticPool, PRAGMA foreign_keys=ON.
    PostgreSQL (--use-postgres): Testcontainer with NullPool.
    """
    if use_postgres:
        if postgres_container is None:
            raise RuntimeError("PostgreSQL container not available. Make sure Docker is running.")

        db_url = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        engine = create_async_engine(db_url, echo=False, poolclass=NullPool)

        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_engine: SQLModel.metadata.create_all(sync_engine, checkfirst=True))

        yield engine
        await engine.dispose()
    else:
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
    is_sqlite = "sqlite" in str(engine.url)
    async with engine.begin() as conn:
        if is_sqlite:
            await conn.execute(text("PRAGMA foreign_keys = OFF;"))
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.execute(text("PRAGMA foreign_keys = ON;"))
            await conn.run_sync(lambda sync_engine: SQLModel.metadata.create_all(sync_engine, checkfirst=True))
        else:
            # PostgreSQL: truncate all tables for faster cleanup
            for table in reversed(SQLModel.metadata.sorted_tables):
                await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))  # noqa: S608


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


@pytest_asyncio.fixture(name="challenge_controller")
async def get_challenge_controller(session: AsyncSession) -> ChallengeController:
    """Create a ChallengeController instance for testing."""
    return ChallengeController(session)


@pytest_asyncio.fixture(name="friend_controller")
async def get_friend_controller(session: AsyncSession) -> FriendController:
    """Create a FriendController instance for testing."""
    return FriendController(session)


@pytest_asyncio.fixture(name="chat_controller")
async def get_chat_controller(session: AsyncSession) -> ChatController:
    """Create a ChatController instance for testing."""
    return ChatController(session)


@pytest_asyncio.fixture(name="profile_controller")
async def get_profile_controller(session: AsyncSession) -> ProfileController:
    """Create a ProfileController instance for testing."""
    return ProfileController(session)


@pytest_asyncio.fixture(name="notebook_controller")
async def get_notebook_controller(session: AsyncSession) -> NotebookController:
    """Create a NotebookController instance for testing."""
    return NotebookController(session)


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
        game_type: GameType = GameType.UNDERCOVER,
    ) -> Room:
        return await room_controller.create_room(owner_id=owner.id, game_type=game_type)

    return _create_room


@pytest_asyncio.fixture(name="create_term_scripts")
async def get_create_term_scripts(session: AsyncSession):
    """Factory fixture: store Arabic forms, given as ``{term: (ar, ar_vocalized)}``."""

    async def _create_term_scripts(scripts: dict[str, tuple[str, str | None]]) -> None:
        entries = [
            TermScriptEntry(term=term, ar=ar, ar_vocalized=vocalized) for term, (ar, vocalized) in scripts.items()
        ]
        await TermScriptController(session).upsert(entries)

    return _create_term_scripts


class StatementCounter:
    """Counts the SQL statements that mention ``needle`` (an engine event listener)."""

    def __init__(self, needle: str):
        self.needle = needle
        self.count = 0

    def __call__(self, conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ARG002
        if self.needle in statement:
            self.count += 1


@pytest_asyncio.fixture(name="count_statements")
async def get_count_statements(engine: AsyncEngine):
    """Factory fixture: start counting statements that mention a table, e.g. ``"term_script"``.

    Used to pin the "one batched lookup per request" rule, so an N+1 regression fails
    a test instead of only showing up as latency.
    """
    counters: list[StatementCounter] = []

    def _count_statements(needle: str) -> StatementCounter:
        counter = StatementCounter(needle)
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        counters.append(counter)
        return counter

    yield _count_statements
    for counter in counters:
        event.remove(engine.sync_engine, "before_cursor_execute", counter)


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
    return await create_room(owner=sample_owner)


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


# ========== Word Quiz Fixtures ==========


@pytest_asyncio.fixture(name="wordquiz_controller")
async def get_wordquiz_controller(session: AsyncSession) -> WordQuizController:
    """Create a WordQuizController instance for testing."""
    return WordQuizController(session)


@pytest_asyncio.fixture(name="wordquiz_game_controller")
async def get_wordquiz_game_controller(session: AsyncSession) -> WordQuizGameController:
    """Create a WordQuizGameController instance for testing."""
    return WordQuizGameController(session)


@pytest_asyncio.fixture(name="create_quiz_word")
async def get_create_quiz_word(session: AsyncSession):
    """Factory fixture for creating quiz words."""

    async def _create_quiz_word(
        word_en: str = "Ibrahim",
        word_ar: str | None = "إبراهيم",
        word_fr: str | None = "Ibrahim",
        accepted_answers: dict | None = None,
        category: str = "Prophets",
        hints: dict | None = None,
    ) -> QuizWord:
        if accepted_answers is None:
            accepted_answers = {"en": [word_en], "ar": [word_ar] if word_ar else [], "fr": [word_fr] if word_fr else []}
        if hints is None:
            hints = {
                "1": {"en": "Hint 1", "ar": "تلميح 1", "fr": "Indice 1"},
                "2": {"en": "Hint 2", "ar": "تلميح 2", "fr": "Indice 2"},
                "3": {"en": "Hint 3", "ar": "تلميح 3", "fr": "Indice 3"},
                "4": {"en": "Hint 4", "ar": "تلميح 4", "fr": "Indice 4"},
                "5": {"en": "Hint 5", "ar": "تلميح 5", "fr": "Indice 5"},
                "6": {"en": "Hint 6", "ar": "تلميح 6", "fr": "Indice 6"},
            }
        quiz_word = QuizWord(
            word_en=word_en,
            word_ar=word_ar,
            word_fr=word_fr,
            accepted_answers=accepted_answers,
            category=category,
            hints=hints,
        )
        session.add(quiz_word)
        await session.commit()
        await session.refresh(quiz_word)
        return quiz_word

    return _create_quiz_word


@pytest_asyncio.fixture(name="setup_wordquiz_game")
async def get_setup_wordquiz_game(session: AsyncSession, create_user, create_room, create_quiz_word):
    """Factory fixture that creates N users + room + RoomUserLinks + QuizWords.

    Returns a dict with users, room, quiz_words.
    """

    async def _setup(num_players: int = 2, num_words: int = 3) -> dict:
        users = []
        for i in range(num_players):
            user = await create_user(
                username=f"wqplayer{i}",
                email=f"wqplayer{i}@test.com",
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

        # Create quiz words
        quiz_words = []
        word_names = ["Ibrahim", "Musa", "Isa", "Nuh", "Yusuf", "Muhammad", "Ali", "Umar", "Bilal", "Dawud"]
        for i in range(min(num_words, len(word_names))):
            qw = await create_quiz_word(
                word_en=word_names[i],
                word_ar=f"عربي_{i}",
                word_fr=f"Français_{i}",
            )
            quiz_words.append(qw)

        return {
            "users": users,
            "room": room,
            "quiz_words": quiz_words,
        }

    return _setup


# ========== MCQ Quiz Fixtures ==========


@pytest_asyncio.fixture(name="mcqquiz_game_controller")
async def get_mcqquiz_game_controller(session: AsyncSession) -> McqQuizGameController:
    """Create a McqQuizGameController instance for testing."""
    return McqQuizGameController(session)


@pytest_asyncio.fixture(name="create_mcq_question")
async def get_create_mcq_question(session: AsyncSession):
    """Factory fixture for creating MCQ questions."""

    async def _create_mcq_question(
        question_en: str = "What is the first pillar of Islam?",
        question_ar: str | None = "ما هو الركن الأول من أركان الإسلام؟",
        question_fr: str | None = "Quel est le premier pilier de l'Islam ?",
        choices: dict | None = None,
        correct_answer_index: int = 0,
        category: str = "Pillars of Islam",
        explanation: dict | None = None,
    ) -> McqQuestion:
        if choices is None:
            choices = {
                "0": {"en": "Shahada", "ar": "الشهادة", "fr": "Shahada"},
                "1": {"en": "Salah", "ar": "الصلاة", "fr": "Salah"},
                "2": {"en": "Zakat", "ar": "الزكاة", "fr": "Zakat"},
                "3": {"en": "Hajj", "ar": "الحج", "fr": "Hajj"},
            }
        if explanation is None:
            explanation = {
                "en": "The Shahada is the declaration of faith.",
                "ar": "الشهادة هي إعلان الإيمان.",
                "fr": "La Shahada est la déclaration de foi.",
            }
        mcq_question = McqQuestion(
            question_en=question_en,
            question_ar=question_ar,
            question_fr=question_fr,
            choices=choices,
            correct_answer_index=correct_answer_index,
            category=category,
            explanation=explanation,
        )
        session.add(mcq_question)
        await session.commit()
        await session.refresh(mcq_question)
        return mcq_question

    return _create_mcq_question


@pytest_asyncio.fixture(name="setup_mcqquiz_game")
async def get_setup_mcqquiz_game(session: AsyncSession, create_user, create_room, create_mcq_question):
    """Factory fixture that creates N users + room + RoomUserLinks + McqQuestions."""

    async def _setup(num_players: int = 2, num_questions: int = 3) -> dict:
        users = []
        for i in range(num_players):
            user = await create_user(
                username=f"mcqplayer{i}",
                email=f"mcqplayer{i}@test.com",
                password="password123",
            )
            users.append(user)

        room = await create_room(owner=users[0])

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

        questions = []
        question_templates = [
            ("Who built the Kaaba?", "من بنى الكعبة؟", "Qui a construit la Kaaba ?", "Prophets"),
            (
                "How many pillars does Islam have?",
                "كم عدد أركان الإسلام؟",
                "Combien de piliers l'Islam a-t-il ?",
                "Pillars of Islam",
            ),
            (
                "What is the longest surah in the Quran?",
                "ما أطول سورة في القرآن؟",
                "Quelle est la plus longue sourate du Coran ?",
                "Quran",
            ),
            (
                "In which city was the Prophet born?",
                "في أي مدينة ولد النبي؟",
                "Dans quelle ville le Prophète est-il né ?",
                "Seerah",
            ),
            (
                "What is the first month of the Islamic calendar?",
                "ما هو أول شهر في التقويم الإسلامي؟",
                "Quel est le premier mois du calendrier islamique ?",
                "Islamic practices",
            ),
        ]
        for i in range(num_questions):
            template = question_templates[i % len(question_templates)]
            q = await create_mcq_question(
                question_en=f"{template[0]} (v{i})",
                question_ar=template[1],
                question_fr=template[2],
                category=template[3],
            )
            questions.append(q)

        return {
            "users": users,
            "room": room,
            "questions": questions,
        }

    return _setup
