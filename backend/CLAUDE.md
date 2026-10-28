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
│   ├── term_script.py # Arabic forms of game terms: batched get_forms + seed upsert
│   ├── notebook.py    # The Kunnash: words kept from finished games (keep / list / delete)
│   └── achievement.py # Achievement tracking + seeding
├── models/            # SQLModel DB tables ONLY
│   ├── table.py       # User, Room, Game, Event tables
│   ├── game.py        # GameStatus enum, GameBase with live_state JSON
│   ├── relationship.py # Link tables (RoomUserLink with last_seen_at)
│   ├── undercover.py  # Word, TermPair tables
│   ├── codenames.py   # CodenamesWord, CodenamesWordPack
│   ├── term_script.py # TermScript (Latin term → ar, ar_vocalized)
│   ├── notebook.py    # NotebookEntry + NotebookGameType (the Kunnash)
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
│   │                  # all four game routers also carry /games/{id}/pause and /resume
│   ├── notebook.py    # /api/v1/notebook/* (a game's words, keep them / one, list by cursor, delete)
│   └── stats.py       # /api/v1/users/{id}/stats, achievements, leaderboard
├── ws/                # Socket.IO real-time notification layer
│   ├── __init__.py    # Exports sio, socketio_app
│   ├── server.py      # AsyncServer with Redis adapter
│   ├── handlers.py    # connect (JWT auth), join_game, disconnect, auto_join_game_room
│   ├── state.py       # Thin wrappers: fetch_room_state, fetch_game_state (reuse controllers)
│   └── notify.py      # notify_room_changed, notify_game_changed (best-effort broadcast)
├── utils/             # Pure helpers (rng, text_match, multilingual, game_state, game_pause, cursor)
├── constants.py       # All magic values
├── rate_limit.py      # slowapi limiter, per-user key (user_or_ip_key), 429 envelope handler
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
- Socket.IO `disconnect` marks the user as disconnected in DB (starts grace period). A background `disconnect_checker_loop` runs every 5s to mark stale heartbeats and permanently remove users past the 60s grace period. Multi-tab connections are deduplicated via `_user_sids` dict; `connect` records the new SID BEFORE closing the old one, and a `disconnect` whose SID has been replaced does not mark the player away (a reload used to flash "away" until the next heartbeat). `join_game` validates user membership in the room and game ownership via DB queries. `you_were_kicked` event is emitted to `user:{user_id}` when the host kicks a player.

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

- The guess is recorded on the turn, `turn["mr_white_guess"] = {word, correct}` (`word` null when the guess timed out), and `_build_vote_history` passes it on as `VoteHistoryRound.mr_white_guess` (`MrWhiteGuessRecord`), so every player's verdict says what he guessed. It used to reach the guesser alone, as a toast.

- Route: `POST /api/v1/undercover/games/{game_id}/mr-white-guess`
- Schemas: `MrWhiteGuessRequest` (contains the guessed word), `MrWhiteGuessResponse` (contains result)
- When Mr. White is eliminated by vote, the game enters a guessing phase. If the guess matches the civilian word, undercovers win. Otherwise, the game continues normally.

### The personal Socket.IO channel, and departures that reach the game

- `connect` without `room_id` is the player's personal channel (`_connect_personal`): the
  token is checked like any other, the SID joins `user:{user_id}` only (room invites,
  `you_were_kicked`), and nothing else happens — no heartbeat, no room state. The app
  shell keeps one open on every signed-in page. It used to be refused ("Missing auth
  token or room_id"); socket.io-client never retries a refused handshake, so every invite
  answered "Invite sent" and never arrived. `join_game` ignores a personal connection.
- `PATCH /rooms/leave` and `PATCH /rooms/{id}/kick` call `notify_member_removed(room_id,
  game_id)`: `notify_game_changed` (which also re-sends the room state) when the room had
  a running game, else `notify_room_changed`. A departure mid-game eliminates the player
  and can move the turn or end the game, while game pages refetch on `game_updated` only.
  **`game_id` is read BEFORE the removal** (`get_active_game_id`, first line of both
  routes): a departure that decides the game (the last Undercover kicked) clears
  `Room.active_game_id`, and the lookup used to run after it — it found no game, sent only
  `room_state`, and the rest of the table sat on a finished game with the leaver still
  seated and no colophon. The E2E kick spec found it (one run in four: when the kicked
  player was the Undercover).
- `get_room_state` lists members ORDER BY `joined_at`, `user_id`: heap order moved with
  every heartbeat, so two phones seated the halqa differently.
- `RoomSettingsRequest.game_type` (a `GameType`) is the host's pick in the lobby, stored
  in `Room.settings["game_type"]`, which `get_room_state` already reads while no game
  runs: every member's lobby follows it. The route dumps the request in JSON mode.

### Kick Player

- Host can kick players via `PATCH /api/v1/rooms/{room_id}/kick` with `{ user_id }`
- Reuses `_handle_permanent_disconnect` from `disconnect.py` for game cleanup
- No auto-disconnect — players are only removed by explicit kick or leaving
- The kicked player's pages (the lobby AND the four game pages) go to /rooms on
  `you_were_kicked` (`useLeaveAfterKick` in the front): they are out of the room's socket
  rooms, so no `game_updated` reaches them any more.

### Leaderboard

- `GET /stats/leaderboard?stat_field=` ranks by one of `LEADERBOARD_SORT_FIELDS`
  (constants.py); anything else is a 400 `InvalidLeaderboardSortError`. It used to be a
  `getattr(UserStats, stat_field)`: any column was accepted, and `win_rate` — the page's
  own "Win rate" sort — is not a column, so it answered a 500. `win_rate` is computed in
  SQL (won / played, 0 with no games), ties broken by wins.

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

**Never raise a bare `BaseError(...)`** (its key, `errors.api.base`, cannot be
translated), and add the new key to `errors.api` in `front/src/i18n/locales/{en,fr,ar}.json`
— `tests/api/test_error_keys.py` enforces both.

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
| TermScript | term_script | Arabic forms (`ar`, `ar_vocalized`) of every Undercover/Codenames term, keyed by the Latin `term` |
| NotebookEntry | notebook_entry | The Kunnash: one row per (user, game type, term) a player kept from a finished game (`term` column; the API calls it `word`) |
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
`GameController.get_game_summary(game_id, requester_id)`, in this order:

1. No `UserGameLink` for the caller → `NotAGameParticipantError` (403). Checked
   FIRST: the two 403s carry different error keys, so asking a stranger "is it
   over?" first told them whether a game they never played was still running.
2. `game_status == IN_PROGRESS` → `GameStillInProgressError` (403). Without this
   the endpoint is a straight cheat vector: a player mid-game reads it and learns
   who the undercover is and what the civilian word is, bypassing the sanitised
   per-role `get_state`. This is the same leak that got the raw `GET /games/{id}`
   endpoint deleted — it simply survived through a second door.

`GET /games/user/{user_id}` takes `requester_id` for the same reason: each entry
carries the subject's `user_role`, so games still IN_PROGRESS are excluded unless
a user is reading their own history.

**Any new game read endpoint must answer both questions: is the game over, and
did this caller take part?** Both live in ONE place,
`GameController.get_past_game_for_participant(game_id, requester_id)`, which the
summary and the notebook both call — reuse it rather than re-deriving the gates.

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
`AchievementToast`, both since deleted: earned badges are now seals on the game-over colophon) had
been wired on the client the whole time with nothing to show.

