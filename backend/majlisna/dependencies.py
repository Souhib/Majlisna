from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.auth import TOKEN_TYPE_ACCESS, AuthController
from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.controllers.chat import ChatController
from majlisna.api.controllers.codenames import CodenamesController
from majlisna.api.controllers.codenames_game import CodenamesGameController
from majlisna.api.controllers.friend import FriendController
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.mcqquiz import McqQuizController
from majlisna.api.controllers.mcqquiz_game import McqQuizGameController
from majlisna.api.controllers.profile import ProfileController
from majlisna.api.controllers.room import RoomController
from majlisna.api.controllers.stats import StatsController
from majlisna.api.controllers.undercover import UndercoverController
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.user import UserController
from majlisna.api.controllers.wordquiz import WordQuizController
from majlisna.api.controllers.wordquiz_game import WordQuizGameController
from majlisna.api.models.table import User
from majlisna.api.schemas.error import InvalidTokenError
from majlisna.api.services.email import EmailService
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.database import get_engine as _get_engine
from majlisna.settings import Settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()  # type: ignore


async def get_engine() -> AsyncEngine:
    """Get the database engine instance."""
    return await _get_engine()


async def get_session(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> AsyncGenerator[AsyncSession, Any]:
    """Get database session with proper transaction handling."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_user_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserController:
    """Get UserController with injected session."""
    return UserController(session)


async def get_room_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoomController:
    """Get RoomController with injected session."""
    return RoomController(session)


async def get_game_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GameController:
    """Get GameController with injected session."""
    return GameController(session)


async def get_undercover_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UndercoverController:
    """Get UndercoverController with injected session."""
    return UndercoverController(session)


async def get_stats_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatsController:
    """Get StatsController with injected session."""
    return StatsController(session)


async def get_achievement_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AchievementController:
    """Get AchievementController with injected session."""
    return AchievementController(session)


async def get_codenames_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CodenamesController:
    """Get CodenamesController with injected session."""
    return CodenamesController(session)


async def get_auth_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthController:
    """Get AuthController with injected session and settings."""
    return AuthController(session, settings)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    auth_controller: Annotated[AuthController, Depends(get_auth_controller)],
) -> User:
    """Get the current authenticated user from cookie or Authorization header."""
    # 1. Try httpOnly cookie first
    effective_token = request.cookies.get("majlisna-access-token")
    # 2. Fall back to Authorization header
    if not effective_token:
        effective_token = token
    if not effective_token:
        raise InvalidTokenError("No authentication token provided")

    payload = auth_controller.decode_token(effective_token, expected_type=TOKEN_TYPE_ACCESS)
    user = await auth_controller.get_user_by_email(payload.email)
    if user is None:
        raise InvalidTokenError("User not found for token")
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the current active user."""
    return current_user


async def get_undercover_game_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UndercoverGameController:
    """Get UndercoverGameController with injected session."""
    return UndercoverGameController(session)


async def get_codenames_game_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CodenamesGameController:
    """Get CodenamesGameController with injected session."""
    return CodenamesGameController(session)


async def get_profile_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileController:
    """Get ProfileController with injected session."""
    return ProfileController(session)


async def get_friend_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FriendController:
    """Get FriendController with injected session."""
    return FriendController(session)


async def get_chat_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatController:
    """Get ChatController with injected session."""
    return ChatController(session)


async def get_challenge_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChallengeController:
    """Get ChallengeController with injected session."""
    return ChallengeController(session)


async def get_wordquiz_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WordQuizController:
    """Get WordQuizController with injected session."""
    return WordQuizController(session)


async def get_wordquiz_game_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WordQuizGameController:
    """Get WordQuizGameController with injected session."""
    return WordQuizGameController(session)


async def get_mcqquiz_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> McqQuizController:
    """Get McqQuizController with injected session."""
    return McqQuizController(session)


async def get_mcqquiz_game_controller(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> McqQuizGameController:
    """Get McqQuizGameController with injected session."""
    return McqQuizGameController(session)


def get_email_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailService:
    """Get EmailService with injected settings."""
    return EmailService(settings)


def get_social_auth_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SocialAuthService:
    """Get SocialAuthService with injected settings."""
    return SocialAuthService(settings)
