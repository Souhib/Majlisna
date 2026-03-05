# IPG (Islamic Party Games)

A real-time multiplayer platform for Islamized versions of popular party games. Learn about Islamic words, prophets, and concepts while playing with friends.

## Overview

IPG brings together classic social deduction and word games, reimagined with Islamic terminology and themes. Players join rooms, get assigned roles, and compete in real-time using Socket.IO for instant communication.

### Key Features

- **Real-time Multiplayer**: Socket.IO-powered gameplay with instant state synchronization across all players
- **Two Games**: Undercover (social deduction, 3-12 players) and Codenames (team word game, 4-10 players)
- **Islamic Terminology**: All game words drawn from Islamic concepts, prophets, places, and terms
- **Room System**: Create/join password-protected rooms, invite friends, manage game settings
- **Player Statistics**: Track wins, games played, achievements, and leaderboard rankings
- **Achievements**: Unlock badges for milestones (first win, win streaks, role-specific feats)
- **Internationalization**: English and Arabic (RTL) with full bidirectional support
- **Light/Dark Mode**: Emerald green + gold themed UI with automatic dark mode

### Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.12, FastAPI, SQLModel, SQLAlchemy (async), python-socketio |
| **Database** | PostgreSQL (prod), SQLite (dev) |
| **Cache/State** | Redis (aredis_om for real-time game state) |
| **Auth** | JWT (python-jose, bcrypt) |
| **Frontend** | React 19, TypeScript, TanStack Router/Query, Tailwind v4, shadcn/ui |
| **Real-time** | Socket.IO (server + client) |
| **API Codegen** | Kubb (OpenAPI -> React Query hooks) |
| **i18n** | i18next (English + Arabic with RTL) |
| **Testing** | pytest (backend), Vitest (frontend), Playwright (E2E) |
| **CI/CD** | GitHub Actions (self-hosted runner on VPS) |
| **Deployment** | Docker + Dokploy (Oracle Cloud VPS) |

## Quick Start

### Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) runtime
- PostgreSQL (or SQLite for local development)
- Redis

### Backend

```bash
cd backend
uv sync --dev
cp .env.example .env.development
# Edit .env.development with your config
echo "IPG_ENV=development" > .env
uv run python main.py
```

API available at `http://localhost:5000`

### Frontend

```bash
cd front
bun install
bun dev
```

Frontend available at `http://localhost:3000`

### Docker (all services)

```bash
docker compose up -d
```

This starts PostgreSQL, Redis (with RedisInsight), backend, and frontend.

| Service | URL |
|---------|-----|
| Backend API | `http://localhost:5051` |
| Frontend | `http://localhost:3051` |
| RedisInsight | `http://localhost:8011` |

### Generate Test Data

```bash
cd backend

# Create tables and seed with test users, games, words, achievements
PYTHONPATH=. uv run python scripts/generate_fake_data.py --create-db

# Delete all data
PYTHONPATH=. uv run python scripts/generate_fake_data.py --delete
```

### Test Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@test.com` | `admin123` |
| User | `user@test.com` | `user1234` |
| Player | `player@test.com` | `player123` |

## Games

### Undercover (3-12 players)

Social deduction game where each player receives an Islamic term. The undercover agent receives a *different but related* term and must blend in during discussion rounds. Civilians vote to find and eliminate the undercover.

**Roles:**
- **Civilian** — Receives the majority word, tries to identify the undercover
- **Undercover** — Receives a similar but different word, tries to stay hidden
- **Mr. White** — Receives no word at all, bluffs entirely (not present in 3-player games)

**Flow:** Discuss -> Vote -> Eliminate -> Repeat until a team wins

### Codenames (4-10 players)

Two teams (Red and Blue) compete to identify their agents on a 5x5 board of Islamic terms. Each team has a Spymaster who gives one-word clues and a number, and Operatives who guess which cards match.

**Roles:**
- **Spymaster** — Sees the key card, gives clues
- **Operative** — Guesses cards based on the Spymaster's clue

**Flow:** Spymaster gives clue -> Operatives guess -> Turn passes -> Repeat until a team wins

## Architecture

### Monorepo Structure