It is now typed as `list[PlayerUnlockedAchievements] | None` (see `schemas/common.py`)
on `UndercoverGameState`, `CodenamesBoardState`, `WordQuizGameState` and
`McqQuizGameState`, and passed through from `state.get(...)` in each `get_state` /
`get_board`. Writing to `live_state` is not the same as returning it — check both ends.

### A Codenames board never carries the same word twice

`get_random_words` samples distinct word **texts**, not distinct rows. The same term
legitimately lives in more than one thematic pack — the seed data has Ikhlas, Tafsir
and Tajweed in two packs each, with different hints — so sampling rows dealt the same
word onto two of the 25 cards on roughly 4% of boards.

That is not cosmetic. A one-word clue cannot say which of two identical cards the
spymaster meant, and anything that addresses a card by its word (the UI, the E2E
suite) hits whichever it finds first. It is also what made
`codenames/game-voting.spec.ts` fail once every few full gate runs — the kind of
low-rate flake that reads as infrastructure and isn't.

`NotEnoughWordsError` counts distinct words too: forty rows of twenty words is not a
board.

### `ADMIN_EMAILS` is a credential, so the account must be verified

`get_current_admin_user` requires the caller's address to be in `ADMIN_EMAILS`
**case-insensitively** and the account to have `email_verified = True`.

Both halves came from getting it wrong first. Comparing raw strings meant a configured
`Admin@Example.com` silently denied the account registered as `admin@example.com`, a
failure indistinguishable from a broken deploy. And naming an address in config turns
that address into a credential: registration is open, `require_email_verification` is
off by default, so if the configured admin has not registered yet, anyone who guesses
the address — a project owner's email is rarely secret — could register it and inherit
content-management rights. Requiring a verified email means squatting the address buys
nothing without access to the mailbox. Keying on user ids would sidestep the squat
entirely, but ids are not knowable when writing a deploy config; a verified address is.

`app.py` logs at boot whether admin access is configured (count and domains only).
An unset `ADMIN_EMAILS` is a valid configuration — it means nobody is an admin — but a
403 from these endpoints is otherwise indistinguishable from a broken deploy.

Both `ADMIN_EMAILS` and `CORS_ORIGINS` are `Annotated[list[str], NoDecode]`. They were
declared `str` with an "after" validator returning a list, so the annotation lied:
`x in settings.admin_emails` type-checked as a *substring* test. `NoDecode` is what
makes `list[str]` usable at all here — without it pydantic-settings JSON-decodes a
list-typed field before validators run, and a plain `a,b` env value raises.

### The type checker is `ty`, it runs in CI, and it passes

`uv run poe check` and the CI backend job both run
**`ty check majlisna/ --error-on-warning`**. The package was once at **311 errors**
behind a pre-commit hook that was never installed — a guarantee that existed only on
paper. CI is what makes it real; the hook is the fast local echo of the same command.

Getting to zero was mostly two changes, and they still hold:

- `api/utils/game_state.py::require_state(game)` narrows `Game.live_state` once, in a
  place that raises if it is empty, instead of leaving `dict | None` to be indexed at
  ~150 sites. Handlers that prefer to bail assign to a local and guard *that* —
  narrowing a local survives an intervening await, narrowing an attribute does not.
- Primary keys declared `id: UUID | None` with `default_factory=uuid4` became `UUID`.
  They are generated in Python and never None; the `| None` was cargo-culted from
  SQLModel's autoincrement examples. **The generated DDL is byte-identical** — verified
  by diffing `CreateTable` output before and after, which matters because there are no
  migrations.

**`--error-on-warning` is load-bearing, not decoration.** ty reports `deprecated`,
`possibly-missing-submodule` and `unused-type-ignore-comment` as *warnings*, which do
not fail a run by default. `possibly-missing-submodule` is what caught an `except`
clause naming `resend.exceptions.ApiError` — a class that does not exist (see below).
A rule that finds a production bug does not get to be advisory.

