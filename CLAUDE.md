# CLAUDE.md - IBG (Islamic Board Games)

## Project Overview

IBG is a real-time multiplayer platform for Islamized versions of popular party games. Currently supports **Undercover** and **Codenames**, with plans for more games.

### Architecture

This is a **monorepo** with separate backend and frontend applications:

```
IBG/
├── backend/                    # Python/FastAPI + Socket.IO
│   ├── ibg/
│   │   ├── api/               # REST API
│   │   │   ├── controllers/   # Business logic
│   │   │   ├── models/        # SQLModel DB tables
│   │   │   ├── schemas/       # Pydantic request/response + base classes
│   │   │   ├── routes/        # FastAPI routers
│   │   │   ├── services/      # External integrations
│   │   │   ├── constants.py   # All magic values
│   │   │   └── middleware.py  # Security, request ID, logging
│   │   ├── socketio/          # Real-time game events
│   │   │   ├── controllers/   # Game logic (undercover, codenames)
│   │   │   ├── models/        # Redis OM game state models
│   │   │   └── routes/        # Socket.IO event handlers
│   │   ├── app.py             # FastAPI app factory
│   │   ├── database.py        # Async SQLAlchemy engine
│   │   ├── dependencies.py    # DI with Annotated + Depends
│   │   ├── settings.py        # Multi-env pydantic-settings
│   │   └── logger_config.py   # Structured Loguru logging
│   ├── tests/
│   ├── scripts/               # Fake data generation
│   ├── main.py                # Entry point
│   └── pyproject.toml
├── front/                     # React 19 SPA
│   ├── src/
│   │   ├── api/               # API client + Kubb generated hooks
│   │   ├── components/        # UI components
│   │   ├── hooks/             # Custom hooks (socket, auth)
│   │   ├── i18n/              # English + Arabic translations
│   │   ├── lib/               # Utilities (cn, socket, auth)
│   │   ├── providers/         # Auth, Query, Theme providers
│   │   └── routes/            # TanStack Router file-based
│   ├── kubb.config.ts         # API codegen from OpenAPI
│   └── vite.config.ts
├── e2e/                       # Playwright tests (future)
├── docker-compose.yml         # Local dev (Postgres + Redis)
├── docker-compose.dokploy.yml # Production (Oracle VPS)
└── .github/workflows/         # CI/CD
```

### Component Documentation

- **[backend/CLAUDE.md](./backend/CLAUDE.md)**: Backend architecture, API patterns, database models
- **[front/CLAUDE.md](./front/CLAUDE.md)**: Frontend patterns, component guidelines, Kubb usage

When working on a specific component, consult both this root CLAUDE.md for project-wide conventions and the component-specific CLAUDE.md for detailed implementation guidance.

## Development Mindset

**Iterate fast, follow best practices without being overkill.** The goal is to ship quickly while maintaining code quality.

## Development Commands

### Backend

```bash
cd backend

# Start dev server
uv run python main.py                    # http://localhost:5000

# Code quality
uv run poe lint                          # Ruff lint check
uv run poe format                        # Ruff format
uv run poe check                         # All checks

# Testing
uv run poe test                          # Run tests
uv run poe test-fast                     # Stop on first failure

# Fake data
PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db
PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete
```

### Frontend

```bash
cd front

# Start dev server
bun dev                                  # http://localhost:3000

# Generate API client from OpenAPI spec (requires backend running)
bun run generate

# Code quality
bun run lint                             # oxlint
bun run typecheck                        # TypeScript
bun run format                           # oxfmt

# Testing
bun run test                             # Vitest
bun run test:coverage                    # With coverage
```

### Docker

