# CLAUDE.md - IPG (Islamic Party Games)

## Project Overview

IPG is a real-time multiplayer platform for Islamized versions of popular party games. Currently supports **Undercover** and **Codenames**, with plans for more games.

### Architecture

This is a **monorepo** with separate backend and frontend applications:

```
IPG/
├── backend/                    # Python/FastAPI (pure REST)
│   ├── ipg/
│   │   ├── api/               # REST API
│   │   │   ├── controllers/   # Business logic + game logic
│   │   │   ├── models/        # SQLModel DB tables
│   │   │   ├── schemas/       # Pydantic request/response + base classes
│   │   │   ├── routes/        # FastAPI routers
│   │   │   ├── services/      # External integrations
│   │   │   ├── constants.py   # All magic values
│   │   │   └── middleware.py  # Security, request ID, logging
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
│   │   ├── hooks/             # Custom hooks
│   │   ├── i18n/              # English + Arabic translations
│   │   ├── lib/               # Utilities (cn, auth)
│   │   ├── providers/         # Auth, Query, Theme providers
│   │   └── routes/            # TanStack Router file-based
│   ├── kubb.config.ts         # API codegen from OpenAPI
│   └── vite.config.ts
├── e2e/                       # Playwright E2E tests
├── docker-compose.yml         # Local dev (PostgreSQL)
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
| Backend | FastAPI, SQLModel, SQLAlchemy (async) |
| Database | PostgreSQL (prod), SQLite (dev) |
| Game State | PostgreSQL JSON column (`Game.live_state`) |
| Auth | JWT (python-jose, bcrypt) |
| Frontend | React 19, TanStack Router/Query, Tailwind v4, shadcn/ui |
| Real-time | TanStack Query polling (2s interval) |
| API Codegen | Kubb (OpenAPI -> React Query hooks) |
| i18n | i18next (English + Arabic) |
| Testing | pytest (backend), Vitest (frontend) |
| CI/CD | GitHub Actions |
| Deployment | Docker + Dokploy (Oracle VPS) |

## Coding Standards

### ⛔ MANDATORY — Zero Tolerance for Test Failures ⛔

**THIS RULE CANNOT BE BYPASSED, FORGOTTEN, OR IGNORED UNDER ANY CIRCUMSTANCES.**

**ABSOLUTE RULE: If ANY test is failing, flaky, or has ANYTHING wrong — YOU MUST FIX IT. Period.**

This is the single most important rule in this entire project. It overrides everything else. No exceptions, no excuses, no "it's pre-existing", no "it's not related to my changes". If you see a broken or flaky test, **YOU FIX IT RIGHT NOW** before doing anything else.

A task is NEVER complete until the ENTIRE test suite passes with:
- **0 failed tests**
- **0 flaky tests**
- **0 tests with any issue whatsoever**

**The E2E suite must pass 5 consecutive runs with 0 failures and 0 flaky.** Three runs is not enough — intermittent issues only surface under repeated execution. All 5 runs must be completely clean before a feature is considered done.

**What counts as broken:**
- A test that fails on any run
- A test that passes on retry (flaky) — "it passes on retry" is NOT acceptable
- A test that produces warnings about instability
- A test that only passes sometimes across multiple runs

**What you MUST do:**
1. Run the full test suite
2. If ANY test fails or is flaky → **STOP everything and fix it**
3. Re-run the full test suite **5 consecutive times** to confirm 0 failures and 0 flaky
4. Only then is the task complete

**What you MUST NOT do:**
- Do NOT report a task as done if any test is broken
- Do NOT say "this is a pre-existing flaky test" as an excuse to skip it
- Do NOT ask the user if it's acceptable — it's NOT
- Do NOT move on to other work while tests are broken
- Do NOT dismiss flaky tests as "timing issues" without fixing them
- Do NOT blame parallel execution, load, or infrastructure — make the tests resilient

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

**All imports must be at the top of the file.** Never place imports inside functions or methods, even for lazy loading. The only acceptable exception is to break circular imports involving Redis OM models (e.g., `ipg.socketio.models` ↔ `ipg.api.controllers`), and even then, add a comment explaining why.

```python
# Good - imports at the top
from loguru import logger
from sqlmodel import select

from ipg.api.models.table import User, Room
from ipg.api.schemas.error import NotFoundError

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
        from ipg.socketio.models.user import User as RedisUser
        ...