**The version is pinned exactly (`ty==0.0.63`), not floored.** ty is pre-1.0 and its
diagnostics change between releases: a range would let a fresh CI checkout resolve a
version reporting errors the developer's lockfile never showed. Upgrading is a
deliberate act — bump the pin, run `uv run poe typecheck`, adjust suppressions.
`[tool.ty.environment] python-version = "3.12"` pins the *analysed* version to what CI
and the production image run, so a developer on 3.13 cannot get a clean run for code CI
rejects. (The mypy config this replaced pinned `python_version` for the same reason.)

There is **no per-module import override** any more. mypy needed
`ignore_missing_imports` for `socketio`, which ships neither stubs nor a `py.typed`
marker; ty resolves it without complaint. `types-passlib` and `types-python-jose` stay
as dev dependencies — ty consumes the same stub distributions, and they are what gives
the auth path real types instead of `Unknown`.

Why the swap was safe to make — measured, not assumed. With every suppression stripped
from the package so both tools saw identical source, mypy reported 54 sites and ty 56,
agreeing on **46 of them** (the SQLModel false-positive families below). The two tails
are the interesting part:

- **ty flags what mypy does not**: `deprecated` APIs (SQLModel's `execute`), the
  `possibly-missing-submodule` that found the `resend` bug, values read out of a JSON
  column, and a dict lookup whose key is `UUID | None`.
- **mypy flags what ty does not**: `Settings()` missing arguments — a
  pydantic-settings false positive that had needed three `# type: ignore` lines and
  now needs none.

So coverage did not shrink; it shifted and, on net, grew. The run went from ~14 s to
~0.3 s, and the toolchain is Astral end-to-end alongside ruff.

### `ty: ignore` discipline — read this before adding one

ty does **not** model SQLAlchemy/SQLModel column operators. `Column < x`,
`Column.is_not(None)`, `.in_(...)`, `A.id == B.id` and `selectinload(Room.users)` all
build SQL expressions, not Python `bool`s/attributes, so ty reports
`unsupported-operator` / `unresolved-attribute` / `invalid-argument-type` on perfectly
correct query code. Those ~60 per-line ignores are false positives, not debt.

Note that ty does **not** honour mypy's `# type: ignore[<mypy-code>]`: the codes are a
different vocabulary, so such a comment is inert (and a *bare* `# type: ignore` is
reported as an unused blanket directive). All of them were removed in the swap.

**But an ignore on a type error can also hide a real bug, so every time you add one:**

1. **Prove it is a false positive.** Ask what would make the line actually wrong at
   runtime. Be most suspicious when the diagnostic is about **nullability** (`X | None`),
   an `unsupported-operator`, or an `invalid-argument-type` — those are exactly the
   shapes a real bug takes too. If the value really can be `None` at runtime, fix the
   code; do not silence it.
2. **Make the surrounding code provably safe and say why, right above the ignore.**
   `_mark_stale_users` is the worked example: the `IS NOT NULL` filter is written
   *first* so the NULL row is gone before the comparison, and the comment says that is
   why. `_prepare_game_start`'s dict lookup is the other: the `in` test is what makes a
   `None` key impossible, not a hint for the checker.
3. **Narrow it to the rule code** (`# ty: ignore[unsupported-operator]`), never a bare
   `# ty: ignore` — a bare one also swallows the next, unrelated, real error there.
4. **Prefer a real construct to a suppression when one exists.** Reading a value back
   out of `TTLCache` (which stores `object`) is `cast(Sequence[Word], cached)`, not an
   ignore: `cast` says "I assert this type" in a way that survives changing checker.
   Importing `resend.exceptions` explicitly beats suppressing the warning about it.

If you cannot satisfy 1–2, the ignore is masking a bug. Do not add it.

### An `except` clause is only evaluated when something raises

`EmailService._send` caught `resend.exceptions.ApiError`. **That class does not
exist** — the SDK's base is `ResendError`, and `NoContentError` is the one class that
does not inherit from it. A missing name inside an `except` tuple costs nothing on the
happy path, because the tuple is not evaluated until an exception reaches it. So every
*successful* send hid it, and every *failed* send raised `AttributeError` out of the
handler that existed to prevent exactly that — surfacing on `POST /auth/register` as a
500 **after** the user row had committed: the account existed and the caller was told
registration had failed.

A `# type: ignore[attr-defined]` sat on that line, silencing the one error that named
the problem. It is the argument for §1 of the discipline above, in one line of code.

`import resend.exceptions` is now explicit rather than reached through the package's
`__init__`, and `tests/api/services/test_email.py` pins both the behaviour (a failing
send returns False) and the class names themselves.

### A drop-out must leave a round the game can still finish

`undercover_rules.repair_turn_after_dropout(state, user_id)` runs on **every**
Undercover departure — grace-period expiry, kick, or voluntary leave — and is what
stops the round the leaver was blocking from becoming permanent. Three ways it
used to wedge:

- **Describing.** `current_describer_index` still pointed into a
  `description_order` containing the departed player, and `submit_description`
  only accepts the player at that index. Nobody could describe, ever.
- **Voting.** `all_voted` is only evaluated inside `submit_vote`. When the one
  player everybody was waiting on left *instead* of voting, the tally became
  complete by subtraction — and nothing counts a tally except a vote arriving.
- **Mr. White guessing.** `mr_white_guesser` still named the departed player, so
  guessing 403'd for everyone while voting and describing rejected the phase.

**None of these were rescued by the timer.** `description_timer` and
`voting_timer` both default to **0**, which means *no time limit*, so
`_is_timer_actually_expired` returns False forever and `handle_timer_expired`
answers `timer_not_expired`. The room's only escape was the host cancelling the
game with a rematch. Any new "the game is waiting on player X" state must either
be repaired here or be reachable by a timeout that is on by default.

`_handle_undercover_disconnect` therefore **cannot return early on an already-dead
player** — the Mr. White who owes a guess is dead by construction. It computes
`already_dead`, skips the elimination bookkeeping, and still repairs. The repair
never pops a vote out of a `resolved` turn: those votes are history, read back by
the elimination overlay and the vote-history panel.

The rules live in their own module for the same import reason as
`game_end_stats`: `base_game` → `room` → `disconnect`, so `disconnect` cannot
import a controller. `UndercoverGameController._eliminate_player_based_on_votes`
and `_get_winning_team` are thin delegates to it.

### A Codenames team needs both roles, not just a body

`_codenames_team_strength` scores a side 2 (spymaster **and** operative), 1 (one
role left) or 0 (gone), and the game ends as soon as either drops below 2. "Is the
team empty?" was the wrong question: teams are dealt exactly one spymaster and the
rest operatives, so at the 4-player minimum *either* departure leaves a team of
one — non-empty, and unable to take a turn.

- No operative: the spymaster gives a clue and nobody can guess or end the turn.
- No spymaster: nobody can give a clue, so `guess_card` answers `NoClueGivenError`
  and the side can only ever pass.

The Codenames timers also default to 0, so nothing switched the turn either. The
score ordering (not a boolean) is what decides the winner when a side drops below
2: an empty team must never beat a crippled one.

### Undercover vote targets are secret until the round resolves

`_visible_votes` returns the caller's own choice and blanks everyone else's while
the round is open; `_build_vote_history` skips the current turn until it is
`resolved`. Both become public once the turn resolves or `state["winner"]` is set.

The UI only ever rendered *who* had voted out of that dict (`deriveVotedPlayers`
takes its keys), but the payload named every target — so anyone with the network
tab open watched the tally build and voted last with perfect information. In a
social-deduction round that is the entire game. `_build_vote_history` was the door
the client actually reads through, and its docstring had always claimed to exclude
the in-progress round while the code did not.

### The Word Quiz hint ladder is released one rung at a time

`_resolve_hints(state, lang, limit)` is capped by the server's own
`_calculate_hints_revealed`, and `WordQuizGameState.max_hints` carries the ladder
length separately because `hints` is now a prefix.

It used to return all six "so the client can control display timing locally". A
correct answer pays `max_hints - hint_number + 1`, with `hint_number` computed
from elapsed *server* time — so reading the network tab showed the most specific
hint at t=0 and paid full marks, while honest players lost a point per rung. The
client keeps animating locally and re-fetches when its clock crosses a rung it
does not hold (there is no Socket.IO event for a hint: nothing mutates).

### The quiz ready quorum excludes the host

`BaseGameController._ready_quorum(state, host_id)`. The host advances a round by
pressing next and is never added to `ready_players`, so comparing against
`len(state["players"])` made "everyone is ready" unreachable whenever the host was
also a player — i.e. in every normal game. The documented feature collapsed to
"only the host can advance", and an absent host stalled the quiz with nothing to
rescue it: the results phase has no timeout. `AdvanceRoundResponse.total_players`
reports the quorum, so it is comparable with `ready_count`.

The two tests that covered this had encoded the bug; one of them said so in a
comment ("We need the host to also mark ready OR the host to force advance… let's
test host override instead"). **A test that documents why the feature can't work
is a bug report, not a spec.**

### An access token must name one account by *both* claims

`get_current_user` rejects a token whose `sub` does not match the row its `email`
resolves to. Resolving on email alone (and decoding `sub` without ever looking at
it) let a token outlive its account: delete and re-register the same address, and
whoever next owns that mailbox inherits every session still holding the old token.
`/auth/refresh` had always made this check; the request path had not.

### Only a live room blocks creating one

`create_room`'s "already in a room" guard joins `Room` and filters
`type == ACTIVE`, matching `get_active_room_for_user`. Without the join a link to
an INACTIVE room barred the player forever: a room is deactivated when its last
*connected* member leaves, which leaves behind the links of anyone marked
disconnected — and Socket.IO `connect` flips such a link back to connected on the
next reconnect. The player then could not create a room, while
`get_active_room_for_user` reported none to leave, so the UI offered no way out.

### Arabic forms of game terms live in `term_script`, keyed by the Latin word

Undercover (`Word.word`) and Codenames (`CodenamesWord.word`) terms are stored as
Latin transliterations ("Sabr", "Hajj", "Dhul-Kifl"). Their Arabic script lives in
the **`TermScript`** table (`models/term_script.py`): `term` (the exact Latin
string, unique) → `ar` (as normally written, no harakat: "صبر", "الفاتحة") and
`ar_vocalized` (conventional harakat: "صَبْر"; **null when not certain** — a missing
vowel beats a wrong one on a prophet's or a place's name).

**Why a separate table, not columns on `word` / `codenames_word`:** there are no
migrations. `create_all` creates a missing table on startup but never ALTERs an
existing one, so a new column would simply never appear on production. A new
table is additive. It also gives one row per term even where the same Latin word
appears in both games or in two Codenames packs.

**Where it is read** — always ONE batched `TermScriptController.get_forms(...)` per
request, never per card (tests pin the statement count with `count_statements`):

- Codenames `get_board`: `word_ar` **and `word_ar_vocalized`** on every card, in
  every view (spymaster, operative, spectator, end-of-game reveal), and on each
  clue-history guess (the Latin is visible to all, so the Arabic reveals nothing).
  The vocalised form is there because the bare one is ambiguous on a card: أحد is
  Uhud or "one", ثور is Thawr or "a bull" — same lookup, no extra query.
  `give_clue` also rejects a clue that is a board word's Arabic form — it is
  printed on the card.
- Undercover `get_state`: `my_word_ar` / `my_word_ar_vocalized` for the caller's
  OWN word only; null for Mr. White and spectators; both words' forms in
  `word_explanations` only once there is a winner. Same visibility as the Latin.
- `GET /games/{id}/summary`: both Undercover words, and each Codenames guess
  (`word_ar` + `word_ar_vocalized`).
- `GET /notebook` and `GET /notebook/games/{id}`: every kept / dealt word (see the
  Kunnash below — a Word Quiz word prefers its own `QuizWord.word_ar`).
- Mr. White's guess is accepted in Latin or in the civilian word's `ar` form, via
  `utils/text_match.matches_any` (diacritics stripped, أ/إ/آ→ا, ة→ه, ى→ي, ؤ→و, ئ→ي,
  article optional in both scripts, "ابن"→"بن" between names, "وو"→"و" so "داوود"
  = "داود"). Word Quiz shares `normalize_answer` from the same module.

**Adding a term:** add the word to `scripts/seed_data/undercover_data.py` or
`codenames_data.py` AND its line to `scripts/seed_data/term_script_data.py`
(`"Latin": ("عربي", "عَرَبِيّ" or None)`). `tests/scripts/test_term_script_data.py`
fails on a gap, an orphan, Latin letters in `ar`, an `ar_vocalized` that does not
strip back to `ar`, or a vocalised phrase with a bare non-final word. Rule for
`ar`: the bare noun as printed on a card; the article only where the term is
conventionally written with it (surahs, "القرآن", "المدينة", "الزبير",
dynasties). No honorific inside the term. Rule for `ar_vocalized`: only the LAST
word is pausal; every earlier word of a multi-word name keeps its case vowel
("لَيْلَةُ الْقَدْر", "خَالِدُ بْنُ الْوَلِيد"), because a bare one reads as a stop.
A word an admin adds through the API without a row simply gets null Arabic forms.

**The seed is an upsert** (`seed_term_scripts` → `TermScriptController.upsert`):
inserts missing terms, rewrites changed ones, leaves every other row alone. It runs
from both `--create-db` and `--seed`, so fixing a spelling in the data module and
running `--seed` on the server is the whole deployment — no drop, no reseed. The
table exists after the first startup but is **empty until `--seed` runs** on that
database; until then every Arabic field is null and the games play as before.

### The Kunnash (كُنّاش): words kept from finished games

`NotebookEntry` (`models/notebook.py`, table `notebook_entry`) — `user_id`, `term`
(the Latin key exactly as the game stored it: `Word.word`, `CodenamesWord.word`,
`QuizWord.word_en`), `game_type` (`NotebookGameType`: undercover / codenames /
word_quiz — the `GameType` values; MCQ has no words), `source_game_id`, `kept_at`
(UTC-aware). A new table, not columns anywhere: no migrations. Registered in
`models/table.py` like every other model, so `--delete`'s `drop_all` drops it
before `user` and `game` (it holds FKs to both).

Endpoints (`routes/notebook.py`; handler names are what the Kubb hooks are named
after, so they all say "notebook"):

| Route | Hook | Params / body → response |
|---|---|---|
| `GET /notebook/games/{id}` | `useGetNotebookGameWords…` | `lang` → `NotebookGameWords {game_id, game_type, words: [{word, word_display, word_ar, word_ar_vocalized, hint, kept, entry_id}]}` |
| `POST /notebook/games/{id}/keep` | `useKeepNotebookGameWords…` | `lang` → `NotebookKeepResponse {added, already_kept, entries}` |
| `POST /notebook/entries` | `useKeepNotebookWord…` | `{game_id, word}` + `lang` → `NotebookKeepResponse` |
| `GET /notebook` | `useListNotebookEntries…` | `lang, limit, cursor` → `NotebookPage {entries, total, next_cursor}` |
| `DELETE /notebook/entries/{id}` | `useDeleteNotebookEntry…` | 204 |

Field names are `word` / `word_ar` / `word_ar_vocalized`, like every other
word-bearing schema (cards, clue guesses, `my_word_*`), so one chip renders them all.

- **Gated exactly like the summary** — `get_past_game_for_participant`: not a
  participant → 403, IN_PROGRESS → 403, then MCQ → 400. Participation first, so a
  stranger gets the same answer whatever the game's state or type. The words ARE
  the secret while a game runs.
- **`GET /notebook/games/{id}` is the game-over colophon's one call.** Word Quiz
  needs it most — `WordQuizGameState` only ever holds the current round's answer, so
  the list could otherwise only be collected round by round on the client, and was
  lost on refresh — and every game needs `kept` / `entry_id` so a revisit shows what
  is kept and can un-keep it (`DELETE /notebook/entries/{entry_id}`). `kept` is
  about the notebook, not the game: a word kept from an earlier game is kept here too.
- **A kept word must belong to the game.** The game's words come from `live_state`
  (Undercover: both words; Codenames: the 25 board words; Word Quiz: `used_word_ids`
  → `QuizWord`), never from the content tables, so the endpoint cannot probe for or
  inject arbitrary terms (`TermNotInGameError`, 404). A Word Quiz word is accepted by
  any of its three spellings — the game shows the answer in the player's language —
  and stored by `word_en`.
- **Idempotent by `UniqueConstraint(*NOTEBOOK_UNIQUE_COLUMNS)` +
  `INSERT … ON CONFLICT DO NOTHING … RETURNING id`**, not read-then-insert: a double
  tap or two tabs would otherwise both see "not kept" and the second insert would
  500. `RETURNING` is what makes `added` / `already_kept` exact under a race
  (`test_concurrent_keeps_insert_each_word_once`, postgres). The dialect `insert`
  (postgresql / sqlite) is chosen from `session.bind`. A word re-kept from another
  game keeps its first `source_game_id`.
- **The listing is keyset-paginated** on (`kept_at`, `id`) DESC: `cursor` is the
  previous page's opaque `next_cursor` (`utils/cursor.py`, base64url of the pair;
  anything else is `InvalidNotebookCursorError`, 400), null on the last page — the
  query fetches `limit + 1` rows to know. An offset made an optimistic delete skip
  the next page's first entry and a keep from another tab repeat one; `id` breaks
  ties because a whole board shares one `kept_at`. `total` still counts the whole
  notebook. (Kubb generates an infinite hook only with `infinite: { queryParam:
  "cursor", cursorParam: "next_cursor" }` in `front/kubb.config.ts` — the frontend's
  call.)
- **Reads are batched**: the listing is one count, one page, one `term_script`
  lookup, at most one query per content table and only for the game types on the
  page (`test_list_entries_resolves_with_batched_queries` pins it); the colophon
  list likewise (`test_game_words_reads_nothing_it_does_not_need`).
- **Display.** `word_display` is the word as its game showed it in `lang`: the Latin
  key for Undercover and Codenames, `word_fr` / `word_ar` / `word_en` for Word Quiz
  (the rule of `_get_correct_answer`). Arabic: `term_script` for Undercover and
  Codenames; for Word Quiz the word's OWN `word_ar` first — it is what the game
  revealed, and `term_script` is keyed by Latin spellings another game's term may
  share — with `term_script`'s vocalisation only when it vocalises that same Arabic.
  `word_ar_vocalized` is therefore null for (almost) every Word Quiz word: the
  client shows `word_ar` then. The hint is `resolve_multilingual`
  (`utils/multilingual.py`) over `Word.hint` (else `long_description`), the oldest
  `CodenamesWord` row with a hint, or `QuizWord.explanation` (else the last rung).
- **Keeps are rate-limited per user** (`NOTEBOOK_KEEP_RATE_LIMIT`,
  `key_func=user_or_ip_key`) — see "Rate limits" below.
- **Someone else's entry is a 404 on DELETE**, the same as a missing id, so ids
  cannot be probed. Account deletion purges the rows (`_purge_user_references`).
- Nothing is pushed over Socket.IO: the notebook is personal, there is no room.

### Rate limits answer the standard envelope, keyed by the caller

`rate_limit.rate_limit_exceeded_handler` answers a 429 with the same JSON as every
`BaseError` (`schemas/error.error_response`): `error_key: errors.api.rateLimitExceeded`,
the English `message`, `details.limit`. slowapi's default body was
`{"error": "Rate limit exceeded: 30 per 1 minute"}` — nothing the client could
translate, so Arabic and French players got raw English.

`rate_limit.user_or_ip_key` counts a signed-in caller per USER: `get_current_user`
records the verified id on `request.state.user_id`, and slowapi checks the limit
inside the endpoint wrapper — after FastAPI has resolved the dependencies — so the id
is there by then, and a forged token has already been answered 401. Per IP was wrong
for a game played by several phones on one home connection: the whole table shared
one budget. Use it on any limited endpoint behind `get_current_user`; anonymous
endpoints (login, register, join) stay per IP.

### The prayer pause (وقفة الصلاة): no move, no clock, nothing lost

When the adhan comes mid-game the host pauses it and resumes it after the prayer.
`POST /api/v1/{undercover|codenames|wordquiz|mcqquiz}/games/{id}/pause` and `/resume`
(no body) call `BaseGameController.pause_game` / `resume_game`; the routes `await
notify_game_changed`. There is deliberately no generic `/games/{id}/pause`: game
mutations live on the per-game routers only. Hooks:
`usePause{Undercover|Codenames|Wordquiz|Mcqquiz}Game…Post`, `useResume…Post`.

- **State.** `live_state["paused"] = {"by", "by_username", "at" (UTC ISO), "reason":
  "salah"}`, absent while the game runs; the key names are `PAUSE_*` constants. Pure
  helpers in `utils/game_pause.py` (the disconnect checker needs them and cannot
  import a controller).
- **What the client reads.** Every state schema declares `paused: GamePause | None`
  and per-caller `can_pause` / `can_resume`. `GamePause` = `by_user_id`,
  `by_username`, `since`, `reason`, plus three values the SERVER derives
  (`_pause_view`): `remaining_seconds` — the current phase's timer frozen at the
  pause, clamped to `[0, duration]`, null when the phase is untimed (timer 0, a
  resolved Undercover vote, a quiz between rounds); `paused_for_seconds`; and
  `anyone_can_resume_at`. Leaving the countdown to the client (`since - anchor`) was
  wrong whenever a timer restarted during the pause — the anchor is then later than
  `since`, and the veil read more than the whole duration. Each controller reports
  its phase's timer in `_phase_timer` (the durations of its
  `_is_timer_actually_expired`). `_build_pause` answers None for a game no longer
  IN_PROGRESS even if the record is still in its `live_state`.