```bash
# Start all services locally
docker compose up -d

# Production deployment (Dokploy)
docker compose -f docker-compose.dokploy.yml up -d
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLModel, SQLAlchemy (async), python-socketio |
| Database | PostgreSQL (prod), SQLite (dev) |
| Cache/State | Redis (aredis_om for game state) |
| Auth | JWT (python-jose, bcrypt) |
| Frontend | React 19, TanStack Router/Query, Tailwind v4, shadcn/ui |
| Real-time | Socket.IO (server + client) |
| API Codegen | Kubb (OpenAPI -> React Query hooks) |
| i18n | i18next (English + Arabic) |
| Testing | pytest (backend), Vitest (frontend) |
| CI/CD | GitHub Actions |
| Deployment | Docker + Dokploy (Oracle VPS) |

## Coding Standards

### Zero Tolerance for Test Failures

**ABSOLUTE RULE: A task is NEVER complete if there is even a single failing or flaky test.** This is non-negotiable — no feature, bugfix, refactor, or any modification of any kind can be considered done until the ENTIRE test suite passes with:
- **0 failed tests**
- **0 flaky tests**

A flaky test IS a failing test. "It passes on retry" is NOT acceptable. If a flaky test exists — whether caused by your changes or pre-existing — you MUST fix it before the task is complete. Do not move on, do not report the task as done, do not ask the user if it's acceptable. Fix it.

### CLAUDE.md Self-Maintenance

**CRITICAL: Keep CLAUDE.md files up to date.** Whenever a change has significant business or technical implications, you MUST update the relevant CLAUDE.md (`CLAUDE.md`, `backend/CLAUDE.md`, or `front/CLAUDE.md`). This includes:
- **Architecture changes**: new authentication flow, new service layer, new game type
- **New tools or libraries**: added a new MCP server, switched linting tool, added a dependency
- **Business logic changes**: new game rules, room management changes, new user roles
- **Coding pattern corrections**: when the user corrects a mistake, add or strengthen the corresponding rule so it won't happen again
- **New models or endpoints**: significant new database tables, API endpoints, or features
- **Removed or renamed concepts**: update references so CLAUDE.md doesn't describe things that no longer exist

If unsure whether a change warrants a CLAUDE.md update, err on the side of updating — stale documentation is worse than verbose documentation.

### Verification After Changes

**CRITICAL: Always run linters and tests after any code change.** Whenever you edit, add, update, or delete code, you MUST verify nothing is broken:

```bash
# Backend — run after any backend change
cd backend && uv run poe check && uv run poe test

# Frontend — run after any frontend change
cd front && bun run lint && bun run typecheck

# E2E — MANDATORY after any backend or frontend change that touches main logic
# (API routes, controllers, Socket.IO, game components, rooms, auth, shared state)
# Only skip for purely cosmetic/unrelated pages (e.g. About page, static content)
cd e2e && npx playwright test
```

**CRITICAL: E2E tests are NOT optional.** Any change to backend controllers, Socket.IO handlers, API routes, game logic, room management, auth flow, or frontend components that interact with the backend MUST be followed by a full E2E run. The E2E suite is the final safety net — unit tests and linters alone are not sufficient to catch integration regressions.

Do not consider a task complete until ALL tests pass with zero failures AND zero flaky tests — whether or not the failures appear related to your changes. A flaky test is still a failing test. If a pre-existing flaky test blocks completion, fix it before moving on.

### Debugging Test Failures

**NEVER use `git stash` to check if a test failure is pre-existing.** When tests fail after your changes, investigate the failure directly:
1. Read the error message and traceback carefully
2. Check the test code and the code it's testing
3. Determine if your changes caused the failure or if it's unrelated
4. Fix the issue — don't try to prove it's "not your fault" by stashing

### Python/FastAPI Guidelines

#### Import Organization

**All imports must be at the top of the file.** Never place imports inside functions or methods, even for lazy loading. The only acceptable exception is to break circular imports involving Redis OM models (e.g., `ibg.socketio.models` ↔ `ibg.api.controllers`), and even then, add a comment explaining why.

```python
# Good - imports at the top
from loguru import logger
from sqlmodel import select

from ibg.api.models.table import User, Room
from ibg.api.schemas.error import NotFoundError

class MyController:
    async def my_method(self):
        ...

# Bad - imports inside methods
class MyController:
    async def my_method(self):
        from loguru import logger  # DON'T DO THIS
        ...

# Acceptable exception - circular import with Redis OM
class MyController:
    async def _check_redis(self):
        # Lazy import to avoid circular dependency:
        # room.py -> socketio.models.user -> socketio.models.shared -> room.py
        from ibg.socketio.models.user import User as RedisUser
        ...
