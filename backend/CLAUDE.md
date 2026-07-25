# CLAUDE.md - Majlisna Backend

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

### API Layer (`majlisna/api/`)

```
api/
├── controllers/       # Business logic (async methods)
│   ├── base_game.py   # BaseGameController — shared methods for all game controllers
│   ├── auth.py        # JWT login, register, refresh
│   ├── user.py        # User CRUD
│   ├── room.py        # Room management + heartbeat + share links
│   ├── game.py        # Game lifecycle
│   ├── undercover.py  # Undercover word/term pairs
│   ├── codenames.py   # Codenames words/packs
│   ├── wordquiz.py    # QuizWord model (word_en/ar/fr, accepted_answers, hints JSON)
│   ├── mcqquiz.py     # McqQuestion model (trilingual questions, JSON choices/explanations)
│   ├── undercover_game.py # Undercover game logic (extends BaseGameController)
│   ├── codenames_game.py  # Codenames game logic (extends BaseGameController)
│   ├── codenames_helpers.py # Board builder, player assigner
│   ├── wordquiz.py        # QuizWord CRUD (get_random_words, create, delete)
│   ├── wordquiz_game.py   # Word Quiz game logic (extends BaseGameController)
│   ├── mcqquiz.py         # McqQuestion CRUD (get_random_questions)
│   ├── mcqquiz_game.py    # MCQ Quiz game logic (extends BaseGameController)
│   ├── game_lock.py   # PostgreSQL advisory locks per game_id (asyncio.Lock fallback for SQLite)
│   ├── disconnect.py  # Disconnect/kick handlers (used by kick_player, includes _handle_mcqquiz_disconnect)
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
│   ├── common.py      # Shared schemas (AdvanceRoundResponse for quiz ready system)
│   └── auth.py        # TokenPayload, LoginRequest, etc.
├── routes/            # FastAPI routers (thin, delegate to controllers, trigger notify)
│   ├── auth.py        # /api/v1/auth/*
│   ├── user.py        # /api/v1/users/*
│   ├── room.py        # /api/v1/rooms/* (notify_room_changed after mutations, share-link)
│   ├── game.py        # /api/v1/games/* — READ-ONLY + authenticated (history + summary only; no raw live_state, no CRUD)
│   ├── undercover.py  # /api/v1/undercover/* (notify_game_changed after mutations, mr-white-guess)
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
- **Controllers MUST NOT import or call `sio` directly.** `ws.server` imports `ws.handlers` → controllers, so a controller emitting Socket.IO events needs an in-function `import sio` to avoid a circular import. Instead, add a `notify_*` coroutine in `ws/notify.py` and `await` it from the route after the controller validates (e.g. `notify_room_invite` for room invites). Keeps the emit in the notify layer and controllers pure.
- **Game start routes call `await auto_join_game_room(game_id, room_id)`** before emitting notifications. This auto-joins all connected room members into `game:{game_id}` Socket.IO room, eliminating the race where `game_updated` fires before clients call `join_game`.
- **`sio.enter_room()` MUST be awaited.** It is an async coroutine in python-socketio. Calling without `await` creates a dangling coroutine that silently never executes — the SID never joins the room and misses all broadcasts. This applies to all `sio.enter_room()` calls in handlers.
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
from majlisna.api.controllers.game_lock import get_game_lock

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

### Timezone-Aware Timestamps

- `Game.start_time` and `Game.end_time` use `DateTime(timezone=True)` columns. Always use `datetime.now(UTC)` for these fields.
- `RoomUserLink.last_seen_at` and `disconnected_at` remain naive (consistent within disconnect checker loop).

### Mr. White Guessing

- Route: `POST /api/v1/undercover/games/{game_id}/mr-white-guess`
- Schemas: `MrWhiteGuessRequest` (contains the guessed word), `MrWhiteGuessResponse` (contains result)
- When Mr. White is eliminated by vote, the game enters a guessing phase. If the guess matches the civilian word, undercovers win. Otherwise, the game continues normally.

### Kick Player

- Host can kick players via `PATCH /api/v1/rooms/{room_id}/kick` with `{ user_id }`
- Reuses `_handle_permanent_disconnect` from `disconnect.py` for game cleanup
- No auto-disconnect — players are only removed by explicit kick or leaving

### Base Classes
**CRITICAL: Always use `majlisna.api.schemas.shared.BaseModel` and `BaseTable`**, never `pydantic.BaseModel` or `sqlmodel.SQLModel` directly.

```python
from majlisna.api.schemas.shared import BaseModel, BaseTable

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
from majlisna.api.schemas.error import BaseError

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
from majlisna.dependencies import get_current_user, get_room_controller

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
All magic values in `majlisna/api/constants.py`:

