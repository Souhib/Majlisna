from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.achievement import AchievementController
from ipg.api.controllers.auth import AuthController
from ipg.api.controllers.codenames import CodenamesController
from ipg.api.controllers.codenames_game import CodenamesGameController
from ipg.api.controllers.game import GameController
from ipg.api.controllers.room import RoomController
from ipg.api.controllers.stats import StatsController
from ipg.api.controllers.undercover import UndercoverController
from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.controllers.user import UserController
from ipg.api.models.table import User
from ipg.api.schemas.error import InvalidTokenError
from ipg.database import get_engine as _get_engine
from ipg.settings import Settings

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
    effective_token = request.cookies.get("ipg-access-token")
    # 2. Fall back to Authorization header
    if not effective_token:
        effective_token = token
    if not effective_token:
        raise InvalidTokenError("No authentication token provided")

    payload = auth_controller.decode_token(effective_token)
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