```
IPG/
├── backend/                    # FastAPI + Socket.IO
│   ├── ipg/
│   │   ├── api/               # REST API
│   │   │   ├── controllers/   # Business logic
│   │   │   ├── models/        # SQLModel DB tables
│   │   │   ├── schemas/       # Pydantic request/response models
│   │   │   ├── routes/        # FastAPI routers (thin, delegate to controllers)
│   │   │   ├── services/      # External integrations
│   │   │   ├── constants.py   # All magic values
│   │   │   └── middleware.py  # Security, request ID, logging (pure ASGI)
│   │   ├── socketio/          # Real-time game events
│   │   │   ├── controllers/   # Game logic (undercover, codenames)
│   │   │   ├── models/        # Redis OM game state models
│   │   │   └── routes/        # Socket.IO event handlers
│   │   ├── app.py             # FastAPI app factory
│   │   ├── database.py        # Async SQLAlchemy engine
│   │   ├── dependencies.py    # DI with Annotated + Depends
│   │   └── settings.py        # Multi-env pydantic-settings
│   ├── tests/                 # pytest suite (425+ tests)
│   ├── scripts/               # Fake data generation
│   └── main.py                # Entry point
├── front/                     # React 19 SPA
│   ├── src/
│   │   ├── api/               # ky HTTP client + Kubb generated hooks
│   │   ├── components/        # UI components (shadcn/ui)
│   │   ├── hooks/             # Socket.IO, auth hooks
│   │   ├── i18n/              # English + Arabic translations
│   │   ├── lib/               # Utilities (cn, socket, auth)
│   │   ├── providers/         # Auth, Query, Theme providers
│   │   └── routes/            # TanStack Router (file-based)
│   └── vite.config.ts
├── e2e/                       # Playwright E2E tests (125+ tests)
│   ├── tests/
│   │   ├── auth/              # Login, register, token refresh
│   │   ├── rooms/             # Room CRUD, join/leave
│   │   ├── undercover/        # Full game flows, multi-round
│   │   ├── codenames/         # Full game flows
│   │   ├── cross-flow/        # Cross-game interactions
│   │   ├── profile/           # User profile, stats
│   │   └── smoke/             # Health checks
│   ├── helpers/               # Shared test utilities
│   └── playwright.config.ts
├── docker-compose.yml          # Local development
├── docker-compose.dokploy.yml  # Production (Dokploy on Oracle VPS)
└── .github/workflows/          # CI/CD pipelines
```

### Backend Design

- **Route -> Controller -> Model**: No business logic in routes — routes delegate everything to controllers
- **Async Everything**: All database operations and external calls are async
- **Dependency Injection**: FastAPI's `Depends()` with `Annotated` type hints
- **REST + Socket.IO**: REST API for CRUD operations, Socket.IO for real-time game events
- **Redis Game State**: Active game state lives in Redis (aredis_om), persistent data in PostgreSQL

### Deployment Environments

| Environment | Infrastructure | Backend | Frontend |
|-------------|---------------|---------|----------|
| **Production** | Oracle Cloud VPS + Docker + Dokploy | `:33648` | `:30819` |
| **E2E Testing** | Docker Compose (isolated stack) | `localhost:5049` | `localhost:3049` |
| **Local Dev** | Docker Compose or bare metal | `localhost:5000` | `localhost:3000` |

### CI/CD

A GitHub Actions workflow on push to `main` (self-hosted runner on the VPS):

1. **Detect changes** — Path-based diff determines which components changed (backend/frontend)
2. **Rsync** — Syncs code to the Dokploy compose directory on the VPS
3. **Build & Deploy** — Selectively rebuilds only changed services (`docker compose up --build --no-deps`)
4. **Health check** — Polls `GET /health` (6 attempts, 60s total)
5. **Cleanup** — Prunes old Docker images

On pull requests, lint and test checks run (informational, non-blocking).

## Development

### Backend

```bash
cd backend

uv run python main.py                    # Start server on :5000
uv run poe lint                          # Ruff lint
uv run poe format                        # Ruff format
uv run poe check                         # All checks (lint + format + type)
uv run poe test                          # pytest with coverage
uv run poe test-fast                     # Stop on first failure
```

### Frontend

```bash
cd front

bun dev                                  # Dev server on :3000
bun run generate                         # Generate API client (backend must be running)
bun run lint                             # oxlint
bun run typecheck                        # TypeScript strict
bun run format                           # oxfmt
bun run test                             # Vitest
bun run test:coverage                    # With coverage
```

### E2E Tests

```bash
cd e2e

# Start the E2E Docker stack
bun run docker:up

# Run full suite (125+ tests, ~20 min)
bun run test

# Run specific test suites
bun run test:smoke
bun run test:auth
bun run test:rooms
bun run test:undercover
bun run test:codenames
bun run test:cross-flow
bun run test:profile

# Run in parallel (2 shards with account pools)
bun run test:parallel

# View HTML report
bun run report

# Tear down
bun run docker:down
```

### Environment Configuration

The backend uses `IPG_ENV` to select which `.env.{env}` file to load:

| File | Purpose |
|------|---------|
| `backend/.env` | Selector: `IPG_ENV=development` |
| `backend/.env.development` | Local dev config (SQLite, local Redis) |
| `backend/.env.production` | Production config (PostgreSQL, Redis service) |
| `backend/.env.example` | Reference template (committed) |

## API Documentation

- **Scalar UI**: `http://localhost:5000/scalar`
- **OpenAPI JSON**: `http://localhost:5000/openapi.json`
- **Health check**: `http://localhost:5000/health`

## Git Conventions

[Conventional Commits](https://www.conventionalcommits.org/) with emojis:

```
feat(auth): ✨ add JWT token refresh endpoint
fix(game): 🐛 fix vote counting in undercover
refactor(models): ♻️ migrate to async database
perf(socket): ⚡ throttle Redis TTL refreshes
ci: 🚀 add GitHub Actions CI/CD pipeline
```

## License

This project is proprietary and confidential.

---

Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Socket.IO](https://socket.io/)