```

#### General Guidelines

- Use `def` for pure functions, `async def` for asynchronous operations
- Python 3.10+ type hints for all function signatures
- **CRITICAL: Always use the project's base classes from `ipg.api.schemas.shared`**, never `pydantic.BaseModel` or `sqlmodel.SQLModel` directly
- **No nested function definitions.** Do not define functions inside other functions. Extract inner logic into separate methods on the class or standalone module-level functions.
- Use descriptive variable names with auxiliary verbs (e.g., `is_active`, `has_permission`)
- Use lowercase with underscores for directories and files
- Store all magic values in `ipg/api/constants.py`

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
- **BaseModel/BaseTable**: All models inherit from `ipg.api.schemas.shared.BaseModel/BaseTable`
- **Enhanced Errors**: Auto i18n keys, auto-logging, `frontend_message` for UI
- **Multi-env Settings**: `IPG_ENV` selector (.env -> .env.{env})
- **Pure REST + Polling**: All game state via REST endpoints, TanStack Query polling for real-time updates (no WebSocket)
- **Game State in PostgreSQL**: `Game.live_state` JSON column stores full game state (previously Redis)
- **Heartbeat via polling**: `RoomUserLink.last_seen_at` updated on each GET request, background task detects disconnects
- **Kubb Codegen**: Auto-generated React Query hooks from FastAPI's OpenAPI spec

## Lessons Learned

### Backend — Game Logic

**All game state mutations use `asyncio.Lock` per game_id.** Vote submission, description submission, and disconnect handling ALL acquire the same lock. If you add a new game mutation endpoint, wrap it in `get_game_lock(str(game_id))`.

**Role distribution must guarantee at least 1 civilian.** 3-player games: `num_mr_white=0, num_undercover=1, num_civilians=2`. The Mr. White role doesn't work with only 3 players.

**Win condition must be role-aware.** Only check Mr. White elimination in games that HAVE Mr. White:
```python
if total_mr_white > 0 and num_alive_mr_white == 0: return UNDERCOVER
```

**Always call `flag_modified(game, "live_state")` after mutating `Game.live_state`.** SQLAlchemy doesn't detect in-place mutations to JSON columns. Without `flag_modified`, changes silently don't persist to the database:
```python
from sqlalchemy.orm.attributes import flag_modified
state = game.live_state
state["some_field"] = new_value  # In-place mutation
game.live_state = state  # Reassigning same object — SQLAlchemy won't detect this!
flag_modified(game, "live_state")  # REQUIRED to mark the column as dirty
session.add(game)
await session.commit()
```

**Use `selectinload()` on ORM queries that cross relationships.** Missing eager-loading causes N+1 query waterfalls.

**Never use `BaseHTTPMiddleware`.** Use pure ASGI middleware for zero-overhead request processing.

### Frontend — Polling Architecture

**Game state is derived from server via `useMemo`, not accumulated from events.** The `useQuery` hook polls every 2s, and all UI state is derived from the server response. No local state accumulation.

**Phase transitions detected by comparing refs to previous state.** `previousPhaseRef` and `previousRoundRef` track changes between polling cycles to trigger animations (e.g., voting transition overlay).

**`refetchOnWindowFocus: true` for game pages.** When user returns to tab, game state refreshes immediately.

### E2E — Playwright

**Never mix `text=` engine with CSS in comma-separated selectors.** Use `.or()` for selector unions:
```typescript
page.locator('text=Discuss and vote')
  .or(page.locator('h2:has-text("Game Over")'))
```

**Use specific element selectors to avoid strict mode violations.** `text=Describe your word` can match multiple elements (heading + label). Use `h2:has-text("Describe your word")` to target one element.

**Always use `activePlayers` from `dismissRoleRevealAll()`, never `setup.players`.** Only players confirmed on the game page should be used for game interactions.

**Always call `verifyAllPlayersVoted()` after every voting loop.** Clicks can silently fail under load.

**Always use `isPageAlive(page)` before interacting with a player page.**

### Infrastructure

**The CI/CD pipeline auto-deploys on push to `main`.** GitHub Actions detects which components changed and only rebuilds what's needed.

**E2E docker-compose is separate from production.** `docker-compose.e2e.yml` runs the backend with `IPG_ENV=development` and a dedicated PostgreSQL. Never mix E2E and production compose files.

**Backend health check endpoint is `/health`.**

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