- **Who.** Pause: the room's current owner only (`OnlyHostCanPauseError`, 403), never
  a spectator (`SpectatorCannotPauseError`) — not even one holding the host role.
  Resume (`_may_resume`, the ONE rule behind both `resume_game` and `can_resume`):
  the current owner — a spectator host included, because host transfer falls back to
  a spectator when nobody else is connected — **or any player of the game** once the
  pause has lasted `PRAYER_PAUSE_MAX_SECONDS` (45 min), or at once when the room has
  no owner (the host deleted their account; `_purge_user_references` nulls
  `Room.owner_id`). Without that, a host whose tab stayed open — so the paused grace
  never removed them — held the table paused for good, and an orphaned room could
  never be resumed at all: the game stayed IN_PROGRESS forever and its words could
  never be kept. A bare spectator never resumes. Pausing a paused game →
  `GameAlreadyPausedError`, resuming a running one → `GameNotPausedError` (both 409),
  a finished one → 400. Each runs under `get_game_lock` with one commit.
- **The game's own type decides.** Each controller sets `GAME_TYPE`; pause / resume
  reached through another game's router answer `GameNotFoundError` (404).
  `_get_game` checks no type, so `POST /undercover/games/{wordquiz_id}/resume` used
  to clear the pause and shift a key the game does not have, leaving its real clock
  to count the whole prayer. The anchors themselves come from
  `constants.PAUSE_TIME_ANCHOR_KEYS[game.type]`, never from the controller class.
