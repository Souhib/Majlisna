# CLAUDE.md - Majlisna Backend

## Overview

FastAPI backend for real-time multiplayer Islamic board games. Uses SQLModel/SQLAlchemy async for database operations. Game state stored as JSON in PostgreSQL (`Game.live_state` column). REST endpoints for mutations + Socket.IO for real-time state notifications. PgBouncer for connection pooling, Redis for Socket.IO cross-worker pub/sub and the slowapi rate-limit counters only.

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

# PostgreSQL run (what CI runs; required before calling backend tests green)
uv run pytest --use-postgres

# Game content only: upserts, safe on every database, production included
PYTHONPATH=. uv run python scripts/generate_fake_data.py --seed

# Fake data: dev and E2E databases ONLY (production refuses both, exit 2; see
# "Migrations (Alembic)" below)

# Migrations (PostgreSQL only; the app runs them at boot). See "Migrations (Alembic)".
export DATABASE_URL=postgresql+asyncpg://...     # a throwaway PostgreSQL 16
uv run alembic revision --autogenerate -m "add x to y"
uv run alembic upgrade head && uv run alembic check
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
│   ├── user.py        # User CRUD + username_is_taken / username_claim_lock (per-name advisory lock)
│   ├── room.py        # Room management + heartbeat + share links
│   ├── game.py        # Game lifecycle
│   ├── undercover.py  # Undercover word/term pairs
│   ├── codenames.py   # Codenames words/packs
│   ├── wordquiz.py    # QuizWord model (word_en/ar/fr, accepted_answers, hints JSON)
│   ├── mcqquiz.py     # McqQuestion model (trilingual questions, JSON choices/explanations)
│   ├── undercover_game.py # Undercover game logic (extends BaseGameController)
│   ├── codenames_game.py  # Codenames game logic (extends BaseGameController)
│   ├── codenames_helpers.py # Board builder, player assigner, turn rules on live_state (votes, reveals + reveal log, departures)
│   ├── wordquiz.py        # QuizWord CRUD (get_random_words, create, delete)
│   ├── wordquiz_game.py   # Word Quiz game logic (extends BaseGameController)
│   ├── mcqquiz.py         # McqQuestion CRUD (get_random_questions)
│   ├── mcqquiz_game.py    # MCQ Quiz game logic (extends BaseGameController)
│   ├── game_lock.py   # PostgreSQL advisory locks per game_id (asyncio.Lock fallback for SQLite)
│   ├── disconnect.py  # Disconnect/departure handlers (used by kick_player, ban_player, leave_room; includes _handle_mcqquiz_disconnect)
│   ├── game_cancel.py # cancel_running_game / detach_room_if_current (models only: no room/disconnect import)
│   ├── token_auth.py  # authenticate_caller / authenticate_access_token: the ONE place an access token (and its session) becomes a User (HTTP + Socket.IO)
│   ├── quiz_rules.py  # Quiz round rules shared with disconnect: everyone_has_answered, results transitions, settle
│   ├── stats.py       # User statistics
│   ├── term_script.py # Arabic forms of game terms: batched get_forms + seed upsert
│   ├── notebook.py    # The Kunnash: words kept from finished games (keep / list / delete)
│   ├── daily_word.py  # The word of the day: lazy daily draw, the caller's play (hint / guess / give up / keep)
│   ├── riddle.py      # Samar riddles: rung 1 of a random QuizWord for a waiting table (never a spoiler)
│   └── achievement.py # Achievement tracking + seeding
├── models/            # SQLModel DB tables ONLY
│   ├── table.py       # User, Room, Game, Event tables
│   ├── game.py        # GameStatus enum, GameBase with live_state JSON
│   ├── relationship.py # Link tables (RoomUserLink with last_seen_at)
│   ├── undercover.py  # Word, TermPair tables
│   ├── codenames.py   # CodenamesWord, CodenamesWordPack
│   ├── term_script.py # TermScript (Latin term → ar, ar_vocalized)
│   ├── notebook.py    # NotebookEntry + NotebookGameType (the Kunnash)
│   ├── daily_word.py  # DailyWord (one QuizWord per Makkah day) + DailyWordPlay (one per user per day)
│   ├── room_ban.py    # RoomBan: a BANNED player may not come back to that room until lifted (a kick writes none)
│   ├── room_invite.py # RoomInvite: a friend's invite, stored, accepted by id without the PIN
│   ├── room_removal.py # RoomRemoval: the host removed (kicked) a player, who may still be banned without a seat
│   ├── auth_session.py # AuthSession (the tokens' `sid`) + revoke_user_sessions (SEC F01)
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
│   ├── daily_word.py  # /api/v1/daily-word (public GET; hint, guess, give-up, keep)
│   ├── riddle.py      # /api/v1/rooms/{room_id}/riddle (members only, per-user limit)
│   └── stats.py       # /api/v1/users/{id}/stats, achievements, leaderboard
├── ws/                # Socket.IO real-time notification layer
│   ├── __init__.py    # Exports sio, socketio_app
│   ├── server.py      # AsyncServer with Redis adapter + the handshake's origin list (socket_allowed_origins)
│   ├── handlers.py    # connect (JWT auth), join_game, disconnect, auto_join_game_room
│   ├── state.py       # Thin wrappers: fetch_room_state, fetch_game_state (reuse controllers)
│   └── notify.py      # notify_room_changed, notify_game_changed (best-effort broadcast)
├── utils/             # Pure helpers (rng, draw, text_match, multilingual, game_state, game_pause, cursor, daily_word, dialect)
├── constants.py       # All magic values
├── rate_limit.py      # slowapi limiter, keys (client_ip_key behind Cloudflare, user_or_ip_key, refresh_sub_key), 429 envelope handler
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
- **A socket can be gone by the time a handler's database read returns.** python-engineio's
  `save_session` then raises `KeyError('Session not found')`; `join_game` saves through
  `handlers._save_session_of_live_socket` and stops there (no room entered for a dead sid,
  no heartbeat, no state). It escaped as "Task exception was never retrieved", an ERROR on
  every page that navigated away mid-join (seen in the E2E gate's backend log;
  `test_handlers.py::test_join_game_for_a_socket_gone_mid_join_stops_quietly`). Likewise
  a player who leaves between `join_game`'s seat check and its state read is refused by
  the game's own `get_state` (a 4xx, already logged at INFO by `BaseError`):
  `ws/state.fetch_game_state` sends nothing and logs at ERROR only a failure of 500 or
  above or a non-`BaseError` exception (`test_notify.py::test_fetch_game_state_for_a_player_no_longer_in_the_game_is_no_server_error`).
