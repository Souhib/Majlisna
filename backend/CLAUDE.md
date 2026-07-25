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

Two things this script needs, both of which have already bitten once:

**It must not go through PgBouncer.** `DIRECT_DATABASE_URL` (set in both compose
files) points at the PostgreSQL server itself. asyncpg caches type introspection
per connection; the drop/create invalidates those types while PgBouncer's
transaction pooling keeps handing out connections with the stale cache, and the
following bulk INSERT dies with "could not resolve query result and/or argument
types in N attempts" — reproducible every single run. The script refuses to start
if `DATABASE_URL` names pgbouncer and `DIRECT_DATABASE_URL` is unset.

**`faker` is a MAIN dependency, not a dev extra — leave it there.** It looks like
a test-only package, but this script is the project's migration mechanism and so
has to run on the production image, which is built with `ARG INSTALL_DEV=false`.
As a dev extra it was absent there: the command above worked in E2E (that image
passes `INSTALL_DEV: "true"`) and failed on the server with a bare
`ModuleNotFoundError` — *after* `--delete` had already dropped everything, leaving
production with an empty schema and no way to refill it.

Belt and braces on top of that: `--create-db` verifies faker is importable BEFORE
touching the database, and `--delete` warns when the follow-up cannot succeed.
`--seed` (game content only) never needs faker and stays the safe minimum.

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

### An Undercover round resolves exactly ONCE

`_eliminate_player_based_on_votes` sets `turn["resolved"] = True`, and
`handle_timer_expired` returns `round_already_resolved` when it sees that flag on a
`"voting"` turn. Both halves are load-bearing:

Once every alive player has voted, the turn *stays* in phase `"voting"` until the
host calls `next-round`, and `timer_started_at` still points at the voting
deadline — so the timer reads as expired for that entire gap. Without the flag,
every timer-expired call re-ran the tally over the SAME votes: another player died
and `eliminated_players` grew a duplicate entry, which desynchronises both
`_build_vote_history` and `GameSummary` (they align `eliminated_players[i]` with
`turns[i]` positionally). The client's timer callback kept it going, one DB write
and one Socket.IO broadcast per cycle.

Related: elimination candidates come from **alive** players only. Seeding the tally
with the whole roster meant a dead player could win it and be "eliminated" twice —
reachable with one player left, where `_auto_fill_missing_votes` cannot record a
vote (nobody to vote for) so every count is 0 and the tie-break picks at random
from everyone, corpses included.

And any phase a timeout lands in must be one the game can *leave*: the Mr. White
guess timeout used to drop `mr_white_guesser` while leaving the phase on
`"mr_white_guessing"`, so guessing 403'd, voting and describing rejected the phase,
and only the host could rescue the game. It now lands on `"voting"` (what a wrong
guess does) or `"game_over"`.

### Every game controller must pass its own `min_players`

`_prepare_game_start(room_id)` defaults to **1**. Undercover relied on that default
while `MIN_PLAYERS_FOR_GAME = 3` sat unused, so a lone host could start a game that
`_compute_roles` filled with one undercover and ZERO civilians — won on paper,
unplayable in fact (the only player may not vote for themselves, which is rejected).
Two players is just the first tie-break coin flip. Codenames passes `min_players=4`;
Undercover passes `MIN_PLAYERS_FOR_GAME`; the quizzes genuinely allow 1.

`NotEnoughPlayersError` takes `required` — it used to hardcode "4 players for
Codenames" in both the log line and the user-facing message, which became wrong for
the wrong game the moment a second caller could reach it.

### Compare room PINs on bytes, not str

`secrets.compare_digest` raises `TypeError` as soon as either **str** argument holds
a non-ASCII character, and nothing constrains the PIN a client sends
(`RoomJoin.password` only coerces to str; the spectator request takes a bare str).
A PIN like `é123` therefore escaped as an unhandled exception — a 500 — instead of
`WrongRoomPasswordError`. `_passwords_match` in `controllers/room.py` compares the
UTF-8 bytes: same constant-time guarantee, never raises.

### Game content endpoints are admin-only, reads included

`routes/undercover.py` (words, term pairs) and `routes/codenames.py` (word packs,
words) sit behind `get_current_admin_user`, which checks membership in
`ADMIN_EMAILS`.

Both directions were holes. The GETs took no authentication at all, and
`GET /undercover/termpair` lists every (civilian word, undercover word) pair — next
to the word a player's own role hands them, that reveals the opposing word, so an
undercover could blend in perfectly. Requiring a login does **not** fix that; every
player has one. And the POST/DELETE routes took only *a* login, so any player could
delete every word in the database and break Undercover globally.

There is no `is_admin` column and no migration mechanism, so admin membership is
configuration, not data. It **fails closed**: `ADMIN_EMAILS` unset means nobody is
an admin, which costs nothing because content is loaded by
`scripts/generate_fake_data.py` and no client calls these routes. Tests use the
autouse `_admin_auth` fixture in the two route test modules.

### Chat returns the NEWEST window

`get_messages` orders **descending**, applies `limit`, then reverses for display.
Ordering ascending before the limit returned the OLDEST `limit` rows, so a room past
50 messages opened the chat panel on the very first messages of the session and
never showed the recent ones — the panel only appends what arrives afterwards over
Socket.IO, so the gap was permanent.

