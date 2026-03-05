# CLAUDE.md - IPG Backend

## Overview

FastAPI backend for real-time multiplayer Islamic board games. Uses SQLModel/SQLAlchemy async for database operations. Game state stored as JSON in PostgreSQL (`Game.live_state` column). Pure REST architecture with TanStack Query polling on the frontend.

## Development Commands

```bash
cd backend

# Run the server
uv run python main.py                    # Starts on http://localhost:5000

# Code quality
uv run poe lint                          # Ruff lint
uv run poe format                        # Ruff format
uv run poe check                         # All checks (lint + format + type)

# Testing
uv run poe test                          # pytest with coverage
uv run poe test-fast                     # Stop on first failure

# Fake data
PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db
PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete
```

## Architecture

### API Layer (`ipg/api/`)

```
api/
├── controllers/       # Business logic (async methods)
│   ├── auth.py        # JWT login, register, refresh
│   ├── user.py        # User CRUD
│   ├── room.py        # Room management + heartbeat
│   ├── game.py        # Game lifecycle
│   ├── undercover.py  # Undercover word/term pairs
│   ├── codenames.py   # Codenames words/packs
│   ├── undercover_game.py # Undercover game logic (REST + PostgreSQL JSON)
│   ├── codenames_game.py  # Codenames game logic (REST + PostgreSQL JSON)
│   ├── codenames_helpers.py # Board builder, player assigner
│   ├── game_lock.py   # In-process asyncio.Lock per game_id
│   ├── disconnect.py  # Background disconnect checker (heartbeat-based)
│   ├── stats.py       # User statistics
│   └── achievement.py # Achievement tracking + seeding
├── models/            # SQLModel DB tables ONLY
│   ├── table.py       # User, Room, Game, Event tables
│   ├── game.py        # GameStatus enum, GameBase with live_state JSON
│   ├── relationship.py # Link tables (RoomUserLink with last_seen_at)
│   ├── undercover.py  # Word, TermPair tables
│   ├── codenames.py   # CodenamesWord, CodenamesWordPack
│   ├── stats.py       # UserStats, AchievementDefinition, UserAchievement
│   ├── error.py       # Game-specific error classes
│   └── shared.py      # DBModel (backward compat)
├── schemas/           # Pydantic request/response models
│   ├── shared.py      # BaseModel, BaseTable (USE THESE)
│   ├── error.py       # Enhanced error classes
│   └── auth.py        # TokenPayload, LoginRequest, etc.
├── routes/            # FastAPI routers (thin, delegate to controllers)
│   ├── auth.py        # /api/v1/auth/*
│   ├── user.py        # /api/v1/users/*
│   ├── room.py        # /api/v1/rooms/*
│   ├── game.py        # /api/v1/games/*
│   ├── undercover.py  # /api/v1/undercover/*
│   ├── codenames.py   # /api/v1/codenames/*
│   └── stats.py       # /api/v1/users/{id}/stats, achievements, leaderboard
├── constants.py       # All magic values
├── middleware.py       # Security, RequestID, Logging
└── services/          # External integrations (future)
```

## Key Patterns

### Game State in PostgreSQL

All game state stored in `Game.live_state` JSON column:
- **Undercover**: `{players, turns, civilian_word, undercover_word, phase, ...}`
- **Codenames**: `{board, players, current_team, current_turn, status, winner, ...}`

All game mutations use `asyncio.Lock` per game_id:
```python
from sqlalchemy.orm.attributes import flag_modified
from ipg.api.controllers.game_lock import get_game_lock

async def submit_vote(self, game_id: UUID, ...):
    async with get_game_lock(str(game_id)):
        game = (await self.session.exec(select(Game).where(Game.id == game_id))).one()
        state = game.live_state
        # ... modify state ...
        game.live_state = state
        flag_modified(game, "live_state")  # REQUIRED — SQLAlchemy won't detect in-place JSON mutations
        self.session.add(game)
        await self.session.commit()
```

**CRITICAL: Always call `flag_modified(game, "live_state")` before committing.** SQLAlchemy's change detection doesn't see in-place mutations to JSON columns. Without it, `session.commit()` silently does nothing.

### Heartbeat & Disconnect Detection

- `RoomUserLink.last_seen_at` updated on each GET request (piggyback on polling)
- Background `disconnect_checker_loop` runs every 5s, checks for stale heartbeats
- `HEARTBEAT_STALE_SECONDS` (10s) → mark disconnected
- `GRACE_PERIOD_SECONDS` (30s) → permanent removal

### Base Classes
**CRITICAL: Always use `ipg.api.schemas.shared.BaseModel` and `BaseTable`**, never `pydantic.BaseModel` or `sqlmodel.SQLModel` directly.

```python
from ipg.api.schemas.shared import BaseModel, BaseTable

class UserCreate(BaseModel):     # For schemas
    username: str
    email: str

class User(BaseTable, table=True):  # For DB tables
    __tablename__ = "user"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str
```

### Async Database Operations
All DB operations MUST be async:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

class MyController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_item(self, item_id: UUID):
        result = (await self.session.exec(
            select(Item).where(Item.id == item_id)
        )).first()
        return result
```

### Error Classes
Errors auto-generate i18n keys and log on construction:

```python
from ipg.api.schemas.error import BaseError

class MyCustomError(BaseError):
    def __init__(self, item_id: UUID):
        super().__init__(
            message=f"Item {item_id} not found",
            frontend_message="Item not found.",
            status_code=404,
            details={"item_id": str(item_id)},
        )
# Auto-generates error_key: "errors.api.myCustom"
```

### Dependencies
Use `Annotated` + `Depends` for DI:

```python
from typing import Annotated
from fastapi import Depends
from ipg.dependencies import get_current_user, get_room_controller

async def my_route(
    user: Annotated[User, Depends(get_current_user)],
    controller: Annotated[RoomController, Depends(get_room_controller)],
):
    ...
```

### Routes - NO Logic
Routes delegate everything to controllers:

```python
@router.get("/items/{item_id}")
async def get_item(
    item_id: UUID,
    controller: Annotated[ItemController, Depends(get_item_controller)],
):
    return await controller.get_item(item_id)
```

### Constants
All magic values in `ipg/api/constants.py`:

```python
from ipg.api.constants import MIN_PLAYERS_FOR_GAME, ROOM_PASSWORD_LENGTH
```

## Database Models

| Model | Table | Purpose |
|-------|-------|---------|
| User | user | Player accounts |
| Room | room | Game rooms (with `active_game_id`) |
| Game | game | Game sessions (with `live_state` JSON, `game_status`) |
| RoomUserLink | room_user_link | Room membership (with `last_seen_at`, `disconnected_at`) |
| Event | event | Game events log |
| Word | word | Undercover words |
| TermPair | term_pair | Undercover word pairs |
| CodenamesWord | codenames_word | Codenames board words |
| CodenamesWordPack | codenames_word_pack | Word pack groupings |
| UserStats | user_stats | Aggregated player statistics |
| AchievementDefinition | achievement_definition | Badge definitions |
| UserAchievement | user_achievement | Earned achievements |

## Environment Configuration

Settings use `IPG_ENV` selector:

| File | Purpose |
|------|---------|
| `.env` | `IPG_ENV=development` (selector) |
| `.env.development` | SQLite, dev JWT key |
| `.env.production` | PostgreSQL, production keys |
| `.env.example` | Template (committed) |

## API Documentation

- Scalar UI: `http://localhost:5000/scalar`
- OpenAPI JSON: `http://localhost:5000/openapi.json`
- Health check: `http://localhost:5000/health`