- **Game start routes call `await auto_join_game_room(game_id, room_id)`** before emitting notifications. This auto-joins all connected room members into `game:{game_id}` Socket.IO room, eliminating the race where `game_updated` fires before clients call `join_game`.
- **`sio.enter_room()` MUST be awaited.** It is an async coroutine in python-socketio. Calling without `await` creates a dangling coroutine that silently never executes — the SID never joins the room and misses all broadcasts. This applies to all `sio.enter_room()` calls in handlers.
- PostgreSQL is the ONLY source of truth. Redis is ONLY for Socket.IO adapter cross-worker pub/sub (and, in db 1, slowapi's rate-limit counters, `RATE_LIMIT_STORAGE_URI`). With Redis down the limits fall back to each worker's memory (`rate_limit.build_limiter`, `in_memory_fallback_enabled`) and go back to Redis once it answers: slowapi's default raised, and every limited route — sign-in, joins, the game routes — answered 500 (review INT-02; `tests/api/test_rate_limit.py::test_a_rate_limit_storage_outage_keeps_the_route_working_and_limited`).
- ZERO game state in Redis. No TTL watchers, no Redis OM.
- Notify functions log errors but don't raise — if a broadcast fails, the REST response still succeeds.
- `notify_game_changed` sends a lightweight `game_updated` signal. Each client invalidates its TanStack Query cache, triggering a REST re-fetch of its own role-aware state.
- **A timer-expired call that changed nothing broadcasts nothing** (BDP-03, SEC F08). Every
  page fires timer-expired from its own clock, so a table of N sends N calls per deadline;
  the routes broadcast every one, and each client got N `game_updated` (N refetches) for one
  change — storm.py measured 100 pushes for 10 clients. The four routes call
  `notify_timer_outcome(game_id, result.action)`, which skips `NO_OP_TIMER_ACTIONS`
  (`paused`, `timer_not_expired`, `not_playing`, `round_already_resolved`, `none`). Only a
  true no-op may enter that set; a new `TimerExpiredAction` that changes the game must stay
  out of it. Every other mutation still notifies (room state included), and so does
  Undercover's next-round on both outcomes: a ready mark changes the count the table shows.
  `_get_room_id_for_game` selects `Game.room_id` alone, never the row with its `live_state`.
  Tests: `tests/api/routes/test_timer_expired_notify.py` (the real stack; 10 concurrent
  calls → one `game_updated` per client), `tests/api/ws/test_notify.py`.
- **The handshake checks the browser's Origin** (SEC F12): `cors_allowed_origins` is
  `ws/server.socket_allowed_origins(settings)` — `CORS_ORIGINS` plus `FRONTEND_URL`,
  reduced to `scheme://host[:port]`, de-duplicated; a `*` keeps allow-all (development).
  It was `[]`, which in python-engineio switches the check OFF (not "same origin", as the
  comment said): any page could open a socket. `FRONTEND_URL` is always added because the
  page connects to its own origin and a same-origin deployment need not list it in
  CORS_ORIGINS — **in production FRONTEND_URL must be the page's origin
  (`https://majlisna.app`), or every socket is refused.** The list is logged once at
  startup. A request without Origin (a native client) is not checked. The FastAPI
  CORSMiddleware wraps the `/socket.io` mount as well, so a cross-origin POLLING client
  would get `Access-Control-Allow-Origin` twice; no client does (every page connects to
  its own origin). Tests: `tests/api/ws/test_wp11_socket_origin.py`.
- Socket.IO handlers are thin wrappers, NOT new controllers. They reuse `RoomController.get_room_state()`, `UndercoverGameController.get_state()`, `CodenamesGameController.get_board()`.
- Broadcasts go to Socket.IO rooms (`room:{room_id}`, `game:{game_id}`), NEVER to individual SIDs (except for per-user game state).
- **The room state goes to each member's own channel, never to `room:{room_id}`** (review R2):
  `notify_room_changed` emits once to `[member_channel(room_id, user_id) for each player and
  spectator the state lists]` (`member:{room_id}:{user_id}`, entered by `connect`). It carries
  the PIN, which a ban rotates so the banned player cannot come back, and a removed socket held
  by ANOTHER worker stays in `room:{room_id}` until that worker's audit tick, up to 5 s after
  the ban route's own push of the new PIN. A socket whose seat is gone is never listed, so
  never addressed, whichever worker holds it. Chat, `game_updated` and `member_removed_by_host`
  still go to `room:{room_id}` (none carries the PIN). Test:
  `tests/api/ws/test_wp04_reconnect_and_detach.py::test_the_ban_routes_own_push_never_hands_the_new_pin_to_a_socket_held_elsewhere`.
- **A socket lives no longer than its session** (review R5): every socket's `AuthSession` id
  is kept per process (`handlers._socket_sessions`, personal and room sockets; a legacy token
  has none), and every worker's tick (`audit_local_socket_memberships`) cuts, in ONE query,
  each local socket whose session is revoked, past `expires_at` or gone — off every channel
  first, then disconnected. The session was checked at connect only, so after a reset the
  thief's open personal socket kept receiving the victim's invites (then code and PIN; an
  invite is now its id, the code and the inviter). Test:
  `test_wp17_sessions.py::test_a_socket_opened_before_its_session_ended_is_cut_by_the_next_tick`.
- Socket.IO `disconnect` marks the user as disconnected in DB (starts grace period). A background `disconnect_checker_loop` runs every 5s (`DISCONNECT_CHECK_INTERVAL_SECONDS`) to mark stale heartbeats (`HEARTBEAT_STALE_SECONDS`, 20 s) and permanently remove users past their grace period (`GRACE_PERIOD_SECONDS`, 180 s, in a running game; `LOBBY_GRACE_PERIOD_SECONDS`, 600 s, in the lobby; 45 min while the game is paused). Multi-tab connections are deduplicated via `_user_sids` dict; `connect` records the new SID BEFORE closing the old one, and a `disconnect` whose SID has been replaced does not mark the player away (a reload used to flash "away" until the next heartbeat). `join_game` validates user membership in the room and game ownership via DB queries. The `you_were_kicked` event (`{room_id, banned}`) is emitted to `user:{user_id}` when the host kicks (`banned: false`) or bans (`banned: true`) a player.
- **Presence, the sweep and the sockets (WP-04, 2026-10 audit).** See "Departures, the sweep and the sockets" below: a return is announced to the room, one worker sweeps per tick, and every worker cuts its own sockets whose seat is gone.

### Game State in PostgreSQL

All game state stored in `Game.live_state` JSON column:
- **Undercover**: `{players, turns, civilian_word, undercover_word, phase, ...}`
- **Codenames**: `{board, players, current_team, current_turn, status, winner, ...}`
- **Word Quiz**: `{players, current_round, total_rounds, round_phase, hints, answers, attempts, current_word, ...}`
- **MCQ Quiz**: `{players, current_round, total_rounds, round_phase, question_ids, answers, ...}`
- **Every game** may also carry the shared keys of the 2026-10 audit (`left_player_ids`, `winner_ids`, `paused`, `hint_usage`, …; "Shared contracts" at the end of this file).

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
- Every way the guess closes — a guess, its timeout, the guesser leaving (a wrong guess) —
  goes through `undercover_rules.record_mr_white_guess`, which also writes
  `live_state[MR_WHITE_GUESS_RESULT_KEY] = {"user_id", "correct"}` for the end-of-game stats.
- **While the guess is owed, nobody reads a winner** (BR-01). `get_state` recomputed one
  from alive counts — no impostor alive → civilians — and built `word_explanations` from
  it, so Mr. White's own payload (REST and the `join_game` push) carried the word he was
  about to guess, and every client showed the game as over and never rendered his guess
  form. The winner is `state["winner"]`, see "The winner must be written" below.
  **Rule: `get_state` reads the winner only from `state["winner"]`; never recompute
  `winning_team()` while the game is IN_PROGRESS** — with the guess pending no impostor is
  alive, so a recompute answers "civilians" and leaks both words. The client checks
  `turn_phase` before `winner` (`front/src/lib/game-state.ts`, `deriveUndercoverPhase`).
  Tests: `test_mr_white_owing_his_guess_reads_no_winner_and_neither_word`
  (`test_undercover_game.py`: Mr. White, a civilian and a spectator),
  `front/src/lib/game-state.test.ts`.
- **Anyone else leaving during the guess decides nothing** (BR-08):
  `repair_turn_after_dropout` returns True while a guesser is still owed, so the
  departure path neither declares a winner nor cancels; the guess or its timeout decides.

### The personal Socket.IO channel, and departures that reach the game

- `connect` without `room_id` is the player's personal channel (`_connect_personal`): the
  token is checked like any other, the SID joins `user:{user_id}` only (room invites,
  `you_were_kicked`), and nothing else happens — no heartbeat, no room state. The app
  shell keeps one open on every signed-in page. It used to be refused ("Missing auth
  token or room_id"); socket.io-client never retries a refused handshake, so every invite
  answered "Invite sent" and never arrived. `join_game` ignores a personal connection.
- `PATCH /rooms/leave`, `PATCH /rooms/{id}/kick` and `POST /rooms/{id}/bans` call
  `notify_member_removed(room_id, game_id)`: `notify_game_changed` (which also re-sends the room state) when the room had
  a running game, else `notify_room_changed`. A departure mid-game eliminates the player
  and can move the turn or end the game, while game pages refetch on `game_updated` only.
  **`game_id` is read BEFORE the removal** (`get_active_game_id`, first line of the three
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

### Kick and ban (owner decision, 2 November 2026)

Two host actions; the decision replaced owner rule (c), under which every kick banned for the
room's lifetime and rotated the PIN (BR-20, SEC F04: the kick used to be undone a second later,
so it had become a ban; the owner wants both).

- **Kick** ("Remove"): `PATCH /api/v1/rooms/{room_id}/kick` `{user_id}` →
  `KickPlayerResponse`. For someone who left without quitting. `kick_player` checks host only
  (`NotRoomHostError`), never yourself (`CannotKickYourselfError`), a seat
  (`UserNotInRoomError`), writes the removal record (`_record_removal`, below), then runs
  `_handle_permanent_disconnect`, whose commit carries the record — and that is all: no
  `RoomBan`, the PIN unchanged, every invite left as it was (theirs, and those to them). They
  come back with the same code and PIN, or through an invite, and members may invite them.
- **Ban**: `POST /api/v1/rooms/{room_id}/bans` `{user_id}` (`BanPlayerRequest`) → 201
  `RoomBanView` (a resource of the bans collection, beside its `GET` and the lift's
  `DELETE /{room_id}/bans/{user_id}`). Same checks (`CannotBanYourselfError`, 400), except that
  the target is seated OR has a removal record (ban after removal, below). Everything a
  kick does, plus, staged before the departure so its single commit carries them: a `RoomBan`
  (`_insert_ban`, `ON CONFLICT DO NOTHING` on the pair, `banned_by` = the host), the room's
  invites the player SENT or was SENT deleted, and a new random PIN that differs from the old
  one (`_new_room_pin`; the banned player holds the share link and could come back under
  another account). `join_room`, `join_room_as_spectator` and `accept_invite` answer
  `RoomBannedError` (403) for a ban, checked BEFORE the PIN; `invite_friend_to_room` answers
  `InviteeBannedError` (403, `errors.api.inviteeBanned`), asked once the invitee is known to be
  the inviter's friend; `list_invites` leaves out a room that banned the caller.
- **An invite racing the ban** (READ COMMITTED: the invite's ban check and the ban's purge do
  not see each other's uncommitted rows) is closed from both ends. `invite_friend_to_room` asks
  again once its row is committed (`_take_back_if_banned_meanwhile`): a ban of the invitee or of
  the inviter committed meanwhile deletes the row and refuses the request
  (`InviteeBannedError` / `InviterNotInRoomError`), so the route pushes nothing. `ban_player`
  sweeps the player's invites to the room once more after its commit
  (`_delete_invites_involving`, a transaction of its own that holds nothing), so a row
  committed between its purge and its commit does not outlive the ban (an unban would bring it
  back). Whichever commits last sees the other.
- **Ordering inside the ban**: the `RoomBan` INSERT and the invites DELETE run BEFORE the new
  PIN is staged: a statement autoflushes, and the room's UPDATE flushed before the game lock
  deadlocked with the deciding vote
  (`test_disconnect_lock_postgres.py::test_a_kick_waiting_behind_the_deciding_vote_keeps_the_result`,
  parametrized kick and ban; see `_handle_permanent_disconnect`, "Lock order"). Any statement
  added to the ban goes before the PIN too (the sweep after the commit is no exception: it
  runs in a new transaction, with no lock held).
- `GET /rooms/{id}/bans` → `list[RoomBanView {user_id, username, banned_at}]` and
  `DELETE /rooms/{id}/bans/{user_id}` → `StatusResponse {status: "lifted"}`
  (`RoomBanNotFoundError`, 404, when absent — a kicked player has none), host only through the
  controller. Lifting neither re-seats the player nor restores the old PIN; after it, invites
  and joins work again. The rows live as long as the room (an INACTIVE room accepts no join
  anyway) and go with the user's account.
- **The routes**: both tell the player (`notify_user_kicked(user_id, room_id, banned=...)`, the
  `you_were_kicked` event `{room_id, banned}` on `user:{id}`), detach the socket
  (`remove_user_from_room_socket`), tell the room which removal it was
  (`notify_member_removed_by_host(room_id, user_id, banned=...)`, the `member_removed_by_host`
  event `{room_id, user_id, banned}` on `room:{id}`, no PIN: every member's activity line says
  "removed" or "banned", not "left"), and only THEN push the room state
  (`notify_member_removed`) — for a ban, the push carrying the new PIN; the lift route pushes
  `notify_room_changed`. That push is addressed to the members still listed
  (`notify.member_channel`), so a removed socket held by another worker never hears the new PIN
  (review R2), and every worker's audit tick cuts a socket whose seat is gone (kick) or banned.
- A friend invite is stored and carries no PIN ("Room invites: stored, accepted without the
  PIN" below), so an invite sent before a ban still opens the room for anyone else. A share
  LINK still carries the PIN of the moment it was made: the join page says the PIN may have
  changed and asks for a new link or invite (review F1).
- Both reuse `_handle_permanent_disconnect` from `disconnect.py` for game cleanup: the removed
  player of a running game is a leaver (owner rule (b)).
- No auto-disconnect — players are only removed by explicit kick, ban or leaving (and the
  grace sweep).
- The removed player's pages (the lobby AND the four game pages) go to /rooms on
  `you_were_kicked` (`useLeaveAfterKick` in the front, which notes "kicked" or "banned" for the
  notice there; "removed", which promises nothing, on the lobby's polling fallback): they are out of the room's socket rooms, so no `game_updated` reaches them any
  more. The event goes to `user:{id}`, which every room socket of the player joins too, so a page
  acts on it only for its own room (`useSocket`): a kick from a room the player had left away,
  or the ban of a removed player, reaches the page of the room they are in now.
- **Ban after removal** (owner request, 3 November 2026). A ban used to need a seat, so a host
  who pressed Remove and then decided "we don't want them back" could not ban until the player
  sat down again. Now:
  - The kick writes a `RoomRemoval` (`models/room_removal.py`, table `room_removal`, migration
    `0003_room_removal`: `room_id`, `user_id`, `removed_by` (nullable), `created_at` /
    `updated_at`; unique `uq_room_removal_room_user`, indexed `user_id` and `removed_by`).
    `_record_removal` is an upsert on the pair, so a second kick refreshes it (the latest host,
    `updated_at` = the latest removal), never a second row. It is a statement executed before
    the departure's game lock, like the ban's own: its foreign keys take KEY SHARE on the room
    and the users, which no move's UPDATE of their other columns waits on.
  - `GET /rooms/{id}/removals` (`list_removals`, host only, `NotRoomHostError` 403) →
    `list[RoomRemovalView {user_id, username, removed_at}]`, newest first (`removed_at` is the
    record's `updated_at`, UTC). It leaves out anyone banned from the room or holding a link in
    it whatever records remain: taking a seat and a ban both delete the record, the filters
    answer one a race left behind (a kick and a ban of the same player at once, then a lift).
  - `ban_player` takes the room lock (`room:{id}`) first and reads the room again under it
    (host only, again), then reads the seat (`_seat_of`), deletes the invites, then takes the
    record (`_take_removal`, `DELETE … RETURNING`, its row lock), then inserts the `RoomBan`, all
    before the PIN is staged. Seated: the ban as above (the record, if a race left one, deleted
    with it). Not seated but recorded: the same `RoomBan`, invites and new PIN, the record
    deleted, then a plain commit — no departure (they left the game when they were removed) and
    no game lock, so no move waits on it in a cycle — and the same sweep after the commit.
    Neither: if the record vanished while the DELETE waited (a return that deleted it first
    committed), the seat is read again and banned like any seat; else `UserNotInRoomError`
    (404), as for anyone never seated or gone by themselves.
  - **The room lock, because of the host's own other requests.** A close mid-game
    (`delete_room`: the game cancelled writes the room row, then the room's records are
    deleted) and the deletion of the host's account (its purge orphans the room, owner NULL, then
    nulls `removed_by` on the record) each write the room row before the record; the ban holds
    the record and writes the room row (the PIN) at its commit. Each held what the other waited
    for, and PostgreSQL killed one (a 500; found in review, 7 November 2026). `delete_room` takes
    the room lock first (`_room_and_game_locks`), and the account deletion takes the room lock of
    every room it still owns, in id order, before the purge (`UserController._owned_room_locks`):
    now one waits for the other. A ban that waited reads the room again: closed, 404 (the record
    went with the room); ownerless, `NotRoomHostError` (403), never a `RoomBan` naming a deleted
    account (a foreign-key 500).
  - Taking a seat deletes the record before it writes the link (`_end_removal`, in `_take_seat`
    — join and invite — and in the spectator's seat), then asks for a ban again: the door's ban
    check ran before the PIN, and a ban of the removed player may commit after it. That DELETE
    waits on the ban's row lock, and the read after it (READ COMMITTED) sees the committed ban:
    403. **Lock order, the same on both sides: the player's invites to the room, then the
    record.** `accept_invite` locks its invite (`FOR UPDATE`) before its seat deletes the record,
    and `_take_seat` spends the invites before `_end_removal`; the ban deletes the invites before
    `_take_removal`. The first version took the record first in the ban and in `_take_seat`: an
    accepted invite and the ban of the same removed player each held what the other waited for,
    and PostgreSQL killed one (`DeadlockDetectedError`, a 500; found in review, 7 November 2026,
    `test_an_invite_accepted_while_the_host_bans_the_removed_player_bans_the_new_seat` and
    `test_a_return_with_the_pin_by_a_player_holding_an_invite_and_their_ban_bans_the_new_seat`).
  - The record also goes with the room (`delete_room`), with the account (`_purge_user_references`
    deletes the records OF the user and nulls `removed_by` on those BY them, like `banned_by`),
    and with a seeded room (`scripts/purge_seed_data.py`).
  - The route is the ban's, unchanged: `you_were_kicked` banned (no room page of theirs takes it;
    their app shell drops that room's invites, which the ban deleted), the detach (nothing to
    detach), `member_removed_by_host` banned (the host's other devices re-read their lists), and
    `notify_member_removed` with the game read first: the room state with the new PIN, and for a
    running game a `game_updated` the game pages answer with a refetch of an unchanged game (kept
    rather than a branch in the route).
- Tests: `tests/api/controllers/test_wp07_room_bans.py` (kick vs ban: the seat, no ban and the
  same PIN for a kick, the ban and the new PIN for a ban, join and spectate, host only and never
  yourself for both, list and lift, mid-game leavers), `test_room_removals.py` (ban after
  removal: the record, its refresh, its list and filters, the seat that ends it by each door,
  the ban of a removed player with no departure, the purges, and seven races on PostgreSQL: a
  return waiting behind that ban is refused, a ban waiting behind a return bans the new seat,
  the lock order against an accepted invite and against a PIN join of a player holding an
  invite: no deadlock, the new seat banned; the room lock against a close mid-game and against
  the host's account deletion: neither fails, and a ban that waited behind the deletion is
  refused),
  `tests/api/test_migrations.py::test_0003_adds_only_the_room_removal_table_and_downgrades_to_0002`,
  `test_room_invites.py` (what each does to
  the invites, `InviteeBannedError`, a raced invite answers 403, an invite racing the ban taken
  back or swept, the list's ban filter), `test_host_only_rules.py`,
  `tests/api/routes/test_room.py` (the ban route's 201, both routes' notify order, the removals list),
  `tests/api/ws/test_notify.py` (`member_removed_by_host`), `tests/api/ws/test_wp04_reconnect_and_detach.py` (the removed socket is cut on
  every worker, kick and ban).

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

**Never sit idle inside a transaction.** Production's PostgreSQL (and the E2E stack's) runs
with `idle_in_transaction_session_timeout=60s` (`docker-compose.dokploy.yml`, BDP-13): a
session that has begun a transaction (any query autobegins one) and then awaits something
else for a minute (an outside HTTP call, a sleep, a socket emit loop) is killed by the
server, and its next statement fails. Commit or roll back before a long await. A statement
that is running, such as a game-lock wait, is not idle. The same flags log every statement
over 250 ms and preload `pg_stat_statements` (the extension itself is created by hand, once).

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
| DailyWord | daily_word | The word of the day: `day` (Makkah date, PK) → `quiz_word_id` |
| DailyWordPlay | daily_word_play | One player's go at one day's word: one row per (`user_id`, `day`) |
| RoomBan | room_ban | A player the host banned from a room (a kick writes none): one row per (`room_id`, `user_id`), `banned_by` nullable |
| AuthSession | auth_session | One signed-in device (`id` = the `sid` claim): refresh jti rotation, absolute `expires_at`, `revoked_at` |
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
- Health check: `http://localhost:5111/health` → `{status, db, timestamp, version}`.
  `version` is `settings.git_sha`: env `GIT_SHA` when it names a commit (CI's `--build-arg
  GIT_SHA`), else `/app/GIT_SHA`, the commit the image's last build step stamped (Dokploy's
  build, see "The image" below), else `"unknown"`; answered on a 503 too: CI's promote job
  waits for it to read the promoted commit (`tests/api/test_health.py`). The same value is
  the Sentry release (`app._configure_observability`; none when unknown).

### The image (`backend/Dockerfile`)

- `CMD ["sh", "-c", "exec uvicorn …"]`: `exec` makes uvicorn PID 1, so `docker stop`'s
  SIGTERM drains it (`--timeout-graceful-shutdown 15`). Never go back to a shell-form CMD
  or drop the `exec`: two shells used to swallow SIGTERM and every stop ended in SIGKILL
  after 10 s, lifespan teardown skipped. Before uvicorn has installed its handlers (the
  first seconds of boot) PID 1 ignores SIGTERM; compose's `init: true` covers that window.
- `--forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-<the ENV default>}"`, default loopback + the
  private ranges (Docker networks), never `'*'` (see root CLAUDE.md, "uvicorn trusts proxy
  headers from Docker-network peers only"; `tests/api/test_trusted_proxies.py` reads the
  Dockerfile AND `docker-compose.dokploy.yml`). The `:-` fallback is load-bearing: an empty
  value trusts no proxy and puts every anonymous visitor in Traefik's one rate-limit bucket,
  and a bare `FORWARDED_ALLOW_IPS:` in compose unsets the variable, ENV default included
  (review INT-01). Compose passes `${FORWARDED_ALLOW_IPS:-}`.
- `appuser` exists before the copies (`COPY --chown`, no `chown -R` layer); uv is only in
  the `dependencies` stage (`UV_PYTHON_DOWNLOADS=never`, so the venv uses the image's
  Python); `python:3.14-slim` and the uv image are pinned by digest.
- The image ships bytecode: `UV_COMPILE_BYTECODE=1` for the venv, `compileall` for the app.
  `PYTHONDONTWRITEBYTECODE=1` stops the container from caching `.pyc`, so without them every
  worker compiled every dependency from source at each boot (`import main` 1.5-2.5x slower),
  inside each deploy's outage. The builder installs `gcc` + `libc6-dev` only: Debian's
  `python3-dev` is Debian's Python 3.13, never this image's 3.14, which has its own headers.
- **The image stamps its own commit, in its LAST step** (3 November 2026). Dokploy passes no
  build arg, so `/health` said `"unknown"`. The first stage is an empty `FROM scratch AS
  gitmeta`; `docker-compose.dokploy.yml` overrides it with the named context `gitmeta: .`
  (the repository root of Dokploy's depth-1 clone, reduced by the root `.dockerignore` to
  `.git/HEAD`, `.git/refs`, `.git/packed-refs`). The last `RUN` bind-mounts it and runs
  `scripts/build-commit.sh <git dir> "$GIT_SHA"` (POSIX sh, no git) into `/app/GIT_SHA`:
  the build arg when it is 40 lowercase hex digits, else HEAD's commit (detached, loose ref
  or `packed-refs`), else `unknown`. `settings._resolve_git_sha` reads the file only when
  the `GIT_SHA` variable names no commit, and believes nothing but 40 hex digits. A bare
  `docker build` or the E2E compose (no context) mounts the empty stage: `unknown`, no
  error. Keep the step last: a new commit then reruns only it. `front/Dockerfile` does the
  same with its own copy of the script (kept identical by `tests/api/test_build_commit.py`).
- Coverage: CI runs `pytest --use-postgres --cov=majlisna --cov-branch --cov-fail-under=88`.
  `dependencies.py` (the auth dependencies) is measured; it used to sit in the omit list.

## Hard-Won Rules

### The owner's product rules (2026-10, binding)

Each rule is spelled out in its own section below; this is the index.

- **(a) Quiz winners**: every top scorer above 0 shares the win; a 0-0 game has no winner; a
  solo game is never a win, "solo" counted over the FINAL roster with leavers excluded
  (`game_end_stats.top_score_winners`, `MIN_PLAYERS_FOR_A_WIN`) — and never a loss either:
  played, no result, the win streak untouched, as `did_user_win` answers None for it (reviews
  R4, INT-03; the player who stayed when everyone else left is charged nothing). → "Shared
  contracts", "Kalimat".
- **(b) Leavers get neither a win nor a loss, in all four games** (`mark_player_left` on every
  departure, `scorable_players`, `did_user_win` → None). → "Shared contracts", "Departures".
- **(c) Kick and ban are two host actions** (owner decision, 2 November 2026, replacing "a kick
  bans for the room's lifetime and rotates the PIN"): a kick only takes the seat (the player may
  come back); a ban also keeps them out until the host lifts it (joins, spectating, invites),
  deletes their room invites and rotates the PIN. → "Kick and ban".
- **(d) Undercover's ready quorum between rounds**: every alive player but the host (every alive
  player without a host); the host can still force it. → "Undercover between rounds".
- **(e) Kalimat: a wrong try costs one rung, at most 5 tries a round**
  (`AnswerAttemptsExhaustedError`). → "Kalimat: a wrong try costs a rung".
- **(f, g) The five special achievements are implemented, and challenges progress at every game
  end.** → "The end-of-game flow" (each special's exact rule).

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
  `pg_advisory_xact_lock` — a *transaction-scoped* lock. Committing there
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
returns the persisted value; the derived one is only a fallback for old rows of a game
that is no longer IN_PROGRESS and whose last turn is not on the Mr. White guess — the
fallback used to run on running games too, which announced the civilians' win (and both
words) while Mr. White still owed the guess that could reverse it. A finished row whose
last turn still says `mr_white_guessing` reads `turn_phase: "game_over"`.
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

### Migrations (Alembic)

The PostgreSQL schema is the migrations' (`backend/migrations/`, `backend/alembic.ini`),
set up on 2026-11-01, once development was finished. SQLite (dev, the default test run)
keeps `create_all`: the migrations are written for PostgreSQL only, and the CLI refuses any
other URL. Until then the schema came from `create_all` at boot plus optional startup DDL
(`POSTGRES_INDEXES`, `POSTGRES_DROPPED_INDEXES`): both are gone, and so is the rule that a
schema change had to be a new table.

**Writing one.** Dev runs on SQLite, so start a throwaway PostgreSQL 16 first:

```bash
cd backend
docker run -d --name majlisna-migrate -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=postgres postgres:16-alpine
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/postgres
uv run alembic upgrade head                                 # the schema as it is today
# ... change the model(s) ...
uv run alembic revision --autogenerate -m "add x to y"     # migrations/versions/<date>_<rev>_<slug>.py
uv run alembic upgrade head && uv run alembic check        # applies, and nothing is left to write
uv run alembic downgrade -1 && uv run alembic upgrade head # the downgrade works too
docker rm -f majlisna-migrate
```

`env.py` reads `Settings` (`DIRECT_DATABASE_URL` when set, else `DATABASE_URL`) and takes
the same schema lock as the boot. A generated revision is formatted and lint-fixed by the
post-write hooks; `migrations/` is in `poe lint` / `format-check` and in CI.

1. **Read every operation autogenerate wrote, and add what it cannot see**: a new value of
   a native enum (`op.execute("ALTER TYPE notebookgametype ADD VALUE IF NOT EXISTS
   'NEW'")`: autogenerate ignores enum labels, `test_a_database_at_head_is_what_the_models_declare`
   catches the omission), an index on an expression or with a sort order (`op.create_index(...,
   [sa.text("lower(x)")])`, its name added to `constants.POSTGRES_ONLY_INDEXES`; a plain index
   is declared in its model), a rename (autogenerate sees a drop and an add:
   `op.alter_column(..., new_column_name=)`), a data step.
2. **Never edit a revision that has run on a server** (production, anyone's E2E database).
   A fix is a new revision. That includes the baseline.
3. **Additive first, destructive later.** A new column on a table with rows is nullable or
   has a `server_default`. A column the deployed code still reads is dropped one release
   after the last code that reads it (a revert redeploys the old code on the new schema); a
   rename is add, copy, then drop, across two releases. A new table that references `user` or
   `room` is additive only while it is empty: the old code does not purge it, so once it has
   rows the old account deletion (and seed purge) fails on its foreign key (no FK declares
   ON DELETE). A revert past such a release empties it first, or runs its downgrade:
   `0003_room_removal` (the kick's record) is one, `DELETE FROM room_removal` before redeploying
   the release before it.
4. **A migration must run on production's data.** A unique index or a NOT NULL on existing
   rows makes the rows fit first, in the same revision. A migration that fails fails the
   boot: the whole schema step rolls back and the workers exit, so production is down until
   a fixed image ships. **A `pg_dump` of production before deploying any migration**
   (`docs/operations/backups.md`).
5. **Locks.** Once the schema lock is held, every statement waits at most
   `SCHEMA_DDL_LOCK_TIMEOUT` (5 s) for a table lock, then the migration and the boot fail and
   the next boot tries again: a DDL statement never sits in a lock queue holding every query
   on its table behind it. `CREATE INDEX CONCURRENTLY` cannot run in the boot's transaction.
6. **Never `op.get_context().autocommit_block()`**: it commits the boot's transaction, which
   releases the schema lock in the middle of the migrations. `ALTER TYPE ... ADD VALUE` runs
   inside a transaction on PostgreSQL 16 (the new value can be used only after the commit, so
   not by a data step of the same revision).
7. **A new table** is a model registered in `models/table.py` (it imports every model, and
   `env.py` sees nothing else: `test_table_py_registers_every_model_of_the_package`), then its
   migration.

**At boot** (`majlisna/schema.py`). Every uvicorn worker's lifespan calls
`database.create_schema` → `create_db_and_tables` → `schema.migrate_to_head`, over
`DIRECT_DATABASE_URL` (never PgBouncer) on a throwaway `NullPool` engine, the app engine
when no direct URL is set. It all runs in ONE transaction under the blocking,
transaction-scoped `pg_advisory_xact_lock(SCHEMA_DDL_LOCK_KEY)`: the first worker migrates,
the next ones find the database at head (INFRA-13: four workers racing on `CREATE TYPE`
crashed three of them). The database is one of:

- **versioned** (`alembic_version` exists): `upgrade head`;
- **empty** (no table of its own; an extension's objects do not count): `upgrade head`,
  baseline first;
- **created before migrations** (tables, no `alembic_version`: production on its first boot
  of this release, an E2E or dev database built by `create_all`): ADOPTED, i.e. stamped at
  `0001_baseline` then upgraded, **only if its schema is exactly what the baseline
  creates**. The baseline is built for the comparison in a schema of its own
  (`SCHEMA_ADOPTION_PROBE_SCHEMA`) inside a savepoint that is always rolled back, and both
  are described from the catalogs by `schema.describe_schema`: tables, columns in their
  order (type, NOT NULL, default, identity), constraints, indexes, enum labels in order,
  sequences, as PostgreSQL renders them (what `pg_dump --schema-only` says of them).
  Anything else is **refused**: `SchemaAdoptionRefusedError` lists every missing and
  unexpected line, logs it, and fails the boot; nothing is written (no stamp, no probe). A
  stamp is a promise about the schema that every later migration builds on: stamping a
  database that breaks it would make the next migrations fail, or succeed on a schema they
  were not written for. A refused dev or E2E database is dropped
  (`docker compose -f e2e/docker-compose.e2e.yml down -v`, or `--delete` then `--create-db`);
  a refused server is brought to the baseline by hand after a `pg_dump`, or stamped by hand
  (`alembic stamp 0001_baseline`) when the difference is known and wanted. A server booted
  before WP-21 still carries `ix_game_live_state_gin` or `ix_roomuserlink_room_id` and is
  refused for it: drop the index, boot again.

The adoption logs a WARNING (`Schema: adopted a database created before migrations`), a
migration an INFO (`Schema: migrated from X to Y`); a boot with nothing to do logs nothing.

**The baseline** (`migrations/versions/20261101_0001_baseline_production_schema.py`) is
production's schema on 2026-11-01 (PostgreSQL 16.15: 33 tables, 8 enum types): a
`pg_dump --schema-only` of a database it builds equals production's dump line for line,
`alembic_version` aside. That dump, schema only, is
`tests/fixtures/production_schema_2026-11-01.sql`, and
`test_the_baseline_builds_exactly_the_production_schema` compares the two on every
PostgreSQL run. Autogenerated, then completed by hand: `fk_room_active_game_id` after both
tables (room and game reference each other; `create_table` leaves a `use_alter` key out),
the three `POSTGRES_ONLY_INDEXES` the old startup DDL created (unique `ix_user_username_lower`
on `lower(username)`, the backstop behind `username_claim_lock`; unique `ix_user_email_lower`
on `lower(email_address)`, one account per mailbox, SEC-F14;
`ix_userstats_total_games_won_desc` for the leaderboard), and the enum types in the
downgrade. `ix_chatmessage_user_id` (account purge), which the old startup DDL created too,
is declared by `ChatMessage.user_id` now. Types are plain SQLAlchemy (`sa.String`, not
sqlmodel's `AutoString`): a frozen revision depends on nothing that can move.

**Production is adopted by its first boot of this release**: 33 tables and no
`alembic_version`, its schema the baseline's (proven before the merge against a restore of
its schema dump: identical, `alembic check` clean afterwards), stamped `0001_baseline`.
Nothing is run by hand. (Adopted on 2026-11-01 at 23:57 UTC, deploy of 87998e4: one boot log line "Schema: adopted a database created before migrations … stamped at 0001_baseline", `alembic_version` = `0001_baseline`, data untouched.)

**Revisions since the baseline**: `0002_room_invite` (`20261102_0002_room_invite.py`): the
`room_invite` table ("Room invites: stored, accepted without the PIN"), additive only (a new
empty table no earlier release reads). Its first production boot runs it: take the
`pg_dump` first, as for every migration. `0003_room_removal` (`20261102_0003_room_removal.py`):
the `room_removal` table ("Kick and ban", "Ban after removal"), additive only, the same way
(`test_0003_adds_only_the_room_removal_table_and_downgrades_to_0002`: nothing of 0002 touched,
and the downgrade gives 0002's schema back).

**What autogenerate compares** (`schema.include_object`, used by `env.py`): everything, but
the `POSTGRES_ONLY_INDEXES` (no model declares them) and a model's UNIQUE that repeats its
primary key (`unique=True` on most `id` fields): PostgreSQL drops such a constraint inside
its CREATE TABLE, so no database has it, production included, and every autogenerate would
otherwise offer to add thirteen of them. `compare_type` is on.

**The drift guard.** CI's backend job runs `alembic upgrade head && alembic check` against
a PostgreSQL service: a model changed without its migration fails it. Tests:
`tests/api/test_migrations.py` (postgres-marked; each test creates databases of its own in
the session's container, so the unique `lower()` indexes never reach the shared test
database): baseline == production, downgrade to empty and back, head == the models with
every enum value, a model changed without a migration fails the check, the CLI, a fresh
database, four worker processes on a fresh and on an unversioned database (one migrates or
adopts), the direct URL, the indexes, the case-variant refusals, adoption with its data,
an extension, the refusals (an index missing or extra, a column, a table, a type, an enum
value), `--delete`, the lock timeout. `tests/api/test_migrations_offline.py`: SQLite's
`create_all`, the CLI's refusal of SQLite, the models' registration.

**Anything that inserts users on PostgreSQL meets the unique indexes**: the dev/E2E seed
draws its random users with `fake.unique` (Faker repeats a name in ~0.14 % of 15-user
seeds, which would crash the reseed; `tests/scripts/test_wp21_seed_unique_users.py`).

Dropping and reseeding is for dev and E2E databases only (the E2E gate does it itself, in
`e2e/global-setup.ts`):

```bash
docker exec -w /app majlisna-e2e-backend env PYTHONPATH=/app python scripts/generate_fake_data.py --delete
docker exec -w /app majlisna-e2e-backend env PYTHONPATH=/app python scripts/generate_fake_data.py --create-db
```

**Production refuses both commands (exit 2) — only `--seed` runs there.** When
`MAJLISNA_ENV` or `ENVIRONMENT` is `production`, `--delete` and `--create-db` stop before
any engine exists unless BOTH `--i-know-this-is-production` and `--dump-taken <path>` are
given; the path must be a `pg_dump -Fc` archive (starts with `PGDMP`) written less than an
hour ago (`PRODUCTION_DUMP_MAX_AGE_SECONDS`), readable inside the container (`docker cp`
it in). This sequence ran on production once: every real account was dropped and 31 fake
ones, 16 with this repo's public passwords, took their place, with no backup (audit
PD-02). A schema change is a migration ("Migrations (Alembic)" above), never a drop.
Tests: `tests/scripts/test_generate_fake_data_guard.py`.

**Seed residue on a server is removed by `scripts/purge_seed_data.py`**, a dry run unless
`--apply --dump-taken <path>` (same dump check). It removes, through `_purge_user_references`,
the accounts at @test.com / @example.* that are never Google-linked, not named by `--keep
EMAIL` (repeatable), and either one of TEST_USERS (public passwords: they go whatever they
did) or never really used (no finished game, no session) — the address alone is not enough,
a real player may have registered a throwaway @test.com (review INT-04). Then the orphan
games (no room, `live_state` null, nobody linked) and the seeded rooms (owned by a seeded
user, no settings, no member, no game) with their bans and chat, in ONE transaction, then says
to restart the backend (the leaderboard is cached per worker; waiting out its 30 s TTL does
the same). The dry run lists every account and room it would delete, and the accounts at a
seed domain it KEEPS. `--apply` is refused (exit 2) while a seeded account sits in a running
game: purging that seat would leave a ghost player. The operator runs it in production after a verified dump; an agent never does.
Tests: `tests/scripts/test_purge_seed_data.py` (SQLite and `--use-postgres`).

Two things this script needs, both of which have already bitten once:

**It must not go through PgBouncer.** `DIRECT_DATABASE_URL` (set in both compose
files) points at the PostgreSQL server itself. asyncpg caches type introspection
per connection; the drop/create invalidates those types while PgBouncer's
transaction pooling keeps handing out connections with the stale cache, and the
following bulk INSERT dies with "could not resolve query result and/or argument
types in N attempts" — reproducible every single run. The script refuses to start
if `DATABASE_URL` names pgbouncer and `DIRECT_DATABASE_URL` is unset.

**`faker` is a MAIN dependency, not a dev extra — leave it there.** It looks like
a test-only package, but this script runs on the production image (built with
`ARG INSTALL_DEV=false`), and `--create-db` needs it wherever it is allowed to run. The
script used to be the schema-change procedure too (drop and reseed: that is what wiped
production's accounts, PD-02, and production now refuses it). As a dev extra faker was
absent from that image: the drop-and-reseed worked in E2E (that image passes
`INSTALL_DEV: "true"`) and failed on the server with a bare `ModuleNotFoundError` —
*after* `--delete` had already dropped everything, leaving production with an empty
schema and no way to refill it.

Belt and braces on top of that: `--create-db` verifies faker is importable BEFORE
touching the database, and `--delete` warns when the follow-up cannot succeed.
`--seed` (game content only) never needs faker and stays the safe minimum.

**The content seeds are upserts: the seed data is the source of truth for game content.**
`seed_quiz_words` (keyed on `word_en`), `seed_codenames_words` (pack + word) and
`seed_undercover_words` (word) insert what is missing AND bring an existing row's seeded
fields back to the data: spellings, accepted answers, theme, difficulty, hints,
explanations, descriptions. So a correction in `wordquiz_data.py`, `codenames_data.py` or
`undercover_data.py` reaches production with `--seed`, like `term_script` (below) and the
retired Codenames cards. They used to only add rows, which left every fixed hint on the
server as it was. The flip side: an edit made through the admin content API to a seeded
word is overwritten by the next `--seed` (no client calls that API; change the data file
instead). `tests/scripts/test_content_seed.py` pins it.

`seed_mcq_questions` is an upsert keyed on `question_en` AND retires every question no
longer in `MCQ_QUESTIONS`: rewriting a question changes its `question_en`, so the first
production `--seed` after the content pass of 2026-10-29 added the 40 rewritten questions
beside their old, corrected-away versions and updated nothing else. Nothing holds a
foreign key to a question; a running game whose next question was retired draws another.
`question_en` must therefore be unique (`test_every_mcq_question_text_is_unique`): two
entries sharing it overwrote each other on every run (the Bayt al-Hikmah question was in
the data twice). Nothing caches the questions (or any game content): every draw reads the
table, so a production `--seed` takes effect on the next game, with no restart.

### Expected 4xx log at INFO, not WARNING

`BaseError` picks `INFO` for < 500 and `ERROR` for >= 500. `app.py` attaches a
Sentry-compatible sink (Bugsink on the host, once `SENTRY_DSN` is set; it is empty in
production today) at WARNING+, so logging routine 4xx as warnings turned every
"You have already voted this round" and every wrong room PIN into a tracked issue,
burying real errors and burning the error-tracker quota.

### Never eager-load `Room.games`

`RoomController._load_room_for_view` (behind `get_room_by_id` and every
create/join/spectate/leave answer) eager-loads `Room.users` only — all `RoomView`
serializes (a lazy relationship load on an async session raises `MissingGreenlet`).
It used to add `selectinload(Room.games)`, i.e. the full `live_state` JSON of every
game ever played in the room, on every join and leave, and `RoomView` threw it away:
it has no games field on purpose (BDP-09; `test_room_reads_never_load_the_rooms_past_games`
counts the statements). Everything that just reads scalar columns — `get_room_state`
(every heartbeat and every Socket.IO broadcast), `kick_player`,
`update_room_settings`, `rematch`, `get_share_link`, `_prepare_game_start` — uses
`get_room_without_relations`.

### Room membership is one row per (room, user)

`RoomUserLink` carries `UniqueConstraint("room_id", "user_id")`. The table has a
surrogate int PK, so without it two concurrent `PATCH /rooms/join` calls from the
same user (double-tap, client retry) both saw "no existing link" and both
inserted — the player appeared twice in the lobby, the count was inflated, and
`.one()` lookups raised `MultipleResultsFound` (a 500).

Also: `join_room` and `join_room_as_spectator` filter on `Room.type == ACTIVE`.
`public_id` is globally unique and rooms are only soft-deleted, so a stale code
otherwise re-attached a user to a closed room (the spectator door still did: BR-22).

### SQLite foreign keys are per-connection

`create_app_engine` installs a pool `connect` listener that issues
`PRAGMA foreign_keys=ON` for every connection. A single PRAGMA on the
table-creating connection does **not** carry over to the rest of the pool, which
left dev running with foreign keys effectively off. `tests/conftest.py` installs
the same listener on its test engine.

### The test fixtures: cheap bcrypt, a database on request, one PostgreSQL schema (WP-19)

`tests/conftest.py`, pinned by `tests/test_wp19_fixtures.py`:

- **Test passwords hash at bcrypt cost 4.** The autouse `cheap_bcrypt` swaps
  `controllers/shared.gensalt` for `bcrypt.gensalt(rounds=4)`; `get_password_hash` reads
  that global at every call (the thread-pool variant too), so fixtures, registration,
  password changes and resets all get it. Production's cost 12 is 0.24 s a hash and was
  about two thirds of the suite's CPU (TQ-11). A test about the hash itself is marked
  `@pytest.mark.real_bcrypt` (`test_shared.py` still asserts `$2b$12$`). The login's
  `_DUMMY_PASSWORD_HASH` stays at 12; no test compares timings.
- **A test gets a database only when it needs `engine`** (directly, or through `session`
  and every factory fixture). The autouse `clear_database` used to DEPEND on `engine`, so
  every test, pure functions included, built (SQLite) or re-checked (PostgreSQL) the
  schema and truncated every table one by one (INFRA-16). It now calls
  `request.getfixturevalue("engine")` only for a test that needs it — first, so the
  tables are emptied after the test's own fixtures (live servers, socket clients, drained
  notifications) have let go of their connections, as before. A `--use-postgres` run of
  pure tests never starts the container.
- **SQLite**: a fresh in-memory database per test (`create_all(checkfirst=False)`;
  disposing the StaticPool engine frees it, nothing is dropped).
- **PostgreSQL**: one container for the session (`fsync`, `synchronous_commit` and
  `full_page_writes` off: tests need no durability; `trust` auth: no SCRAM exchange on
  each of the many connects) and one schema (`postgres_schema`, a NullPool engine, so
  every session end still closes its connection and nothing a test leaves on one reaches
  the next; a commit therefore costs a reconnect, ~25-30 ms through Docker Desktop, which
  is now most of a PostgreSQL test's time). After each test
  that used it: ONE `TRUNCATE <every table> RESTART IDENTITY CASCADE`, under a
  `lock_timeout` of 30 s. Every table the models declare is in it (`room_ban`,
  `auth_session`, any new one); the enum types stay.
- So a test may not rely on rows another test left (there are none) or on a sequence's
  value (each test starts at 1, `roomuserlink.id` included), may not keep a transaction
  open past its own fixtures (the cleanup then fails at that test's teardown, naming it,
  instead of hanging the run), and may not DROP or ALTER the shared schema — it creates a
  database of its own, as `test_migrations.py` does. The shared schema is `create_all`'s,
  not the migrations': `test_migrations.py` holds the two equal.

### Host-supplied settings are bounded

`RoomSettingsRequest` bounds every numeric field (see `constants.py`:
`MAX_TIMER_SECONDS`, `MAX_QUIZ_ROUNDS`, …) and uses a `DifficultyLevel` enum.
These values are copied verbatim into `Room.settings` and then into a game's
`live_state`, so `word_quiz_rounds=10_000_000` made game creation try to draw ten
million questions, and a negative timer made the expiry check pass immediately.
The quiz round durations (`word_quiz_turn_duration`, `mcq_quiz_turn_duration`) have
their own floor, `MIN_QUIZ_TURN_SECONDS`: the quizzes have no "0 = untimed", and a
round of 0-2 s expired the moment it opened (BR-17). Undercover and Codenames keep 0.
Behind the schema, both quiz controllers read a stored duration of 0 or less as
untimed — `_is_timer_actually_expired` answers False and `_phase_timer` None — so a
value already in a `live_state` can no longer close every round at once.

### Closing a room or a rematch cancels its running game

`delete_room` and `rematch` hold the room lock (`room:{id}`, which a game start holds
while it deals), re-read the room, then hold the active game's lock, and end that game
through `game_cancel.cancel_running_game` (CANCELLED, `end_time`, pause cleared), in
one commit. `delete_room` used to leave the game IN_PROGRESS and still playable in a
deleted room (BR-05); a rematch flipped the status without the game lock (BR-06). A
finished game stays finished.

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
next round opens (see "Undercover between rounds: the ready quorum"), and `timer_started_at` still points at the voting
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

There is no `is_admin` column: admin membership is configuration, not data (chosen when
there were no migrations; it stays so because no API path can grant it). It **fails closed**: `ADMIN_EMAILS` unset means nobody is
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
`_prepare_game_start` excludes spectators from the roster entirely. Within each kind a
connected member comes first (`disconnect._next_owner`).

`remaining` is every seat still CONNECTED or away INSIDE its grace (`disconnect._still_seated`,
the sweep's own rule): a room is empty, deactivated and its running game cancelled only when
nobody is coming back. It used to count the connected seats alone (review R1): a sweep during
the in-person discussion — phones lock, heartbeats go stale after 20 s — cancelled the game for
players still seated inside their 180 s grace, and the first phone to outlast a prayer pause's
45 minutes cancelled it for everyone still inside theirs. Tests: `test_disconnect.py`,
`test_a_sweep_while_the_others_are_only_briefly_away_plays_the_departure` and its neighbours.

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

What `record_game_end` writes since the 2026-10 audit (WP-03), for the scorable players
only (a leaver gets nothing at all, owner rule (b)):

- **`live_state[WINNER_IDS_KEY]`**, for every game type: the winners who are scorable,
  and `[]` when the final roster (players minus leavers) is below `MIN_PLAYERS_FOR_A_WIN`.
- **One resolver reads it: `controllers/stats.did_user_win(game, user_id) -> bool | None`**,
  used by the profile chart, head-to-head and `GET /games/user/{id}` (`user_won`). `None`
  = no result, and every reader skips the game: not FINISHED, a leaver, anyone not in the
  final `players` (a spectator has a `UserGameLink` too), a solo game, an old row with no
  winner. Rows older than the key fall back to side / team / top score (rule (a)). It used
  to know only Undercover and Codenames, so every quiz win read as a loss on the chart, a
  draw head-to-head and "no result" in history, while `UserStats` counted it. It lives in
  `stats.py` because `game_end_stats` imports `stats` (the reverse is a cycle).
- **The counters nothing wrote**: `games_hosted` (the player named by
  `HOST_USERNAME_STATE_KEY`), `mr_white_correct_guesses` (`MR_WHITE_GUESS_RESULT_KEY` —
  it must be written BEFORE `_finish_game` runs), `codenames_perfect_rounds` (each clue
  turn of the team in `clue_history` that turned exactly `clue_number` cards, all its
  own; a clue of 0 never counts — the reveal log has no `clue_number`). Applied before the
  achievement check, so a badge unlocks in the game that earned it.
- **The five special achievements** (`stat_field: None`): `SPECIAL_ACHIEVEMENT_RULES`
  (code → game type + predicate over the final state), unlocked through
  `AchievementController.unlock_special(user_id, code, commit=False)`, idempotent, which
  refuses a code that has a counter. `perfect_undercover` (an undercover who won, no vote
  ever named them), `unanimous_vote` (a resolved round where every ballot but the target's own
  names the target, ≥ `UNANIMOUS_VOTE_MIN_VOTES` such ballots, none drawn by the timer —
  `_auto_fill_missing_votes` lists its draws in `turn["auto_voters"]`; this player cast
  one of them, the target never earns it. "Every ballot" could never happen: the target
  votes too, for someone else), `last_survivor` (alive, winning
  side, its only living member), `sweep_victory` (the team won and every card it turned —
  at least one — was its own, from `reveal_log`, else `clue_history`), `assassin_finder`
  (an operative among the `voter_ids` of the assassin's reveal). `test_wp03_specials.py`
  fails if a `stat_field: None` code has no rule, or if any achievement's stat field has no
  writer in `controllers/`.
- **The daily and weekly challenges** (owner rule (g)): `assign_missing_challenges` then
  `check_progress`, both `commit=False`. `check_progress` had no caller at all, so every
  challenge sat at 0/N; assignment happened only when /challenges was opened, so a
  player's first games counted for nothing. Two conditions beyond play / win /
  play_as_role (review R7): `win_as_role` (`weekly_win_undercover_role`, role
  `undercover`: a civilian's win used to complete it) and `play_distinct_types`
  (`weekly_play_both`: Undercover AND Codenames; `weekly_play_all_3`, "Play 3 different
  games": any three of the four), whose `UserChallenge.progress` is a bitmask over the
  code's types (`challenge.DISTINCT_TYPE_CHALLENGES`; no new column) shown as the number of
  bits set — two quizzes used to complete "Play both Undercover and Codenames".
  `seed_challenges` is an upsert by code (it inserted missing codes only, so a corrected
  definition never reached production): `--seed` brings the stored rows to the data.
- **One read per table for the whole table of players (BDP-07)**:
  `StatsController.get_or_create_many`, `AchievementController.load_user_achievements`,
  `ChallengeController.load_active`, handed to the per-player calls (`stats=`, `known=`,
  `active=`). A 12-player game end went from ~113 statements to ~12 inside the lock
  (`test_a_game_end_reads_each_table_once_for_twelve_players` pins one SELECT per table).

`GET /stats/users/{id}/stats` is **read-only** (`StatsController.read_user_stats`): 404
`UserNotFoundError` for an unknown user, an unsaved zero row for a user with none. It used
to call `get_or_create_user_stats`, so an anonymous GET inserted rows and an unknown id was
a foreign-key 500, on SQLite too. `POST /challenges/seed` takes `get_current_admin_user`.

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

Game content is not cached either (WP-24). The admin lists (`get_words`,
`get_term_pairs`, `get_word_packs`) kept their ORM rows for an hour, and after an admin
write three workers in four went on serving the old list; `get_all` on the MCQ and Word
Quiz controllers cached rows nothing read and is gone. The draws never hydrate a table:
`get_random_questions` / `get_random_words` (Word Quiz and Codenames) /
`get_random_term_pair` select the ids (plus the difficulty, or the Codenames text for the
distinct-word rule), draw with `rng`, then fetch only the drawn rows by id, and
`utils/draw.in_draw_order` puts them back in drawn order — a `WHERE id IN` answers in the
database's order, and the order is the MCQ rounds and the Codenames layout. They used to
load every question (609 rows, 925 kB) on each MCQ start and every quiz word on each
Kalimat round, inside the game lock.

### The game lock waits in PostgreSQL's queue (WP-22)

`get_game_lock` on PostgreSQL runs `SELECT set_config('lock_timeout', '<LOCK_TIMEOUT_SECONDS>s',
true)` (that is `SET LOCAL`) then the BLOCKING `SELECT pg_advisory_xact_lock(:key)`. A waiter
sleeps in the server's lock queue and is woken when the holder commits or rolls back, first
come, first served; a wait that runs out is `lock_not_available`, raised as `TimeoutError`,
and a deadlock is broken by the server (`deadlock_detected`, raised as is). It replaced a
`pg_try_advisory_xact_lock` retried every 100 ms (BDP-06): no order, the lock idle between
polls, 12 simultaneous moves waiting ~530 ms at the median. A waiter holds its connection (a
PgBouncer server slot) in both designs.

- **The timeout is transaction-local on purpose**: a session-level `SET` would stay on the
  server connection for PgBouncer's next client. It is not put back once the lock is held
  (one more round trip in the critical section, paid by every queued move in turn), so the
  rest of the transaction runs under the same bound: a row lock that does not come within
  `LOCK_TIMEOUT_SECONDS` fails the request instead of holding the slot for good.
- **Pooled engines in the tests.** The shared `engine` fixture is `NullPool`: every session
  end closes its connection, which releases session-level locks too, so a
  `pg_advisory_lock` mutant passed 129 lock tests (TQ-06). **Rule: a lock-leak test uses a
  pooled engine** — `test_game_lock.py`'s `pooled_pair` is two `AsyncAdaptedQueuePool`
  engines of `pool_size=1`, so the connection given back stays open and a leaked lock is
  still held on it (`test_pg_lock_is_released_when_the_pooled_connection_goes_back`). It
  builds `AsyncAdaptedQueuePool` engines: a lock taken and committed must not stay on the
  connection given back to its pool, the median wait of 12 contenders (lowest of 3 bursts)
  stays under 150 ms, waiters are served in arrival order (read from `pg_locks`), the
  timeout, its scope, and the deadlock.

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

### The account lifecycle (WP-27)

Tests: `tests/api/controllers/test_wp27_account_lifecycle.py`,
`test_wp27_password_bytes.py`, `tests/api/models/test_user.py`,
`tests/api/routes/test_user.py`, `tests/api/routes/test_friend.py`.

- **Deleting an account is a departure first** (SEC F05). `delete_user_account` and
  `delete_user` run `_leave_every_room`: `_handle_permanent_disconnect` for every
  `RoomUserLink` of the user (elimination or turn repair, ownership transfer to a player
  first, deactivation of an emptied room, `mark_player_left` — a deleted player is a
  leaver: neither a win nor a loss). Each departure takes and releases its game lock
  (one commit each); only then does `_purge_user_references` run and the user row go, in
  one more commit, outside every lock. The purge used to delete the seats itself: the
  ghost stayed alive at the describer's seat of an untimed round for ever, and a host's
  deletion orphaned the room under a game still IN_PROGRESS. Both return
  `list[DepartedRoom {room_id, game_id}]` (`game_id` read BEFORE the departure), and
  `DELETE /users/me/account` calls `remove_user_from_room_socket` and
  `notify_member_removed` for each, exactly like the leave route.
- **The confirmation comes first, and is one of two** (SEC F14). `DeleteAccountRequest`
  takes EXACTLY one of `password` / `google_access_token` (neither or both: 422). A
  Google token is verified by `SocialAuthService.verify_google_access_token` — the
  sign-in's audience check — and its `sub` must equal `user.google_sub`, else
  `GoogleAccountMismatchError` (403; also for an account never linked to Google). A
  Google-only account's password is a random sentinel its owner never saw, so deletion
  used to need a password reset first (still accepted). A refused confirmation plays no
  departure.
- **Passwords are measured in bytes** (SEC F10). bcrypt 5 raises past 72 bytes of
  UTF-8 (`BCRYPT_MAX_PASSWORD_BYTES`), and the schemas counted characters: a long login
  was an unauthenticated 500, and 40 Arabic letters (80 bytes) passed registration and
  then 500'd at hashing. `verify_password` answers False on bcrypt's `ValueError` (a
  login is a 401); `get_password_hash` raises `PasswordTooLongError` (400), which covers
  the reset; and `UserCreate.password`, `UserUpdatePassword.current_password` /
  `new_password` and `DeleteAccountRequest.password` run
  `models/user.refuse_password_over_bcrypt_limit` in `mode="before"`, so any password
  over 72 bytes — over 72 characters or not — gets the translated 400.
- **A password change signs out every OTHER session** (SEC F01):
  `update_user_password(..., keep_session_id=request.state.session_id)` calls
  `revoke_user_sessions(..., except_session_id=)` in the change's commit; a caller on a
  legacy token (no `sid`) keeps none.
- **"Change password" works for every account; `auth_provider` email means "has a password
  of its own"** (2026-11-02, no schema change). `UserUpdatePassword` takes EXACTLY one of
  `current_password` / `google_access_token` (neither or both: 422), and
  `UserController._confirm_password_change` asks for the credential the account signs in
  with: an account with a password (`has_own_password`) confirms with it, and a Google
  token for it is `CurrentPasswordRequiredError` (403: on a shared computer Google's session
  is often still open, the password is the stronger proof); a Google-only account confirms
  with Google, verified as deletion does (`_confirm_with_google`: the audience check, 401
  `invalidCredentials`; `sub` == `google_sub`, else 403 `GoogleAccountMismatchError`), and a
  typed password for it is `GoogleConfirmationRequiredError` (403). `set_own_password`
  hashes the password AND sets `auth_provider` email, `google_sub` kept: the very state of
  an email account linked to Google, so `AuthController.login` (which refuses any account
  `has_own_password` says no to) takes the password, and Google sign-in (found by
  `google_sub`) still works. The reset uses it too: a Google-only account's "Forgot
  password?" now sets a password the login accepts (it used to be stored, then refused). An
  account reset before this keeps `auth_provider` google until it sets a password again.
  `PATCH /users/{id}/password` is limited per user (`PASSWORD_CHANGE_RATE_LIMIT`,
  `user_or_ip_key`): every try is a bcrypt check or a call to Google. Tests:
  `tests/api/controllers/test_password_for_every_account.py`.
- **`profile_picture_url` is Google's avatar CDN, bounded** (SEC F15):
  `models/user.avatar_url_is_allowed` — https, no userinfo, no explicit port, no
  backslash or whitespace, a plain-DNS host ending in `ALLOWED_AVATAR_HOST_SUFFIXES`, at
  most `AVATAR_URL_MAX_LENGTH` — else `InvalidAvatarUrlError` (400). The UI never sets
  it; Google sign-in stores Google's picture directly. Values stored before stay as they
  are.
- **`POST /friends/request` is limited per user** (`FRIEND_REQUEST_RATE_LIMIT`,
  `user_or_ip_key`).
- **A validator never raises `ValueError` for a request schema**: pydantic puts the
  exception object in the error's `ctx`, and the app's `RequestValidationError` handler
  cannot serialise it — the request answered a 500 (every unknown `country` did). Raise
  `PydanticCustomError` (a 422) or a named `BaseError` (it propagates out of validation
  to its own handler).

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
  by diffing `CreateTable` output before and after, which mattered because there were
  no migrations then (the baseline came later, from these models).

**`--error-on-warning` is load-bearing, not decoration.** ty reports `deprecated`,
`possibly-missing-submodule` and `unused-type-ignore-comment` as *warnings*, which do
not fail a run by default. `possibly-missing-submodule` is what caught an `except`
clause naming `resend.exceptions.ApiError` — a class that does not exist (see below).
A rule that finds a production bug does not get to be advisory.

**The version is pinned exactly (`ty==0.0.63`), not floored.** ty is pre-1.0 and its
diagnostics change between releases: a range would let a fresh CI checkout resolve a
version reporting errors the developer's lockfile never showed. Upgrading is a
deliberate act — bump the pin, run `uv run poe typecheck`, adjust suppressions.
`[tool.ty.environment] python-version = "3.14"` pins the *analysed* version to what CI
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
   out of `TTLCache` (which stores `object`) is `cast(Sequence[LeaderboardEntry], cached)`, not an
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

What the 2026-10 audit added (WP-02; tests in `test_undercover_rules.py`,
`test_undercover_game.py` and `test_wp02_ready_quorum.py`):

- **Describing: `advance_describer(state, turn)` runs after EVERY description and every
  departure** (BR-02). The skip used to run only at the moment of a departure, from the
  index as it stood then, so a player who left LATER in the order than the current
  describer locked the round as soon as the turn reached their empty seat. **Rule: every
  turn pointer moves through that one helper**, which skips seats no longer alive; after
  any departure the turn must still offer a legal move or a server-side timeout; and a
  departure test seats the leaver LATER in the order, not only at the current actor
  (`test_a_later_describer_leaving_does_not_lock_the_round[leave|sweep]`,
  `test_the_last_describer_leaving_opens_voting_after_the_others`).
- **Voting: the ballots naming the departed player go back to their voters** (BR-07),
  who may vote again. Otherwise the players who had not voted yet decided the round
  alone — and when everyone had voted for the leaver, the tally completed by
  subtraction with every count at 0 and the tie-break eliminated a random player. A
  ballot counts only if it names a living player, and a complete tally where none does
  is never resolved.
- **Between rounds: the leaver's ready mark is dropped, and a departure that completes
  the quorum opens the next round** (not when it decides the game, not while paused).
  The disconnect handler passes `host_id=room.owner_id`; without it the quorum asks
  every alive player, which can only open the round later, never early.

**Rule for every game: a departure removes every reference the current turn holds to the
leaver** — their own vote, the votes that name them (Undercover), their card vote (Codenames,
`release_departed_operative`), their ready mark — **and every quorum counts only the players
still in the game.** An all-zero tally is never resolved with `rng`: the round stays open.
Tests: `test_votes_for_a_player_who_leaves_can_be_cast_again`,
`test_nobody_is_eliminated_with_zero_votes_when_the_suspect_walks_out[0..5]`
(`test_undercover_game.py`), `test_a_departed_operatives_card_vote_never_counts`
(`test_disconnect.py`), `test_undercover_rules.py`.

### A Codenames team needs both roles, not just a body

`_codenames_team_strength` scores a side 2 (spymaster **and** operative), 1 (one
role left) or 0 (gone), and the game ends as soon as either drops below 2. "Is the
team empty?" was the wrong question: teams are dealt exactly one spymaster and the
rest operatives, so at the 4-player minimum *either* departure leaves a team of
one — non-empty, and unable to take a turn.

- No operative: the spymaster gives a clue and nobody can guess or end the turn.
- No spymaster: nobody can give a clue, so `guess_card` answers `NoClueGivenError`
  and the side can only ever pass (and since BR-15 not even that: `end_turn` needs a
  clue too).

The Codenames timers also default to 0, so nothing switched the turn either. The
score ordering (not a boolean) is what decides the winner when a side drops below
2: an empty team must never beat a crippled one.

### Codenames moves: the row's status, one-word clues, the votes that count, the reveal log

The rules of a turn live in `codenames_helpers.py`, on `live_state` alone (the disconnect
handler shares them and cannot import a controller). WP-09 of the 2026-10 audit:

- **Every move checks the Game ROW first** (`_ensure_in_progress`, in `give_clue`,
  `guess_card`, `end_turn`, `handle_timer_expired`): `game_status` AND
  `live_state["status"]` must be IN_PROGRESS, else `GameNotInProgressError`. Checking
  `live_state` alone kept a game a rematch had CANCELLED playable from a stale tab, and
  finishing it rewrote it FINISHED, credited stats and unlinked the room's NEW game
  (BR-06). The finish path (`_finish_game`) lets go of the room only through
  `game_cancel.detach_room_if_current`.
- **A clue is one word** (`_validated_clue`): stripped; blank or holding any whitespace →
  `ClueMustBeOneWordError` ("the Sunnah" went through the UI with the Sunnah card on the
  board); a card's own word → `ClueWordIsOnBoardError`, compared casefolded NFKD and
  through `text_match.matches_any` (accents, the "al-" article) against the Latin words
  AND their `term_script` Arabic forms (`clue_names_a_card`). The STRIPPED clue is stored
  and answered.
- **`end_turn` before the clue → `NoClueGivenError`** (BR-15): one operative passed the
  team's whole turn.
- **The quorum is the operatives on the team now, and only their votes count**
  (`current_operative_ids`, `counted_operative_votes`, `tally_operative_votes` → the card,
  or None until every one of them has voted; a tie is drawn with `rng` among the top cards).
  A departed operative's ballot used to fill the quorum and could be the card turned
  (BR-09). `guess_card` also drops such stale ballots from `card_votes`.
- **A departure settles the vote it completes**: `release_departed_operative(state,
  user_id)` (for `_handle_codenames_disconnect`, under the game lock; works whether or not
  the leaver is still in `players`) pops the leaver's vote and, when the remaining votes
  now make the quorum, turns the agreed card and returns the outcome (else None). A
  finishing outcome leaves the Game row to the caller (FINISHED, `end_time`,
  `detach_room_if_current`, `record_game_end`). It applies during a prayer pause too:
  the votes were cast before, as with an Undercover vote a departure completes.
- **Every card turned goes through `apply_card_reveal(state, idx, voter_ids)`**, which
  returns a `CodenamesRevealOutcome` (its value is `GuessCardResponse.result`) and appends
  `{card_index, team, card_type, voter_ids, clue_turn}` to
  `live_state[CODENAMES_REVEAL_LOG_KEY]` — the guessing team, the operatives whose vote was
  that card (the lone operative of a team of one), and the clue's turn. `clue_turn` is
  `live_state[CODENAMES_CLUE_TURN_KEY]`, +1 per `give_clue` (0 at the deal; a game without
  the key counts `len(clue_history)`), so it is the clue's 1-based position in
  `clue_history`. `game_end_stats` reads the log for sweep_victory and assassin_finder
  (owner rule (f)).
- **hint-viewed and timer-expired call `_require_participant`** (a stranger: 403;
  BR-13, SEC F07/F08). A hint view is recorded only for a board word whose meaning the
  caller can open (`hint_is_visible`: every card for the spymaster, a turned card for an
  operative), once, and at most `HINT_USAGE_MAX_WORDS_PER_USER` per user; anything else,
  a spectator's included, answers `recorded=False` and writes nothing.

Tests: `tests/api/controllers/test_codenames_helpers.py` (the pure rules),
`test_codenames_game.py` (the WP-09 block: a cancelled game after a rematch, the departed
ballot, the clue shapes, the reveal log re-read from the database, the hint rules),
`tests/api/routes/test_codenames_game.py` (the translated errors through the real stack).

### A quiz round a departure completes goes to results at once

Word Quiz and MCQ move a round to results when the last answer arrives
(`submit_answer`). When instead the one player everybody was waiting on leaves, is
kicked or is removed by the grace sweep, every remaining player is already done —
and nothing else noticed: no answer could arrive any more, so the round sat open
until its timer ran out. `_handle_wordquiz_disconnect` / `_handle_mcqquiz_disconnect`
now call `quiz_rules.settle_round_if_everyone_answered(state, game_type)` after
removing the player, under the game lock and in the handler's single commit.

- **One rule, each game's own meaning** — `quiz_rules.everyone_has_answered`: every
  remaining player has an entry in `answers`. MCQ writes every lock-in there; Word
  Quiz only the answer that found the word (a wrong try is an `attempt`, and the
  player may type again), so "done" is "answered" in one and "found it" in the
  other — or, in Word Quiz, "has used all `WORDQUIZ_MAX_ATTEMPTS_PER_ROUND` tries"
  (`wordquiz_out_of_tries`), since such a player can type nothing more. Both
  `submit_answer` branches use the same function (the last allowed miss can close
  the round), and the controllers'
  `_transition_to_results` are thin delegates to `quiz_rules` — a module of its own
  for the import reason of `undercover_rules` (`disconnect` cannot import a
  controller).
- **Only an open round** (`round_phase == "playing"`), never an empty table (the
  handler cancels it), and **never while paused**: the departure is recorded (roster,
  answers, attempts, ready marks), the round stays as the prayer found it, and
  `resume_game` settles it — `BaseGameController._settle_after_resume(state, host_id)`,
  a no-op the two quiz controllers override (and Undercover, for its ready quorum),
  runs after the pause is cleared, in the resume's commit.
- Notifications need nothing new: kick and leave already `notify_member_removed`
  (→ `notify_game_changed`), and the sweep returns the game for `on_game_changed`.

Tests: `tests/api/controllers/test_quiz_dropout.py` (both quizzes × leave / kick /
sweep; a departure that does not complete the round — including a Word Quiz player
whose only try was wrong; the paused case settled by the resume; a resume that
must leave an unfinished round open). Disabling the settle fails ten of them.
E2E, through the real stack and the push to the remaining player's page:
`e2e/tests/mcqquiz/drop-out.spec.ts` (a leave) and `e2e/tests/wordquiz/drop-out.spec.ts`
(a kick), each on a five-minute clock that the result must beat by far.

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

### Undercover between rounds: the ready quorum

Owner rule (d), BR-23, SEC F05. `POST /undercover/games/{id}/next-round` is the host's
"next round" AND every other player's "I'm ready" — one endpoint, one hook
(`useStartNextRound…`), answered by `StartNextRoundResponse.advanced`:

- the host (`Room.owner_id`) opens the next round at once (`advanced: true`, with
  `turn_number` and `description_order`), as before;
- any other caller must be a player of the game (`NotAGamePlayerError`, 403) who is
  alive (`NotAnAlivePlayerError`, 400); their call adds them, once, to
  `turn[UNDERCOVER_READY_PLAYERS_KEY]` on the resolved round, and opens the next round
  when every alive player but the host is ready (`undercover_rules.ready_required`).
  Otherwise `advanced: false` with `ready_players` (ids, arrival order), `ready_count`
  and `ready_quorum`. Same checks as before for everyone: in progress, the right room,
  not paused (`GamePausedError`), round resolved and no guess owed
  (`RoundNotResolvedError`);
- with no host (`owner_id` NULL — the host deleted their account) nobody forces and
  every alive player is asked. Every next-round answered 403 there, so such a game
  could never finish.

It used to be the host's call alone: a host whose tab stayed open but who had stopped
playing held the table between rounds indefinitely (host transfer needs 180 s
*disconnected*). The one place a round opens is `undercover_rules.open_next_round(state)`
(new describing turn, its order, `timer_started_at`, the ready list cleared); the host
path, the quorum path and the departure path all call it. `UndercoverGameState` carries
`ready_players`, `ready_count`, `ready_quorum` and the caller's `is_ready` while the
resolved round waits (empty otherwise). A ready mark is a visible change, so the route
notifies on both outcomes. A departure during a prayer pause that completes the quorum
opens nothing (nothing moves while paused); the resume opens it, in its commit
(`UndercoverGameController._settle_after_resume` → `open_next_round_if_ready`, review R6:
a ready player reads "You are ready" and cannot mark again, so with no owner nobody could
open the round, for good).

### Undercover rule enforcement, hint views and the clock (WP-02)

- **A description may not be the describer's own word** (BR-16): `matches_any` against
  the Latin term and its `term_script` forms (case, accents, diacritics, article
  ignored) → `DescriptionRevealsWordError` (400, no details: the word is the secret).
  Only the describer's OWN word — refusing the other side's would reveal it.
- **hint-viewed** (BR-13, SEC F07): `_require_participant` (403 for a stranger), then
  only the caller's own word in Latin or Arabic counts, stored as the game's term (one
  word, one entry), capped at `HINT_USAGE_MAX_WORDS_PER_USER`. Anything else answers
  `recorded: false` and writes nothing — a spectator and Mr. White have no word.
- **timer-expired** (SEC F08) calls `_require_participant` first (players, eliminated
  ones included, and spectators).
- **No Turn / Event rows** (BDP-08): `create_and_start` and `start_next_round` no longer
  call `GameController.create_turn` / `create_turn_event`; `live_state` is the record.

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

**One helper for every door: `controllers/token_auth.authenticate_access_token(session,
settings, token)`.** `get_current_user` and both Socket.IO connects (`_connect_personal`,
`_authenticate_member`) call it; nothing else turns an access token into a `User`. The
sockets had their own copy, which checked the type but resolved by `email` only — so an old
token opened the re-registered account's personal channel and rooms (SEC F09). A new token
rule (the session check) goes there and reaches HTTP and Socket.IO at once. Its tests run on
real JWTs (`tests/api/routes/test_wp00_token_type.py`, `tests/api/ws/test_wp00_socket_auth.py`):
every older test mocked `decode_token`, so removing `expected_type` passed the whole suite.
The account is looked up by `sub` (primary key) and must carry the `email` claim's address.

### Sessions: a signed-out device is signed out for real (SEC F01)

The JWTs were stateless: logout only cleared cookies, a reset touched no token state, and
`/auth/refresh` minted a fresh 7-day pair from any signed refresh token — so a leaked token
renewed itself forever. Now every token names a server-side session
(`models/auth_session.AuthSession`, table `auth_session`):

- **Claims.** Both tokens carry `sid` (the session id) and `iat`; the refresh token also its
  single-use `jti`. Login, Google sign-in and the legacy upgrade open a session
  (`AuthController._open_session`, `expires_at = now + SESSION_ABSOLUTE_LIFETIME_DAYS`).
  `create_token_pair` is gone: nothing mints a pair without a session. `create_access_token`
  / `create_refresh_token` without `session_id` mint the legacy shape, for tests only.
- **Every door checks it.** `token_auth.authenticate_caller` loads the session and its user
  in ONE primary-key read (it replaces the email lookup) and answers `SessionRevokedError`
  (401, `errors.api.sessionRevoked`) when the session is missing, revoked or past
  `expires_at` — on every request and at every Socket.IO connect. `get_current_user` sets
  `request.state.session_id` (the caller's sid, None for a legacy token): a password change
  revokes the OTHER sessions with `revoke_user_sessions(..., except_session_id=)`.
- **Refresh is single use** (`AuthController.refresh_session`; no logic in the route). The
  row is read `FOR UPDATE`. `jti == current_refresh_jti`: rotate (previous := current,
  current := new, `rotated_at` := now). `jti == previous_refresh_jti` within
  `REFRESH_REUSE_GRACE_SECONDS` of the rotation: two tabs raced, re-mint the CURRENT refresh
  token (same jti, same exp: `_session_tokens` is a pure function of the row) and a fresh
  access token. Any other jti: a replayed copy — revoke the session (committed), answer
  `SessionRevokedError`. `expires_at` never moves; a refresh token's `exp` is capped at it.
  Without the row lock, two simultaneous refreshes both rotated and the loser's next refresh
  read as theft (`test_two_tabs_refreshing_one_token_at_once_both_stay_signed_in`).
- **Who revokes.** Logout (the session named by the access token, else the refresh cookie;
  an expired but signed token still names it), `reset_password` (every session of the user),
  a password change (every OTHER session: "The account lifecycle" above), reuse detection,
  and Google taking back an unverified account (below).
- **One door.** Every access token becomes a `User` only through
  `token_auth.authenticate_caller` (and its `authenticate_access_token` wrapper), over HTTP
  (`get_current_user`) and Socket.IO (`_connect_personal`, `_authenticate_member`) alike: a
  new token rule goes there and reaches both.
- **Bounded table.** Every sign-in adds a row, so `_open_session` first deletes the
  account's rows past `expires_at` (their tokens can never work again; a missing session is
  refused exactly like an ended one). Revoked rows inside their lifetime stay, as the record
  of who signed out when.
- **Legacy tokens** (minted before this shipped: no `sid`/`jti`). An access token is
  accepted until it expires (≤ `access_token_expire_minutes`): nobody is signed out at
  deploy. A refresh token carries no `jti`, so its sha256 digest is what is tracked:
  `/auth/refresh` upgrades it ONCE into a new session that records it
  (`AuthSession.legacy_refresh_digest`, unique), which then rotates and revokes like any other.
  Presented again within `REFRESH_REUSE_GRACE_SECONDS` of the upgrade (two tabs at the deploy)
  it answers that session's current pair; later, it is a replayed copy: the session it opened
  is revoked and the answer is `SessionRevokedError` (review R3 — it used to open a new session
  on every use, so a stolen copy outlived a logout, a reset and reuse detection). Two first
  presentations racing: the unique digest refuses the second insert, which takes the grace
  path (`test_two_tabs_upgrading_one_legacy_token_at_once_get_one_session`, postgres). **Time-boxed: remove `_upgrade_legacy_refresh` and the `sid is None` branch of
  `authenticate_caller` `refresh_token_expire_days` (7 in production) after the deploy** —
  every legacy token has expired by then (removal due: the production deploy date of this
  change + 7 days; write the date here when it ships). Until then one gap is left: a legacy
  refresh token never presented before a reset can still be upgraded once after it (no
  password-change instant is stored to compare with).
- **No response body carries a refresh token** (review INT-06, SEC F13): login, refresh and
  Google sign-in set it as the httpOnly cookie only (`LoginResponse`, `AccessTokenResponse`,
  `SocialLoginResponse`; `TokenPairResponse` and `SocialLoginResult` stay inside the server).
  A body still holding one is accepted by `/auth/refresh` (an old client's stored token).
- Tests: `tests/api/controllers/test_wp17_sessions.py` (HTTP, sockets, both dialects; the
  race is postgres-marked).

### Google links only into a verified account (SEC F02)

`social_login` found an existing account by email and linked `google_sub` without checking
`email_verified` — and registration needs no verification. Someone who registered an address
they do not own before its owner's first "Continue with Google" kept a working password into
the owner's account. Now a VERIFIED account is linked as is; an unverified one is taken back
for the mailbox's owner first (`_take_back_for_mailbox_owner`): password → social sentinel,
`auth_provider` google, `email_verified` True, every session revoked, then linked. Google's
verified email is the proof (`SocialAuthService` refuses `email_verified: false`). Tested
without mocking Google itself: `SocialAuthService(settings, transport=httpx.MockTransport(...))`
(`tests/api/services/test_social_auth_service.py`, TQ-02).

### One account per mailbox: addresses are lowercased (SEC F14)

`controllers/auth.normalize_email` (strip + `str.lower`, matching SQL `lower()`; not
`casefold`, which folds `ß` and would disagree with the database) runs on register, login,
forgot-password, resend-verification and the Google lookup; new rows are stored normalised.
`get_user_by_email` compares `lower(email_address)`, so a mixed-case row from before is still
found (exact spelling first if a mailbox still has two rows). `User.email_address`'s own
constraint compares exactly; on PostgreSQL the baseline migration has the unique
`ix_user_email_lower` on `lower(email_address)` (WP-21, "Migrations (Alembic)"), the
backstop.

### Reset and verification tokens: hashed at rest, aware comparisons

`PasswordResetToken.token` / `EmailVerificationToken.token` hold the sha256 hex digest
(`token_digest`), never the token; redeemed by digest (PD-15, SEC F06). No schema change (the
column kept its name); links issued before stopped working. Issuing a token purges every
expired one of its kind. `expires_at` reads back naive on SQLite, so it is compared through
`utc_instant` — the plain comparison raised `TypeError` and every dev reset/verify link
answered 500 (TQ-03). Tests: `test_auth.py::test_the_reset_token_is_stored_as_its_sha256_digest`,
`::test_the_stored_digest_itself_does_not_reset`, `::test_an_expired_reset_token_is_refused`.

### Two read rules: SQLite's naive timestamps, and GETs that never write

- **SQLite reads `TIMESTAMP WITH TIME ZONE` columns back as NAIVE datetimes.** Normalise
  them (`auth.utc_instant`, `utils/game_state.as_utc`: `tzinfo=UTC` on a naive value)
  before comparing with `datetime.now(UTC)`. Without it the password-reset and
  email-verification flows crashed on the dev stack while PostgreSQL (aware) was fine. The
  deliberate exception stays: `RoomUserLink`'s timestamps are naive on purpose and compared
  naive (root CLAUDE.md).
- **A GET never writes.** `GET /stats/users/{id}/stats` used to call
  `get_or_create_user_stats`: an anonymous read inserted rows, and an unknown id answered a
  foreign-key 500. It is `read_user_stats` now (404 for an unknown user, an unsaved zero row
  otherwise). Tests: `tests/api/routes/test_stats.py::test_anonymous_stats_read_writes_nothing`,
  `::test_anonymous_stats_read_for_an_unknown_user_is_a_404`.

### Room invites: stored, accepted without the PIN

A friend's invite used to be a Socket.IO push carrying the room's code AND PIN, stored
nowhere; the PIN rotates (then on every kick, now on a ban), so an invite sent before it opened
a join that was refused. It is now a row, `RoomInvite` (`models/room_invite.py`, table
`room_invite`, migration `0002_room_invite`): `room_id`, `inviter_id`, `invitee_id`,
`created_at` / `updated_at`, `expires_at` (all UTC-aware; SQLite reads them back naive,
compare through `controllers/auth.utc_instant`).

- **Inviting** (`RoomController.invite_friend_to_room`: the inviter connected in the room, the
  invitee a friend, not banned from the room — `InviteeBannedError`, 403 — and not connected in
  it) upserts on the unique
  pair `uq_room_invite_room_invitee` (`INSERT … ON CONFLICT DO UPDATE`): one live invite per
  (room, invitee), a re-invite keeps the id and takes the latest inviter and a full
  `ROOM_INVITE_LIFETIME_MINUTES` (30) again, so a strip already on the friend's screen still
  opens it. It first deletes every expired invite (anyone's). `RoomInviteResponse.invite`
  is the `RoomInviteView` `{id, room_id, public_id, invited_by, expires_at}` the route hands to
  `notify_room_invite`, which emits exactly that (no room read, never the PIN).
- **Accepting** (`POST /rooms/invites/{invite_id}/accept` → `accept_invite`, RoomView, then
  `notify_room_changed` like a join; `ROOM_JOIN_RATE_LIMIT` per user, its own bucket — a
  `shared_limit` with the fixed scope `ROOM_INVITE_ACCEPT_RATE_LIMIT_SCOPE`, because a plain
  limit counts per path and the path names the invite: each made-up id bought a fresh
  budget): the invite row is read `FOR UPDATE` for the caller (someone else's, unknown,
  spent or deleted by a ban → `RoomInviteNotFoundError` 404), then `expires_at`
  (`RoomInviteExpiredError` 410), the room
  ACTIVE (`RoomNotFoundError`), `_ensure_not_banned` (403), `_ensure_not_seated_elsewhere`
  (409, the invite stays so the client can leave and accept again), then `_take_seat` — the
  same seat code as `join_room` (reconnection included), which deletes the host's removal
  record of the player first (asking for a ban again: "Ban after removal" above) and the
  invites the player holds to that room in the seat's commit. A join with the code and PIN spends them
  too. The row lock is what makes two tabs accepting at once seat the player once (the
  second answers 404); without it the second insert of the seat's unique pair was a 500.
  There is no room capacity at join (game starts bound the player count), so none here.
- **Reading**: `GET /rooms/invites` (`list_invites`, declared before `GET /rooms/{room_id}`)
  → the caller's live invites (not expired, ACTIVE room, no ban of the caller from it), newest `expires_at` first, at
  most `ROOM_INVITE_LIST_LIMIT`: the app shell's strip shows an invite sent while the page
  was closed, and re-reads it after a socket reconnect.
- **Purges** (no FK declares ON DELETE): `_purge_user_references` deletes the invites a user
  sent or received; `delete_room` deletes the room's; `ban_player` deletes the room's invites
  the banned player sent or was sent (in the ban's commit, with the ban and the new PIN; a kick
  deletes none);
  `scripts/purge_seed_data.py` deletes those of the rooms it removes. A room deactivated
  otherwise (its last member left) keeps its rows until they expire: accepting answers
  `RoomNotFoundError`, `list_invites` leaves them out, and the next invite issued purges
  them once expired. An expired invite likewise stays in the table until then: the list's
  `expires_at` filter is what hides it.
- A ban is checked when inviting (403 `inviteeBanned`: the inviter's dialog says the friend is
  banned from this room), again once the invite is committed (a ban that committed meanwhile
  takes it back: 403, no push), by the ban's sweep after its commit, and on accepting (403
  `roomBanned`, the last door for a row that slipped past both). A lift makes new invites
  possible again.
- Tests: `tests/api/controllers/test_room_invites.py` (stored without the PIN, refresh,
  expired purge, accept after a ban, a kicked player's sent and received invites kept, a
  banned player's deleted, a raced invite refused, inviting a banned or a kicked friend, the
  lift, someone else's, expired, closed and deactivated rooms, seated
  elsewhere then leave and accept, a link join spends it, the live list (its expiry and
  ACTIVE filters each tested with the rows still present), account deletion both ways, and
  two concurrent accepts, postgres), `tests/api/routes/test_room.py` (routes, error keys,
  the per-user accept limit, a new invite id per call),
  `tests/api/ws/test_notify.py::test_notify_room_invite_names_the_stored_invite_and_never_the_pin`,
  `tests/scripts/test_purge_seed_data.py`.

### One live room at a time, and only a live room blocks

`RoomController._ensure_not_seated_elsewhere` is the one rule, called by `create_room`,
`join_room`, `join_room_as_spectator` and `accept_invite`: a user CONNECTED in another ACTIVE room gets
`UserAlreadyInRoomError` (409, `details.room_id` = that room, so the client can offer
"leave it and join"). Only `create_room` used to check it, so a share link seated a
player in room B while room A's host could still deal them into a game they never saw
(BR-21, FR-2). An away (disconnected) seat does not block. The guard joins `Room` and
filters `type == ACTIVE`, matching `get_active_room_for_user`. Without the join a link to
an INACTIVE room barred the player forever: a room is deactivated when nobody is left
connected or inside their grace ("Host transfer prefers a player", `_still_seated`), which
can still leave behind the links of anyone marked disconnected past it — and Socket.IO
`connect` flips such a link back to connected on the next reconnect. The player then could not create a room, while
`get_active_room_for_user` reported none to leave, so the UI offered no way out.

### Arabic forms of game terms live in `term_script`, keyed by the Latin word

Undercover (`Word.word`) and Codenames (`CodenamesWord.word`) terms are stored as
Latin transliterations ("Sabr", "Hajj", "Dhul-Kifl"). Their Arabic script lives in
the **`TermScript`** table (`models/term_script.py`): `term` (the exact Latin
string, unique) → `ar` (as normally written, no harakat: "صبر", "الفاتحة") and
`ar_vocalized` (conventional harakat: "صَبْر"; **null when not certain** — a missing
vowel beats a wrong one on a prophet's or a place's name).

**Why a separate table, not columns on `word` / `codenames_word`:** when it was added
there were no migrations, and `create_all` never ALTERs an existing table, so a new
column would never have reached production. It also gives one row per term even where
the same Latin word appears in both games or in two Codenames packs.

**Where it is read** — always ONE batched `TermScriptController.get_forms(...)` per
request, never per card (tests pin the statement count with `count_statements`):

- Codenames `get_board`: `word_ar` **and `word_ar_vocalized`** on every card, in
  every view (spymaster, operative, spectator, end-of-game reveal), and on each
  clue-history guess (the Latin is visible to all, so the Arabic reveals nothing).
  The vocalised form is there because the bare one is ambiguous on a card: أحد is
  Uhud or "one", ثور is Thawr or "a bull" — same lookup, no extra query.
  `give_clue` also rejects a clue that is a board word's Arabic form — it is
  printed on the card (`codenames_helpers.clue_names_a_card`, on the stripped clue).
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
Where the dictionaries disagree, the comment above the line records the choice and its
source: حِطِّين (Yaqut), الحُدَيْبِيَة with a light yaa (the lexicographers; the hadith
reciters double it), جِنَازَة with a kasra (al-Jawhari, al-Fayyumi: "والكسر أفصح"), سَحُور
the meal against سُحُور the act, مُصْحَف with a damma. Change one only with a source.
A word an admin adds through the API without a row simply gets null Arabic forms.

**The seed is an upsert** (`seed_term_scripts` → `TermScriptController.upsert`):
inserts missing terms, rewrites changed ones, leaves every other row alone. It runs
from both `--create-db` and `--seed`, so fixing a spelling in the data module and
running `--seed` on the server is the whole deployment — no drop, no reseed. The
table exists after the first startup but is **empty until `--seed` runs** on that
database; until then every Arabic field is null and the games play as before.

### Seed content rules: the ladder, the hadith, the digits

Everything in `scripts/seed_data/` reaches production through `--seed` (the content
seeds are upserts), so these rules hold for every word, card and question.
`tests/scripts/test_content_integrity.py` enforces the first four mechanically; each of
its finders takes its data as an argument, so it can be pointed at an older copy of a
file (`git show HEAD:<file>` into a temp path, never `git stash`) to see what it catches.

- **No Kalimat hint names its word — hint 6 included.** No rung, in any language,
  contains the word itself or any of its `accepted_answers`, compared the way the Word
  Quiz compares (`utils/text_match`: diacritics and accents stripped, case, Arabic
  letters folded, the article "ال" / "al" optional, a joined و/ف/ب/ل/ك allowed) and on
  whole words. Hint 6 is the most decisive rung, not the answer: a Qur'anic detail, a
  sahih hadith, a date — not a translation or a gloss of the word ("The Opening",
  "Repentance", "سورة الكهف" all leaked). The test reports word, rung and language.
- **No weak hadith.** Every hadith or Prophetic saying, quoted, paraphrased or alluded to
  ("the Prophet said", "قال رسول الله", "known as the heart of the Qur'an"), is graded on
  dorar.net or sunnah.com (islamqa.info / islamweb.net for the grading's source).
  Sahih or hasan: keep it in the source's wording, with its reference (Bukhari/Muslim
  number, or surah:ayah). Da'if, mawdu' or no basis: remove it, or replace it with an
  authentic report on the same point. Weak stories told as fact go too (the spider and
  the dove at Thawr, Salman proposing the trench, Ali tearing off Khaybar's gate). No
  grading established → drop the attribution. `WEAK_HADITH_PHRASES` in the test lists
  the wordings already removed ("الدعاء مخ العبادة", Yasin "the heart of the Qur'an",
  Ar-Rahman "the bride", "أنا مدينة العلم", the hafiz interceding for ten, …), scanned
  over the seed data AND the front locales: add a phrase whenever one is taken out, and
  keep it narrow enough that no legitimate text matches.
- **Western digits only.** No Eastern Arabic digit (٠-٩) anywhere in `seed_data`, Arabic
  strings included ("سنة 1453م", "2.5%", "(العنكبوت: 14)").
- MCQ: four choices `"0".."3"`, distinct and non-empty in en, ar and fr, and a valid
  `correct_answer_index`. Not checked, but a rule: an Arabic choice does not just repeat
  the question's own words ("what does الحمد لله mean?" → "الحمد لله" leaked).
- Every fact says the same thing in all three languages; a correction made in one is
  mirrored in the other two.

### The Kunnash (كُنّاش): words kept from finished games

`NotebookEntry` (`models/notebook.py`, table `notebook_entry`) — `user_id`, `term`
(the Latin key exactly as the game stored it: `Word.word`, `CodenamesWord.word`,
`QuizWord.word_en`), `game_type` (`NotebookGameType`: undercover / codenames /
word_quiz — the `GameType` values; MCQ has no words — plus **daily_word**, the word of
the day: a QuizWord resolved exactly like a word_quiz one, kept with
`source_game_id` null, through `POST /daily-word/keep` only), `source_game_id`,
`kept_at` (UTC-aware). A new table, not columns anywhere (added before migrations existed). Registered in
`models/table.py` like every other model, so `--delete`'s `drop_all` drops it
before `user` and `game` (it holds FKs to both).

**`game_type` is a native PostgreSQL ENUM** (`notebookgametype`, which stores the
member NAMES: `UNDERCOVER`, `CODENAMES`, `WORD_QUIZ`, `DAILY_WORD`), created with all
four by the baseline migration. **A new member needs a migration that runs `ALTER TYPE
notebookgametype ADD VALUE IF NOT EXISTS '<NAME>'`**, written by hand (autogenerate does
not see enum labels; `test_a_database_at_head_is_what_the_models_declare` fails without
it), deployed with or before the code that writes it — without it the insert answers
"invalid input value for enum".

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
  `word_ar_vocalized` is therefore null for a Word Quiz word whose Latin key
  ("Ibrahim / Abraham") or Arabic differs from term_script's (101 of the 191 seeded
  words on 2026-10-28): the client shows `word_ar` then. A seeded quiz word that IS a
  term_script term spells `word_ar` exactly as term_script's `ar`, article included
  ("الحديبية", "الصفا", "الخندق", "القرآن", "الأمويون"). The hint is `resolve_multilingual`
  (`utils/multilingual.py`) over `Word.hint` (else `long_description`), the oldest
  `CodenamesWord` row with a hint, or `QuizWord.explanation` (else the last rung).
- **Keeps are rate-limited per user** (`NOTEBOOK_KEEP_RATE_LIMIT`,
  `key_func=user_or_ip_key`) — see "Rate limits" below.
- **Someone else's entry is a 404 on DELETE**, the same as a missing id, so ids
  cannot be probed. Account deletion purges the rows (`_purge_user_references`).
- Nothing is pushed over Socket.IO: the notebook is personal, there is no room.
- **Word Quiz and word-of-the-day entries share one `quiz_word` lookup**
  (`_QUIZ_WORD_TYPES`, a tuple: `in` compares by equality, while a set of StrEnum
  members hashes them by NAME and misses their plain-string values). The dialect
  insert is `utils/dialect.dialect_insert(session, Model)`, shared with the daily word.

### The word of the day (Kalimat al-yawm, كلمة اليوم)

A daily solo puzzle on the Word Quiz content: one `QuizWord` per day, the same for
everyone, found from its six-rung ladder and typed in any language or script.

- **The day turns at midnight in Makkah** (`DAILY_WORD_TIMEZONE = "Asia/Riyadh"`, UTC+3,
  no DST — 21:00 UTC, i.e. 22:00 or 23:00 in France, prime time for European players).
  `utils/daily_word.py` holds the pure rules: `makkah_day(instant)`,
  `daily_word_number(day)` = `(day - DAILY_WORD_EPOCH).days + 1`, never below 1
  (2026-10-29, the Makkah day of the first production deploy, is #1, so the first word
  players saw reads #1; never move the epoch once live, every shared "#N" would change),
  `next_day_starts_at(day)` (UTC), `ladder_length(hints)` (consecutive rungs "1".."n",
  capped at `DEFAULT_WORD_QUIZ_MAX_HINTS`, at least 1), `solved_score` (Kalimat's
  `max_hints - hints_revealed + 1`) and `compute_streaks`. The production image has the
  zone database (`python:3.14-slim` installs `tzdata`; checked in `e2e-backend`).
- **Tables** (in the baseline migration; registered in `models/table.py`):
  `daily_word` (`day` DATE PK → `quiz_word_id`, `created_at`) and `daily_word_play`
  (`UniqueConstraint(user_id, day)`; `hints_revealed` from 1, `attempts`, `last_guess`,
  `guesses` — the most recent `DAILY_WORD_GUESSES_KEPT`, for the "your tries" list —
  `solved_at`, `gave_up`, `score`, `started_at`; index on `day` for the solvers count).
  A `QuizWord` that has been a daily word can no longer be deleted (FK): the seed never
  deletes quiz words (it upserts by `word_en`), and `WordQuizController.delete` has no
  route — a future one must handle that row first.
- **The draw is lazy and race-safe.** The first request of a day draws with `rng`
  among the words not drawn in the last `DAILY_WORD_NO_REPEAT_DAYS` (180; all of them if
  that leaves none), `INSERT … ON CONFLICT DO NOTHING` on `day`, commits, then re-reads:
  two first requests racing agree on the word
  (`test_concurrent_first_requests_agree_on_the_word`, postgres).
- **A play is created on the first move** (hint, guess or give-up — viewing hint 1
  writes nothing) by the same insert on `(user_id, day)`, then read `SELECT … FOR
  UPDATE` (SQLite drops the clause): a double tap or two tabs are serialised and each
  move is one commit, so a give-up racing a right guess cannot both land
  (`test_concurrent_first_moves_make_one_play`, postgres). Finished = `solved_at` set or
  `gave_up`; nothing moves after that (`DailyWordAlreadyFinishedError`, 409).
- **Matching is Kalimat's, literally**: `utils/text_match.matches_quiz_answer(answer,
  spellings=(word_en, word_ar, word_fr), accepted_answers=…)`, which
  `WordQuizGameController._check_answer` now delegates to. A blank answer (nothing left
  once normalised) is `EmptyAnswerError` and is not counted.
- **A wrong try opens the next rung**, as a hint would (`guess`: `hints_revealed += 1`
  while a rung is left; on the last rung tries are free). It costs the point a hint
  costs. A free wrong try made the ladder pointless: the category leaves 17 to 53
  candidates (Places 17 … Islamic Concepts 53 of the 191 seeded words), so typing them
  one by one at hint 1 — a person with a list of prophets, or a script well inside the
  rate limit — paid the full 6 points. Now such a walk reaches the last rung and scores 1.
- **Score and streaks.** Solved: `max_hints - hints_revealed + 1` (6 → 1); give-up: 0.
  The streak is the run of solved Makkah days ending today, or yesterday while today is
  still open; a give-up closes today, so the streak reads 0. Best streak = the longest
  run. Both come from ONE query over the player's plays (`test_streaks_are_one_query`).
- **The secret.** Before the caller has finished, no payload — state, error envelope,
  anything — carries the word's spellings, an accepted answer, the explanation, or a
  rung past `hints_revealed`: `hints` is the revealed prefix (`_resolve_hints`), and
  `answer` is set only on the caller's own solved or given-up play. Other players
  finishing changes nothing for anyone else. `test_no_payload_carries_the_word_before_the_caller_finishes`
  drives the real stack (routes, real JWTs, the DB) in all three languages and reads
  every raw body; it fails if `_resolve_hints` sends the whole ladder (checked).
- **Every move names its day.** `POST`s take `?day=` (the day the page shows); another
  day than today in Makkah is `DailyWordNotTodayError` (409). Without it a page left open
  past midnight would have its guess judged against the new word and counted as a
  wrong try on it. `keep` accepts any day the caller finished, so that page can still
  keep the word it revealed. `day` is optional (today) but the client should always send it.
- **Anonymous callers** (`get_optional_current_user` in `dependencies.py`) see the
  number, the category and hint 1, `streak`/`best_streak` null, never the answer. No
  token at all is anonymous; a token that IS presented must be valid (401 otherwise),
  so an expired session goes through the client's 401 handling instead of silently
  showing a signed-in player the signed-out page.
- **Keep** writes a `daily_word` notebook entry via `NotebookController.keep_daily_word`
  (idempotent, rate-limited per user with `NOTEBOOK_KEEP_RATE_LIMIT`); 409
  `DailyWordNotFinishedError` before a finish. The reveal is
  `NotebookController.get_word_forms` — the notebook's own resolution (`word_display`
  in `lang`, the word's `word_ar`, term_script's vocalisation when it vocalises that
  same Arabic, the explanation else the last rung) — plus `kept` / `entry_id` from
  `find_entry`.
- **Guesses are rate-limited per user** (`DAILY_WORD_GUESS_RATE_LIMIT`, 30/minute,
  `user_or_ip_key`, standard 429 envelope). The limit protects the server and only slows
  a script; what keeps a scripted walk from paying is the wrong-try rule above. A script
  can still solve at 1 point and lift `solvers_today` and its own streak: there is no
  leaderboard on these, so that is accepted. Account deletion purges the plays.
- Nothing is pushed over Socket.IO: the word of the day is personal.
- **The client** (`/today`, `front/src/components/daily`, and the home card) relies on
  three of these rules: it reads `GET /daily-word` only once its auth has settled (a
  stale token would 401 and bounce a visitor to the login page), sends `day` = the
  state's `day` on every move, and reads the day again on a 409 `dailyWordNotToday`,
  `dailyWordAlreadyFinished` or `dailyWordNoMoreHints`. It counts down to `next_day_at`
  and re-reads just after it. Changing any of these changes `front/CLAUDE.md` too.

| Route | Hook | Params / body → response |
|---|---|---|
| `GET /daily-word` | `useGetDailyWordApiV1DailyWordGet` | `lang` (optional auth) → `DailyWordState` |
| `POST /daily-word/hint` | `useRevealDailyWordHintApiV1DailyWordHintPost` | `lang, day` → `DailyWordState` |
| `POST /daily-word/guess` | `useGuessDailyWordApiV1DailyWordGuessPost` | `{answer}` + `lang, day` → `DailyWordGuessResponse {correct, state}` |
| `POST /daily-word/give-up` | `useGiveUpDailyWordApiV1DailyWordGiveUpPost` | `lang, day` → `DailyWordState` |
| `POST /daily-word/keep` | `useKeepDailyWordApiV1DailyWordKeepPost` | `lang, day` → `NotebookKeepResponse` |

`DailyWordState`: `day`, `number`, `category` (`WordQuizCategory` | null), `max_hints`,
`hints` (prefix), `hints_revealed`, `status` (`not_started | playing | solved |
gave_up`), `attempts`, `guesses`, `score`, `streak`, `best_streak`, `solvers_today`,
`next_day_at`, `answer` (`DailyWordAnswer {word_display, word_ar, word_ar_vocalized,
explanation, kept, entry_id}` | null). Every field is always sent. Errors:
`dailyWordAlreadyFinished`, `dailyWordNoMoreHints`, `dailyWordNotFinished`,
`dailyWordNotToday` (all 409), plus `emptyAnswer` and `noQuizWordsAvailable`.
Tests: `tests/api/utils/test_daily_word.py`, `tests/api/controllers/test_daily_word.py`
(freezegun at noon in Makkah; the turn of the day; the window; races),
`tests/api/routes/test_daily_word.py` (wiring, the 429, the leak test).

### Samar riddles (السَّمَر): a riddle for a waiting table, never a spoiler

`GET /api/v1/rooms/{room_id}/riddle?lang=` (`routes/riddle.py`, hook
`useGetRoomRiddleApiV1RoomsRoomIdRiddleGet`) → `RoomRiddle {id, category, hint, answer:
RoomRiddleAnswer {word_display, word_ar, word_ar_vocalized}}`: rung 1
(`ROOM_RIDDLE_HINT_RUNG`) of a random `QuizWord` and its answer, for the lobby while it waits
and for The Quiz between two questions (the client keeps the answer back). Existing content
only: nothing is written for the riddle. `controllers/riddle.py` (`RiddleController`):

- **Members only**, by the `RoomUserLink`'s existence (like the chat: a briefly disconnected
  member and a spectator get one), asked first: `RoomMembersOnlyError` (403,
  `errors.api.roomMembersOnly`) tells a stranger nothing about the room.
- **Never today's word of the day**: the day's word is drawn first if nobody has asked for it
  yet (`DailyWordController.get_today(None)`, the lazy draw /daily-word does), or the day's
  draw could land on the riddle just shown. The words of the last `DAILY_WORD_NO_REPEAT_DAYS`
  are left out too, unless nothing else is left (then only today's).
- **Never a word of the room's running game.** The Quiz deals all its questions at the start
  (`question_ids`, plus `current_question`): every right choice, in every language, is a key,
  and a word whose spellings or accepted answers share one is left out (`_answer_keys`: case,
  diacritics, accents, hyphens, Arabic letter variants, the article in either script, each side
  of "Ibrahim / Abraham"; wider than Kalimat's match, since a wider net only skips a riddle).
  **Any other game in progress answers `RiddleNotDuringGameError` (409)**: Kalimat draws its
  words one round at a time (`used_word_ids` grows), so a riddle between its rounds could be a
  later round's word; Undercover and Codenames are not a waiting table. A finished game left on
  the room holds nothing back. The draw never falls back to the whole table (`pick_ids` does):
  no word left is `NoQuizWordsAvailableError`.
- **Resolved in `lang`** through `normalize_lang` first (the notebook's spelling compares the
  code raw: "ar-SA" answered the Latin word) then `resolve_multilingual` and
  `NotebookController.get_word_forms` (the word as Kalimat shows it, its Arabic, term_script's
  vocalisation when it vocalises that same Arabic).
- **Rate-limited per signed-in user** (`ROOM_RIDDLE_RATE_LIMIT`, 20/minute, and
  `ROOM_RIDDLE_DAILY_LIMIT`, 30/day, both `user_or_ip_key`): a client asks once when its panel
  shows (then keeps the riddle in the tab) and once per "Another riddle". The daily cap is the
  real guard: a riddle's answer comes from the words the NEXT word of the day is drawn from, so
  a script under the minute's limit must not collect the whole table in an afternoon (solo
  Kalimat exposes the same words, more slowly). Pre-drawing the daily calendar and excluding
  it would close it fully; not done. Reads: two narrow column selects at most (sqlmodel types four columns), then
  the drawn row; never the content table's ladders.
- Not fixed here (a later change to Kalimat's draw): a riddle shown in a lobby whose next game
  is Kalimat may be one of that game's words (about 7 in 190 per riddle); the client offers no
  tap reveal in a Kalimat lobby, and the start answers it only after the game.
- Tests: `tests/api/controllers/test_riddle.py` (both dialects: the daily word, the recent
  ones, the Quiz's answers in any script, the 409 per game type, languages, members),
  `tests/api/routes/test_riddle.py` (wiring, envelopes, the per-user 429).

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
endpoints (login, register) stay per IP. "Per IP" is `rate_limit.client_ip_key` (the
limiter's default key and `user_or_ip_key`'s fallback): `CF-Connecting-IP` when the peer is
inside `CLOUDFLARE_IP_RANGES`, else the peer itself — every request reaches production
through a Cloudflare edge, and keying on the edge address made unrelated visitors share a
budget while an attacker got one per edge (SEC F03, INFRA-07, PD-07). A direct caller's
header is ignored, so it needs no origin lock, but it does need uvicorn's
`--forwarded-allow-ips` narrowed to the proxy network (backend/Dockerfile). `/auth/refresh`
is keyed per ACCOUNT its token names (`refresh_sub_key`; the account is recorded by the
`get_presented_refresh_token` dependency, signature-checked, else per address): every page
load spends a refresh, and a table of phones on one connection exhausted a per-IP budget
(FR-3 d). Room join and spectate
(`ROOM_JOIN_RATE_LIMIT`) and room invites (`ROOM_INVITE_RATE_LIMIT`) are per user (SEC
F03, F15). So are the game routes any client can call at will, each a locked write and/or
a broadcast (WP-11): Kalimat's `/answer` (`WORDQUIZ_ANSWER_RATE_LIMIT`, BR-10, SEC F15),
the three hint-viewed routes (`HINT_VIEW_RATE_LIMIT`, SEC F07) and the four timer-expired
routes (`TIMER_EXPIRED_RATE_LIMIT`, SEC F08: anyone could make the whole table refetch
as often as they liked). A client fires timer-expired once per timer window and again
after 15 s at most (`PhaseTimer`), and treats a failed call as best-effort, so the limits
never bind on an honest page. Tests: `tests/api/routes/test_wp11_game_route_limits.py`. There is deliberately no per-room failed-PIN counter: rotating the PIN on
failures would let anyone break a room's share link.

**A plain `@limiter.limit` is counted per request PATH, not per route.** slowapi's
`key_style` defaults to `"url"`, so the bucket is (key, path): a path parameter splits the
budget, one per value. That is harmless where the value is pinned (a game id the caller
plays in, their own user id) and a hole where the caller names any value at will: the
invite accept (`/rooms/invites/{invite_id}/accept`) gave a fresh budget to every made-up
id. Such a route takes `@limiter.shared_limit(..., scope=<a constant>)`
(`ROOM_INVITE_ACCEPT_RATE_LIMIT_SCOPE`), and its test sends a different path each call.

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
  not drop a player at a timestamp that no longer exists. The re-check runs UNDER
  the game lock (`_remove_member(..., only_if_expired=True)`), which a resume holds
  too, so a resume can no longer slip in between it and the removal. If every phone
  outlasts even the paused grace, the first removal finds nobody connected or inside
  their grace, deactivates the room and CANCELS the game (BR-05) instead of leaving it
  running and paused for ever. One phone outlasting it while the others are still inside
  theirs is only that player's departure (review R1: it used to cancel the game for all). On resume, `_shift_disconnect_grace` moves each
  still-disconnected link's `disconnected_at` by the same rule (naive, like every
  `RoomUserLink` timestamp), so the ordinary grace counts only running time. **No
  auto-resume on host departure**: the host leaving during the prayer is the normal
  case, and restarting the clocks then would defeat the feature.
- **Drop-outs during the pause still apply** (they are real departures): one that
  decides the game ends it through the usual end-of-game flow; the game then reads
  as not paused and cannot be resumed (400). A quiz departure that completes the
  open round does NOT move it while paused; the resume does
  (`_settle_after_resume`, see "A quiz round a departure completes").

Tests: `tests/api/controllers/test_game_pause.py` (all four games; the anchor tests
are written so that removing the shift fails them; the cap, the orphaned room, the
mismatched router, the server-side countdown, `can_pause` / `can_resume`, the batched
sweep and its re-check; three postgres-marked races: pause vs a move, double pause,
and double resume shifting once — that one ages the round anchor BEFORE backdating
the pause, or the anchor reads as set during the pause and is capped),
`tests/api/routes/test_game_pause.py`, `tests/api/utils/test_game_pause.py`.

### Usernames are unique — by a locked check, not by constraint

`user.username` carries **no unique constraint in the model**. On PostgreSQL the baseline
migration has the unique `ix_user_username_lower` on `lower(username)` (WP-21,
"Migrations (Alembic)" above) — a backstop that turns a bypassed check into an
`IntegrityError`, and what the `lower()` lookup reads — but SQLite (dev, the default test
run) has none, so the check below stays the rule. `controllers/user.username_is_taken(session, name, exclude_user_id=)` asks
first, case-insensitively (`lower()` on both sides: ASCII on SQLite, full Unicode on
PostgreSQL; Arabic has no case), always inside `username_claim_lock` (below), and
three paths use it (four with the internal `UserController.create_user`):

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
- `_create_social_user`: a generated Google name that collides in any case gets a
  random `_xxxx` suffix; each candidate (the name, then up to
  `SOCIAL_USERNAME_SUFFIX_ATTEMPTS` distinct suffixed ones) is locked and checked in
  turn, all locks held until the commit (`AsyncExitStack`). Every candidate taken is
  `UsernameAlreadyTakenError` — never in practice.

**The race is closed by a per-name lock held until the insert commits.** Check-then-
insert without a constraint let two concurrent registrations (or renames, or a
rename and a registration) of one new name both pass the check and both commit.
`username_claim_lock(session, name)` serialises every claim of a name:

- PostgreSQL: `pg_advisory_xact_lock(hashtext('username:' || lower(name)))`
  (`USERNAME_LOCK_PREFIX`) — **blocking**, and **transaction-scoped**, so the
  caller's commit (or rollback; the request's session closing on an error) releases
  it, and PgBouncer's transaction pooling is safe. The second claimer waits, then its
  check (a fresh READ COMMITTED statement) sees the first one's row. Never the
  session-level `pg_advisory_lock`: it leaks when the pool recycles a connection. A
  32-bit hash may give two names one key; they only wait for each other.
- SQLite (dev, tests): an in-process `asyncio.Lock` keyed on `name.lower()` in a
  `WeakValueDictionary`, like `get_game_lock`. Not reentrant — which is why the
  Google candidates are de-duplicated before they are locked.

**Rule for every claim of a username: lock, check, insert/update, ONE commit, all
inside the `async with`.** A commit before the insert would release the lock with
the name still unclaimed. Tests: `test_two_concurrent_registrations_of_one_new_username_admit_exactly_one`
and `test_two_concurrent_google_signups_of_one_name_never_share_it`
(`test_auth.py`), `test_two_concurrent_renames_to_one_new_username_admit_exactly_one`
(`test_user.py`, two cases of one name), all postgres-marked with a session per task
— each fails with the lock replaced by a no-op — plus the fallback's own tests.

### The Socket.IO `game_state` push is read in the client's language

`join_game` answers with the caller's full state (`ws/state.fetch_game_state`), and
the client writes it straight into its query cache for Undercover and Codenames. It
called every controller with the English default, so an Arabic player's game-over
meanings (`word_explanations.*_hint`, card hints) turned English a moment after the
REST response (`?lang=ar`) had them right. The handshake now accepts `auth.lang` and
`join_game` accepts `{"game_id", "lang"}` (payload wins, then the handshake, then
`en`; `utils/multilingual.normalize_lang` keeps it to `SUPPORTED_LANGUAGES`).
**The client must send it** — until it does, the push stays English.

`normalize_lang` reads a BCP 47 tag by its language part, case-insensitively (`fr-FR` →
`fr`, `ar-SA` → `ar`, `fr_CA` → `fr`; unknown, `arn` or a non-string → `en`), and
`resolve_multilingual` runs its `lang` through it. It used to accept exact codes only, so
the regional tag a browser sends (`?lang=ar-SA`, `fr-FR`) fell back to English for every
hint, meaning and notebook entry. The REST `lang` parameters are still plain `str` (each
route declares its own), so code that compares `lang` itself — `lang == "ar"` in the MCQ
question text, the Word Quiz word display and the notebook's `word_display`, and the two
`hint_data.get(lang)` in the Word Quiz hints and MCQ choices — should go through
`normalize_lang` as well (the client sends bare codes since WP-05, so this is defence in
depth). Tests: `tests/api/utils/test_multilingual.py`, `tests/api/routes/test_wp05_regional_lang.py`
(the real stack: `GET /daily-word?lang=ar-SA` answers the Arabic hint).

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

### Kalimat: a wrong try costs a rung, five tries a round (owner rule (e))

The multiplayer twin of the word of the day's rule (BR-10, SEC F15). A wrong try was
free, so walking the theme's 17-53 words at hint 1 paid the full 6 points — a script,
or a fast typist with a list, beat every honest player, and each try was a locked
write plus a broadcast.

- **The penalty.** Each wrong try of the round costs the player
  `WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY` (1) rung on the answer that finally finds the
  word: `points = max_hints - min(max_hints, hint on screen + rungs lost) + 1`, so never
  below 1. The ladder itself stays the table's, released by time
  (`_calculate_hints_revealed`): unlike the word of the day, a miss reveals no hint —
  the hints are shared by everyone at the table. `answered_at_hint` and the answer
  response's `hint_number` stay the rung that was on screen; `points` carries the
  penalty. The wrong tries are counted from `live_state["attempts"]` (every try, minus
  the one that found it: `quiz_rules.wordquiz_wrong_tries`), no new key.
- **The cap.** A round takes at most `WORDQUIZ_MAX_ATTEMPTS_PER_ROUND` (5) tries, the
  one that finds the word included; the next is `AnswerAttemptsExhaustedError` (409,
  `errors.api.answerAttemptsExhausted`, `{{max}}`), checked after `AlreadyAnsweredError`
  and before the empty-answer check, and it records nothing. A player out of tries is
  done with the round (`everyone_has_answered`), so the round goes to results once
  everyone else is done too, not when the timer runs out.
- **The state.** `WordQuizGameState.my_attempts_left` (null for a spectator, once the
  caller found the word, and outside `playing`), `my_rungs_lost` (the caller's own,
  0 for a spectator) and `max_attempts`. The per-user limit on the route
  (`WORDQUIZ_ANSWER_RATE_LIMIT`) protects the server; the rule above is what keeps a walk
  from paying.
- **Also in the quiz controllers (WP-10):** `submit_answer` calls `_check_game_in_progress`
  first (a CANCELLED quiz used to accept and score answers, BR-18); `handle_timer_expired`
  calls `_require_participant` before the status check (a stranger fired the timers,
  SEC F08); the finish writes `state["winner"]` through `quiz_rules.quiz_winner_label`
  (the one winner's username, else null) from the same `top_score_winners` set it passes
  to `record_game_end`, and both state schemas carry `winner_ids` at game over; the
  finish detaches the room through `detach_room_if_current`. A host-less room
  (`owner_id` null) counts every player in the ready quorum, and a test keeps it so
  (SEC F05).

Tests: `tests/api/controllers/test_wordquiz_game.py` and `test_mcqquiz_game.py` (the
"WP-10" sections), `test_quiz_dropout.py` (a game everyone else left has no winner), and
the real-stack route tests in `tests/api/routes/test_{wordquiz,mcqquiz}_game.py` (the 409
envelope, a stranger's timer call, an answer on a cancelled game).

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

### Departures, the sweep and the sockets (WP-04)

`controllers/disconnect.py` and `ws/handlers.py`. Tests: `test_disconnect.py`,
`test_disconnect_lock_postgres.py` (postgres), `test_heartbeat_timing.py`,
`tests/api/ws/test_handlers.py`, `tests/api/ws/test_wp04_reconnect_and_detach.py` (real
python-socketio clients against the real handlers on uvicorn).

- **A departure takes the game lock BEFORE it reads the game** (BR-04).
  `_handle_permanent_disconnect(session, link)` (signature fixed: kick, ban, leave, account
  deletion and the sweep call it) reads only `Room.active_game_id` (a column, autoflush
  off), takes `get_game_lock`, then re-reads the room and the game with
  `populate_existing`. It read the Game first and "re-read" it under the lock from the
  session's identity map (`expire_on_commit=False`), so a kick waiting behind a vote
  committed the state it had read before the vote: votes vanished (10 runs in 15 of a
  7-vote burst), and a game decided meanwhile stayed FINISHED with no winner. **Any read
  of a row another request may have changed while you waited for a lock goes through
  `populate_existing`** (or a column select, which never fills the identity map —
  `_paused_game_ids` does that).
- **One commit for the whole departure.** The `_handle_*_disconnect` handlers no longer
  lock or commit themselves when called from there (`commit=False`); room deactivation
  and ownership transfer happen inside the same locked block. **Lock order: room lock,
  then game lock**; a caller may hold the room lock, never a game lock (the SQLite
  fallback is not reentrant). A caller's staged writes (the ban's RoomBan, deleted invites and new PIN) are
  flushed only after the game lock is held: flushed before, a room-row UPDATE would wait
  on a move that finishes the game (it writes that row) while this waits on its lock.
- **Every departure marks the leaver** (`mark_player_left`, owner rule (b)) in all four
  handlers, as soon as the player is found, before any end-of-game write.
- **Codenames: a departure releases the leaver's card vote**
  (`codenames_helpers.release_departed_operative`, WP-09); when the leaver was the last
  operative the team waited on, the votes in hand turn the card now (reveal log
  included), and a card that ends the game is finished like `guess_card` finishes it.
- **A room that lets go of its game cancels it** (BR-05): when the last connected member
  leaves, `cancel_running_game` under the lock (a prayer pause every phone outlasts ends
  CANCELLED, not running and paused for ever). Who is still connected is read BEFORE the
  departure is played, and a departure that empties the room is NOT played into the game
  (`_record_departure_from_cancelled_game` only marks the leaver and sets a quiz's
  `game_over`): played first, the undercover leaving decided a civilians' win for players
  who were all away, and with every phone asleep the sweep's row order picked the result. Every finish path uses
  `detach_room_if_current`. The sweep also cancels games already orphaned — IN_PROGRESS
  while their room is INACTIVE or points at another game — once every
  `ORPHANED_GAME_SWEEP_EVERY_TICKS` (the lookup reads the game table).
- **The seat delete is a statement** (`_delete_link`, rowcount): a second path removing
  the same member gets 0 and stops, instead of the SAWarning "expected to delete 1
  row(s); 0 were matched" and a second elimination.
- **One sweeper per tick** (BDP-11, PD-12). `run_sweep_tick` runs only in the worker whose
  dedicated transaction takes `pg_try_advisory_xact_lock(DISCONNECT_SWEEP_LOCK_KEY)` (the
  sweep commits per removal, so the election cannot share its transaction); SQLite always
  sweeps. The sweep's transaction ends with a COMMIT even when it only read (rollbacks
  outnumbered commits ten to one in production).
- **A return is announced** (BDP-04). `update_heartbeat` returns a `HeartbeatResult`
  (`NOT_A_MEMBER` / `REFRESHED` / `RESTORED`); `connect`, `heartbeat` and `join_game`
  `fire_notify_room_changed` on `RESTORED` (the connect's broadcast replaces its
  sid-only initial state). The REST paths that restore a link
  (`BaseGameController._update_heartbeat_throttled`, `RoomController.get_room_state`)
  call `announce_presence_restored(room_id)`: a page polling REST while its socket is down
  restores the link first, and the socket's reconnect then has nothing to announce.
  Controllers cannot reach Socket.IO, so the listener is the checker loop's
  `on_room_changed`, registered for as long as the loop runs (`presence_listener`); no
  loop (tests, scripts), no announcement. `mark_user_disconnected` returns whether it
  flipped the link, and only a flip is broadcast.
- **A socket's close has the last word over its own presence writes** (November 2026).
  python-socketio runs `disconnect` as soon as the transport closes, while that socket's
  `connect` or `heartbeat` may still be awaiting: `connect` wrote `connected=True` after its
  awaits, so a tab closed during its handshake (or right after a heartbeat) read "connected"
  until the 20 s stale sweep. Every presence write of a socket now goes through
  `ws/handlers._write_presence` (connect, heartbeat, join_game) or `_write_absence`
  (disconnect), both under the member's per-worker `asyncio.Lock` (`_presence_locks`, key
  `"{user_id}:{room_id}"`), and `_write_presence` writes only while
  `sio.manager.is_connected(sid)` (false from `pre_disconnect`, BEFORE the disconnect
  handler runs): a close that began first leaves the write undone; one that begins during
  it waits and writes the away mark after. A per-worker lock is enough because a socket's
  events, its disconnect included, are all served by the worker holding it; across workers
  (an old tab here, its replacement there) the newer socket's heartbeat restores the seat
  within one interval, as before. `connect` also stops, refused, when the socket closed
  during its token check (it used to raise `KeyError` on the gone session). Never write
  presence for a socket outside these two helpers. Tests: `tests/api/ws/test_presence_race.py`
  (interleavings forced with pause points, every wait bounded).
- **Presence writes read the seat `FOR UPDATE`** (`update_heartbeat`,
  `mark_user_disconnected`, `populate_existing`). Read plainly, a leave, kick or sweep
  deleting the seat between the read and the write made the flush's UPDATE match no row:
  `StaleDataError`, logged at WARNING with its traceback (`_welcome_to_game`, the
  heartbeat) and sent to Bugsink. Now the deletion waits for this commit (one row, nothing
  else held, no lock-order risk), and a seat deleted first answers `NOT_A_MEMBER`.
  Tests: `tests/api/controllers/test_presence_writes_postgres.py` (PostgreSQL; SQLite has
  no row locks).
- **A removed seat cuts the socket, on every worker** (SEC F04; a kick and a ban alike).
  `remove_user_from_room_socket` leaves `room:{id}` and every `game:*` channel, then
  disconnects the local SID. `_user_sids` is per process, so every worker also runs
  `audit_local_socket_memberships` on every tick (`on_worker_tick`, outside the
  election; wired in `main.py`): ONE query for all its (user, room) pairs, and each
  socket whose seat is gone or whose `RoomBan` exists is detached and disconnected —
  within `DISCONNECT_CHECK_INTERVAL_SECONDS`. `heartbeat` (seat gone) and `join_game`
  re-check the seat and cut the socket at once; `connect` refuses a banned player even
  while a seat row exists. `_user_sids` keys and `room:{id}` use the canonical UUID.

### Shared contracts of the 2026-10 audit (WP-00)

Declared once so every later change uses the same rule. Tests:
`tests/api/controllers/test_wp00_contracts.py`, `test_game_cancel.py`.

- **Leavers get neither a win nor a loss** (owner rule (b), all four games). Every departure
  path — leave, kick, the grace sweep, account deletion — must record it with
  `utils/game_state.mark_player_left(state, user_id)` (`live_state[LEFT_PLAYER_IDS_KEY]`, a
  de-duplicated list of ids; the caller owes `flag_modified`); `left_player_ids(state)` reads
  it. A departure path that does not mark is scoring its leaver.
  `game_end_stats.scorable_players` drops those ids, so `record_game_end` writes nothing for a
  leaver: no stats row change, no achievement, no challenge progress. An Undercover drop-out
  stays in `state["players"]` (dead) and never shares the win.
- **Quiz winners** (owner rule (a)): `top_score_winners(players, *, left_ids=())` returns every
  player with the top `total_score`, only when that score is above 0 and the final roster
  (minus `left_ids`) has at least `MIN_PLAYERS_FOR_A_WIN` (2) players. A tie is a shared win; a
  0-0 game has no winner; a solo game is never a win (it fed the leaderboard and the streaks:
  three solo one-question quizzes answered wrong made a 3-win streak).
- **A running game the room lets go of is cancelled**: `controllers/game_cancel.py`.
  `cancel_running_game(session, game, room=None) -> bool` (IN_PROGRESS → CANCELLED, `end_time`,
  the pause record removed, room detached; False and nothing changed otherwise; the caller
  holds `get_game_lock` and commits). `detach_room_if_current(room, game)` clears
  `active_game_id` only when it is THIS game — the rule for every finish path (a finish of an
  old game used to unlink the room's new one). The module imports models only (the
  `base_game` → `room` → `disconnect` cycle).
- **`BaseGameController._require_participant(game, state, user_id, *, allow_spectator=True)`**:
  a player of `state["players"]` (an eliminated one included; returns the entry) or, when
  allowed, a spectator link of `game.room_id` (returns None); anyone else
  `NotAGameParticipantError` (403). For hint-viewed and timer-expired, which took any caller.
  **Rule: every hint-viewed and timer-expired call checks it, and hint-viewed accepts only a
  word the caller can see, at most `HINT_USAGE_MAX_WORDS_PER_USER` per user.** Today that holds
  for all four timer-expired routes and for Undercover's and Codenames' hint-viewed
  (`test_hint_viewed_by_a_stranger_is_refused`, `test_timer_expired_by_a_stranger_is_refused`,
  `test_a_strangers_hint_view_and_timer_call_are_refused`, `test_a_stranger_cannot_fire_the_timer`
  in both quizzes), and for Word Quiz's `record_hint_view` too since review INT-05 (a stranger:
  403; a spectator: `recorded=False`, nothing written; `test_wordquiz_game.py`,
  `test_a_stranger_cannot_record_a_hint_view`).
- **Shared `live_state` keys** (constants.py, shape documented next to each):
  `LEFT_PLAYER_IDS_KEY`, `WINNER_IDS_KEY` (list of ids, every game), `MR_WHITE_GUESS_RESULT_KEY`,
  `CODENAMES_REVEAL_LOG_KEY`, `UNDERCOVER_READY_PLAYERS_KEY` (on the current turn).
- **Two new tables** (additive, through `create_all` at the time; in the baseline migration since): `room_ban`
  (`RoomBan`, unique per room and user) and `auth_session` (`AuthSession`, plus
  `revoke_user_sessions(session, user_id, *, except_session_id=None) -> int`, one UPDATE of the
  live rows, no commit). `_purge_user_references` deletes the user's sessions and the bans OF the
  user, and nulls `banned_by` on the bans BY the user.
- **Error classes declared ahead of their packages**, each with its three translations:
  `ClueMustBeOneWordError`, `DescriptionRevealsWordError`, `AnswerAttemptsExhaustedError` (409,
  `{{max}}`), `RoomBannedError` (403), `RoomBanNotFoundError` (404), `PasswordTooLongError`,
  `SessionRevokedError` (401), `NotAnAlivePlayerError`, `InvalidAvatarUrlError`,
  `GoogleAccountMismatchError` (403). None carries a secret word.