### Host transfer prefers a player over a spectator

`_handle_permanent_disconnect` picks the first non-spectator in `remaining` and only
falls back to a spectator when nobody else is left. `remaining` includes spectators,
and the host is who starts games, changes settings and kicks — while
`_prepare_game_start` excludes spectators from the roster entirely.

### The end-of-game flow lives in `game_end_stats.py`, and the disconnect path uses it

`controllers/game_end_stats.py` holds `record_game_end` plus the per-game winner
resolvers. All four game controllers' `_process_game_end_stats` delegate to it, and so
do `_handle_undercover_disconnect` / `_handle_codenames_disconnect`.

It is a separate module for an import reason, not for tidiness: `base_game` imports
`RoomController`, which imports `disconnect`, so a controller import from `disconnect`
closes the cycle. `game_end_stats` reaches only `stats`, `achievement` and the models.

Why the disconnect path matters: it used to record **nothing**. The handlers flipped
the game to FINISHED and wrote the winner but never ran the stat/achievement flow, so
a game decided by someone closing their tab — a common ending — counted for no one.

Two invariants carried over: **no commit inside** (every caller holds
`get_game_lock`, transaction-scoped on PostgreSQL) and **no swallowing
SQLAlchemyError** (the session needs a rollback after a failed statement, so
catch-and-continue turned into `PendingRollbackError` for the whole write).

The quizzes also went through this: they updated stats but never checked
achievements, so a quiz-only player's counters rose while no badge ever unlocked.

### Game draws come from `api/utils/rng.py`, never `random.*`

`rng = random.SystemRandom()`. The default Mersenne Twister is reproducible — its
state is recoverable from a run of observed outputs, after which every future draw is
predictable. In a social-deduction game the draw *is* the secret: who is undercover,
which side gets which word, where the assassin sits. Import the shared instance so
there is one place to look (and one patch target in tests — patch `module.rng.choice`,
not `module.random.choice`).

### `TTLCache` is per-worker: never cache what must not go stale, never cache ORM rows

Production runs `UVICORN_WORKERS=4`, so `cache.invalidate()` reaches one worker out of
four. A TTL is the real freshness bound; invalidation is a bonus.

`get_user_stats` is therefore **not** cached — it was, for 5 minutes, and a player
watched their own win appear or not depending on which worker answered. It also cached
the `UserStats` ORM instance, i.e. a detached row shared across sessions. It is a
single indexed lookup; there was nothing to buy.

The cache is bounded (`MAX_ENTRIES`) and evicts on write. Entries used to be dropped
only when someone read them back, so a key written once and never read again stayed
resident for the life of the worker.

Same reason `AchievementController` memoises the definitions **on the instance**, not
in this cache: they are session-bound ORM rows, and one controller already serves
every player of a single game end (`check_achievements` runs once per player, and used
to re-read the whole table each time, inside the game lock).

### `_fallback_locks` is a `WeakValueDictionary`

An entry vanishes as soon as no task holds the lock — the `async with` is the only
strong reference, which is why the code keeps a local `lock` variable instead of
looking the key up twice. It was a plain dict growing one entry per game forever;
`cleanup_game_lock` existed to purge it and had no caller anywhere, which made the
leak look handled.

### Each elimination carries the round that produced it

`eliminated_players[i]` used to be paired with `turns[i]` **by position** in both
`_build_vote_history` and `GameSummary`. Every entry now carries `round`; a drop-out
carries `round: 0` (it is not a round's outcome) and readers skip it. Rows written
before the field fall back to the index. Positional coupling is what turned the
duplicate-elimination bug into a silently wrong history.

### Player counts are bounded on both ends

`MIN_PLAYERS_FOR_GAME` / `MAX_PLAYERS_UNDERCOVER` (12) and 4 / `MAX_PLAYERS_CODENAMES`
(10), passed to `_prepare_game_start`. Only the minimums were checked; role
distribution scales past the maximum without erroring, so a 20-player room produced a
game nobody had played or tested.

### Removed on purpose: `GET /users` and `DELETE /users/{user_id}`

- `GET /users` returned the whole user table, unpaginated, to any authenticated
  caller — a full table scan per call and a directory of the player base. Add a
  paginated search if one is ever needed, not a list-everything route.
- `DELETE /users/{user_id}` destroyed the caller's own account irreversibly on nothing
  but a valid session, while `DELETE /users/me/account` does the same thing and
  requires the password. A stolen token was enough.

Neither had a client. `UserController.get_users` / `delete_user` remain as internal
primitives — do not re-expose them.

### A game-state schema must declare every field the client reads

`newly_unlocked_achievements` was written into `live_state` by all four controllers and
declared by **none** of the state schemas. `BaseModel` is `extra="forbid"`, so it never
left the server: the achievement toast (`useAchievementNotifications` +
`AchievementToast`) had been wired on the client the whole time with nothing to show.

It is now typed as `list[PlayerUnlockedAchievements] | None` (see `schemas/common.py`)
on `UndercoverGameState`, `CodenamesBoardState`, `WordQuizGameState` and
`McqQuizGameState`, and passed through from `state.get(...)` in each `get_state` /
`get_board`. Writing to `live_state` is not the same as returning it — check both ends.