- **While paused, every move is refused** with `GamePausedError` (409) by
  `_ensure_not_paused`, called first in: Undercover `submit_description`,
  `submit_vote`, `submit_mr_white_guess`, `start_next_round`; Codenames `give_clue`,
  `guess_card`, `end_turn`; Word Quiz / MCQ `submit_answer`, `advance_to_next_round`
  (ready marks included). `handle_timer_expired` in all four answers
  `TimerExpiredAction.PAUSED` without acting — not an error, because clients fire it
  from their own timers — so a paused game can never be ended by a timer.
  `TimerExpiredResponse.action` is that enum, so every value reaches OpenAPI and the
  client switches on a union rather than on hard-coded strings. Hint views stay open
  (they change nothing a player competes on). Room-level host actions (kick, rematch)
  and voluntary leaves still work: they are explicit decisions, not clocks.
- **Resume moves every clock forward.** `PAUSE_TIME_ANCHOR_KEYS`: Undercover /
  Codenames `timer_started_at`; the quizzes `round_started_at`, which also drives the
  hint ladder, Word Quiz scoring and `answer_time_ms`, and the MCQ speed bonus.
  `shifted_instant` moves each by the paused duration but never past the resume: an
  anchor set *during* the pause (a drop-out moved an Undercover round to voting) has
  counted nothing and starts at the resume. **A new time-based rule must add its
  anchor there**, or its clock runs through the prayer. Read paths that derive
  something from elapsed time use `clock_now(state)`, frozen at the pause — the Word
  Quiz ladder does. `Game.start_time` / `end_time` are wall-clock history, unshifted.