```python
from majlisna.api.constants import MIN_PLAYERS_FOR_GAME, ROOM_PASSWORD_LENGTH
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

Settings use `MAJLISNA_ENV` selector:

| File | Purpose |
|------|---------|
| `.env` | `MAJLISNA_ENV=development` (selector) |
| `.env.development` | SQLite, dev JWT key |
| `.env.production` | PostgreSQL, production keys |
| `.env.example` | Template (committed) |

## API Documentation

- Scalar UI: `http://localhost:5111/scalar`
- OpenAPI JSON: `http://localhost:5111/openapi.json`
- Health check: `http://localhost:5111/health`

## Hard-Won Rules

### `GET /games/{id}/summary` is participants-only AND finished-games-only

The summary payload contains every player's role plus the secret Undercover words
and the whole Codenames clue history. It is gated twice in
`GameController.get_game_summary(game_id, requester_id)`:

1. `game_status == IN_PROGRESS` → `GameStillInProgressError` (403). Without this
   the endpoint is a straight cheat vector: a player mid-game reads it and learns
   who the undercover is and what the civilian word is, bypassing the sanitised
   per-role `get_state`. This is the same leak that got the raw `GET /games/{id}`
   endpoint deleted — it simply survived through a second door.
2. No `UserGameLink` for the caller → `NotAGameParticipantError` (403).

`GET /games/user/{user_id}` takes `requester_id` for the same reason: each entry
carries the subject's `user_role`, so games still IN_PROGRESS are excluded unless
a user is reading their own history.

**Any new game read endpoint must answer both questions: is the game over, and
did this caller take part?**

### There is no room directory

`GET /rooms` was removed. It returned every ACTIVE room's `public_id`, owner and
member list to any authenticated user, which combined with a 4-digit PIN and a
per-IP-only rate limit made "enumerate rooms, then brute-force 10 000 PINs"
practical. Rooms are joined by a code shared out-of-band. Do not re-add a
list-all-rooms endpoint.

### `_process_game_end_stats` must not commit, and must not swallow SQLAlchemy errors

All four game controllers stage stat/achievement writes and let the calling
mutation's single `commit()` persist them.

- **No commit inside it.** It runs inside `get_game_lock`, which on PostgreSQL is
  `pg_try_advisory_xact_lock` — a *transaction-scoped* lock. Committing there
  releases the game lock in the middle of the end-of-game critical section.
- **No `except SQLAlchemyError: continue`.** After a failed statement the session
  requires a rollback, so catching-and-continuing made every later query in the
  loop and the caller's `commit()` raise `PendingRollbackError`, losing the whole
  game-end write. Letting it propagate rolls the request back cleanly; the game
  is still IN_PROGRESS so the client's retry re-runs the flow.

More generally: **one commit per locked block.** Two commits inside a
`get_game_lock` body means the second half runs unprotected on PostgreSQL.

### The winner must be written into `live_state`, not recomputed

