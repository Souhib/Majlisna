# CLAUDE.md - Majlisna

## Project Overview

**Majlisna** (`majlisna.app`) is a real-time multiplayer platform for Islamized versions of popular party games. Four games are live: **Undercover**, **Codenames**, **Kalimat** (Word Quiz) and **The Quiz** (MCQ), plus a daily solo puzzle, the **word of the day** (`/today`).

### Architecture

This is a **monorepo** with separate backend and frontend applications:

```
Majlisna/
├── backend/                    # Python/FastAPI (REST + Socket.IO)
│   ├── majlisna/
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
│   │   ├── database.py        # Async SQLAlchemy engine, the schema at boot
│   │   ├── schema.py          # Alembic at boot: migrate to head, adopt, refuse
│   │   ├── dependencies.py    # DI with Annotated + Depends
│   │   ├── settings.py        # Multi-env pydantic-settings
│   │   └── logger_config.py   # Structured Loguru logging
│   ├── migrations/            # Alembic (PostgreSQL): env.py, versions/ (alembic.ini beside)
│   ├── tests/
│   ├── scripts/               # Content seed (--seed), dev/E2E fake data, purge_seed_data.py
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
├── e2e/                       # Playwright E2E tests (+ docker-compose.e2e.yml, run-local.sh)
├── infrastructure/db-backups/ # Nightly encrypted pg_dump (Dagu), restore drill
├── docs/operations/           # Runbooks (backups.md)
├── docker-compose.yml         # Local dev (PostgreSQL)
├── docker-compose.dokploy.yml # Production (Oracle VPS, Traefik labels)
└── .github/workflows/         # CI (suites, then `promote` to the `production` branch; Dokploy deploys it)
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

# Game content only (safe everywhere, production included; upserts, no restart needed)
PYTHONPATH=. uv run python scripts/generate_fake_data.py --seed

# Fake data: dev and E2E databases ONLY. Production refuses both (exit 2), see
# Infrastructure → "Production data rules"
PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db
PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete

# Migrations (PostgreSQL only; the app runs them at boot). backend/CLAUDE.md, "Migrations (Alembic)"
export DATABASE_URL=postgresql+asyncpg://...     # a throwaway PostgreSQL 16
uv run alembic revision --autogenerate -m "add x to y"
uv run alembic upgrade head && uv run alembic check
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
| Migrations | Alembic, PostgreSQL only, run by the app at boot (SQLite keeps `create_all`); see `backend/CLAUDE.md`, "Migrations (Alembic)" |
| Game State | PostgreSQL JSON column (`Game.live_state`) |
| Auth | JWT (python-jose, bcrypt) |
| Frontend | React 19, TanStack Router/Query, Tailwind v4, Samar design system on Radix (`DESIGN.md`), self-hosted @fontsource fonts |
| Real-time | Socket.IO (python-socketio + socket.io-client) — notification layer over REST |
| Infra | PgBouncer (connection pooling), Redis (Socket.IO pub/sub and the rate-limit counters only; ephemeral) |
| Monitoring | Umami (analytics), Uptime Kuma (uptime), Dozzle (live logs), Beszel (host metrics), Bugsink (Sentry-compatible errors, projects `majlisna-backend` and `majlisna-front`), alerts in the owner's Discord (Majlisna category). Self-hosted, admin UIs reachable over Tailscale only (Infrastructure → "Admin tools"), hostnames in Claude Code memory |
| Security | Trivy in CI (lockfiles and the backend image; a fixable CRITICAL blocks the deploy), Dependabot; CrowdSec runs on the host but does not see the HTTP traffic yet (Infrastructure) |
| API Codegen | Kubb (OpenAPI -> React Query hooks) |
| i18n | i18next (English + Arabic + French) |
| Testing | pytest (backend), Vitest (frontend), Playwright (E2E). Counts move every week, so ask the tools: `cd backend && uv run pytest --collect-only -q --no-cov \| tail -1`, `cd front && bunx vitest list \| wc -l`, `cd e2e && bunx playwright test --list \| tail -1` |
| CI/CD | GitHub Actions |
| Deployment | Docker + Dokploy (Oracle VPS) |
| Domain | `majlisna.app` (Cloudflare DNS + proxy) |
| SSL | Cloudflare reaches the origin over HTTPS (mode Full, never Flexible: Traefik redirects plain HTTP to HTTPS, so Flexible would loop) |
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

**⛔ NEVER commit or push without running ALL tests first.** You MUST run the full backend suite (`uv run pytest --use-postgres`), the full frontend suite (`bun run test`) and, for any change to app logic, the E2E gate (`cd e2e && bun run gate`) BEFORE every commit. Running linters alone is NOT sufficient.

CI now gates the deploy (nothing reaches production until the suites are green), but it is still not a substitute for local verification: it runs the backend and frontend suites only — the E2E gate is local and authoritative — and a failure discovered in CI means a 13-minute round trip per attempt.

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
# Backend — run after any backend change (PostgreSQL: see the zero-tolerance rule above)
cd backend && uv run poe check && uv run pytest --use-postgres

# Frontend — run after any frontend change
cd front && bun run lint && bun run typecheck

# E2E — MANDATORY after any backend or frontend change that touches main logic
# (API routes, controllers, game components, rooms, auth, shared state)
# Only skip for purely cosmetic/unrelated pages (e.g. About page, static content)
cd e2e && bun run gate          # 3 consecutive clean runs — see "The E2E gate" below
```

### The E2E gate

**The local docker stack is the ONLY authoritative regression gate. Run it before
every push that touches app logic:**

```bash
cd e2e && bun run gate          # = ./run-local.sh -n 3
```

`run-local.sh` does the whole dance in one command, because doing it by hand is
five steps and skipping one gives a misleading result:

1. brings up the isolated stack (`docker-compose.e2e.yml`, loopback :5049/:3049),
2. waits for backend **and** frontend to answer,
3. runs Playwright N times, failing on the first unclean run; **each run reseeds the
   database first**, in one place only: `global-setup.ts` (`--delete`, `docker restart
   -t 1` of the disposable PgBouncer and backend, `--create-db`, a backend restart), so
   each run starts identical — a run against an unseeded DB fails on missing test
   accounts, which reads like a product bug. A failing step fails the run: there is no
   seed retry loop any more, and `run-local.sh` no longer seeds as well (it used to, so
   every run seeded twice; INFRA-19),
4. `--down` tears the stack back down.

Retries are OFF, locally and in CI (`retries: 0` in `playwright.config.ts`), so
a test that only passes on a second attempt is reported as a failure. That is the
intent: **a flaky test is a failing test.** Do not consider a task complete until
the gate is green — whether or not a failure looks related to your change. If a
pre-existing flake blocks you, fix it before moving on.

Handy narrower runs while iterating (then finish with the full gate):
`bun run test:local` (one run), `bun run test:rooms`, `bun run test:undercover`,
`bun run test:daily-word`, `./run-local.sh --no-build` (reuse images),
`./run-local.sh -- --grep "room join"`.

**Workers: `./run-local.sh -w N` (= `E2E_WORKERS=N`).** `playwright.config.ts` runs
`E2E_WORKERS` workers, 2 when unset; anything but a positive integer stops the run. CI
takes the repository variable `E2E_WORKERS` on the x86_64 home runner only
(`runner.arch == 'X64'` in the `e2e` job) and runs 2 on the one-core VPS runner whatever
the variable says. Measured on the home server, 2 November 2026, 3 clean runs each: 2
workers ≈ 10–12 min a run, 4 ≈ 6 min, 6 ≈ 4 min 40 s (4 min 54 s squeezed into the CI
slice's 8 CPUs), 8 ≈ 4 min 25 s. Past 6 it barely moves: the floor is the seed (~40 s)
plus the two `disconnect-during-game` tests, which wait out the real 180 s grace. That is
why the `websocket` project comes FIRST in the config: seventh, they started 2.5 min into
a run and the other workers idled through their last 1.7 min (6 workers: 6 min 12 s →
4 min 40 s). A spec must hold at any worker count: its own accounts
(`generateTestAccounts`), rooms and codes, never a seeded account's seat or password, and
a page closed to make a seat away only once its room socket is in (`invite.spec.ts`,
`watchRoomState`). Every Playwright request to the API sends `NO_SOCKET_REUSE`
(`helpers/api-client.ts`): the worker's shared keep-alive agent reused a socket uvicorn had
just closed and a sign-in failed with "socket hang up", the race `apiFetch` already avoids.

**CI runs the same script, and it BLOCKS the deploy.** The `e2e` job in
`.github/workflows/pipeline.yml` calls this very `run-local.sh` with `CI=true`, and
`promote` lists it in `needs` — so nothing reaches production until the browser
suite is green. Two consequences worth knowing:

- The job lives in `pipeline.yml`, not its own workflow file, because `needs`
  cannot reference a job in another workflow. That is the only way to make it
  actually block. (There used to be a separate `e2e.yml`; it was merged in.)
- Because CI executes the same script, **editing `run-local.sh` changes what gates
  production.** It is not a local-only convenience.

It costs little wall-clock: `e2e` runs in parallel with `backend`, on a different
runner, so the deploy waits for max(backend, e2e) rather than their sum.

**Runner isolation (18 September 2026).** E2E remains on the existing VPS by
owner preference, using the `ci-majlisna` account and its own rootless Docker daemon.
The runner has no sudo, host Docker access, or access to Dokploy's files; egress to
private/admin/metadata networks is denied. Its user slice limits CPU to one core
and memory to 4 GiB, including containers. Browser OS libraries are installed by
an administrator; CI only installs the Playwright browser. The `isolated-rootless`
label prevents scheduling onto an old privileged runner. The kernel is shared,
and runner state persists between jobs: this is not VM isolation. Keep fork workflow
approval enabled and do not grant this account production credentials.

**Second runner on the owner's home server (2 November 2026, owner decision).**
`ci-majlisna-home` (labels `isolated-rootless,home-x64`) on `lgf` (x86_64, 12 cores),
the machine LaTabdhir's CI already uses: same model (account `ci-majlisna`, no sudo, its
own rootless Docker, an egress chain refusing the home network and the tailnet, a slice
of 8 cores and 16 GiB), installed by `infrastructure/home-ci/` (README there). The E2E job
runs where the repository variable `E2E_RUNS_ON` says: `["self-hosted","home-x64"]` now,
the home server; delete the variable when that server is down, or the job waits for it.
A developer gate run on that host while a CI job runs collides on ports 3049/5049.

**E2E is the layer that catches what nothing else can.** The audit of 2026-07-25
found room join/leave returning 422 for every client: the request schemas had
dropped `user_id` while the frontend still sent it, and `BaseModel` is
`extra="forbid"`. Backend tests missed it (they call controllers directly, never
the route's Pydantic validation) and `tsc` missed it (the generated Kubb client
was stale). Only a browser run through the real stack failed.

### CI Must Pass After Every Push

**After every `git push`, check that CI passes.** Use `gh run list --repo Souhib/Majlisna --workflow=pipeline.yml --limit 1` to find the run, then `gh run watch <run-id> --repo Souhib/Majlisna` to wait for completion.

A red CI can no longer ship: Dokploy watches the **`production`** branch, and only
the `promote` job advances it, after the suites are green (see Infrastructure →
"GitHub Actions gates the deploy"). So a failure leaves `main` untested-but-not-live
rather than broken-in-production. Fix it anyway — until it is green, nothing you
pushed has reached production, and it is easy to assume otherwise.