- **Disconnects.** Phones lock and sockets drop during a prayer, and the 180 s
  in-game grace would have removed half the table. While a room's game is paused,
  `_remove_expired_users` keeps a disconnected member for
  `PAUSED_GAME_GRACE_PERIOD_SECONDS` (45 min — a Jumu'ah with its khutbah). It is
  finite on purpose: a host who never comes back is eventually removed, ownership
  transfers (preferring a player), and the new host resumes. The sweep reads the
  rooms and their active games in ONE query each — a paused game keeps its
  expired-looking links for 45 min, and per-link lookups cost two queries per away
  player every 5 s — then re-reads each link it is about to remove
  (`_still_expired`): a reconnect or a resume committed since the sweep's read must
  not drop a player at a timestamp that no longer exists. The re-check runs outside
  the game lock, so a resume landing in the milliseconds between it and the removal
  can still slip through. On resume, `_shift_disconnect_grace` moves each
  still-disconnected link's `disconnected_at` by the same rule (naive, like every
  `RoomUserLink` timestamp), so the ordinary grace counts only running time. **No
  auto-resume on host departure**: the host leaving during the prayer is the normal
  case, and restarting the clocks then would defeat the feature.
- **Drop-outs during the pause still apply** (they are real departures): one that
  decides the game ends it through the usual end-of-game flow; the game then reads
  as not paused and cannot be resumed (400).

