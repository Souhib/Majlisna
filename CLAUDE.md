# CLAUDE.md - Majlisna (Islamic Party Games)

## Project Overview

**Majlisna** (`majlisna.app`) is a real-time multiplayer platform for Islamized versions of popular party games. Currently supports **Undercover** and **Codenames**, with plans for more games.

### Architecture

This is a **monorepo** with separate backend and frontend applications:

```
IPG/
├── backend/                    # Python/FastAPI (REST + Socket.IO)
│   ├── ipg/
│   │   ├── api/               # REST API + WebSocket
│   │   │   ├── controllers/   # Business logic + game logic
│   │   │   ├── models/        # SQLModel DB tables
│   │   │   ├── schemas/       # Pydantic request/response + base classes
│   │   │   ├── routes/        # FastAPI routers (trigger notify after mutations)
│   │   │   ├── ws/            # Socket.IO server, handlers, notify, state
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
│   │   ├── i18n/              # English + Arabic + French translations
│   │   ├── lib/               # Utilities (cn, auth)
│   │   ├── providers/         # Auth, Query, Theme providers
│   │   └── routes/            # TanStack Router file-based
│   ├── kubb.config.ts         # API codegen from OpenAPI
│   └── vite.config.ts
├── e2e/                       # Playwright E2E tests
├── docker-compose.yml         # Local dev (PostgreSQL)
├── docker-compose.dokploy.yml # Production (Oracle VPS, Traefik labels)
└── .github/workflows/         # CI (lint/test on ubuntu-latest; Dokploy handles CD)
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
uv run python main.py                    # http://localhost:5111

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

# Production deployment (Dokploy) — usually handled by CI/CD
docker compose -f docker-compose.dokploy.yml up -d
```

### Production URLs

- **Frontend**: https://majlisna.app
- **Backend API**: https://majlisna.app/api/v1/ or https://api.majlisna.app/api/v1/
- **Health check**: https://majlisna.app/health
- **API docs**: https://majlisna.app/scalar
- **OpenAPI spec**: https://majlisna.app/openapi.json

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLModel, SQLAlchemy (async) |
| Database | PostgreSQL (prod), SQLite (dev) |
| Game State | PostgreSQL JSON column (`Game.live_state`) |
| Auth | JWT (python-jose, bcrypt) |
| Frontend | React 19, TanStack Router/Query, Tailwind v4, shadcn/ui |
| Real-time | Socket.IO (python-socketio + socket.io-client) — notification layer over REST |
| Infra | PgBouncer (connection pooling), Redis (Socket.IO pub/sub only) |
| Monitoring | Umami (`analytics.majlisna.app`), GlitchTip (`glitchtip.majlisna.app`), Uptime Kuma (`kuma.majlisna.app`), Dozzle (`dozzle.majlisna.app`) |
| Security | Trivy (CI vulnerability scanning) |
| API Codegen | Kubb (OpenAPI -> React Query hooks) |
| i18n | i18next (English + Arabic + French) |
| Testing | pytest (backend, 587+ tests), Vitest (frontend, 166 tests), Playwright (E2E, 145 tests) |
| CI/CD | GitHub Actions |
| Deployment | Docker + Dokploy (Oracle VPS) |
| Domain | `majlisna.app` (Cloudflare DNS + proxy) |
| SSL | Cloudflare Flexible (CF terminates HTTPS, HTTP to origin) |
| Reverse Proxy | Traefik (managed by Dokploy, routes via Docker labels) |

## Coding Standards

### ⛔ MANDATORY — Zero Tolerance for Test Failures ⛔

**THIS RULE CANNOT BE BYPASSED, FORGOTTEN, OR IGNORED UNDER ANY CIRCUMSTANCES.**

**ABSOLUTE RULE: If ANY test is failing, flaky, or has ANYTHING wrong — YOU MUST FIX IT. Period.**

This is the single most important rule in this entire project. It overrides everything else. No exceptions, no excuses, no "it's pre-existing", no "it's not related to my changes". If you see a broken or flaky test, **YOU FIX IT RIGHT NOW** before doing anything else.