`_finish_game` sets `state["winner"]`. Undercover used to leave it unset, so
`GameHistoryEntry.winner` / `GameSummary.winner` (which both read
`state.get("winner")`) were `None` for **every** undercover game and `user_won`
was always null — the history UI showed neither Won nor Lost. Recomputing from
alive counts also can't express "Mr. White guessed the civilian word", where
undercovers win while civilians are still alive and ahead. `_get_winner_label`
prefers the persisted value and only falls back to the derived one for old rows.
The disconnect handler (`_handle_undercover_disconnect`) writes it too — ending
by disconnect is a very common path.

### Columns must match the awareness of what the controller writes

`UserStats.last_played_at` and `UserAchievement.unlocked_at` are
`TIMESTAMP(timezone=True)`. As plain `TIMESTAMP` they rejected every write on
PostgreSQL (`asyncpg`: *can't subtract offset-naive and offset-aware datetimes*),
so `update_stats_after_game` failed for every player at the end of every game —
silently, because the caller swallowed the exception. SQLite never caught it,
which is why the whole test suite passed while production recorded no stats.
**When changing a `datetime.now()` to `datetime.now(UTC)`, change the column with
it, and verify with `pytest --use-postgres`.**

### There are no migrations

`create_all` only CREATEs missing tables — it never ALTERs an existing one. A
change to a column or index on a table that already exists on a server is applied
by dropping and reseeding:

```bash
docker exec -w /app majlisna-backend env PYTHONPATH=/app python scripts/generate_fake_data.py --delete
docker exec -w /app majlisna-backend env PYTHONPATH=/app python scripts/generate_fake_data.py --create-db
```

Do not add Alembic-style migration DDL to `database.py`.

### Expected 4xx log at INFO, not WARNING

`BaseError` picks `INFO` for < 500 and `ERROR` for >= 500. `app.py` attaches a
Sentry/GlitchTip sink at WARNING+, so logging routine 4xx as warnings turned every
"You have already voted this round" and every wrong room PIN into a tracked issue,
burying real errors and burning the error-tracker quota.

### `get_room_by_id` is the expensive one

It eager-loads `Room.users` **and** `Room.games` — i.e. the full `live_state` JSON
of every game ever played in that room. Only callers that serialize the Room
through `RoomView` need it (a lazy relationship load on an async session raises
`MissingGreenlet`). Everything that just reads scalar columns — `get_room_state`
(every heartbeat and every Socket.IO broadcast), `kick_player`,
`update_room_settings`, `rematch`, `get_share_link`, `_prepare_game_start` — uses
`get_room_without_relations`.

### Room membership is one row per (room, user)

`RoomUserLink` carries `UniqueConstraint("room_id", "user_id")`. The table has a
surrogate int PK, so without it two concurrent `PATCH /rooms/join` calls from the
same user (double-tap, client retry) both saw "no existing link" and both
inserted — the player appeared twice in the lobby, the count was inflated, and
`.one()` lookups raised `MultipleResultsFound` (a 500).

Also: `join_room` filters on `Room.type == ACTIVE`. `public_id` is globally unique
and rooms are only soft-deleted, so a stale code otherwise re-attached a user to a
closed room.

### SQLite foreign keys are per-connection

`create_app_engine` installs a pool `connect` listener that issues
`PRAGMA foreign_keys=ON` for every connection. A single PRAGMA on the
table-creating connection does **not** carry over to the rest of the pool, which
left dev running with foreign keys effectively off. `tests/conftest.py` installs
the same listener on its test engine.

### Host-supplied settings are bounded

`RoomSettingsRequest` bounds every numeric field (see `constants.py`:
`MAX_TIMER_SECONDS`, `MAX_QUIZ_ROUNDS`, …) and uses a `DifficultyLevel` enum.
These values are copied verbatim into `Room.settings` and then into a game's
`live_state`, so `word_quiz_rounds=10_000_000` made game creation try to draw ten
million questions, and a negative timer made the expiry check pass immediately.

### A player cannot become a spectator mid-game

`join_room_as_spectator` rejects (409) flipping an existing non-spectator link
while `room.active_game_id` is set. Their entry stays in `live_state["players"]`
regardless, so the flag only desynchronises the two views — and nothing, not even
the host, can flip it back.