Tests: `tests/api/controllers/test_game_pause.py` (all four games; the anchor tests
are written so that removing the shift fails them; the cap, the orphaned room, the
mismatched router, the server-side countdown, `can_pause` / `can_resume`, the batched
sweep and its re-check; three postgres-marked races: pause vs a move, double pause,
and double resume shifting once — that one ages the round anchor BEFORE backdating
the pause, or the anchor reads as set during the pause and is capped),
`tests/api/routes/test_game_pause.py`, `tests/api/utils/test_game_pause.py`.

### Usernames are unique — by check, not by constraint

`user.username` is indexed but carries **no unique constraint**, and there are no
migrations to add one (nor a functional `lower(username)` index) to the existing
table. So `controllers/user.username_is_taken(session, name, exclude_user_id=)` asks
first, case-insensitively (`lower()`: ASCII on SQLite, full Unicode on PostgreSQL;
Arabic has no case), and three paths use it:

- `AuthController.register` → `UsernameAlreadyTakenError` (409,
  `errors.api.usernameAlreadyTaken`, `error_params.username`). It also checks the
  email first → `UserAlreadyExistsError` (409); the email used to be left to the
  unique constraint, whose `IntegrityError` nothing caught — a 500 — and a second
  "admin" registered without complaint (`e2e/tests/auth/validation.spec.ts`
  "duplicate username shows error"). An `IntegrityError` on commit (an email race)
  still maps to `UserAlreadyExistsError`.
- `UserController.update_user_by_id` (profile rename): another account's name in any
  case is refused; re-casing one's own name is not a collision. `UserUpdate.username`
  now has registration's pattern (no whitespace, `<>/\@`), or "admin " would slip
  past the check.