A task is NEVER complete until the ENTIRE test suite passes with:
- **0 failed tests**
- **0 flaky tests**
- **0 tests with any issue whatsoever**
- **Backend tests MUST be run with `--use-postgres` flag** (`uv run pytest --use-postgres`). The default SQLite mode skips PostgreSQL-specific tests (advisory locks, etc.). You cannot declare backend tests as passing unless they were run with this flag. Note: `uv run poe test` does NOT forward extra args — use `uv run pytest --use-postgres` directly.

**The E2E suite must pass 3 consecutive runs with 0 failures and 0 flaky.** Intermittent issues only surface under repeated execution. All 3 runs must be completely clean before a feature is considered done.

**What counts as broken:**
- A test that fails on any run
- A test that passes on retry (flaky) — "it passes on retry" is NOT acceptable
- A test that produces warnings about instability
- A test that only passes sometimes across multiple runs

**What you MUST do:**
1. Run the full test suite
2. If ANY test fails or is flaky → **STOP everything and fix it**
3. Re-run the full test suite **3 consecutive times** to confirm 0 failures and 0 flaky
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
# (API routes, controllers, game components, rooms, auth, shared state)
# Only skip for purely cosmetic/unrelated pages (e.g. About page, static content)
cd e2e && npx playwright test
```

**CRITICAL: E2E tests are NOT optional.** Any change to backend controllers, API routes, game logic, room management, auth flow, or frontend components that interact with the backend MUST be followed by a full E2E run. The E2E suite is the final safety net — unit tests and linters alone are not sufficient to catch integration regressions.

Do not consider a task complete until ALL tests pass with zero failures AND zero flaky tests — whether or not the failures appear related to your changes. A flaky test is still a failing test. If a pre-existing flaky test blocks completion, fix it before moving on.

### Debugging Test Failures

**NEVER use `git stash` to check if a test failure is pre-existing.** When tests fail after your changes, investigate the failure directly:
1. Read the error message and traceback carefully
2. Check the test code and the code it's testing
3. Determine if your changes caused the failure or if it's unrelated
4. Fix the issue — don't try to prove it's "not your fault" by stashing

### No Retries as Fixes

**NEVER add retries, reloads, or try/catch-and-retry to "fix" a failing test or flaky behavior.** Retries mask the real problem and create silent bugs that surface later in production or in harder-to-debug scenarios.

When something fails or is flaky:
1. **Understand the root cause deeply** — read error messages, check state, trace the flow
2. **Fix the actual problem** — wrong selector, race condition, missing wait, incorrect data
3. **Never wrap a failure in a retry loop** and call it done — that's hiding the bug, not fixing it
4. **If a wait/timeout is genuinely too short**, increasing it is fine — but only after confirming the underlying logic is correct and the timeout is the only issue
5. **If you must add resilience** (e.g., page reload), it must be justified, logged visibly (`console.warn`), and still fail hard if the retry doesn't resolve it — never swallow errors silently

### Python/FastAPI Guidelines

#### Import Organization

**All imports must be at the top of the file.** Never place imports inside functions or methods, even for lazy loading.

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
- No external services to mock — game locks use in-process `asyncio.Lock`

### Root-Cause-First Testing Philosophy

When a test fails, the goal is NEVER to make the test pass — it's to have a working app.

**Process**:
1. **Understand the failure deeply** — read error messages, check screenshots, trace the data flow
2. **Identify multiple possible root causes** — don't jump to the first theory
3. **Fix the application, not the test** — if the frontend crashes, fix the frontend. If the backend returns bad data, fix the backend. The test is correct if it exposes a real bug.
4. **Never add workarounds to tests** — no page reloads to recover from crashes, no `force: true` clicks, no retry loops around flaky operations, no `.catch(() => {})` to swallow errors
5. **If the test itself has a bug** (wrong selector, missing wait, logic error), fix the test — but verify the app works first

## Key Patterns

- **Route -> Controller -> Model**: No business logic in routes
- **Async Everything**: All DB operations and external calls are async
- **Dependency Injection**: FastAPI's `Depends()` with `Annotated` type hints
- **BaseModel/BaseTable**: All models inherit from `ipg.api.schemas.shared.BaseModel/BaseTable`
- **Enhanced Errors**: Auto i18n keys, auto-logging, `frontend_message` for UI
- **Multi-env Settings**: `IPG_ENV` selector (.env -> .env.{env})
- **REST + Socket.IO Notifications**: Mutations go through REST. Socket.IO pushes state updates to clients after mutations. PostgreSQL is the ONLY source of truth — Redis is ONLY for Socket.IO cross-worker pub/sub (ephemeral, no game data).
- **Game State in PostgreSQL**: `Game.live_state` JSON column stores full game state
- **Manual kick**: Host can kick players from room; no auto-disconnect
- **Lobby disconnect tolerance**: Players in rooms without an active game are NEVER auto-removed (mobile users background tabs constantly). They are marked `connected=False` but their `RoomUserLink` is preserved. Only rooms with an active game enforce the 180s grace period for permanent removal. The host can manually kick idle players.
- **Kubb Codegen**: Auto-generated React Query hooks from FastAPI's OpenAPI spec
- **Spectator Mode**: Users can join rooms as spectators (`RoomUserLink.is_spectator`). Spectators see sanitized game state (no roles/words until game over), read-only UI with no action buttons.
- **Friend Invites**: Room hosts can invite friends via `POST /api/v1/rooms/{id}/invite`. Socket.IO personal rooms (`user:{user_id}`) deliver real-time invite notifications.
- **Game History**: `GET /api/v1/games/{id}/summary` returns typed `GameSummary` with `VoteRound`, `ClueHistoryEntry`, player roles, and word explanations.
- **Caching**: `ipg.api.utils.cache.TTLCache` caches undercover words/term pairs, codenames word packs, and user stats. Tests use autouse `clear_cache` fixture.
- **PWA**: Manifest + service worker for installable web app with offline navigation shell.
- **Pre-commit**: `prek` hooks run ruff lint/format + mypy on commit.
- **BaseGameController**: All 4 game controllers inherit from `ipg.api.controllers.base_game.BaseGameController`, which provides shared methods: `_get_game`, `_check_is_host`, `_update_heartbeat_throttled`, `_check_spectator`, `_resolve_multilingual`. Game-specific logic stays in each subclass.
- **Room Share Links**: `GET /api/v1/rooms/{id}/share-link` returns `public_id` + `password`. Frontend constructs URL `majlisna.app/rooms/join?code=X&pin=Y`. The `/rooms/join` route auto-joins via `useEffect` with the join mutation.
- **Shared Quiz Components**: `PlayerScoreboard` and `QuizGameOver` in `components/games/shared/` are used by both Word Quiz and MCQ Quiz. Game-specific i18n keys passed via props.
- **Google OAuth**: "Continue with Google" on login/register pages. Frontend uses `@react-oauth/google` (`useGoogleLogin` hook → access token). Backend `POST /api/v1/auth/social/login` verifies via Google userinfo API, creates/links user, returns JWT pair. User model has `google_sub`, `auth_provider`, `profile_picture_url` fields. Social users get a sentinel password and cannot use password login. GCP project: same as Latabdhir (`<REDACTED_GCP_PROJECT_ID>`), OAuth client: "Majlisna Web". Env vars: `GOOGLE_CLIENT_ID_WEB` (backend), `VITE_GOOGLE_CLIENT_ID` (frontend).

## Lessons Learned

### Backend — Game Logic

**`get_room_state()` includes ALL room members, not just connected ones.** The room state query must NOT filter by `connected == True`. Players who briefly disconnect (Socket.IO reconnection) must still appear in the player list. In the lobby (no active game), disconnected players are NEVER auto-removed — only the host can kick them. During active games, players are permanently removed after 180s grace period. Filtering by connection status causes the player count to flicker during brief disconnections, breaking game start flows.

**All game state mutations use `get_game_lock(game_id, session)`.** This uses PostgreSQL **transaction-level** advisory locks (`pg_try_advisory_xact_lock`) in production — they auto-release on commit/rollback, preventing lock leaks. Falls back to in-process `asyncio.Lock` for SQLite (tests). Vote submission, description submission, and disconnect handling ALL acquire the same lock. If you add a new game mutation endpoint, wrap it in `get_game_lock(str(game_id), self.session)`. **Never use session-level advisory locks** (`pg_advisory_lock`) — they leak when connections are recycled by the pool.

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

**Always use timezone-aware timestamps for values sent to the frontend.** Use `datetime.now(UTC).isoformat()` (produces `+00:00` suffix) instead of `datetime.now().isoformat()` (naive). JavaScript's `new Date()` interprets naive ISO strings as local time, causing clock skew between Docker containers (UTC) and browsers (local timezone).

**Never use Pydantic v1 `class Config: json_encoders` in models.** Pydantic v2 serializes UUIDs to strings by default. The v1 `json_encoders = {UUID: str}` pattern creates `FieldInfoMetadata` objects that are unhashable, crashing FastAPI's OpenAPI schema generation with `TypeError: unhashable type: 'FieldInfoMetadata'`.

**Always type response schemas fully — no `list[dict]` or `dict`.** Create proper Pydantic models for all nested structures (e.g., `VoteRound`, `ClueHistoryEntry`). Untyped dicts can cause Pydantic schema generation issues and produce useless OpenAPI/Kubb types.

**Dev backend runs on port 5111 to avoid macOS AirPlay conflict on port 5000.** Configured via `PORT=5111` in `.env.development`. Docker containers still use 5000 internally (no AirPlay conflict inside containers).

### Frontend — Socket.IO + TanStack Query

**Socket.IO pushes state into TanStack Query cache via `queryClient.setQueryData()`.** The `useSocket` hook connects to Socket.IO, receives `room_state` and `game_state` events, and writes them directly into the query cache. It returns `{ connected }` so consumers can disable polling when connected. All pages (game pages and room lobby) use `refetchInterval: socketConnected ? false : 2_000` — zero polling when Socket.IO is up, fast 2s fallback when disconnected.

**Game pages get roomId from SessionStorage for instant Socket.IO connection.** The room lobby stores `roomId` via `storeRoomIdForGame()` before navigating. Game pages read it via `retrieveRoomIdForGame()` in a lazy `useState` initializer, avoiding the ~2s delay of waiting for the first REST poll. Falls back to REST-provided roomId on page refresh.

**Game state is derived from server via `useMemo`, not accumulated from events.** All UI state is derived from the server response (whether from Socket.IO push or initial fetch). No local state accumulation.

**Phase transitions detected by comparing refs to previous state.** `previousPhaseRef` and `previousRoundRef` track changes to trigger animations (e.g., voting transition overlay).

**Socket.IO is a NOTIFICATION LAYER, not a game engine.** Mutations go through REST POST. Route handlers **await** Socket.IO notifications so events are guaranteed to be emitted before the HTTP response returns. Game start routes call `await auto_join_game_room()` to pre-join all room members into the game's Socket.IO room, eliminating the race condition where `game_updated` fires before clients call `join_game`. The client's `useSocket` hook invalidates queries on reconnect to catch up on any events missed during disconnection.

**`sio.enter_room()` MUST be awaited.** It is an async coroutine in python-socketio. Calling without `await` silently fails — the SID never joins the room.

**Route handlers MUST `await notify_*()`, never `fire_notify_*()`** in route code. The `fire_*` variants are reserved for background tasks only (disconnect checker loop, Socket.IO event handlers).

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

**GitHub Actions = CI only** (on `ubuntu-latest`). On push to `main` or PR, the pipeline detects changed components and runs CI checks (lint, format, test) in parallel. No deploy job — CI is informational on push, blocking on PRs. Backend tests use SQLite (no `--use-postgres` in CI). No self-hosted runners needed for CI.

**Dokploy = CD.** Dokploy autodeploy is enabled — it pulls from `main` on every push, builds images, and runs `docker compose up -d`. Deploy does NOT wait for CI. This eliminates container conflicts (Dokploy owns all containers) and removes the need for rsync, health checks, orphan adoption, and image pruning in the pipeline.

**CI is a real quality gate for PRs.** No `continue-on-error` on any CI step. `cancel-in-progress: true` since there's no deploy to protect.

**E2E docker-compose is separate from production.** `docker-compose.e2e.yml` runs the backend with `IPG_ENV=development` and a dedicated PostgreSQL. Never mix E2E and production compose files.

**Backend health check endpoint is `/health`.**

**Production domain is `majlisna.app`.** Routing:
- `majlisna.app` → Frontend (Nginx serving React SPA)
- `majlisna.app/api/*`, `/socket.io/*`, `/health`, `/scalar`, `/openapi.json` → Backend (FastAPI)
- `api.majlisna.app` → Backend (alternative subdomain)

Cloudflare handles DNS (proxied/orange cloud) and SSL termination (Flexible mode — HTTPS to Cloudflare, HTTP to origin). Traefik on the server routes requests via Docker compose labels. `VITE_API_URL` is baked at frontend build time — rebuild frontend when changing it.

**Production server**: Oracle VPS at `<SERVER_IP>`, accessible via SSH as `ubuntu`. Dokploy compose project is named "IBG" (`<REDACTED_DOKPLOY_ID>`), connected to `Souhib/IBG` GitHub repo, branch `main`, compose path `./docker-compose.dokploy.yml`. Repo clone at `<REDACTED_SERVER_PATH>`.

**Redis is ephemeral and non-critical.** Redis is only used for Socket.IO cross-worker pub/sub. If Redis is down, the app works but Socket.IO won't broadcast across workers. The CI pipeline treats Redis health as a non-blocking warning. If Redis crash-loops due to corrupt `dump.rdb`, delete the RDB file from the Docker volume and recreate the container.

**Monitoring tools** are deployed alongside the app:
- **Umami** (`analytics.majlisna.app`, port 31200): Privacy-focused web analytics. Own PostgreSQL database.
- **GlitchTip** (`glitchtip.majlisna.app`, port 31300): Error tracking and alerting (open-source Sentry alternative). Own PostgreSQL + Redis + Celery worker.
- **Dozzle** (`dozzle.majlisna.app`, port 31400): Real-time Docker log viewer. Zero storage, streams from Docker API. Use for quick debugging.
- **Uptime Kuma** (`kuma.majlisna.app`, port 31500): Uptime monitoring with alerting. Monitors endpoints, sends notifications on failures.
- **Trivy**: CI-only vulnerability scanner. Runs filesystem scan on PRs and container image scan post-build on deploy. Non-blocking (exit-code 0).

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

### Word Quiz (Kalimat)
- 1+ players (solo or group)
- Progressive hint system: 6 hints revealed every N seconds (vague → specific)
- Players type answers — faster = more points (hint 1 = 6pts, hint 6 = 1pt)
- Multiple rounds, highest score wins
- Answer matching: Arabic diacritics stripped, case-insensitive, whitespace-normalized
- Trilingual hints (EN, FR, AR) with `QuizWord` model

### MCQ Quiz
- 1+ players (solo or group)
- Multiple choice questions with 4 answer choices per question
- Configurable timer (default 15s) and number of rounds (default 10)
- One attempt per round — answer locks in on submit
- Simple scoring: correct = 1pt, wrong = 0pt
- Shows explanation after each round
- 200+ trilingual questions (EN, FR, AR) across 8 Islamic knowledge categories
- Prophet names use Arabic transliteration (e.g., "Yunus" not "Jonah")
- `McqQuestion` model with JSON columns for multilingual choices and explanations

### Hint System (All Games)
- Words have multilingual hints (JSON `hint` column: `{en, ar, fr}`)
- Hints shown via Info icon popover (HintButton component)
- Hint usage tracked in `live_state.hint_usage` for achievements
- `POST /games/{game_id}/hint-viewed` records unique word views
- Game over screen shows all word explanations
- `_resolve_hint(hint_dict, lang)` helper with fallback chain: exact lang → `en` → first value

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