Two more things a green run does NOT mean: a suite that failed and passed on a re-run does
not deploy (`promote` refuses a run whose backend, frontend or e2e failed in an earlier
attempt: dispatch a fresh run instead), and a successful `promote` is not a live deploy until
`/health` answers the promoted commit (see Infrastructure → "`promote` can wait for the deploy
to go live").

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

from majlisna.api.models.table import User, Room
from majlisna.api.schemas.error import NotFoundError

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
- **CRITICAL: Prefer Pydantic models over raw `dict` for structured data.** Controller/service inputs and outputs, request/response bodies, and nested structures should be typed models (`BaseModel`/`BaseTable`), never bare `dict`/`list[dict]`. The few legitimate exceptions: an in-process lookup map (e.g. `{achievement_id: count}`), a generic JSON helper, or an inherently-unstructured third-party API response (e.g. Google's `userinfo` JSON). Note the deliberate exception of `Game.live_state`, which is a JSON dict by design — but everything crossing an API boundary must still be typed.
- **CRITICAL: Always use the project's base classes from `majlisna.api.schemas.shared`**, never `pydantic.BaseModel` or `sqlmodel.SQLModel` directly
- **No nested function definitions.** Do not define functions inside other functions. Extract inner logic into separate methods on the class or standalone module-level functions.
- **Check library docs via Context7 before implementing against an external library/SDK** (Stripe, Resend, google APIs, python-socketio, etc.). Use `resolve-library-id` then `get-library-docs` rather than guessing API signatures — SDKs change and guesses cause silent breakage.
- Use descriptive variable names with auxiliary verbs (e.g., `is_active`, `has_permission`)
- Use lowercase with underscores for directories and files
- Store all magic values in `majlisna/api/constants.py`

#### Performance & the event loop

- **Never block the event loop with synchronous I/O.** All DB and external calls must be `await`ed async. If a dependency only exposes a blocking call (e.g. the Resend SDK's `Emails.send`), wrap it in `await asyncio.to_thread(...)` — a blocking call in an `async def` stalls every other request on that worker.
- **Avoid N+1 queries.** Never issue one query per item in a loop; use a single `GROUP BY`/aggregate or `selectinload()` across the set. (e.g. achievement rarity is one grouped `COUNT`, not one `COUNT` per definition.)

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
- **No test may mock away the check it claims to test.** Every older auth test mocked
  `decode_token`, so deleting its `expected_type` check passed the whole suite (TQ-01). Each
  security rule keeps at least one test on real tokens or a real HTTP transport: the token
  type and both claims (`tests/api/routes/test_wp00_token_type.py`,
  `tests/api/ws/test_wp00_socket_auth.py`), Google's `aud`/`azp` through `httpx.MockTransport`
  (`tests/api/services/test_social_auth_service.py`), sessions over HTTP and sockets
  (`test_wp17_sessions.py`). **Every authorization rule has a negative test**: host-only kick,
  start and rematch, and friendship and membership on invite (`test_host_only_rules.py`);
  membership on hint-viewed and timer-expired (`test_hint_viewed_by_a_stranger_is_refused`,
  `test_timer_expired_by_a_stranger_is_refused` and their Codenames and quiz twins).
- **A feature the UI shows needs a test that drives it through the real game-end path.**
  Challenges were linked from the nav while `check_progress` had no caller, and 12
  achievements were bound to counters nothing wrote. `test_wp03_specials.py`
  (`test_every_stat_field_an_achievement_reads_has_a_writer`,
  `test_every_special_code_has_a_rule_and_every_rule_a_special_code`) must stay green whenever
  an achievement or a stat is added.
- Test passwords hash at bcrypt cost 4 (autouse `cheap_bcrypt`); mark a test `real_bcrypt` to get production's 12. A test gets a database only by asking for `session` or `engine`; with `--use-postgres` the schema is created once per session and emptied by one `TRUNCATE … RESTART IDENTITY CASCADE` after each test that used it (`backend/CLAUDE.md`, "The test fixtures")

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
- **BaseModel/BaseTable**: All models inherit from `majlisna.api.schemas.shared.BaseModel/BaseTable`
- **Enhanced Errors**: Auto i18n keys, auto-logging, `frontend_message` for UI
- **Multi-env Settings**: `MAJLISNA_ENV` selector (.env -> .env.{env})
- **REST + Socket.IO Notifications**: Mutations go through REST. Socket.IO pushes state updates to clients after mutations. PostgreSQL is the ONLY source of truth — Redis is ONLY for Socket.IO cross-worker pub/sub and the slowapi rate-limit counters (ephemeral, no game data).
- **Game State in PostgreSQL**: `Game.live_state` JSON column stores full game state
- **Manual kick, which is a ban** (owner rule (c)): Host can kick players from room; no auto-disconnect. A kick BANS the player from that room for its lifetime (`RoomBan`; join and spectate answer 403 `errors.api.roomBanned`) and rotates the room PIN; the host lists and lifts bans with `GET /api/v1/rooms/{id}/bans` and `DELETE /api/v1/rooms/{id}/bans/{user_id}` (lifting does not re-seat or restore the old PIN). In the lobby the host confirms a kick in a dialog that says the player cannot come back, and lifts bans from `RoomBans` under the roster (`front/CLAUDE.md`, "The lobby"). A user connected in one ACTIVE room cannot join, spectate or create another (409 `errors.api.userAlreadyInRoom`). Join, spectate and invite are rate-limited per user. Tests: `tests/api/controllers/test_wp07_room_bans.py`, `e2e/tests/rooms/kick-ban.spec.ts`, `join-while-seated.spec.ts`.
- **Leavers get neither a win nor a loss, in all four games** (owner rule (b)). Every departure — leaving, a kick, the grace sweep, account deletion — calls `utils/game_state.mark_player_left` (`live_state[LEFT_PLAYER_IDS_KEY]`); `game_end_stats.scorable_players` skips those ids, so a leaver gets no stats, no achievement and no challenge progress, and `stats.did_user_win` answers `None` (no Won/Lost chip, skipped by the chart and head-to-head). An Undercover drop-out stays dead in `players` and never shares the win. Tests: `test_every_departure_marks_the_player_as_a_leaver` (`test_disconnect.py`, four games), `test_wp00_contracts.py`, `e2e/tests/stats/leaver.spec.ts`.
- **One winner resolver.** `record_game_end` persists `live_state["winner_ids"]` (`WINNER_IDS_KEY`) for every game type; stats, history (`user_won`), the profile chart and head-to-head all read it through `stats.did_user_win(game, user_id) -> bool | None`. A solo game is never a win, and quiz ties and 0-0 games follow the rule in Games → Word Quiz. Tests: `test_game_end_stats.py`, `test_stats.py`, `tests/api/routes/test_stats.py::test_a_twelve_player_mcq_won_by_the_host_reads_as_a_win_everywhere`.
- **A room that lets go of its game cancels it.** Deleting a room, every rematch, and a departure that leaves nobody connected end the room's IN_PROGRESS game through `game_cancel.cancel_running_game` (CANCELLED, `end_time`, pause cleared) under the game lock; the sweep also cancels games already orphaned. Once a room no longer points at a game nothing else can ever end it, so it must not be left running. Every finish path lets go of the room only through `detach_room_if_current` (only when the room still points at THIS game). Tests: `test_room.py::test_deleting_a_room_mid_game_cancels_its_game`, `::test_a_rematch_cancels_the_running_game`, `test_disconnect.py::test_the_last_connected_member_leaving_cancels_the_running_game`, `test_game_cancel.py`, `e2e/tests/rooms/room-rematch.spec.ts`.
- **Challenges progress at every game end, and the five special achievements are computed from the final `live_state`** (owner rules (f), (g)): `record_game_end` assigns the missing daily/weekly challenges and checks their progress for every scorable player, and unlocks `perfect_undercover`, `unanimous_vote`, `last_survivor`, `sweep_victory` and `assassin_finder` through `SPECIAL_ACHIEVEMENT_RULES` (each rule is spelled out in `backend/CLAUDE.md`, "The end-of-game flow"). Codenames keeps `live_state["reveal_log"]` for the last two. Tests: `test_wp03_specials.py`, `test_game_end_stats.py`, `e2e/tests/challenges/challenges.spec.ts`.
- **Leaving or being kicked mid-game reaches the game pages**: `leave_room` / `kick_player` routes call `notify_member_removed` (game_updated + room_state when the room has a running game); a room_state alone left the table on a stale game.
- **The host's game pick is the room's**: `RoomSettingsRequest.game_type` stores it in `Room.settings`, so every member's lobby describes the game the host chose.
- **Lobby disconnect tolerance**: Players in rooms without an active game have a 10-minute grace period (`LOBBY_GRACE_PERIOD_SECONDS = 600`) before auto-removal. They are marked `connected=False` but their `RoomUserLink` is preserved during the grace period. Rooms with an active game enforce a shorter 180s grace period. The host can manually kick idle players at any time. `RoomPlayerState.away_seconds_left` is the server-computed countdown ("away · 9:58"; null while connected), from the same grace rule as the sweep and the deliberately naive `RoomUserLink` timestamps. A player who comes back (socket reconnect, heartbeat, `join_game`, or a REST poll) is announced to the room at once (`HeartbeatResult.RESTORED` → `room_state`). The sweep runs in ONE worker per tick (`pg_try_advisory_xact_lock(DISCONNECT_SWEEP_LOCK_KEY)`), while every worker cuts its own sockets whose seat is gone or banned, or whose session has ended, each tick (`audit_local_socket_memberships`). A room counts as empty — deactivated, its running game cancelled — only when no seat is connected or inside its grace (review R1: it counted the connected ones only, and a sweep while phones were locked cancelled the game for players still seated). The room state (it carries the PIN) is addressed to each listed member's own channel (`member:{room_id}:{user_id}`), never to `room:{id}`, so a kicked socket on another worker never hears the new PIN (review R2). See `backend/CLAUDE.md`, "Departures, the sweep and the sockets".
- **Kubb Codegen**: Auto-generated React Query hooks from FastAPI's OpenAPI spec
- **Spectator Mode**: Users can join rooms as spectators (`RoomUserLink.is_spectator`). Spectators see sanitized game state (no roles/words until game over), read-only UI with no action buttons.
- **Friend Invites**: A member seated in the room invites a friend via `POST /api/v1/rooms/{id}/invite`, which STORES the invite (`RoomInvite`, table `room_invite`, migration `0002_room_invite`): one live invite per (room, invitee), and re-inviting refreshes it (same id, the latest inviter, `ROOM_INVITE_LIFETIME_MINUTES` = 30 again). An invite never carries the PIN: the friend accepts it by id, `POST /api/v1/rooms/invites/{invite_id}/accept`, which seats them WITHOUT the PIN through the join path (theirs, else 404 `roomInviteNotFound`; not expired, else 410 `roomInviteExpired`; the room ACTIVE; not banned, else 403 `roomBanned`; not seated elsewhere, else 409 `userAlreadyInRoom`), rate-limited per user like a join (one bucket whatever invite id the path names: `ROOM_INVITE_ACCEPT_RATE_LIMIT_SCOPE`), and notifies the room like a join. So an invite sent before a kick (which rotates the PIN) still opens the room, and a kicked player's old invite does not. The invites the kicked player SENT to that room die with the kick (deleted in its commit): an invite needs no PIN, so it is the other thing they handed out, and their friend's strip answers 404. Taking a player's seat in the room (an accepted invite, or a join with the code and PIN) spends the invites to it. `GET /api/v1/rooms/invites` lists the caller's live invites (the strip shows one sent while the page was closed). Account deletion, closing a room and the seed purge delete invites (no FK has ON DELETE). Socket.IO personal rooms (`user:{user_id}`) deliver real-time invite notifications (`room_invite` = `RoomInviteView` `{id, room_id, public_id, invited_by, expires_at}`): every signed-in page keeps a socket WITHOUT a `room_id` (the app shell, `_auth.tsx`), which `connect` accepts as the personal channel only (it used to refuse it, so no invite ever arrived). The invite shows as a quiet strip under the nav (`RoomInviteStrip`, which accepts it itself: a refusal is said on the strip, a seat elsewhere is offered "Leave {{room}} and join"), never a toast.
- **Game History**: `GET /api/v1/games/{id}/summary?lang=` returns typed `GameSummary` with `VoteRound`, `ClueHistoryEntry`, player roles, and word explanations (meanings resolved in `lang`).
- **Colophon**: all four game states carry `host_username` (the host who started the game, kept in `live_state`), `started_at` and `ended_at` (UTC; `ended_at` null while running).
- **Prayer pause (وقفة الصلاة)**: when the adhan comes the host pauses the game — `POST /api/v1/{undercover|codenames|wordquiz|mcqquiz}/games/{id}/pause` and `/resume` (IN_PROGRESS-only, a spectator cannot pause, double pause/resume → 409, a game of another type reaching a router → 404). While paused every move answers `GamePausedError` (409) and `timer-expired` answers `action="paused"` (`TimerExpiredAction` enum) without acting. Every state schema carries `paused: GamePause | None` with server-computed `remaining_seconds` (frozen countdown), `paused_for_seconds`, `anyone_can_resume_at`, plus per-caller `can_pause` / `can_resume`. Only the host pauses; resume is the host's, or any player's once the pause outlasts `PRAYER_PAUSE_MAX_SECONDS` (45 min) or the room has no owner — a pause can never hold a table for good. Resume moves every clock forward (`PAUSE_TIME_ANCHOR_KEYS`, chosen by the game's own type) and the disconnect grace of anyone away; while paused a disconnected member is kept 45 min instead of 180 s. See `backend/CLAUDE.md`.
- **Kunnash (كُنّاش, the notebook)**: players keep words from finished games — `GET /api/v1/notebook/games/{id}` (the game-over colophon: every word the game dealt, with `kept` / `entry_id`), `POST /api/v1/notebook/games/{id}/keep` (all of a game's words), `POST /api/v1/notebook/entries` (`{game_id, word}`, which must belong to that game), `GET /api/v1/notebook` (newest first, keyset `cursor` → `next_cursor`, resolved in `lang`: `word_display`, `word_ar`, `word_ar_vocalized`, `hint`), `DELETE /api/v1/notebook/entries/{id}` (owner only, others get 404). Same gates as the summary (`GameController.get_past_game_for_participant`: participation first, then status); MCQ has no words (400). Idempotent via a unique constraint + `ON CONFLICT DO NOTHING`. Keeps are rate-limited per signed-in user (not per IP), and a 429 answers the standard error envelope (`errors.api.rateLimitExceeded`). Table `notebook_entry`; see `backend/CLAUDE.md`.
- **Word of the day (Kalimat al-yawm, كلمة اليوم)**: one `QuizWord` per Makkah day (`Asia/Riyadh`, the day turns at 21:00 UTC; #1 = 2026-10-29, the launch day, never below 1), the same for everyone, drawn lazily by the day's first request (`INSERT … ON CONFLICT DO NOTHING` on `daily_word.day`, no repeat within 180 days). `GET /api/v1/daily-word?lang=` is public (`get_optional_current_user`: no token = anonymous, a bad token = 401): number, category, the revealed PREFIX of the hints (hint 1 for anonymous), status, streaks, `solvers_today`, `next_day_at`; `answer` only once the caller solved or gave up. Moves (auth, `?day=` = the page's day, another day → 409 `dailyWordNotToday`): `POST /daily-word/hint`, `/guess` (`{answer}`, Kalimat's matching via `utils/text_match.matches_quiz_answer`, 30/min per user), `/give-up` (0 points), `/keep` (a `daily_word` Kunnash entry, `source_game_id` null). One `daily_word_play` row per (user, day), row-locked per move. Score = Kalimat's `max_hints - hints_revealed + 1`, and a wrong try opens the next rung like a hint (so typing the theme's words one by one at hint 1 does not pay; the rate limit only protects the server). See `backend/CLAUDE.md`. The page is `/today` (public, `front/src/components/daily`), with a card on the home page between the hero and the games, and a link in the menu sheet and the footer; the client reads only once `AuthProvider` has settled, keys the read by viewer, and sends `day: state.day` on every move (see `front/CLAUDE.md`).
- **Samar riddles (السَّمَر)**: while a table waits (the lobby, for its quorum or its host; The Quiz between two questions) each member gets rung 1 of a random Kalimat word and its answer: `GET /api/v1/rooms/{id}/riddle?lang=` (members only, 403 `roomMembersOnly`; 20/min and 30/day per user). Never a spoiler: never today's word of the day (drawn first if needed) nor a recent one, never a right answer of the room's running Quiz, and 409 `riddleNotDuringGame` while any other game runs (Kalimat draws round by round). The answer comes on a tap after 30 s, or at the room's next wait ("The last riddle, “…”, was Ibrahim."); no riddle between Kalimat rounds. See `backend/CLAUDE.md` and `front/CLAUDE.md` ("The samar riddle").
- **Caching**: `majlisna.api.utils.cache.TTLCache` caches the leaderboard only (30 s). Game content (words, term pairs, word packs, quiz questions) and user stats are read from the DB every time; a content draw selects the ids, picks with `rng`, then fetches only the drawn rows (`api/utils/draw.py`). Tests use autouse `clear_cache` fixture.
- **PWA**: Manifest + service worker for installable web app with offline navigation shell. `front/public/sw.js` refreshes the shell (`/`) from every successful navigation; bump its versioned `CACHE_NAME` when its logic changes.
- **Pre-commit**: `prek` hooks run ruff lint/format + `ty` type checking on commit.
- **BaseGameController**: All 4 game controllers inherit from `majlisna.api.controllers.base_game.BaseGameController`, which provides shared methods: `_get_game`, `_check_is_host`, `_check_game_in_progress`, `_require_participant`, `_update_heartbeat_throttled`, `_check_spectator`, `_resolve_multilingual`, `pause_game` / `resume_game`. Game-specific logic stays in each subclass.
- **Room Share Links**: `GET /api/v1/rooms/{id}/share-link` returns `public_id` + `password`. Frontend constructs URL `majlisna.app/rooms/join?code=X&pin=Y`. The `/rooms/join` route auto-joins via `useEffect` with the join mutation, after dropping `code` and `pin` from the address (`history.replaceState`); a player seated in another room (409) is offered "Leave {{room}} and join", a banned one (403) is told so.
- **Shared Quiz Components**: `PlayerScoreboard` and `QuizGameOver` in `components/games/shared/` are used by both Word Quiz and MCQ Quiz. Game-specific i18n keys passed via props.
- **Timer expiration**: Any player can trigger timer expiration (not just host). The server validates that the timer has actually elapsed before processing the action. A call that changed nothing (`ws/notify.NO_OP_TIMER_ACTIONS`: paused, not expired, already done) broadcasts nothing — every client fires its own, and broadcasting them all sent each client N pushes per deadline. The route is rate-limited per user, like Kalimat answers and hint views. Client half: the host's page reports at once, every other page after a 1–2 s jitter that the next state cancels, and no refetch follows a no-op answer (`front/src/hooks/use-timer-report.ts`). Tests: `tests/api/routes/test_timer_expired_notify.py` (ten concurrent calls at the deadline → one `game_updated` per client), `front/src/hooks/use-timer-report.test.ts`.
- **Google OAuth**: "Continue with Google" on login/register pages. Frontend uses `@react-oauth/google` (`useGoogleLogin` hook → access token); its provider is mounted by `GoogleLoginButton` itself (`WithGoogleOAuth`), never by the root layout, so Google's script loads on those two pages only (and in the open deletion dialog and password form of a Google account, whose "Confirm with Google" sends `google_access_token`: `front/src/components/profile/DeleteAccount.tsx`, `ChangePassword.tsx`), and the button renders nothing in a build without `VITE_GOOGLE_CLIENT_ID`. Backend `POST /api/v1/auth/social/login` verifies via Google userinfo API, creates/links user, returns JWT pair. User model has `google_sub`, `auth_provider`, `profile_picture_url` fields. Social users get a sentinel password and cannot use password login until they set one ("Change password" in the profile, confirmed with Google, or "Forgot password?"): `auth_provider` email means "has a password of its own" (`controllers/user.has_own_password` / `set_own_password`), the `google_sub` is kept, so both doors open the account. Env vars: `GOOGLE_CLIENT_ID_WEB` (backend), `VITE_GOOGLE_CLIENT_ID` (frontend). Since 28 September 2026 the OAuth client lives in its own Google Cloud project `majlisna` (it used to share La Tabdhir's project, so users saw "La Tabdhir" on the Google consent screen); that project's consent screen links to the public privacy policy at `/privacy` (`front/src/routes/privacy.tsx`, strings under `privacy.*` in en/fr/ar), which Google requires to publish the app. Keep that page accurate when data collection or providers change: the flows it names are listed in `front/CLAUDE.md` ("Privacy").

## Lessons Learned

### Backend — Game Logic

**`get_room_state()` includes ALL room members, not just connected ones.** The room state query must NOT filter by `connected == True`. Players who briefly disconnect (Socket.IO reconnection) must still appear in the player list. In the lobby (no active game), disconnected players have a 10-minute grace period (`LOBBY_GRACE_PERIOD_SECONDS = 600`) before auto-removal. During active games, players are permanently removed after 180s grace period. The host can manually kick idle players at any time. Filtering by connection status causes the player count to flicker during brief disconnections, breaking game start flows.

**All game state mutations use `get_game_lock(game_id, session)`.** This uses a blocking PostgreSQL **transaction-level** advisory lock (`pg_advisory_xact_lock`: waiters queue first come, first served; the wait is bounded by a `SET LOCAL lock_timeout` of `LOCK_TIMEOUT_SECONDS`, answered as `TimeoutError`) in production — it auto-releases on commit/rollback, preventing lock leaks. It replaced a 100 ms polling try-lock (WP-22, BDP-06: 12 simultaneous moves waited ~530 ms at the median). Falls back to in-process `asyncio.Lock` for SQLite (tests). Vote submission, description submission, and disconnect handling ALL acquire the same lock. If you add a new game mutation endpoint, wrap it in `get_game_lock(str(game_id), self.session)`. **Never use session-level advisory locks** (`pg_advisory_lock`) — they leak when connections are recycled by the pool. The shared test engine is `NullPool` (closing a connection releases every lock), so only the pooled-engine tests in `test_game_lock.py` catch such a leak (TQ-06). **Read the game AFTER taking the lock, with `populate_existing`** — sessions use `expire_on_commit=False`, so a plain re-select under the lock returns the identity-mapped copy read before it: the departure path (kick, leave, sweep) did that and erased every move committed while it waited (BR-04; `backend/CLAUDE.md` → "Departures, the sweep and the sockets"). **Never write back a `Game` row that was read before `get_game_lock`**: take the lock first, then `select(...).execution_options(populate_existing=True)` (or select columns only). Tests: `tests/api/controllers/test_disconnect_lock_postgres.py` (a kick waiting behind a vote keeps the vote; a 7-vote burst with a kick loses none).

**Every move checks the Game ROW's status first, and a finish lets go of the room only if the room still points at it.** Each move endpoint calls `_check_game_in_progress(game)` (Codenames: `_ensure_in_progress`, row and `live_state` both) before anything else; `live_state["status"]` alone kept a game a rematch had CANCELLED playable from a stale tab, and finishing it then unlinked the room's NEW game. Finish paths clear `room.active_game_id` only through `game_cancel.detach_room_if_current`. Tests: `test_a_cancelled_game_refuses_every_move_and_leaves_the_new_game_alone` (`test_codenames_game.py`), `test_an_answer_on_a_cancelled_game_is_refused` (both quizzes), `test_finishing_a_game_leaves_the_rooms_newer_game_attached` (`test_undercover_game.py`).

**Concurrency tests must assert an INVARIANT, not a timing-dependent outcome.** Once the advisory lock actually serializes concurrent submissions, the interleaving order is nondeterministic. For turn-based actions (e.g. undercover descriptions) the successful actors are always a *prefix* of the turn order — and if the tasks happen to serialize in order, *all* of them succeed, which is valid. Assert the prefix invariant (`set(successes) == set(order[:len(successes)])`), never "at least one must fail" — that passes locally and flakes in CI.

**Concurrency tests MUST give each `asyncio.gather` task its own `AsyncSession`.** A single SQLAlchemy async session (and its asyncpg connection) cannot be driven by multiple tasks at once — sharing one across concurrent tasks raises `ResourceClosedError: This transaction is closed`. Production gives every request its own session via the `get_session` dependency, so the game advisory lock serializes mutations across *distinct* connections. Tests replicate that with a per-task session helper (`_mutate` in `test_concurrent_mutations.py`), never a shared controller. These postgres-marked tests only run under `pytest --use-postgres` (now enforced in CI).

**One commit per locked block applies to EVERY mutation, not just game creation.** `start_next_round` called `create_turn`/`create_turn_event` with their default `commit=True` inside `get_game_lock`, so the first commit released the transaction-scoped advisory lock and the rest of the block ran unprotected — two concurrent next-round calls could each append a turn. Any helper called inside a lock must be passed `commit=False`. (Those two, which wrote Turn/Event rows nothing read, are gone since WP-03: `live_state` is the record of a game.)

**A round resolves exactly once, and every timeout must land in a phase the game can leave.** An Undercover turn stays in phase `voting` after its elimination (until the next round opens: the host's call or the ready quorum) while `timer_started_at` still points at the voting deadline — so the timer reads as expired for that whole gap. `_eliminate_player_based_on_votes` therefore sets `turn["resolved"]` and `handle_timer_expired` answers `round_already_resolved`; without it every timer call re-ran the same votes, killed another player, and the client's timer callback kept the cycle going. Same class of bug: the Mr. White guess timeout used to leave the phase on `mr_white_guessing` with no guesser, which no action could exit. Details in `backend/CLAUDE.md`.

**A player who leaves before the end gets neither a win nor a loss, in all four games.** Every departure path (leave, kick, grace sweep, account deletion) must record it with `utils/game_state.mark_player_left` — a path that does not is scoring its leaver; `game_end_stats.scorable_players` skips those ids, so `record_game_end` writes nothing for them, and an Undercover drop-out never shares the win. The shared contracts of the 2026-10 audit (`game_cancel`, `token_auth`, `_require_participant`, the live-state keys, `room_ban` / `auth_session`) are in `backend/CLAUDE.md`, "Shared contracts of the 2026-10 audit".

**Every game controller passes its own `min_players`.** `_prepare_game_start` defaults to 1. Undercover relied on that while `MIN_PLAYERS_FOR_GAME = 3` sat unused, so a solo host could start a game with one undercover and zero civilians.

**The end-of-game stat/achievement flow lives in `controllers/game_end_stats.py`, and the disconnect handlers call it too.** Ending by disconnect used to record nothing at all — the handlers set FINISHED and wrote the winner but never ran the flow, so a game decided by someone closing their tab counted for no one. It is a separate module because `base_game` → `room` → `disconnect` would otherwise be a cycle. Same invariants as before: no commit inside, no swallowing SQLAlchemy errors. It also writes `live_state[WINNER_IDS_KEY]` for every game, advances the daily/weekly challenges (they had no caller and never moved), writes `games_hosted` / `mr_white_correct_guesses` / `codenames_perfect_rounds`, and unlocks the five special achievements (`SPECIAL_ACHIEVEMENT_RULES`). **Who won is answered in ONE place, `stats.did_user_win(game, user_id) -> bool | None`** (history `user_won`, the profile chart, head-to-head; `None` = a leaver, a spectator, a solo or unfinished game, skipped by all three) — quiz wins used to read as losses on the chart. `GET /stats/users/{id}/stats` is read-only (404 for an unknown user) and `POST /challenges/seed` is admin-only. See `backend/CLAUDE.md`.

**Game draws come from `api/utils/rng.py` (`SystemRandom`), never `random.*`.** The default Mersenne Twister is reproducible from observed outputs, and in a social-deduction game the draw *is* the secret.

**`TTLCache` is per-uvicorn-worker.** A TTL is the real freshness bound; `invalidate()` reaches one worker in four. User stats are therefore not cached (they were, and players saw their own win appear or not depending on the worker), and nothing caches ORM rows. See `backend/CLAUDE.md`.

**Player counts are bounded on both ends** — `MAX_PLAYERS_UNDERCOVER` (12), `MAX_PLAYERS_CODENAMES` (10). Only the minimums used to be checked.

**Usernames are unique case-insensitively, by a locked controller check.** `user.username` has no unique constraint in the model (on PostgreSQL a unique `lower(username)` index, created by the baseline migration, is only the backstop), so `username_is_taken` guards registration (409 `errors.api.usernameAlreadyTaken`), profile renames and Google sign-up — always inside `username_claim_lock`, a blocking transaction-level `pg_advisory_xact_lock(hashtext('username:' || lower(name)))` (an in-process `asyncio.Lock` on SQLite) held from the check until the insert's single commit. **The race where two simultaneous claims of one new name both won the check is closed, twice over**: by `username_claim_lock`, and on PostgreSQL by the unique index `ix_user_username_lower` that the startup DDL adds (WP-21; skipped with a log while a case-variant duplicate is stored, which production has none of). Tests: `test_two_concurrent_registrations_of_one_new_username_admit_exactly_one`, `test_two_concurrent_renames_to_one_new_username_admit_exactly_one` (postgres, each fails with the lock replaced by a no-op), `test_database_ddl.py::test_two_usernames_differing_only_in_case_cannot_both_be_stored`; see `backend/CLAUDE.md`.

**A quiz departure that completes the round sends it to results at once.** When the last player still owing an answer (MCQ) or the word (Word Quiz) leaves, is kicked or is swept, the disconnect handler moves the round to results under the game lock (`quiz_rules.settle_round_if_everyone_answered`) instead of leaving it to the timer. Never while paused: the resume settles it. See `backend/CLAUDE.md`.

**Every error the API answers has a translated key.** Never raise a bare `BaseError(...)` (key `errors.api.base`, untranslatable); add a named class and its `errors.api.*` entry in all three locales — `backend/tests/api/test_error_keys.py` fails otherwise.

**The Socket.IO `join_game` push must be read in the player's language.** The client writes it into the query cache, so an English push overwrote Arabic meanings. The server accepts `lang` in `join_game` (and `auth.lang`); `useSocket` sends both (`i18n.language`, the same value the pages put in `?lang=`) and writes the push only into the query keyed by that language.

**A browser's regional language tag is its language, on both ends.** Phones send `ar-SA`, `fr-FR`; that raw tag used to become `i18n.language` (Arabic laid out left to right, cached in localStorage for good) and reach the API as `?lang=ar-SA`, which the content resolver did not know and answered in English. The client's i18n init normalises to exactly `en`/`fr`/`ar` (`supportedLngs` + `convertDetectedLanguage`, `front/CLAUDE.md` → i18n), and the server's `utils/multilingual.normalize_lang` maps a tag to its language part (unknown → `en`); `resolve_multilingual` applies it, so every hint and meaning read through it is right whatever the client sends.

**`GET /users` and `DELETE /users/{user_id}` were removed.** The first returned the entire unpaginated user table to any caller; the second deleted an account on nothing but a valid session, while `/users/me/account` does the same and requires the password.

**Game content endpoints (undercover words/term pairs, codenames word packs) are admin-only — reads included.** `ADMIN_EMAILS` + `get_current_admin_user`, fail-closed. The GETs took no auth at all and `GET /undercover/termpair` reveals the opposing word to any player; the writes took only *a* login, so any player could delete all game content. There is no `is_admin` column (chosen before migrations existed, kept because no API path can grant it), so admin membership is configuration — matched case-insensitively, and the account must have a **verified** email, because naming an address in config turns that address into a credential anyone could register. See `backend/CLAUDE.md`.

**The frontend CSP is ENFORCED.** The API, Umami and Sentry origins (and the API's `ws(s)://` origin) are substituted into `security-headers.conf` from the same build args the bundle is compiled with. `script-src` has no `'unsafe-inline'`: each inline `<script>` of the built `index.html` is allowed by its sha256 (`front/scripts/csp-inline-hashes.mjs`), and an inline event handler or a `javascript:` URL fails the image build. Fonts are self-hosted (`front/src/fonts.ts`), so `style-src`/`font-src` allow no font CDN. `'self'` does not cover a different port or subdomain, so a split-origin API needs its own entry. `e2e/tests/smoke/csp.spec.ts` fails on any violation, and `front/scripts/csp-inline-hashes.test.mjs` pins the hashing. See `front/CLAUDE.md`.

**Type checking is `ty` (Astral), it passes, and it runs in CI** — `ty check majlisna/ --error-on-warning`, in `uv run poe check` and in the `backend` job. It replaced mypy: measured on identical suppression-free source the two agree on 46 sites, ty additionally catching deprecated APIs, a missing submodule and JSON-derived types while mypy's extra hits were `Settings()` false positives that had needed three ignores. ~14 s → ~0.3 s, one toolchain with ruff. The version is pinned **exactly** (`ty==0.0.63`) because ty is pre-1.0 and its diagnostics move between releases. `--error-on-warning` is deliberate: ty's warning-level rules are not advisory here — `possibly-missing-submodule` is what found an `except` clause naming a `resend` exception class that does not exist, which turned every failed email into a 500 on registration. `api/utils/game_state.py::require_state` is what makes `Game.live_state` typed; primary keys are `UUID`, not `UUID | None`. Read the `ty: ignore` discipline in `backend/CLAUDE.md` before adding a suppression.

**`notify_game_changed` addresses the room as well as the game room.** Game-room membership is built from a per-process SID map, so with 4 workers the first `game_updated` of a game reached only a fraction of the table.

**Game creation must be ONE transaction — never commit mid-`create_and_start`.** `GameController.create_game` takes a `commit: bool = True` flag (so did `create_turn` / `create_turn_event`, since removed); the four `create_and_start` methods call it with `commit=False` and commit once at the end. Previously these helpers committed internally, which released the room advisory lock (it is transaction-scoped) *before* `active_game_id` was set — so two truly-concurrent starts for the same room both slipped through and created two games. `_prepare_game_start` also reads `active_game_id` with `SELECT ... FOR UPDATE` on postgres (a plain read returned a stale `None` from an older MVCC snapshot). Together these make concurrent same-room starts safe (see `test_concurrent_game_starts_same_room`).

**Access and refresh JWTs carry a `type` claim (`access`/`refresh`).** `decode_token(token, expected_type=...)` rejects a mismatch. `get_current_user` requires `access`, `/auth/refresh` requires `refresh`, Socket.IO `connect` requires `access`. Without this a long-lived refresh token could authenticate ordinary API calls. `TokenPayload.type` is optional so legacy tokens still decode, but the callers above enforce it.

**Every token names a server-side session (`AuthSession`, the `sid` claim; a refresh token also carries its single-use `jti`), and refresh tokens are single use (SEC F01).** Logout, a password reset and a replayed refresh token revoke the session, and a password change revokes every OTHER session of the account; `authenticate_caller` (`controllers/token_auth.py`) refuses a revoked or expired session with `SessionRevokedError` (401, `errors.api.sessionRevoked`) on every request and socket connect. Two tabs refreshing at once are answered the same current token for `REFRESH_REUSE_GRACE_SECONDS`; any later reuse of an old token revokes the whole session. A session ends `SESSION_ABSOLUTE_LIFETIME_DAYS` after login however often it is refreshed. Google links into an existing account only when its email is verified; an unverified one is reset to the Google owner first (password, sessions). Emails are stored and compared lowercased. Reset/verification tokens are stored as sha256 digests. Legacy (pre-session) tokens are accepted until they expire; a legacy refresh token is upgraded into a session ONCE (its digest is recorded, `AuthSession.legacy_refresh_digest`; a later replay revokes that session, review R3); the upgrade path is to be removed 7 days after the deploy. No response body carries a refresh token: it is the httpOnly cookie only (review INT-06). A socket is cut by its worker's next tick once its session ends (review R5). Every access token becomes a `User` only through `controllers/token_auth` (`authenticate_caller` / `authenticate_access_token`), over HTTP and Socket.IO alike. Tests: `tests/api/controllers/test_wp17_sessions.py`, `test_social_auth.py` (an unverified account is taken back), `test_auth.py::test_registration_stores_the_address_lowercased`, `test_auth.py::test_the_reset_token_is_stored_as_its_sha256_digest`, `e2e/tests/auth/token-management.spec.ts`. See `backend/CLAUDE.md` "Sessions".

**Per-IP rate limits key on the visitor, not the Cloudflare edge.** Behind Cloudflare the client IP is resolved in two steps: uvicorn trusts only Docker-network proxies (`FORWARDED_ALLOW_IPS`, the private ranges by default, never `'*'`), then `rate_limit.client_ip_key` reads `CF-Connecting-IP` only when that peer is inside `CLOUDFLARE_IP_RANGES`, else it uses the peer. Key a limit on the signed-in user wherever there is one (`user_or_ip_key`); `/auth/refresh` is limited per account (`refresh_sub_key`). Tests: `tests/api/test_trusted_proxies.py` (runs uvicorn's middleware with the Dockerfile's own value), `tests/api/test_rate_limit.py::test_a_cloudflare_peer_is_keyed_on_the_visitor_it_names`. See Infrastructure Gotchas.

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

**DELIBERATE EXCEPTION — `RoomUserLink` timestamps (`joined_at`, `last_seen_at`, `disconnected_at`) are intentionally NAIVE. Do not "fix" them to UTC-aware.** The disconnect/heartbeat logic does Python-side datetime arithmetic on these (`datetime.now() - link.last_seen_at` in `base_game._update_heartbeat_throttled`, grace thresholds in `disconnect.py`). SQLite (dev + tests) reads `TIMESTAMP WITH TIME ZONE` columns back as **naive**, so making these columns aware would leave `datetime.now(UTC) - <naive from DB>` raising `TypeError` in every dev/SQLite run. The subsystem is kept uniformly naive on purpose; keep any new comparison in it naive too. (Values that leave the API — `Game.start_time`/`end_time`, `created_at` — stay UTC-aware as above.)

**Timer expiration is triggerable by ANY player, in all four games.** `handle_timer_expired` must not require the host — it only acts when `_is_timer_actually_expired()` is true. Gating on host would stall a game whenever the host is AFK/disconnected. (`is_host` may be returned in the response for the UI, but never used to reject the call.)

**Verify the OAuth token audience, never trust `userinfo` alone.** `SocialAuthService.verify_google_access_token` calls Google's `tokeninfo` and checks `aud`/`azp == GOOGLE_CLIENT_ID_WEB` before accepting a token. `userinfo` returns data for *any* valid Google token regardless of which app it was minted for, so skipping the audience check allows account takeover with a token issued to a different application.

**Passwords are ALWAYS hashed at rest.** Any path that creates or sets a password (`AuthController.register`, `UserController.create_user`, `update_user_password`, social sentinel) must run it through `async_get_password_hash`. Storing a raw password leaves plaintext credentials in the DB and produces accounts that can never log in (bcrypt verify fails against a non-hash). Changing a password requires the current one, or for a Google-only account a fresh Google token naming it (`update_user_password(user_id, current_password, new_password, google_access_token=, social_auth_service=)`; the other kind is a named 403), like account deletion, signs out every other session, and is rate-limited per user (`PASSWORD_CHANGE_RATE_LIMIT`). bcrypt's limit is 72 BYTES of UTF-8 (`BCRYPT_MAX_PASSWORD_BYTES`): every password a client sets or confirms is checked in bytes (`PasswordTooLongError`, 400), and a longer one at login is a 401, never a 500 (`verify_password` never raises). Tests: `tests/api/controllers/test_wp27_password_bytes.py`.

**`UserUpdate` only exposes safe profile fields (username, country, bio, profile_picture_url).** It must NOT inherit `UserBase`: doing so lets a client PATCH `email_verified`, `email_address`, `auth_provider`, or `google_sub` via mass assignment (e.g. self-verify their email, or change their address). Keep security-sensitive fields out of any user-editable schema.

**Deleting a user must purge every FK reference first.** No FK in the schema declares an ON DELETE action, so deleting a user with any related row (UserStats — created for every user — plus achievements, challenges, chat, friendships, owned rooms, created games, events/activities, tokens, room/game links) raises a foreign-key violation. `UserController._purge_user_references` deletes the child rows, nulls the nullable "actor" references (`Game`/`Event`/`Activity.user_id`), and orphans owned rooms (`Room.owner_id` is nullable → set to NULL + INACTIVE). Both `delete_user` and `delete_user_account` call it — AFTER leaving every room through `_handle_permanent_disconnect` (WP-27, SEC F05: purging the seats directly left a ghost alive in a running game and orphaned the host's room under it). A Google-only account confirms the deletion with a fresh Google access token (`DeleteAccountRequest.google_access_token`, its `sub` must be the account's). Tests must delete a user WITH related data, or they give false confidence.

**Never use Pydantic v1 `class Config: json_encoders` in models.** Pydantic v2 serializes UUIDs to strings by default. The v1 `json_encoders = {UUID: str}` pattern creates `FieldInfoMetadata` objects that are unhashable, crashing FastAPI's OpenAPI schema generation with `TypeError: unhashable type: 'FieldInfoMetadata'`.

**Always type response schemas fully — no `list[dict]` or `dict`.** Create proper Pydantic models for all nested structures (e.g., `VoteRound`, `ClueHistoryEntry`). Untyped dicts can cause Pydantic schema generation issues and produce useless OpenAPI/Kubb types.

**Dev backend runs on port 5111 to avoid macOS AirPlay conflict on port 5000.** Configured via `PORT=5111` in `.env.development`. Docker containers still use 5000 internally (no AirPlay conflict inside containers).

**Every game endpoint must be authenticated AND membership/role-aware — never expose raw `Game`/`live_state`.** The generic `/games` CRUD router (`POST /games`, `GET /games`, `GET /games/{id}`, `PATCH /games/{id}`, `PATCH .../end`, `DELETE /games/{id}`) was REMOVED because it had zero authentication and returned the raw `live_state` JSON — i.e. every player's role and the secret words. A player could read `GET /games/{id}` mid-game to cheat (bypassing the sanitized `get_state`), and anyone could mutate/end/delete any game by ID. `routes/game.py` now exposes ONLY two authenticated read endpoints: `GET /games/user/{user_id}` (history) and `GET /games/{game_id}/summary` (post-game summary). Games are created and mutated EXCLUSIVELY through the per-game routers (`/undercover`, `/codenames`, `/wordquiz`, `/mcqquiz`), which enforce auth + membership + role-aware sanitization via `_check_spectator`/`get_state`. **Never re-add a raw game-state read or a generic game-mutation route.**

**Chat endpoints must verify room membership (IDOR guard).** `ChatController.send_message` and `get_messages` call `_ensure_member(room_id, user_id)`, which requires a `RoomUserLink` to exist for that (room, user). Without it, any authenticated user could read or post in ANY room by guessing/knowing its `room_id`. Membership is checked by link EXISTENCE, not the `connected` flag, so a member who is briefly disconnected (Socket.IO reconnect / grace period) can still use chat — a non-member has no link at all, which is what we reject.

**Controllers must NOT touch the Socket.IO server directly — emit via `notify_*` from the route.** `majlisna.api.ws.server` imports `ws.handlers`, which imports the controllers, so a controller doing `from ...ws.server import sio` needs an in-function import to dodge the circular import. Instead, add a `notify_*` coroutine in `ws/notify.py` (which routes already import safely) and `await` it in the route AFTER the controller validates. Example: room invites emit through `notify_room_invite(friend_user_id, room_id, invited_by)` from `routes/room.py`, not from `RoomController.invite_friend_to_room` (which now only validates friendship/membership and returns).

### Frontend — Socket.IO + TanStack Query

**Socket.IO pushes state into TanStack Query cache via `queryClient.setQueryData()`.** The `useSocket` hook connects to Socket.IO, receives `room_state` and `game_state` events, and writes them directly into the query cache. It returns `{ connected }` so consumers can disable polling when connected. All pages (game pages and room lobby) use `refetchInterval: socketConnected ? false : 2_000` — zero polling when Socket.IO is up, fast 2s fallback when disconnected. Because nothing polls while the socket is up, a stale state that arrives last stays for good: every `RoomState` carries `as_of_ms` (when the server read it) and the client keeps the state read last (`front/src/lib/room-state.ts`); a connect's initial read used to land after a concurrent change's push (CI, 2026-11-01).

**Game pages get roomId from SessionStorage for instant Socket.IO connection.** The room lobby stores `roomId` via `storeRoomIdForGame()` before navigating. Game pages read it via `retrieveRoomIdForGame()` in a lazy `useState` initializer, avoiding the ~2s delay of waiting for the first REST poll. Falls back to REST-provided roomId on page refresh.

**Game state is derived from server via `useMemo`, not accumulated from events.** All UI state is derived from the server response (whether from Socket.IO push or initial fetch). No local state accumulation.

**Phase transitions detected by comparing refs to previous state.** `previousPhaseRef` and `previousRoundRef` track changes to trigger animations (e.g., voting transition overlay).

**Socket.IO is a NOTIFICATION LAYER, not a game engine.** Mutations go through REST POST. Route handlers **await** Socket.IO notifications so events are guaranteed to be emitted before the HTTP response returns. Game start routes call `await auto_join_game_room()` to pre-join all room members into the game's Socket.IO room, eliminating the race condition where `game_updated` fires before clients call `join_game`. The client's `useSocket` hook invalidates queries on reconnect to catch up on any events missed during disconnection, the lobby chat's history included: python-socketio replays nothing. The first connect re-reads the chat history only (a line sent before the socket joined the room was pushed to nobody); the room and the game come with the connect itself.

**`sio.enter_room()` MUST be awaited.** It is an async coroutine in python-socketio. Calling without `await` silently fails — the SID never joins the room.

**Route handlers MUST `await notify_*()`, never `fire_notify_*()`** in route code. The `fire_*` variants are reserved for background tasks only (disconnect checker loop, Socket.IO event handlers).

**A route broadcasts only when the controller changed something.** The timer-expired routes
call `notify_timer_outcome`, which skips every action in `ws/notify.NO_OP_TIMER_ACTIONS`
(`paused`, `timer_not_expired`, `not_playing`, `round_already_resolved`, `none`). Every client
fires its own timer, so an unconditional notify meant N pushes and N refetches per client at
each round boundary (N² for the table). A new `TimerExpiredAction` that changes the game must
stay out of that set. Tests: `tests/api/routes/test_timer_expired_notify.py`.

**Any change the other players can see broadcasts `room_state` to the room, a return
included.** A reconnect, a heartbeat or a REST poll that flips `connected` back to True is
`HeartbeatResult.RESTORED` and is pushed to `room:{id}`; emitting the state to the returning
SID alone left the whole table showing that player as "away". Tests:
`tests/api/ws/test_wp04_reconnect_and_detach.py` (real python-socketio clients: seen back
within the bound, a present player's heartbeat broadcasts nothing).

### E2E — Playwright

**Never mix `text=` engine with CSS in comma-separated selectors.** Use `.or()` for selector unions:
```typescript
page.locator('text=Discuss and vote')
  .or(page.locator('h2:has-text("Game Over")'))
```

**Use specific element selectors to avoid strict mode violations.** `text=Describe your word` can match multiple elements (heading + label). Use `h2:has-text("Describe your word")` to target one element.

**Always use `activePlayers` from `dismissRoleRevealAll()`, never `setup.players`.** Only players confirmed on the game page should be used for game interactions.

**Vote with `voteOut(voters, alive, target, fallback)`**: every living player votes in the UI
(the target for the fallback), then `verifyAllPlayersVoted` ASSERTS each ballot is in. It
used to re-cast a missing ballot itself, which turned a lost click into a pass (TQ-16).

**`isPageAlive(page)` is `!page.isClosed()`.** It used to call `page.url()` in a try/catch,
which never throws, so it answered true for a closed page (TQ-15). Only the specs that close
a browser on purpose meet a closed page; anywhere else a closed page is a failure.

**No spec swallows its own failure** (TQ-07, TQ-08, TQ-09). No try/catch, `.catch(() => {})`
or early `return` around an assertion or a setup call; a refusal is asserted by its exact
status and `error_key` (`expectApiError(res, 403, "errors.api.cantVoteForYourself")`), never
`res.ok === false`, which a 500 or a 422 also satisfies. No `isVisible()` snapshot as a branch
condition, and never pass it a `timeout` (it ignores it), no fixed sleep where the server can
be polled (`expect.poll`), and a wait helper that runs out of time throws. A data page's spec
asserts its rows or its failure state (`leaderboard-row` / `leaderboard-error`), a validation
spec the field's own error AND that no request left (`waitForRequest` rejects). **A
`data-testid` asserted for presence must exist only in the state under test**: the
leaderboard's `data-testid="leaderboard"` sat on the table while loading too, so "it is there"
passed on a page that never loaded a row.

**One runner of the shared E2E stack at a time.** When several agents or people work on the
tree at once, only one of them (the E2E owner, or the agent running the gate) brings up
`docker-compose.e2e.yml`; the others write their specs and hand them over. Two runs on the one
stack reseed each other's database mid-run.

**Quiz rounds have a 10 s floor** (`MIN_QUIZ_TURN_SECONDS`): a spec ends a round by its
answers (the word from the database) or polls the server while the pages report the clock
(a guest 1–2 s late), never with a 1 s round and a sleep.

**The E2E fixtures sign in like a browser** (`fixtures/auth.fixture.ts`, `signInContext`):
the login goes through the context's request client, so the httpOnly refresh cookie lands
in the context's jar, and localStorage gets only what the app keeps (the access token, its
expiry, the session marker, the user). Never write a refresh token into localStorage.

**One write to the database, standing in for the mailbox:** the stack sends no mail and
stores reset tokens as digests, so `forgot-reset.spec.ts` gives the issued row the digest
of a token it knows (`dbPlantPasswordResetToken`) and follows the link. Everything else in
`helpers/db.ts` only reads.

**A wait that can be satisfied before the event is not a test.** `disconnect-during-game`
waited for `text=Eliminated` "within 120 s" of a browser closing — but the in-game grace is
`GRACE_PERIOD_SECONDS` (180 s), so it could only ever pass on some unrelated "Eliminated" on
screen. The redesign removed that text and the spec failed, as it should have. Scope a
wait to the thing that changes (the leaver's own seat, after asserting it is NOT eliminated
yet) and give it the real budget (stale 20 s + grace 180 s + checker 5 s).

**The helpers open the next Undercover round as the host** (`startNextRoundAsHost`, which
forces it); the ready quorum of the other players has its own spec
(`undercover/ready-quorum.spec.ts`). An eliminated player has no ballot and cannot mark
ready: act only with the living (`state.players[].is_alive`).

**A secret the API withholds is read from the E2E database, never from the API.**
Today's word of the day (`daily_word` ⋈ `quiz_word`) and a Kalimat round's word
(`game.live_state -> 'current_word'`) come from `e2e/helpers/db.ts`, which runs
read-only `psql` in `majlisna-e2e-db` (`execFileSync`, no shell quoting). A spec that
solved the word from an API answer would only prove the API leaks it. The same helper
checks the stored rows after a move (`daily_word_play`, `notebook_entry`, whose
`game_type` is the enum NAME, `DAILY_WORD`). The daily-word specs
(`e2e/tests/daily-word/`) run in the `daily-word` and `mobile-daily-word` projects, and
each test registers its own players: the word is the same for everyone, the play is not.

**The specs read what a player reads.** No test-only text in a page (the quiz pages' hidden
"Round 1/…", "Question n/m" and "#1" spans are gone); prefer roles and accessible names:
the game picker is `getByRole("tab")`, the clue count a `group` of toggles, the lobby's
code and PIN are `CodeTiles` groups ("Room code", "PIN").

**New suites:** `tests/notebook/kunnash.spec.ts` (keep a game's words from the colophon,
read and remove them in /notebook, EN + AR; Kalimat keep / un-keep) and
`tests/pause/prayer-pause.spec.ts` (host-only Pause, the veil on every seat, moves refused
and the clock frozen, resume, a pause that survives a reload). `contrast.spec.ts` now
measures Kalimat's hint rung in play (a translucent brass wash) in both lights.

**The 2026-10 audit's journeys (WP-20):** `auth/` logout (the old token refused,
`sessionRevoked`), two tabs refreshing at once, password change (other devices signed
out), forgot → reset, account deletion (and mid-game: the others play on); `rooms/`
kick → ban → lift → rejoin with the new PIN, join while seated elsewhere (the 409 prompt),
a mid-game rematch (the game CANCELLED); `chat/reconnect.spec.ts` (a line sent during a
10 s outage, shown on reconnect); `friends/invite.spec.ts`; `undercover/` Mr. White's
guess (right and wrong) and the ready quorum; `wordquiz/tries.spec.ts`;
`codenames/game-ending.spec.ts` (the decisive card before the veil); `stats/` (a leaver
gets no result, quiz Won/Lost chips and shared wins, the summary from the history);
`challenges` progress after a game; `pause/` Codenames and The Quiz too, and the frozen
clock exact to the thread; `i18n/regional-locale.spec.ts` (ar-SA, Google's script on the
sign-in pages only); `accessibility/phase-focus.spec.ts`; `smoke/cache-headers.spec.ts`;
`perf/` (the thread clock's layouts, the sky and arch image sizes; projects `stats` and
`perf`). The suite caught one product bug on its first run: `api/client.ts` dropped the
body of every DELETE, so every account deletion from the profile answered 422.

**The gate's additions (after the review fixes):** `stats/achievements.spec.ts` plays the
special achievements to certainty from the dealt roles (an undercover who wins at parity,
never named by a vote: Perfect Infiltrator + Last One Standing; a Codenames team that turns
only its own cards, one clue exactly: Clean Sweep + Flawless Round), each sealed on every
seat's colophon, plus Games hosted / Rooms created on /stats; `codenames/game-ending.spec.ts`
checks Assassin Finder; `undercover/ready-quorum.spec.ts` a walk-out that completes the
quorum, and one during the prayer pause that the resume opens (review R6);
`rooms/kick-ban.spec.ts` no repair line for a ban, the "PIN may have changed" advice on a
link made before a kick, and no frame carrying the new PIN on the kicked page's sockets
(R2); `stats/leaver.spec.ts` the player left alone by a walk-out is charged nothing (R4);
`stats/quiz-history.spec.ts` a 0-0 game ("No one scored") and the win/loss chart. **A
Codenames card is found by its whole word** (`cardButton`: the name up to its end or its
first ", "): `^Word\b` also took "Umar ibn Abdul Aziz" for "Umar", and `.first()` clicked
whichever came first. **Consecutive guesses from one page wait for the page's own answer**
(`requestfinished` of the guess, then the card turned on that board): the page drops a tap
while its guess is in flight (FR-4), so a tap timed on the API alone can vanish.

**The motion package's coverage (November 2026):** an animated screen is checked from its
FIRST frame: `helpers/motion.ts` `watchFrames` records, from inside the page, every frame
from the one in which a selector first matches (its text, the animations running in it),
started BEFORE the move that brings the screen; the text must be complete in every frame,
an animation must have run, and nothing may be drawn below full opacity once it settles.
Each such spec watches one seat with motion and one with `emulateMedia({ reducedMotion:
"reduce" })`: `undercover/final-text.spec.ts` (the verdict's turn; a seat emptied mid-round),
`codenames/clue-final-text.spec.ts`, `mcqquiz/reveal-final-text.spec.ts` (tallies, the woven
scoreboard, and the riddle between two questions). Also `rooms/riddle.spec.ts` (the samar
riddle checked against its `quiz_word` row, a reload that asks nothing, the answer at the
room's next wait, the 30 s tap, none in a Kalimat lobby), `theme/follow-the-sky.spec.ts`
(project `non-game`: the light from the stored city with no request, stored, and applied by
index.html alone with every app script refused), `mcqquiz/colophon-share.spec.ts` (Share
copies the colophon's line without Web Share; hands a PNG to a share sheet that takes files).
**`global-setup.ts` refuses a run whose `API_URL` / `FRONTEND_URL` is not the stack**
(localhost:5049 / :3049): it `docker exec`s into the majlisna-e2e-* containers whatever the
URLs say, so a run aimed at a private stack used to drop and reseed the shared database
under a gate run in progress.

### Infrastructure

**GitHub Actions gates the deploy; Dokploy performs it.** On push to `main` the
pipeline detects changed components and runs the suites in parallel — backend
(with `--use-postgres`, so the dialect-specific tests actually execute), frontend,
and **e2e** (the full Playwright suite, on the self-hosted runner). When all three
are green, the `promote` job fast-forwards the **`production`** branch to the
tested commit. A red or flaky suite means nothing ships.

**Dokploy watches `production`, not `main`.** Its compose app for
`majlisna-compose` has `autoDeploy=true`, `triggerType=push`, `branch=production`.
The push handler filters on `(autoDeploy, triggerType, branch, repository, owner)`,
so pushes to `main` are ignored and only a promotion triggers a build. Dokploy
still owns every container, so there is no rsync, health-check or orphan-adoption
logic in the pipeline.

**Why a release branch and not Dokploy's deploy webhook.** In Dokploy v0.26.7 the
manual webhook `POST /api/deploy/compose/<refreshToken>` is *also* gated on
`autoDeploy` — with the flag off it answers `400 {"message":"Automatic deployments
are disabled for this compose"}`. So "webhook-only deploys" is not expressible:
the flag is all-or-nothing. Verified empirically on 2026-07-25. Pointing Dokploy
at a branch that only ever advances from a green run achieves the same gate using
Dokploy's own semantics, needs no API key or webhook secret, and is undone by
setting `branch` back to `main`.

**Do not push directly to `production`** — that bypasses the gate entirely. To
deploy without a code change, use Dokploy's Deploy button.

**`cancel-in-progress: false` AND `queue: max`.** A cancelled run's commits are
never tested, and a cancelled run never reaches `promote`. `cancel-in-progress:
false` alone was not a queue: GitHub keeps one pending run per group and cancels it
when a newer one arrives, so the middle of three quick pushes was dropped with zero
jobs (2026-09-18, INFRA-12). `queue: max` keeps up to 100 pending runs, in order.
On top of that, `paths-filter` diffs a push against **`production`** (`base:
production`), not against the commit before the push: a suite skips only when
nothing it covers differs from what is live, so a lost or red run's components are
re-tested by the next one. No `continue-on-error` on any CI step.

**A suite green only on a re-run does not deploy.** `promote` reads the earlier
attempts of its run (`gh api …/attempts/N/jobs`) and refuses when backend,
frontend or e2e did not pass in one of them (run 36482914044 had shipped an e2e
"1 flaky" that way). To deploy after an infrastructure hiccup, dispatch a fresh
run (Actions → CI → Run workflow on `main`): it runs every suite.

**What else gates `promote`** (`.github/workflows/pipeline.yml`):
- `security-scan`: Trivy pinned to a commit SHA (`trivy-action` v0.36.0, never a
  tag: they were hijacked in March 2026). A CRITICAL with a released fix in any
  lockfile fails it (`ignore-unfixed`); HIGHs and unfixed ones are reported only.
- `backend-image`: builds the production image, scans it the same way, starts it
  (`/health` must answer `version` = the commit) and times `docker stop` (exit 0
  in under 5 s, or uvicorn is not getting SIGTERM).
- Coverage: the backend suite runs `--cov-branch --cov-fail-under=88`, the
  frontend `bun run test:coverage` (floors in `front/vitest.config.ts`), then
  `bun run build` and `bun run check:bundle`.
- E2E `timeout-minutes: 55`; the job warns from 35 min on.
- Dependabot (`.github/dependabot.yml`): weekly, 7-day cooldown, for uv, bun
  (front, e2e), github-actions, the Dockerfiles' base images and the compose files.
  actionlint runs clean with `.github/actionlint.yaml` (it lists the self-hosted
  label and ignores `concurrency.queue`, which actionlint 1.7.12 does not know).

**`promote` can wait for the deploy to go live** (INFRA-11): after the push it
polls `https://majlisna.app/health` until `version` is the promoted commit, 10 min,
red otherwise. A Dokploy build that failed after promote used to leave production
13.7 h behind with every signal green. It runs only with the repository variable
`VERIFY_DEPLOYED_VERSION=true`, to set once Dokploy builds the backend with the
`GIT_SHA` build arg (until then `version` is `"unknown"`, and promote prints a
"Deploy not verified" notice). **A green CI without that check does not mean deployed**:
until the variable is on, look at `https://majlisna.app/health` (or Dokploy's deployment
list) after a promote.

**Run-once work must not run unguarded in every uvicorn worker.** Production runs 4 workers,
and each one runs the lifespan. The migrations at boot run under the blocking
`pg_advisory_xact_lock(SCHEMA_DDL_LOCK_KEY)` (the four raced on `CREATE TYPE` on the deploy
that added `notebook_entry`, INFRA-13), and the disconnect sweep elects one worker per tick
with `pg_try_advisory_xact_lock(DISCONNECT_SWEEP_LOCK_KEY)` (four loops swept the same links,
PD-12); only what is per process (each worker's own sockets) runs everywhere. Tests:
`tests/api/test_migrations.py::test_four_workers_booting_on_a_fresh_database_all_succeed` (four
processes: Alembic's `context` is process-global),
`test_disconnect_lock_postgres.py::test_four_workers_sweeping_at_once_handle_each_link_once`.

**E2E docker-compose is separate from production.** `docker-compose.e2e.yml` runs the backend with `MAJLISNA_ENV=development` and a dedicated PostgreSQL. Never mix E2E and production compose files.

**Backend health check endpoint is `/health`.** It answers `{status, db, timestamp,
version}`; `version` is the image's `GIT_SHA` (`settings.git_sha`, `"unknown"` without
the build arg), on a 503 too.

**A container CMD must `exec` its server: the backend image runs uvicorn as PID 1**
(`CMD ["sh", "-c", "exec uvicorn …"]`, `--timeout-graceful-shutdown 15`; CI's
`backend-image` job fails when `docker stop` takes 5 s or more). The shell-form CMD put two
shells in front of it:
SIGTERM never reached uvicorn, every stop and deploy waited out Docker's 10 s and
ended in SIGKILL, and the lifespan teardown never ran (INFRA-10). The image is built
without a `chown -R` layer (`COPY --chown`), uv stays in the build stage, both
base images are pinned by digest (Dependabot bumps them), and it ships its bytecode
(`UV_COMPILE_BYTECODE`, `compileall`): every worker used to compile every dependency from
source at each boot, inside the deploy's outage.

**The Socket.IO handshake accepts only `CORS_ORIGINS` + `FRONTEND_URL`** (SEC F12; it was
`[]`, which python-engineio reads as "no origin check at all"). The page connects to its
own origin, so **`FRONTEND_URL` must be the page's origin in every deployment**
(`https://majlisna.app` in production, `http://localhost:3049` reaches E2E through
`CORS_ORIGINS`), or every socket is refused. An empty list means NO check at all, never
"same origin". Both variables default to the server's IP in `docker-compose.dokploy.yml`, so
before a deploy check that the Dokploy env names `https://majlisna.app` in `CORS_ORIGINS` (or
`FRONTEND_URL`). The effective list is logged at startup. Tests:
`tests/api/ws/test_wp11_socket_origin.py`.

**Production domain is `majlisna.app`.** Routing:
- `majlisna.app` → Frontend (Nginx serving React SPA)
- `majlisna.app/api/*`, `/socket.io/*`, `/health`, `/scalar`, `/openapi.json` → Backend (FastAPI)
- `api.majlisna.app` → Backend (alternative subdomain)

Cloudflare handles DNS (proxied/orange cloud) and reaches the origin over HTTPS (the Traefik log shows its traffic on `websecure`), so the SSL mode is Full, not Flexible. Traefik on the server routes requests via Docker compose labels: each service has an HTTPS router on `websecure` and an HTTP router on `web` that only applies Dokploy's `redirect-to-https@file`. Switching Cloudflare to Flexible would make every request loop on that redirect. Those `web` redirect routers are the repo's labels: production gets them only once the Dokploy patch below is disabled (the 2026-10-30 audit still got `200` over plain `http://majlisna.app`, INFRA-08). Still open on Cloudflare's side (lead actions, not visible from the repo): "Always Use HTTPS", minimum TLS 1.2 (1.0 and 1.1 were accepted), locking the origin's 80/443 to Cloudflare's ranges (the origin answered `majlisna.app` directly, INFRA-09), then SSL Full (strict).

**`docker-compose.dokploy.yml` reaches production only if Dokploy has no `update` patch for it.** The patch `security-majlisna-db-images-20260916` (type `update`, a whole-file replacement) overwrote the file with a frozen 2026-09-16 copy at every deploy ("Applying 1 patch(es)..." in the deploy log), silently discarding every compose change made in the repo since (INFRA-02). Its image digests now live in the repo, and the lead disables the patch in the deploy that ships the 2026-10 audit; **status 2026-10-31: still enabled**. Before relying on a compose change, check Dokploy's patch table (read-only: `select "patchId", type, "filePath", enabled from patch where "composeId" = '<id>'` in Dokploy's database), and never fix production with a Dokploy patch again. Images are pinned by digest, and `e2e/docker-compose.e2e.yml` pins the same ones so the gate tests what ships: keep the two files' `image:` lines identical (no test compares them; `grep -n "image:"` both). A change to a service's config recreates that container on the next deploy (db included: deploy such a change in a quiet window, after a backup). The backend's healthcheck uses `start_interval`, which needs Compose 2.20.2+ and Engine 25+ on the server: an older Compose rejects the whole file (`docker compose config` fails), so the e2e file leaves the key out for workstations.

**The frontend's nginx reaches the backend as `majlisna-api`** (see Infrastructure Gotchas → "nginx upstreams on a shared Docker network"). `VITE_API_URL` is baked at frontend build time — rebuild frontend when changing it.

**Production server**: Oracle VPS, shared with other projects (one Dokploy, one Traefik). Dokploy compose project connected to the `Souhib/Majlisna` GitHub repo, **branch `production`** (only `promote` advances it), compose path `./docker-compose.dokploy.yml`. **SSH only through Tailscale** (MagicDNS alias, direct connection): port 22 on the public IP is filtered before it reaches the host. Connection details are in Claude Code memory (whose `ssh ubuntu@<public-ip>` line is stale: the owner updates it).

**Production data rules** (PD-02, PD-03: a documented "migration" dropped every table on production once and refilled it with 31 fake accounts, 16 of them with this repo's public passwords, with no backup):
- never run `generate_fake_data.py --delete` or `--create-db` on production: the script exits 2 there unless given `--i-know-this-is-production` AND `--dump-taken <a pg_dump -Fc written in the last hour>` (`tests/scripts/test_generate_fake_data_guard.py`);
- a fresh `pg_dump` before any destructive or schema operation (`docs/operations/backups.md`);
- schema changes are Alembic migrations, which the app runs at boot (one worker at a time, in one transaction; a failed migration fails the boot): additive first, reviewed, never an edit of a revision that has run, never a drop-and-reseed (`backend/CLAUDE.md`, "Migrations (Alembic)"). Production (created by `create_all`, no `alembic_version`) is adopted by its first boot with Alembic: stamped at the baseline only if its schema is exactly the baseline's, else the boot fails and nothing is written;
- production receives game content only through `--seed` (upserts, effective on the next game, no restart);
- seed residue (the test and Faker accounts, orphan games and rooms) is removed by `scripts/purge_seed_data.py`, run by the operator after a verified dump, never by an agent (`tests/scripts/test_purge_seed_data.py`).

**Redis is ephemeral and non-critical.** Redis is only used for Socket.IO cross-worker pub/sub and the rate-limit counters (db 1). If Redis is down, the app works but Socket.IO won't broadcast across workers (and the rate limits, `RATE_LIMIT_STORAGE_URI`, lose their shared counters: they fall back to each worker's memory, `in_memory_fallback_enabled`, and return to Redis once it answers — without that fallback every limited route answered 500, review INT-02). It keeps nothing on disk (`--save ""`, `--appendonly no`, `/data` on a tmpfs): a restart empties it by design, and there is no `dump.rdb` left to corrupt (one used to crash-loop it). `maxmemory-policy volatile-lru` only ever evicts keys that carry a TTL.

**Database backups: `infrastructure/db-backups/`, documented in `docs/operations/backups.md`.** A dedicated Dagu scheduler (`majlisna-backup-dagu`, project `/home/ubuntu/majlisna-backups/`, no UI, no port) runs `pg_dump -Fc` at 03:45 UTC as the read-only role `majlisna_backup`. The dump is gpg-encrypted to the owner's PUBLIC key (`9E6A…7D92`, the same key as LaTabdhir's; the private key is never on the VPS), sent to the bucket `majlisna-db-backups` in LaTabdhir's SeaweedFS (newest 30 versions), and confirmed by a Kuma push heartbeat. An off-host S3 copy is optional. Restores and the monthly drill (`restore-drill.sh`) run on the operator's machine. Every destructive or schema operation in production needs a fresh backup run first (`generate_fake_data.py` and `purge_seed_data.py` refuse to run destructively without `--dump-taken`). The config is tested end to end locally by `infrastructure/db-backups/test/test-backup-restore.sh`. SeaweedFS shares the VPS disk, so until the off-host copy exists this is not off-host. **Status 2026-11-01: installed on the VPS; first backup `majlisna-20261101T100913Z.dump.gpg` (579 kB) and a restore drill that passed (31 tables, 1 727 rows, identical to production). Still to do (owner): the Kuma push monitor (`BACKUP_HEARTBEAT_URL` is empty) and the off-host S3 copy.**

**Admin tools are reachable over Tailscale only** (checked 2026-10-30, INFRA-25). Pangolin SSO is retired (its containers are gone; the CrowdSec acquisition file says so). Dokploy, Uptime Kuma, Dozzle, Beszel and the Umami dashboard now sit on a Tailscale-only `private` Traefik entrypoint (`private-tools.yml` in Traefik's dynamic config): from the public internet, through Cloudflare or straight at the origin, their hostnames answer `403`. From a Mac on the tailnet, split DNS resolves `*.majlisna.app` to `100.100.x.x` and the same hostnames answer `200`/`302`: that is the private entrypoint, not an exposure, so re-test from off the tailnet. Only the telemetry ingest paths must stay public (Umami's `/script.js` and `/api/send`, which every page calls, and Bugsink's ingest): a change to the private entrypoint keeps them, or analytics and error reports stop without a sound. The monitoring compose has `traefik.enable=false` and **no host port bindings** — direct `IP:31xxx` access used to bypass authentication entirely.

**CrowdSec does not protect the HTTP traffic today** (INFRA-05, status 2026-10-30). `monitoring-crowdsec` runs with the host's `crowdsec-firewall-bouncer-nftables` (its `nftables_hooks` must keep **both `input` and `forward`**: Docker-published ports are DNAT'd and traverse FORWARD), but its Traefik acquisition is a single-file bind mount pinned to an inode Dokploy's daily log cleanup rotated away on 2026-09-16: it has read no access-log line since, and holds 0 local decisions. SSH needs nothing from it (port 22 is filtered upstream). Fixing it is a lead action, and the fix has two halves: mount the directory, not the file; and parse the visitor IP (`Cf-Connecting-Ip`) with Cloudflare's ranges whitelisted, because 2304 of 2314 `majlisna.app` lines carry a Cloudflare edge as the client, and banning one would cut off every visitor behind it. Acquisition config: `/home/ubuntu/monitoring/crowdsec/acquis.yaml`.

**Uptime Kuma must probe services internally, not through their public hostname.** A check against a public admin hostname meets the private entrypoint's `403` (and, behind the old SSO, a login page's cheerful `200 - OK`): it says nothing about the tool. Monitors target container endpoints directly (`http://monitoring-umami:3000/api/heartbeat`, `http://monitoring-dozzle:8080/healthcheck`, `http://monitoring-beszel:8090/`, the Majlisna database and Redis by container name). The 2026-10-30 audit found 4 Majlisna monitors with notifications; Kuma recorded a down beat at each deploy while the backend restarted (INFRA-10).

**Every network a container needs must be declared in the compose file.** `monitoring-uptime-kuma` reaches `majlisna-db` / `majlisna-redis` by container name, and those live only on the Majlisna stack's internal network. That attachment had been made with a manual `docker network connect`, which silently vanished the next time the container was recreated — both database monitors went blind. It is now declared as the external network `majlisna-internal` in the monitoring compose. Never rely on a manual `docker network connect`.

**Monitoring tools** run in the shared monitoring stack on the same host (see Claude Code memory for URLs; containers `monitoring-*`: uptime-kuma, crowdsec, dozzle, umami, openobserve, bugsink, beszel, cloudbeaver, homepage, docker-reader):
- **Umami**: Privacy-focused web analytics. Own PostgreSQL database. Page views carry no query string (`data-exclude-search`).
- **Bugsink**: Sentry-compatible error tracker (there is no GlitchTip any more), shared with LaTabdhir. Majlisna has its own team (`Majlisna`) and two projects since 2026-11-02: `majlisna-backend` (9, `SENTRY_DSN`) and `majlisna-front` (10, the `VITE_SENTRY_DSN` build arg, so the CSP allows its origin); both DSNs are in Dokploy's environment. Ingest (`/api/<id>/envelope/`) is public and answers CORS `*`; the UI is Tailscale-only. New issues and regressions alert `#majlisna-errors` (Bugsink's native Discord service, one per project). The code: `app.py`'s WARNING+ sink, `front/src/lib/report-error.ts`.
- **OpenObserve**: runs, but nothing ships Majlisna's container logs to it yet (lead action).
- **Dozzle**: Real-time Docker log viewer. Zero storage, streams from Docker API. Use for quick debugging; its history ends at the container's last recreation.
- **Uptime Kuma**: Uptime monitoring with alerting (above), and the push heartbeat of the backups.
- **Discord** (the owner's private server, guild `724737220300374106`, category **Majlisna**, set up 2026-11-02 with the owner's bot "Souhib Monitoring", whose token lives in LaTabdhir's `.env.discord`): `#majlisna-uptime` (Kuma notification 2: availability), `#majlisna-errors` (Bugsink), `#majlisna-deployments` (CI failures and recoveries on main: `.github/workflows/discord-ci.yml` + `.github/scripts/ci_alert.py`, secret `DISCORD_CI_WEBHOOK`; green runs are quiet), `#majlisna-backups` (each nightly backup's summary, `DISCORD_WEBHOOK` in the server's `/home/ubuntu/majlisna-backups/secrets.env`). Dokploy's deploy notifications go to the shared `#server-deployments`. Channels are private (owner, bot role, `@everyone` denied); webhook URLs are secrets, never in git. Delivery test: `gh workflow run discord-ci.yml -f run_id=<completed main run>`.
- **Beszel**: host metrics (CPU, memory, disk).
- **Trivy**: CI-only vulnerability scanner, pinned to a commit SHA. Scans the lockfiles (`security-scan`) and the built backend image (`backend-image`; the frontend image is not scanned); a CRITICAL with a released fix fails the job and blocks `promote`, everything else is reported only.

## Games

### Undercover
- 3-12 players
- Roles: Civilian, Undercover, Mr. White
- Each player gets an Islamic term; undercover gets a different one
- Vote to eliminate the undercover agent
- **Mr. White guessing**: When Mr. White is eliminated by vote, they get one chance to guess the civilian word. If correct, undercovers win. If wrong, game continues normally. Endpoint: `POST /api/v1/undercover/games/{game_id}/mr-white-guess`. The guess is the whole table's news: the turn keeps `mr_white_guess` `{word, correct}` (`word` null on a timeout) and `vote_history[].mr_white_guess` carries it to every player's verdict; `live_state[MR_WHITE_GUESS_RESULT_KEY]` `{user_id, correct}` keeps it for the stats. While the guess is owed nobody reads a winner or the other words (the winner is only ever the recorded `state["winner"]`), and anyone else leaving does not decide the game: the guess, or its timeout, does. Tests: `test_mr_white_owing_his_guess_reads_no_winner_and_neither_word`, `test_a_departure_during_the_guess_leaves_the_guess_to_decide` (`test_undercover_game.py`), `front/src/lib/game-state.test.ts`, `e2e/tests/undercover/mr-white-guess.spec.ts`.
- A description may not be the describer's own word, in any case or in its Arabic form (`DescriptionRevealsWordError`, 400); the other side's word is allowed (refusing it would reveal it).
- **Ready system between rounds** (owner rule (d)): the same `POST /undercover/games/{id}/next-round` is the host's "next round" (opens it at once) and any other alive player's "I'm ready" (`advanced: false` + `ready_players` / `ready_count` / `ready_quorum`). The round opens when every alive player but the host is ready — every alive player when the room has no owner — or when a departure completes that quorum. The state carries the same fields plus the caller's `is_ready` while the resolved round waits. On the round-over screen (`RoundOverPanel`) the host keeps "Next round", every other alive player gets "I’m ready" (then "You are ready…"), and everyone reads "2 of 3 ready"; nothing there says "Waiting for" (the E2E helpers read that as "has voted"). The host can always force the round; an eliminated player cannot mark ready (`NotAnAlivePlayerError`). Tests: `tests/api/controllers/test_wp02_ready_quorum.py`, `front/src/components/games/undercover/__tests__/RoundOverPanel.test.tsx`, `e2e/tests/undercover/ready-quorum.spec.ts`.

### Codenames
- 4-10 players, 2 teams (Red/Blue)
- No card carries a Name of Allah (`RETIRED_CODENAMES_WORDS` in `scripts/seed_data/codenames_data.py`: Rahman, Bismillah, Masha'Allah, SubhanAllah, Alhamdulillah, In sha Allah). A card is pointed at, dyed, covered by the assassin's cloth and struck in the clue chips; `--seed` also deletes them from a database that has them.
- Roles: Spymaster, Operative
- 5x5 board of Islamic terms
- Spymaster gives one-word clues (no whitespace, never a card's own word in any case or script), operatives guess
- A team's operatives vote; the card turns once every operative still on the team has voted (a leaver's vote is dropped, and a departure can complete the vote). No passing the turn before the clue.
- Every card turned is logged in `live_state["reveal_log"]` (team, card, voters, clue turn) for the sweep_victory and assassin_finder achievements

### Word Quiz (Kalimat)
- Displayed as **Kalimat** (EN/FR) and **كلمات** (AR); the MCQ Quiz is **The Quiz** / **Le Quiz** / **مسائل**; Undercover and Codenames are written phonetically in Arabic (**أندركفر**, **كودنيمز**), and so are the roles (**سيفيليان**, **أندركفر**, **مستر وايت**, **سبايماستر**, **أوبريتيف**; French keeps the English role names: Civilian, Undercover, Mr. White, Spymaster, Operative; glossary in `DESIGN.md` §10). Codenames teams are the plain colour: Red / Blue, Rouge / Bleue, الأحمر / الأزرق. Visual system: root `DESIGN.md`.
- 1+ players (solo or group)
- Progressive hint system: 6 hints revealed every N seconds (vague → specific)
- Players type answers — faster = more points (hint 1 = 6pts, hint 6 = 1pt)
- **A wrong try costs one rung** (`WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY`: 4 misses then the word at hint 1 pays 2, never below 1) and a round allows **at most 5 tries** (`WORDQUIZ_MAX_ATTEMPTS_PER_ROUND`; the next answers 409 `AnswerAttemptsExhaustedError`). The ladder on screen stays the table's; the state carries `my_attempts_left`, `my_rungs_lost`, `max_attempts`. The answer field counts the tries left and closes at 0, the 409 is said in the field, and "worth N points now" counts the rungs lost (`AnswerInput`, `use-wordquiz-game.ts`; front/CLAUDE.md). A player out of tries is done with the round. Tests: the "WP-10" sections of `tests/api/controllers/test_wordquiz_game.py`, `front/src/components/games/wordquiz/wp26-tries-left.test.tsx`, `e2e/tests/wordquiz/tries.spec.ts`
- **When a score rewards speed, a wrong try must cost something** (as here and in the word of the day), or walking the theme's words at hint 1 pays full marks; and every scoring endpoint is rate-limited per signed-in user (`WORDQUIZ_ANSWER_RATE_LIMIT`, `DAILY_WORD_GUESS_RATE_LIMIT`, `user_or_ip_key`; `tests/api/routes/test_wp11_game_route_limits.py`, `tests/api/routes/test_daily_word.py`). The limit only protects the server: the cost is what keeps a script from paying
- Multiple rounds, highest score wins — **quiz winners (owner rule (a), both quizzes)**: every top scorer with a score above 0 shares the win; a 0-0 game has no winner; a solo game is never a win — nor a loss: it is played, no result, streak untouched (reviews R4, INT-03) — and "solo" is counted over the FINAL roster, leavers excluded (a game everyone else left is a solo game, which also stops win farming with a second account that leaves) (`game_end_stats.top_score_winners`, `MIN_PLAYERS_FOR_A_WIN`). `state["winner"]` names a player only when exactly one won (null for a shared win, a 0-0 or a solo game); `winner_ids` holds them all at game over. Tests: `test_wp00_contracts.py` (the `top_score_winners` cases), `test_game_end_stats.py`, `test_quiz_dropout.py`, `e2e/tests/stats/quiz-history.spec.ts`
- Answer matching: Arabic diacritics stripped, case-insensitive, whitespace-normalized
- Trilingual hints (EN, FR, AR) with `QuizWord` model
- The state carries the word's theme as a key (`category`: prophets, companions, places, quran, islamic_history, islamic_concepts, daily_life — the client words it)
- Round results say what each player typed (`typed_answer`: the answer that found it, else their last wrong try) and `attempts`; only from the results phase on, never while the round is open
- **Ready system**: Non-host players can mark themselves as ready for next round. Round advances when every player but the host is ready (every player when the room has no owner) OR the host overrides.

### MCQ Quiz
- 1+ players (solo or group)
- Multiple choice questions with 4 answer choices per question
- Configurable timer (default 15s) and number of rounds (default 10)
- One attempt per round — answer locks in on submit
- The round goes to results once everyone still playing has answered — also when the last player still owing an answer leaves (Word Quiz: once everyone left has found the word); while paused, at the resume
- **Time-based scoring**: 1 base point + up to 2 bonus points for fast answers (1-3 points total)
- **No spoiler before the reveal**: points are earned at lock-in, but while the question is open every state shows the scores as they stood before the round (`current_round_points`/`my_points` 0); the reveal (`choice_tallies`, `my_choice_index`, `my_answer_time_ms`, per-row `choice_index`/`answer_time_ms`) comes from the server once the round resolves, so it survives a reload
- Shows explanation after each round
- 609 trilingual questions (EN, FR, AR) across 8 Islamic knowledge categories (count them: `len(MCQ_QUESTIONS)` in `scripts/seed_data/mcqquiz_data.py`; `--seed` retires a question that leaves the data)
- Prophet names use Arabic transliteration (e.g., "Yunus" not "Jonah")
- `McqQuestion` model with JSON columns for multilingual choices and explanations
- **Ready system**: Non-host players can mark themselves as ready for next round. Round advances when every player but the host is ready (every player when the room has no owner) OR the host overrides.

### Prayer Pause (All Games)
- The host pauses for the adhan and resumes after the prayer; nothing moves and no clock runs in between
- Every timer keeps exactly the time it had left; the Word Quiz hint ladder and the MCQ speed bonus stand still too
- Phones that lock during the prayer keep their seat for 45 min; past 45 min of pause any player may resume

### Kunnash (All Games but MCQ)
- After a game, players keep its words in their notebook (كُنّاش): Undercover's two words, the 25 Codenames board words, every Kalimat round's word
- Each kept word shows its Arabic (vocalised where certain) and its meaning in the player's language
- The word of the day can be kept too, once found or given up

### Word of the day (Kalimat al-yawm, كلمة اليوم)
- A daily solo puzzle on the Kalimat words: one word a day, the same for everyone; the day turns at midnight in Makkah
- Hint 1 is free; each further hint (up to 6) costs a point: found at hint N scores 7 − N (6 down to 1), giving up scores 0 and shows the word
- Answers in any language or script, matched exactly like Kalimat; every try is counted, and a wrong one opens the next hint (it costs the point a hint costs; on the last rung tries are free)
- Streak: consecutive days found (a give-up ends it); best streak; how many players found it today
- Signed-out visitors see the number, the theme and hint 1; playing needs an account
- The page is `/today`: Kalimat's ladder, its next rung offering "Another hint: 5 points instead of 6", the answer field, the tries, Give up behind a confirmation; once over, a reveal card in the arch (the vocalised Arabic, the word, its meaning, how it went, the streaks, Keep in your kunnash, Share — a plain line without the answer — and the countdown to the next word)
- The home page shows the day's number, theme and hint 1 in a card that leads to `/today` (a player under way sees the hint they reached and "Continue"; once over, how it went)

### Hint System (All Games)
- Words have multilingual hints (JSON `hint` column: `{en, ar, fr}`)
- Hints shown via Info icon popover (HintButton component)
- Hint usage tracked in `live_state.hint_usage` for achievements
- `POST /{undercover|codenames|wordquiz}/games/{game_id}/hint-viewed` records unique views, rate-limited per user (`HINT_VIEW_RATE_LIMIT`). Undercover and Codenames take only a participant (`_require_participant`, 403 otherwise) and only a word the caller can see (their own word; a card their role may open), at most `HINT_USAGE_MAX_WORDS_PER_USER` per user; anything else answers `recorded: false` and writes nothing. Word Quiz records the current round number once per caller (bounded by the rounds) and does not check participation yet (see `backend/CLAUDE.md`)
- Game over screen shows all word explanations
- `utils/multilingual.resolve_multilingual(data, lang)` is the one fallback chain: `normalize_lang(lang)` → `en` → first value

## Git Conventions

**CRITICAL: Never commit unless the user explicitly asks you to.** Do not auto-commit after completing work.

Use Conventional Commits with emojis:
- `feat(auth): ✨ add JWT refresh endpoint`
- `fix(game): 🐛 fix vote counting in undercover`
- `refactor(models): ♻️ migrate to async database`

**IMPORTANT**: Do NOT add `Co-Authored-By` lines or any AI attribution to commit messages.

## Test Accounts (dev and E2E databases ONLY)

These accounts are created by `generate_fake_data.py --create-db`, and their passwords are in
this public repository, so **they must not exist in production**. Production refuses
`--create-db` (exit 2), and the seed residue a past run left there (these accounts among 31
seeded ones, all email-verified; INFRA-03, PD-03) is removed by `scripts/purge_seed_data.py`,
which the operator runs after a verified dump. "Admin" here is a label: admin rights come only
from `ADMIN_EMAILS` (set in Dokploy, never in code) plus a verified email.

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@test.com | admin123 |
| User | user@test.com | user1234 |
| Player | player@test.com | player123 |

## Infrastructure Gotchas

### nginx `add_header` is not inherited into a location that has its own

`front/nginx.conf` keeps the security headers in `front/security-headers.conf` and
`include`s that file in **every** `location` block. nginx inherits `add_header`
from the parent level *only if the current level declares none of its own* — and
both `location /` (which serves index.html) and the static-asset location set
their own `Cache-Control` via `add_header`. A single server-level block therefore
shipped index.html and every JS/CSS asset with **no** X-Frame-Options, no nosniff
and no HSTS. If you add a `location`, include the file in it.

The CSP there is enforced, and its build-time values are substituted by the frontend
Dockerfile: the Umami, Sentry and API origins (plus the API's `ws(s)://` origin) from the
build args, and the sha256 of every inline `<script>` of the built `index.html`
(`front/scripts/csp-inline-hashes.mjs`). `script-src` has no `'unsafe-inline'` and
`connect-src` no blanket `ws: wss:`. The hashes are computed from the BUILT `dist/index.html`
at image build, so a new or edited inline script is allowed only by a rebuilt image (never by
editing the policy by hand), and `e2e/tests/smoke/csp.spec.ts` must stay clean. See
front/CLAUDE.md.

### nginx upstreams on a shared Docker network

On `dokploy-network` the name `backend` resolved to three projects' backend containers, and
nginx resolved it once at start, so it kept a stale address list and a recreated backend was
unreachable through it (PD-08). The frontend's nginx reaches the backend as `majlisna-api`, an
alias the backend carries on its project's own network in all three compose files, resolved per
request (`resolver 127.0.0.11 valid=10s` plus a variable in `proxy_pass`). Any new upstream on a
shared network gets a project-unique alias and the resolver. No test covers it (the E2E stack
has one project on its network): check `front/nginx.conf` and the three compose files together.

### Unhashed public files must not match the immutable asset rule

`front/nginx.conf` makes only `location ^~ /assets/` (Vite's content-hashed output) immutable
for a year. Every file from `public/` keeps its name across releases: `/sw.js` is `no-cache`
(an immutable worker could sit at Cloudflare's edge for a year), the skies (`/sky/`) get a week,
and every other static file (favicon, icons, og-image, `souhib.jpeg`, anything added later) a
day. The extension regex used to make all of them immutable. Every location includes
`security-headers.conf`. The copies Cloudflare cached under the old one-year rule stay at
the edge until purged: the deploy that ships this rule needs one purge of `/sw.js` and the
public files. So the cache rules are: `sw.js` and `index.html` `no-cache`; favicons, icons,
the manifest and og-image a short max-age; the immutable one-year rule for the hashed
`/assets` only. Test: `e2e/tests/smoke/cache-headers.spec.ts`.

### Published container ports are bound to loopback

`docker-compose.dokploy.yml` publishes backend and frontend on `127.0.0.1:` only.
A `0.0.0.0` publish let anyone reach the API directly at `SERVER_IP:33648`,
bypassing Cloudflare (WAF) and Traefik — and because uvicorn ran with
`--forwarded-allow-ips '*'`, a direct caller could spoof `X-Forwarded-For` and defeat
every slowapi rate limit. Traefik reaches the containers over `dokploy-network`, so
no public host port is needed. This is the same class of hole already documented
for the monitoring stack ("direct IP:31xxx access bypassed authentication").

### uvicorn trusts proxy headers from Docker-network peers only

The backend image passes `--forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-…}"`, default
`127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` (`ENV` in `backend/Dockerfile`, and the
CMD's own `:-` fallback for an empty value; overridable from compose, which passes
`FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-}`). Never a bare `FORWARDED_ALLOW_IPS:` with no
value in a compose file: the engine then UNSETS the variable, ENV default included, and the
CMD used to pass `--forwarded-allow-ips ""` — uvicorn trusted no proxy and every anonymous
per-IP limit became one bucket keyed on Traefik (review INT-01). With `'*'` uvicorn took the LEFT-MOST `X-Forwarded-For`
entry, which the client writes, so every per-IP rate limit was keyed on a value of the
caller's choosing (SEC F03, INFRA-07, PD-07). Now the client is the first untrusted hop
from the right: the Cloudflare edge for proxied traffic, the real peer for a direct hit.
The limiter reads `CF-Connecting-IP` only from a Cloudflare peer (WP-17). Never add a
Cloudflare range or `*` to the list; a list that misses the proxy's network puts every
visitor in one bucket, so check one request's `client_ip` in the logs after changing it.
`backend/tests/api/test_trusted_proxies.py` runs uvicorn's middleware with the
Dockerfile's own value, and resolves the container's environment from
`docker-compose.dokploy.yml` with Dokploy setting nothing. After the deploy, check
`docker exec majlisna-backend sh -c 'tr "\0" " " </proc/1/cmdline'` with one request's
`client_ip`.

### E2E gate exit status

`e2e/run-local.sh` must capture `PIPESTATUS[0]` immediately after the Playwright/tee
pipeline. An enclosing `if` resets that array and previously let a failed browser
suite return success. `e2e/test-run-local.sh` checks clean, failed and flaky outcomes
with mock executables; CI runs it before the real full suite. Do not weaken either.