```

#### General Guidelines

- Use `def` for pure functions, `async def` for asynchronous operations
- Python 3.10+ type hints for all function signatures
- **CRITICAL: Always use the project's base classes from `ibg.api.schemas.shared`**, never `pydantic.BaseModel` or `sqlmodel.SQLModel` directly
- **No nested function definitions.** Do not define functions inside other functions. Extract inner logic into separate methods on the class or standalone module-level functions.
- Use descriptive variable names with auxiliary verbs (e.g., `is_active`, `has_permission`)
- Use lowercase with underscores for directories and files
- Store all magic values in `ibg/api/constants.py`

#### Route → Controller → Model

- **CRITICAL: NO logic in routes.** Routes must NEVER contain database queries, business logic, or data transformation. All `select()`, `session.exec()`, model validation, and data processing MUST live in controllers. Routes only call controller methods and return results.

#### Error Handling

- Handle errors and edge cases at the beginning of functions
- Use early returns for error conditions to avoid deeply nested if statements
- Place the happy path last in the function for improved readability
- Use custom error classes for consistent error handling

### Testing Guidelines

- All tests follow the **Prepare / Act / Assert** pattern with clear section separation
- Always verify both **return values** and **database state** (re-fetch from DB after mutations)
- Mock external services (Redis) in unit tests; use real Redis (testcontainers) in socket tests

## Key Patterns

- **Route -> Controller -> Model**: No business logic in routes
- **Async Everything**: All DB operations and external calls are async
- **Dependency Injection**: FastAPI's `Depends()` with `Annotated` type hints
- **BaseModel/BaseTable**: All models inherit from `ibg.api.schemas.shared.BaseModel/BaseTable`
- **Enhanced Errors**: Auto i18n keys, auto-logging, `frontend_message` for UI
- **Multi-env Settings**: `IBG_ENV` selector (.env -> .env.{env})
- **Socket.IO + REST**: REST for CRUD, Socket.IO for real-time game events
- **Kubb Codegen**: Auto-generated React Query hooks from FastAPI's OpenAPI spec

## Lessons Learned (E2E, Backend, Frontend, Infrastructure)

These are hard-won lessons from debugging the full E2E suite (125 tests), backend performance, and real-time Socket.IO game flows. Every item below caused real failures — keep them in mind when touching these areas.

### Backend — Socket.IO

**Always send events to individual SIDs, never room broadcasts.**
When a player's socket reconnects (page reload, network blip), the new socket does NOT automatically rejoin the Socket.IO room. Room broadcasts silently miss reconnected players. Always iterate over `game.players` and send to each `p.sid` directly:
```python
# WRONG — reconnected players miss this
await sio.emit("player_eliminated", payload, room=room_public_id)

# RIGHT — guaranteed delivery to each player
for p in game.players:
    if p.sid:
        await send_event_to_client(sio, "player_eliminated", payload, room=p.sid)
```

**Redis game state votes use UUIDs, not strings.** `game.turns[-1].votes` is a `dict[UUID, UUID]` (voter_id → voted_for_id). Always use `.get()` for safe lookup — dead players from previous rounds won't have entries:
```python
# WRONG — KeyError if player didn't vote (eliminated)
votes[player.user_id]
# RIGHT
votes.get(player.user_id)
```

**Put the "all voted" check inside the Redis lock.** In `set_vote`, two concurrent vote handlers can both see a complete vote set and both trigger elimination. The all-voted check and elimination must happen atomically inside the lock to prevent double-elimination corrupting `eliminated_players`.

**`get_undercover_state` is the reconnection handler — it must be complete.** This handler is called on every page load/reload. It must:
- Cancel any pending disconnect cleanup (`cancel_disconnect_cleanup`)
- Update the player's SID if it changed
- Detect game-over state via `get_winning_team()` and include `winner` in response
- Rejoin the socket to the SIO room (`sio.enter_room`)

**Clean up per-SID state on disconnect.** Any in-memory tracking keyed by SID (event counters, throttle maps) must be cleaned up in the disconnect handler to prevent memory leaks. We added `cleanup_sid_counter(sid)` for the TTL throttle counter.

### Backend — Performance

**Never use `BaseHTTPMiddleware` for high-concurrency apps.** Starlette's `BaseHTTPMiddleware` wraps the entire request body in memory, prevents streaming, and serializes request processing. Under E2E load (125 concurrent browser sessions), this caused connection pool exhaustion and 60-minute test suites. Use pure ASGI middleware instead:
```python
# WRONG — BaseHTTPMiddleware blocks under load
class MyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        ...

# RIGHT — Pure ASGI, zero overhead
class MyMiddleware:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # ... middleware logic ...
        await self.app(scope, receive, send)
