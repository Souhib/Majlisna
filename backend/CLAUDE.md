# CLAUDE.md - IPG Backend

## Overview

FastAPI backend for real-time multiplayer Islamic board games. Uses SQLModel/SQLAlchemy async for database operations. Game state stored as JSON in PostgreSQL (`Game.live_state` column). REST endpoints for mutations + Socket.IO for real-time state notifications. PgBouncer for connection pooling, Redis for Socket.IO cross-worker pub/sub only.

## Development Commands

```bash
cd backend

# Run the server
uv run python main.py                    # Starts on http://localhost:5111

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
│   ├── wordquiz.py    # QuizWord model (word_en/ar/fr, accepted_answers, hints JSON)
│   ├── mcqquiz.py     # McqQuestion model (trilingual questions, JSON choices/explanations)
│   ├── undercover_game.py # Undercover game logic (REST + PostgreSQL JSON)
│   ├── codenames_game.py  # Codenames game logic (REST + PostgreSQL JSON)
│   ├── codenames_helpers.py # Board builder, player assigner
│   ├── wordquiz.py        # QuizWord CRUD (get_random_words, create, delete)
│   ├── wordquiz_game.py   # Word Quiz game logic (create, submit_answer, timer, rounds)
│   ├── mcqquiz.py         # McqQuestion CRUD (get_random_questions)
│   ├── mcqquiz_game.py    # MCQ Quiz game logic (create, submit_answer, timer, rounds)
│   ├── game_lock.py   # PostgreSQL advisory locks per game_id (asyncio.Lock fallback for SQLite)
│   ├── disconnect.py  # Disconnect/kick handlers (used by kick_player)
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
│   ├── wordquiz.py    # Word Quiz schemas (QuizWordCreate, SubmitAnswer, WordQuizGameState)
│   ├── mcqquiz.py     # MCQ Quiz schemas (McqSubmitAnswerRequest, McqQuizGameState)
│   └── auth.py        # TokenPayload, LoginRequest, etc.
├── routes/            # FastAPI routers (thin, delegate to controllers, trigger notify)
│   ├── auth.py        # /api/v1/auth/*
│   ├── user.py        # /api/v1/users/*
│   ├── room.py        # /api/v1/rooms/* (notify_room_changed after mutations)
│   ├── game.py        # /api/v1/games/*
│   ├── undercover.py  # /api/v1/undercover/* (notify_game_changed after mutations)
│   ├── codenames.py   # /api/v1/codenames/* (notify_game_changed after mutations)
│   ├── wordquiz.py    # /api/v1/wordquiz/* (start, state, answer, timer, next-round)
│   ├── mcqquiz.py     # /api/v1/mcqquiz/* (start, state, answer, timer, next-round)
│   └── stats.py       # /api/v1/users/{id}/stats, achievements, leaderboard
├── ws/                # Socket.IO real-time notification layer
│   ├── __init__.py    # Exports sio, socketio_app
│   ├── server.py      # AsyncServer with Redis adapter
│   ├── handlers.py    # connect (JWT auth), join_game, disconnect, auto_join_game_room
│   ├── state.py       # Thin wrappers: fetch_room_state, fetch_game_state (reuse controllers)
│   └── notify.py      # notify_room_changed, notify_game_changed (best-effort broadcast)
├── constants.py       # All magic values
├── middleware.py       # Security, RequestID, Logging
└── services/          # External integrations (future)
```

## Key Patterns

### Socket.IO Notification Layer

Socket.IO is a **notification layer**, not a game engine. The flow is:
1. Client → REST POST → Controller (with advisory lock) → PostgreSQL → Response
2. Route **awaits** `notify_room_changed()` or `notify_game_changed()` — Socket.IO event is guaranteed to be emitted before the HTTP response returns
3. Notify functions open a fresh DB session, call existing controllers with `update_heartbeat=False`, and emit to Socket.IO rooms

**Key rules:**
- **Route handlers MUST `await` notify functions** — never fire-and-forget. This eliminates the race condition where the client receives the REST response before the Socket.IO event is emitted. `fire_notify_*` variants exist ONLY for background tasks (disconnect checker loop, Socket.IO event handlers).
- **Game start routes call `auto_join_game_room(game_id, room_id)`** before emitting notifications. This auto-joins all connected room members into `game:{game_id}` Socket.IO room, eliminating the race where `game_updated` fires before clients call `join_game`.
- PostgreSQL is the ONLY source of truth. Redis is ONLY for Socket.IO adapter cross-worker pub/sub.
- ZERO game state in Redis. No TTL watchers, no Redis OM.
- Notify functions log errors but don't raise — if a broadcast fails, the REST response still succeeds.
- `notify_game_changed` sends a lightweight `game_updated` signal. Each client invalidates its TanStack Query cache, triggering a REST re-fetch of its own role-aware state.
- Socket.IO handlers are thin wrappers, NOT new controllers. They reuse `RoomController.get_room_state()`, `UndercoverGameController.get_state()`, `CodenamesGameController.get_board()`.
- Broadcasts go to Socket.IO rooms (`room:{room_id}`, `game:{game_id}`), NEVER to individual SIDs (except for per-user game state).
- Socket.IO `disconnect` marks the user as disconnected in DB (starts grace period). A background `disconnect_checker_loop` runs every 5s to mark stale heartbeats and permanently remove users past the 60s grace period. Multi-tab connections are deduplicated via `_user_sids` dict. `join_game` validates user membership in the room and game ownership via DB queries. `you_were_kicked` event is emitted to `user:{user_id}` when the host kicks a player.

### Game State in PostgreSQL

All game state stored in `Game.live_state` JSON column:
- **Undercover**: `{players, turns, civilian_word, undercover_word, phase, ...}`
- **Codenames**: `{board, players, current_team, current_turn, status, winner, ...}`
- **Word Quiz**: `{players, current_round, total_rounds, round_phase, hints, answers, current_word, ...}`

All game mutations use `get_game_lock(game_id, session)` — PostgreSQL advisory locks in production, asyncio.Lock fallback for SQLite tests:
```python
from sqlalchemy.orm.attributes import flag_modified
from ipg.api.controllers.game_lock import get_game_lock

async def submit_vote(self, game_id: UUID, ...):
    async with get_game_lock(str(game_id), self.session):
        game = (await self.session.exec(select(Game).where(Game.id == game_id))).one()
        state = game.live_state
        # ... modify state ...
        game.live_state = state
        flag_modified(game, "live_state")  # REQUIRED — SQLAlchemy won't detect in-place JSON mutations
        self.session.add(game)
        await self.session.commit()
```

**CRITICAL: Always call `flag_modified(game, "live_state")` before committing.** SQLAlchemy's change detection doesn't see in-place mutations to JSON columns. Without it, `session.commit()` silently does nothing.

### Kick Player

- Host can kick players via `PATCH /api/v1/rooms/{room_id}/kick` with `{ user_id }`
- Reuses `_handle_permanent_disconnect` from `disconnect.py` for game cleanup
- No auto-disconnect — players are only removed by explicit kick or leaving

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
| QuizWord | quiz_word | Word Quiz words (multilingual hints, accepted answers) |
| McqQuestion | mcq_question | MCQ Quiz questions (trilingual questions, JSON choices/explanations) |
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

- Scalar UI: `http://localhost:5111/scalar`
- OpenAPI JSON: `http://localhost:5111/openapi.json`
- Health check: `http://localhost:5111/health`