- `_create_social_user`: a generated Google name that collides in any case gets the
  random suffix.

**Residual race:** two concurrent registrations (or renames) to the same new name
can both pass the check and both commit — check-then-insert without a constraint.
It needs two people choosing the same new name within milliseconds; the fix, if it
ever matters, is a new table holding `lower(username)` under a unique constraint
(additive, so `create_all` would create it).

### The Socket.IO `game_state` push is read in the client's language

`join_game` answers with the caller's full state (`ws/state.fetch_game_state`), and
the client writes it straight into its query cache for Undercover and Codenames. It
called every controller with the English default, so an Arabic player's game-over
meanings (`word_explanations.*_hint`, card hints) turned English a moment after the
REST response (`?lang=ar`) had them right. The handshake now accepts `auth.lang` and
`join_game` accepts `{"game_id", "lang"}` (payload wins, then the handshake, then
`en`; `utils/multilingual.normalize_lang` keeps it to `SUPPORTED_LANGUAGES`).
**The client must send it** — until it does, the push stays English.

`GET /games/{id}/summary` takes `lang` too and now carries the meanings:
`word_explanations.civilian_word_hint` / `undercover_word_hint` and each Codenames
`clue_history[].guesses[].hint`, all through `resolve_multilingual`.

### MCQ points are withheld until the reveal

Points are added to `total_score` at lock-in. While `round_phase == "playing"`, every
caller's state therefore shows each player's score BEFORE the round
(`total_score - this round's points`), `current_round_points = 0` and `my_points = 0`
(`_build_player_states`, `_round_is_revealed`) — a total moving by 1-3 told the table
who had just been right, and how fast. `current_round_answered` stays visible
("2 of 5 answered"). From `results` on, everything is real. The answer response
(`McqSubmitAnswerResponse.correct/points_earned`) still tells the caller alone.

The reveal itself comes from the server so it survives a reload, and is null while
the question is open: `choice_tallies` (4 counts, indexed like `choices`),
`my_choice_index`, `my_answer_time_ms` on the state, and `choice_index` /
`answer_time_ms` per `round_results` row. `answer_time_ms` is stored at lock-in from
`round_started_at` (which a resume shifts past the prayer).

### Word Quiz: the word's theme, and what each player typed

- `WordQuizGameState.category` — the current word's `QuizWord.category` (stored in
  `live_state["category"]` at start and each new round) as a `WordQuizCategory` key
  (`constants.WORD_QUIZ_CATEGORY_KEYS`: prophets, companions, places, quran,
  islamic_history, islamic_concepts, daily_life). A theme, not a kind: the client
  words it. An admin-made label outside the map, or a game started before the key
  existed, reads null. Not a secret: the header shows it during play.
- `live_state["attempts"][user_id] = {count, last_text, last_hint}` records every
  answer, right or wrong (`_record_attempt`; reset each round), and a correct answer
  keeps `answer_text`. `_transition_to_results` copies them into the round's results:
  `WordQuizRoundResult.typed_answer` (the answer that found it, else the last wrong
  try, else null) and `attempts`. **Only round_results carries them, and only from
  the results phase on** — a correct `typed_answer` IS the answer
  (`test_typed_answers_appear_only_once_the_round_resolves` checks the open payload
  never contains it). `answered_at_hint` was already there.

### The colophon: who hosted, and when

All four state schemas carry `host_username`, `started_at`, `ended_at`
(`schemas/common.GameColophon`, built by `BaseGameController._build_colophon`; sent in
every phase — none is a secret):

- `host_username` is the room owner when the game STARTED, written into
  `live_state[HOST_USERNAME_STATE_KEY]` by each `create_and_start`
  (`_host_username_at_start`), so a later host transfer does not rename "Yusuf's
  majlis". A game started before the key existed falls back to the current owner's
  name — `_get_room_host` reads the owner id and username in ONE query (it replaced
  `_get_room_owner_id` in the state reads, so the colophon costs no extra query).
- `started_at` / `ended_at` are `Game.start_time` / `end_time` through
  `utils/game_state.as_utc` (SQLite hands them back naive). `ended_at` is null while
  the game runs. Wall-clock: a prayer pause counts in the duration.

### The lobby's away countdown is server-computed

`RoomPlayerState.away_seconds_left`: whole seconds, rounded up, before the sweep
removes a disconnected member; null while connected (or when a link has no
`disconnected_at`, which the sweep never removes). The grace is the sweep's own rule
(`disconnect.member_grace_seconds(room, active_game)` → `_grace_seconds`): 600 s in
the lobby, 180 s in a running game, 45 min while it is paused. Clamped to
`[0, grace]`; 0 means "due at the next sweep" (every 5 s). The arithmetic is NAIVE
(`datetime.now()` against the naive `RoomUserLink.disconnected_at`) — never make
those columns aware (root CLAUDE.md). `get_room_state` already read the active game
for the game type, so this adds no query; the client counts down locally from the
value it last received.

### Every error the API answers is named and translated

`tests/api/test_error_keys.py` fails when an error class's key (or one of the
handlers' literal keys) is missing from `errors.api` in `en`/`fr`/`ar.json`, and when
anything constructs a bare `BaseError(...)`. A bare one answers `errors.api.base`,
which no locale can translate because its message varies — forty of them did, so an
Arabic player read "You have already voted this round." in English. They are now
named classes in `schemas/error.py` ("Errors that used to be raised as a bare
BaseError") that keep the old `message` (logs and tests match on it) and
`frontend_message` (the client's fallback). A new error needs its class AND its three
translations.