```

**Throttle Redis TTL refreshes.** Refreshing TTL on every single socket event floods Redis. Use a per-SID counter and only refresh every N events (we use 50). This dropped Redis command volume dramatically.

**Use `selectinload()` on ORM queries that cross relationships.** Missing eager-loading causes N+1 query waterfalls. Particularly important for `Game.turns`, `Game.room`, and `Room.users`:
```python
select(Game).where(Game.id == game_id).options(
    selectinload(Game.turns), selectinload(Game.room)
)
```

### Backend — Undercover Game Logic

**Role distribution must guarantee at least 1 civilian.** The formula `num_undercover = max(2, num_players // 4)` with `num_mr_white = 1` gives 0 civilians for 3 players. Zero civilians triggers the undercover win condition immediately on reconnection (`get_undercover_state` → `get_winning_team()` → `num_alive_civilian == 0` → undercovers win).

**3-player games have no Mr. White.** Explicit rule: `if num_players == 3: num_mr_white=0, num_undercover=1, num_civilians=2`. The Mr. White role doesn't work with only 3 players.

**Win condition must be role-aware.** Only check Mr. White elimination in games that HAVE Mr. White:
```python
# WRONG — triggers false win in 3-player games with 0 Mr. White
if num_alive_mr_white == 0: return UNDERCOVER

# RIGHT — only check if the role exists in this game
if total_mr_white > 0 and num_alive_mr_white == 0: return UNDERCOVER
```

### Frontend — Socket.IO State Management

**`get_undercover_state` response overrides local phase.** The reconnection handler sets `phase` based on `turn_number` and `winner`, NOT based on the current local phase. This means if the frontend is showing the elimination screen (phase="elimination") and a socket reconnection triggers `get_undercover_state`, the response will set phase="playing" (because `turn_number > 0` and no winner), wiping the elimination screen. This is a known race condition — E2E tests must handle it.

**Track round changes to avoid resetting vote state.** Without `lastServerRoundRef`, the initial `undercover_game_state` response on mount resets `hasVoted` and `selectedVote`, clearing a vote the user just cast. Only reset vote state when the server round number actually changes.

### E2E — Playwright Selectors

**Never mix `text=` engine with CSS in comma-separated selectors.** Playwright's `text=` engine consumes the ENTIRE remaining string as the text to match, including commas. This is a silent failure — the selector matches nothing but doesn't error:
```typescript
// WRONG — searches for literal "Discuss and vote, h2:has-text("Game Over")"
page.locator('text=Discuss and vote, h2:has-text("Game Over")')

// RIGHT — use .or() for selector unions
page.locator('text=Discuss and vote')
  .or(page.locator('h2:has-text("Game Over")'))
```
This also applies to `"text=Voted, text=Waiting for other players"` — it does NOT match either text.

### E2E — Socket.IO Race Conditions

**The elimination screen can vanish before you interact with it.** After `player_eliminated` sets `phase="elimination"`, a socket reconnection can trigger `get_undercover_state` which resets `phase="playing"`. The "Next Round" button disappears. Tests must:
1. Check if "Next Round" is visible before clicking (with short timeout)
2. If not visible, skip the click — the page already transitioned
3. Reload players to get fresh state from the server

**`waitForEliminationOrGameOver` must check multiple indicators.** The skull icon (`.lucide-skull`) only appears on the elimination screen. If the screen is replaced, check the player list for "Eliminated" text as a fallback. The function now detects elimination via three signals: skull icon, Game Over heading, or "Eliminated" in the player list.

**Reloading a page during a game triggers `get_undercover_state`.** The frontend's `useEffect` on `isConnected` fires `get_undercover_state` on every reconnection. After reload, the page gets the server's current state, which may show a DIFFERENT phase than what was on screen before. This is by design for reconnection recovery, but it means tests can't rely on page state surviving a reload.

### E2E — Test Infrastructure

**Check the host player first when waiting for navigation.** `startGameViaUI` was checking players sequentially with 5s timeout each. With 5 players, the host (who clicks "Start Game") would navigate while the test was waiting on a different player. Fix: check host first with 10s timeout, then others with 3s as fallback.

**`flushRedis()` only runs in `test.beforeAll`, not between tests.** Tests within the same `describe` block share Redis state. Each test creates a fresh room via `setupRoomWithPlayers`, so old game state doesn't usually leak — but be aware of it for debugging.

**Never reload ALL players simultaneously in multi-player tests.** Mass reload disconnects all sockets at once. The backend processes all disconnect events, potentially canceling the game. Reload one player at a time, or at most reload alive players sequentially with socket reconnection waits between each.

**5-player tests are inherently more flaky than 3-player tests.** More socket connections = more chances for missed events, timing issues, and connection pool pressure. 5-player multi-round tests need extensive fallback logic (reload → check state → retry). Design tests to be resilient, not rigid.

### E2E — Resilience Patterns for Game Tests

**Always use `activePlayers` from `dismissRoleRevealAll()`, never `setup.players`.** `dismissRoleRevealAll()` returns only players confirmed on the game page. Using `setup.players` includes players whose pages may have disconnected under browser resource pressure. This was the root cause of the majority of flaky tests.

**Reconnect voters to the game page before voting.** A player may be redirected away from `/game/undercover/` during phase transitions. Before calling `voteForPlayer`, check if the voter is on the game page and navigate them back:
```typescript
for (const voter of activePlayers) {
  const pageAlive = await voter.page.evaluate(() => true).catch(() => false);
  if (!pageAlive) continue;

  if (!/\/game\/undercover\//.test(voter.page.url()) && gameUrl) {
    await voter.page.goto(gameUrl);
    await voter.page.waitForLoadState("domcontentloaded");
  }
  await voteForPlayer(voter.page, voteTarget);
}
```

**Find the observer page dynamically, don't fallback to `activePlayers[0]`.** After voting or waiting for results, find a player who is actually on the game page. If no player is on the game page, the game was cancelled — early return:
```typescript
const observerPage = activePlayers.find(
  (p) => /\/game\/undercover\//.test(p.page.url()),
)?.page;
if (!observerPage) return; // All redirected — game cancelled
```

**Check for early game over before proceeding with test actions.** Games can end during the describing phase if players disconnect. Always check before voting:
```typescript
const earlyOver = await player.page
  .locator("h2:has-text('Game Over')")
  .isVisible()
  .catch(() => false);
if (earlyOver) return;
```

**Never reload player pages during the describing phase.** Reloading causes `get_undercover_state` to fire, which may return broken state ("Players (0/0)") if the socket hasn't fully reconnected. Use `waitFor({ state: "attached" })` with longer timeouts instead of reload fallbacks.

**Disconnect grace period is 5s in E2E.** The `DISCONNECT_GRACE_PERIOD_SECONDS` env var in `docker-compose.e2e.yml` is set to 5. Tests that wait for disconnect effects (player removal, game cancellation) must wait at least 8s (5s grace + 3s processing buffer).

### Infrastructure — Docker & Deployment

**The CI/CD pipeline auto-deploys on push to `main`.** GitHub Actions detects which components changed (backend/frontend) and only rebuilds what's needed. The pipeline syncs code to the Dokploy VPS, builds Docker images, deploys, and runs health checks. No manual deploy needed for most changes.

**E2E docker-compose is separate from production.** `docker-compose.e2e.yml` runs the backend with `IBG_ENV=testing` and a dedicated Redis + Postgres. Never mix E2E and production compose files.

**Backend health check endpoint is `/health`.** The deploy pipeline polls this (6 attempts, 60s total) after deploy. If it fails, the pipeline logs backend container output for debugging.

## Games

### Undercover
- 3-12 players
- Roles: Civilian, Undercover, Mr. White
- Each player gets an Islamic term; undercover gets a different one
- Vote to eliminate the undercover agent

### Codenames
- 4-10 players, 2 teams (Red/Blue)
- Roles: Spymaster, Operative
- 5x5 board of Islamic terms
- Spymaster gives one-word clues, operatives guess

## Git Conventions

**CRITICAL: Never commit unless the user explicitly asks you to.** Do not auto-commit after completing work.

Use Conventional Commits with emojis:
- `feat(auth): ✨ add JWT refresh endpoint`
- `fix(game): 🐛 fix vote counting in undercover`
- `refactor(models): ♻️ migrate to async database`

**IMPORTANT**: Do NOT add `Co-Authored-By` lines or any AI attribution to commit messages.

## Test Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@test.com | admin123 |
| User | user@test.com | user1234 |
| Player | player@test.com | player123 |
