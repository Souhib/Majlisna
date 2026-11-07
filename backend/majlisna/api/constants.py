import re
from datetime import date
from pathlib import Path

# Room constants
ROOM_PASSWORD_LENGTH = 4
ROOM_PUBLIC_ID_LENGTH = 5
PUBLIC_ID_GENERATION_ATTEMPTS = 10  # Retries before giving up on a free room code

# Bounds for host-configurable room settings. Without them a host could set a
# 10-million-round quiz or a negative timer and wedge (or DoS) the room.
MIN_TIMER_SECONDS = 0  # 0 means "no time limit"
MAX_TIMER_SECONDS = 600
# The quizzes' round duration has no "no limit" value: their expiry check is
# elapsed >= duration - TIMER_EXPIRATION_TOLERANCE_SECONDS, so 0-2 s made every round
# expire the moment it opened (BR-17). The settings UI offers 30-180 s / 10-60 s.
MIN_QUIZ_TURN_SECONDS = 10
MIN_QUIZ_ROUNDS = 1
MAX_QUIZ_ROUNDS = 50
MIN_HINT_INTERVAL_SECONDS = 3
MAX_HINT_INTERVAL_SECONDS = 120
MAX_CUSTOM_WORD_PACKS = 20

# Game constants
MIN_PLAYERS_FOR_GAME = 3
# A game is a win only against someone: a final roster (leavers excluded) of fewer
# players than this has no winner. Owner rule (a): a solo quiz is never a win, which
# also stops win farming with a second account that leaves.
MIN_PLAYERS_FOR_A_WIN = 2
# Upper bounds, matching what each game is designed and tested for. Only the minimums
# were enforced: role distribution scales past these numbers without erroring, so a
# 20-player room produced a game nobody had ever played or tested.
MAX_PLAYERS_UNDERCOVER = 12
MAX_PLAYERS_CODENAMES = 10

# Undercover role distribution. The win rule (undercover_rules.winning_team) hands
# the impostors the game as soon as undercover + Mr. White >= civilians, so every
# deal must start with civilians strictly ahead — the old table dealt 4 players as
# 1 civilian / 2 undercover / 1 Mr. White and decided the game on the first vote.
# Mr. White therefore needs 5 players: at 4, one undercover + one Mr. White already
# tie the two civilians.
UNDERCOVER_MR_WHITE_MIN_PLAYERS = 5
UNDERCOVER_MR_WHITE_THRESHOLD_SMALL = 10  # < 10 players: 1 Mr. White
UNDERCOVER_MR_WHITE_THRESHOLD_MEDIUM = 15  # <= 15 players: 2 Mr. White
UNDERCOVER_MR_WHITE_COUNT_SMALL = 1
UNDERCOVER_MR_WHITE_COUNT_MEDIUM = 2
UNDERCOVER_MR_WHITE_COUNT_LARGE = 3
UNDERCOVER_RATIO = 4  # 1 undercover per 4 players
UNDERCOVER_MIN_COUNT = 1

# Codenames board constants
CODENAMES_BOARD_SIZE = 25
CODENAMES_FIRST_TEAM_CARDS = 9
CODENAMES_SECOND_TEAM_CARDS = 8
CODENAMES_NEUTRAL_CARDS = 7
CODENAMES_ASSASSIN_CARDS = 1

# Timer defaults (seconds) — 0 means no time limit
DEFAULT_DESCRIPTION_TIMER_SECONDS = 0
DEFAULT_VOTING_TIMER_SECONDS = 0
DEFAULT_CODENAMES_CLUE_TIMER_SECONDS = 0
DEFAULT_CODENAMES_GUESS_TIMER_SECONDS = 0

# Word Quiz constants
WORD_QUIZ_MIN_PLAYERS = 1
DEFAULT_WORD_QUIZ_TURN_DURATION = 60
DEFAULT_WORD_QUIZ_HINT_INTERVAL = 10
DEFAULT_WORD_QUIZ_ROUNDS = 7
DEFAULT_WORD_QUIZ_MAX_HINTS = 6
# What a player typed is kept per round (live_state["attempts"]) and shown in the
# round's results once it resolves — never before, since a correct one IS the answer.
WORD_QUIZ_TYPED_ANSWER_MAX_LENGTH = 100
# Owner rule (e), the multiplayer twin of the word of the day's rule (BR-10): a free
# wrong try made the ladder pointless — walking a theme's 17-53 words at hint 1 paid
# the full 6 points. A wrong try costs the player one rung, and a round allows at most
# WORDQUIZ_MAX_ATTEMPTS_PER_ROUND tries (AnswerAttemptsExhaustedError past that).
WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY = 1
WORDQUIZ_MAX_ATTEMPTS_PER_ROUND = 5
# Per signed-in user (rate_limit.user_or_ip_key). Protects the server: each try is a
# locked write plus a broadcast to the table. The rule above is what makes a walk not pay.
WORDQUIZ_ANSWER_RATE_LIMIT = "30/minute"
# The stable keys of the seeded QuizWord categories (QuizWord.category is free text,
# so an admin-created category outside this map reads as null). The client
# translates the key; the stored English label never reaches the UI.
WORD_QUIZ_CATEGORY_KEYS: dict[str, str] = {
    "Prophets": "prophets",
    "Companions": "companions",
    "Places": "places",
    "Quran": "quran",
    "Islamic History": "islamic_history",
    "Islamic Concepts": "islamic_concepts",
    "Daily Life": "daily_life",
}

# MCQ Quiz constants
MCQ_QUIZ_MIN_PLAYERS = 1
DEFAULT_MCQ_QUIZ_TURN_DURATION = 15
DEFAULT_MCQ_QUIZ_ROUNDS = 10
MCQ_QUIZ_CHOICE_COUNT = 4

# Timer tolerance (seconds) — how early a timer-expired request is accepted
TIMER_EXPIRATION_TOLERANCE_SECONDS = 2

# The prayer pause (وقفة الصلاة). The record lives at live_state[PAUSE_STATE_KEY] and
# is absent while the game runs: {by, by_username, at (UTC ISO instant), reason}.
PAUSE_STATE_KEY = "paused"
PAUSE_RECORD_BY = "by"
PAUSE_RECORD_BY_USERNAME = "by_username"
PAUSE_RECORD_AT = "at"
PAUSE_RECORD_REASON = "reason"
# The live_state keys holding the ISO instant each game's clocks count from, by
# GameType value. A resume moves every one of them forward by the paused duration, so
# the pause consumes none of their time. Keyed by the game's own type — never by the
# router a request came through — so a clock can never be shifted under the wrong key.
# A new time-based rule must add its anchor here, or its clock runs through the prayer.
PAUSE_TIME_ANCHOR_KEYS: dict[str, tuple[str, ...]] = {
    # Undercover: the describing, voting and Mr. White timers.
    "undercover": ("timer_started_at",),
    # Codenames: the clue and the guess timers.
    "codenames": ("timer_started_at",),
    # Word Quiz: the round timer, the hint ladder, scoring and answer_time_ms.
    "word_quiz": ("round_started_at",),
    # MCQ: the round timer and the speed bonus.
    "mcq_quiz": ("round_started_at",),
}

# Connection lifecycle constants (seconds)
HEARTBEAT_STALE_SECONDS = 20  # Mark disconnected after 20s without heartbeat
GRACE_PERIOD_SECONDS = 180  # Permanently remove after 180s of being disconnected (game only)
LOBBY_GRACE_PERIOD_SECONDS = 600  # Permanently remove after 600s (10 min) of being disconnected in lobby
DISCONNECT_CHECK_INTERVAL_SECONDS = 5  # How often the checker loop runs
# The shared sweep (stale heartbeats, expired graces, orphaned games) runs once per tick
# across ALL uvicorn workers: on PostgreSQL the worker that wins
# pg_try_advisory_xact_lock(DISCONNECT_SWEEP_LOCK_KEY) does it, the others skip the tick
# (BDP-11, PD-12: 4 workers swept the same rows). Above 2**32 on purpose: the game locks
# hash to 32 bits (game_lock._game_id_to_lock_key) and the username locks to int4, so
# this key can never collide with either.
DISCONNECT_SWEEP_LOCK_KEY = 0x4D414A4C53575045  # "MAJLSWPE"
# The schema at boot (schema.migrate_to_head on PostgreSQL) runs in every uvicorn worker's
# lifespan, and `alembic` from the CLI takes the same lock (migrations/env.py).
# pg_advisory_xact_lock(SCHEMA_DDL_LOCK_KEY) makes them take turns: the first migrates,
# the others find the database at head (INFRA-13: 3 of 4 workers crashed on CREATE TYPE
# when they raced). Above 2**32 like the sweep key, so it collides with no other lock.
SCHEMA_DDL_LOCK_KEY = 0x4D414A4C53434841  # "MAJLSCHA"
# How long a migration statement may wait for a table lock, once the schema lock is held
# (the wait for that one is unbounded): a DDL statement queued behind a long transaction
# would otherwise hold every query on its table behind it. Past it the migration fails,
# the boot with it, and the next boot tries again.
SCHEMA_DDL_LOCK_TIMEOUT = "5s"
# Alembic (backend/migrations/, backend/CLAUDE.md "Migrations (Alembic)"). The baseline
# is the schema production had when migrations were set up (2026-11-01, built by
# create_all); a database created before then has no alembic_version and is stamped at
# it, once, if its schema is exactly what the baseline creates.
ALEMBIC_BASELINE_REVISION = "0001_baseline"
ALEMBIC_VERSION_TABLE = "alembic_version"
# Where adoption builds the baseline to compare a database without alembic_version with,
# inside a savepoint that is always rolled back: nothing of it is ever committed.
SCHEMA_ADOPTION_PROBE_SCHEMA = "majlisna_baseline_probe"
# The PostgreSQL-only indexes, which the models do not declare: two on an expression, one
# with a sort order. The migrations create them (the baseline: these three); autogenerate
# must not offer to drop them, so migrations/env.py leaves them out of the comparison. Add
# the name of every such index a later migration creates; a plain index is declared in its
# model instead. The two unique lower() ones must stay out of the models: the test
# databases (create_all) store case variants of usernames and addresses on purpose.
POSTGRES_ONLY_INDEXES = frozenset(
    {
        "ix_user_username_lower",
        "ix_user_email_lower",
        "ix_userstats_total_games_won_desc",
    }
)
# Every how many ticks the elected sweeper also cancels orphaned running games (an
# IN_PROGRESS game whose room is INACTIVE or points at another game). Nothing is waiting
# on an orphan, and the lookup reads the game table, so once a minute is enough.
ORPHANED_GAME_SWEEP_EVERY_TICKS = 12
# While the host has paused a game for the prayer, a disconnected player is kept this
# long instead of GRACE_PERIOD_SECONDS: phones lock and sockets drop while everyone
# prays, and nobody is waiting on anyone. Long enough for a congregational prayer
# (Jumu'ah with its khutbah), and finite on purpose — it is what eventually removes a
# host who never comes back, so ownership transfers and the new host can resume.
PAUSED_GAME_GRACE_PERIOD_SECONDS = 45 * 60
# How long a pause belongs to the host alone. Past it, any player of the game may
# resume: a host whose tab stays open (so the grace above never removes them) but who
# never comes back would otherwise hold the whole table paused for good. Same bound as
# the paused grace, so a prayer that keeps a disconnected player also keeps the host's
# say over resuming.
PRAYER_PAUSE_MAX_SECONDS = PAUSED_GAME_GRACE_PERIOD_SECONDS

# The username of the host who started a game, written into live_state at start so the
# game-over colophon can say whose majlis it was even after ownership has moved on.
HOST_USERNAME_STATE_KEY = "host_username"

# ── Shared live_state keys (WP-00 contracts; wave-1 packages read and write these) ──
# Every player who left before the end — voluntary leave, kick, the grace sweep,
# account deletion. Shape: list[str] of user ids, de-duplicated, in departure order.
# Written ONLY through utils/game_state.mark_player_left, read through left_player_ids.
# Owner rule (b): a leaver gets neither a win nor a loss, in all four games
# (game_end_stats.scorable_players drops them), and an Undercover drop-out — still in
# state["players"], dead — never shares the win.
LEFT_PLAYER_IDS_KEY = "left_player_ids"
# Who won, for every game type. Shape: list[str] of user ids (empty: no winner, e.g. a
# 0-0 or a solo quiz). The quizzes' state["winner"] named one player; ties share.
WINNER_IDS_KEY = "winner_ids"
# The last Mr. White guess, for the verdict every player reads.
# Shape: {"user_id": str, "correct": bool}.
MR_WHITE_GUESS_RESULT_KEY = "mr_white_guess_result"
# Codenames: every card turned, in order. Shape: list of {"card_index": int, "team":
# str (the guessing team), "card_type": str (red/blue/neutral/assassin), "voter_ids":
# list[str] (the operatives who pointed at it), "clue_turn": int}. Read by the
# assassin_finder and sweep_victory achievements.
CODENAMES_REVEAL_LOG_KEY = "reveal_log"
# Codenames: how many clues have been given in the game, an int (0 at the start). Every
# give_clue adds 1, so the clue_turn of a reveal is that clue's 1-based position in
# state["clue_history"]. A game that predates the key counts len(clue_history).
CODENAMES_CLUE_TURN_KEY = "clue_turn"
# Undercover next-round ready quorum (owner rule (d)), stored on the CURRENT TURN, not
# at the top of the state: turn["ready_players"] = list[str] of user ids. The round
# advances when every alive non-host player is ready, or when the host forces it.
UNDERCOVER_READY_PLAYERS_KEY = "ready_players"

# The unanimous_vote achievement: every ballot of a round but the target's own names the
# target, with at least this many such ballots (two players agreeing is not a table's
# verdict), and none of them drawn by the timer.
UNANIMOUS_VOTE_MIN_VOTES = 3
# Stored on the turn: the ids whose ballot _auto_fill_missing_votes drew at the deadline.
UNDERCOVER_AUTO_VOTERS_KEY = "auto_voters"
# hint-viewed: the distinct words one user may record in a game's live_state["hint_usage"]
# (a Codenames board is 25). The list was unbounded, so anyone with a game id could grow
# live_state without limit (SEC F07).
HINT_USAGE_MAX_WORDS_PER_USER = 25

# Per-user rate limits (rate_limit.user_or_ip_key) on endpoints that each cost a locked
# write and/or a broadcast; room join stays per IP where the caller is anonymous.
HINT_VIEW_RATE_LIMIT = "60/minute"
TIMER_EXPIRED_RATE_LIMIT = "30/minute"
ROOM_JOIN_RATE_LIMIT = "10/minute"
ROOM_INVITE_RATE_LIMIT = "20/minute"
# A friend's room invite (RoomInvite) opens the room without the PIN for this long after it
# was sent or last re-sent; then it answers RoomInviteExpiredError (410).
ROOM_INVITE_LIFETIME_MINUTES = 30
# GET /rooms/invites: the caller's live invites, newest first (the strip shows the first).
ROOM_INVITE_LIST_LIMIT = 20
# POST /rooms/invites/{id}/accept counts ROOM_JOIN_RATE_LIMIT in this one bucket per user.
# slowapi's default bucket is the request path, which holds the invite id: without a fixed
# scope each made-up id bought a fresh budget.
ROOM_INVITE_ACCEPT_RATE_LIMIT_SCOPE = "room-invite-accept"
FRIEND_REQUEST_RATE_LIMIT = "20/minute"
# PATCH /users/{id}/password, per user: each try is a bcrypt check or a call to Google,
# and without it a stolen session could guess the current password at will.
PASSWORD_CHANGE_RATE_LIMIT = "5/minute"

# Auth constants
# NOTE: token lifetimes live in settings.py (access_token_expire_minutes /
# refresh_token_expire_days) — do not duplicate them here.
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1
EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt truncates at 72 bytes
# The limit bcrypt actually has is in BYTES of UTF-8, not characters: 72 Arabic
# letters are 144 bytes, of which bcrypt silently ignores the second half (or, with
# bcrypt >= 4.1, raises). PasswordTooLongError answers a password over it.
BCRYPT_MAX_PASSWORD_BYTES = 72

# Server-side sessions (SEC F01). A session (models/auth_session.AuthSession, its id is
# the tokens' "sid" claim) lives at most this long, however often it is refreshed.
SESSION_ABSOLUTE_LIFETIME_DAYS = 30
# A refresh token is single-use; the PREVIOUS one is still accepted this long after a
# rotation, so two tabs refreshing at once (or a retried request) do not read as theft.
REFRESH_REUSE_GRACE_SECONDS = 30

# Profile pictures: an https URL on one of these host suffixes (Google's avatar CDN),
# at most this long. Any URL used to be stored and shown to every visitor (SEC F15).
AVATAR_URL_MAX_LENGTH = 512
ALLOWED_AVATAR_HOST_SUFFIXES = (".googleusercontent.com",)
AVATAR_URL_SCHEME = "https"
# The host must be plain DNS labels (no userinfo, port, percent-escape or IDN trick that
# a browser would read as another host than the suffix check saw).
AVATAR_HOST_PATTERN = r"^[a-z0-9-]+(\.[a-z0-9-]+)+$"

# Cloudflare's published edge ranges: the only peers whose X-Forwarded-For /
# CF-Connecting-IP may be trusted (uvicorn ran with --forwarded-allow-ips '*', so a
# direct caller could spoof its address and defeat every per-IP rate limit).
# Source: https://www.cloudflare.com/ips-v4 and https://www.cloudflare.com/ips-v6
# (also https://api.cloudflare.com/client/v4/ips), fetched 2026-10-30. Re-fetch when
# Cloudflare announces a change; a missing range makes its visitors share one limit.
CLOUDFLARE_IP_RANGES = (
    # IPv4
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    # IPv6
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)
# The visitor's address as Cloudflare saw it (it overwrites any copy a client sends).
# Read by rate_limit.client_ip_key only when the peer is inside CLOUDFLARE_IP_RANGES.
CF_CONNECTING_IP_HEADER = "CF-Connecting-IP"

# User constants
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
# No whitespace, no markup characters, no "@" (a username must not read as an address).
USERNAME_PATTERN = r"^[^\s<>/\\@]+$"
# Namespace of the advisory lock that serialises claims of one username
# (controllers/user.username_claim_lock): pg_advisory_xact_lock(hashtext(prefix || lower(name))).
USERNAME_LOCK_PREFIX = "username:"
# A generated Google username that is taken gets a random suffix; this many suffixed
# candidates are tried (each checked under its own lock) before sign-up gives up.
SOCIAL_USERNAME_SUFFIX_ATTEMPTS = 3

# Languages the game content is written in ({en, ar, fr} JSON values). A `lang` a
# client sends is normalised to one of these (utils/multilingual.normalize_lang).
SUPPORTED_LANGUAGES = ("en", "ar", "fr")
DEFAULT_LANGUAGE = "en"

# Heartbeat throttle (seconds) — skip DB write if last heartbeat is fresher
HEARTBEAT_THROTTLE_SECONDS = 10

# Chat constants
CHAT_MESSAGE_MAX_LENGTH = 500

# Game lock constants
LOCK_TIMEOUT_SECONDS = 30

# Undercover word constants
UNDERCOVER_WORD_MAX_LENGTH = 50

# Cache TTLs (seconds). NOTE: the cache is per-uvicorn-worker, so a TTL is the only
# real freshness bound — invalidation reaches one worker out of four. User stats are
# deliberately NOT cached; see StatsController.get_user_stats. Nor is game content:
# draws and the admin lists read the database (see utils/draw.py).
CACHE_TTL_LEADERBOARD_SECONDS = 30

# What the leaderboard can be ranked by (`GET /stats/leaderboard?stat_field=`). A
# whitelist: the field used to be looked up with getattr on UserStats, so any column
# name was accepted, and `win_rate` (the page's own "Win rate" sort) is not a column
# at all, which answered a 500. `win_rate` is computed in SQL from won / played.
LEADERBOARD_SORT_FIELDS = (
    "total_games_won",
    "total_games_played",
    "win_rate",
    "current_win_streak",
    "longest_win_streak",
)

# Auth providers. AUTH_PROVIDER_EMAIL means "the account has a password of its own" (the
# login refuses any other); a Google-only account (GOOGLE, a random sentinel password)
# becomes EMAIL once it sets a password, its google_sub kept (controllers/user.py).
AUTH_PROVIDER_EMAIL = "email"
AUTH_PROVIDER_GOOGLE = "google"

# Notebook (Kunnash) constants — words kept from finished games
NOTEBOOK_PAGE_DEFAULT_LIMIT = 50
NOTEBOOK_PAGE_MAX_LIMIT = 100
# The opaque keyset cursor (kept_at + id, base64url). Anything longer is not one of ours.
NOTEBOOK_CURSOR_MAX_LENGTH = 200
NOTEBOOK_TERM_MAX_LENGTH = 100
# The unique constraint keeping one row per (user, game type, word); the keep insert
# resolves its conflicts on exactly these columns.
NOTEBOOK_UNIQUE_COLUMNS = ("user_id", "game_type", "term")
# Keeping writes up to 25 rows per call (a Codenames board), so it is limited like
# other writes; listing and deleting are cheap reads/owner-scoped deletes. Counted per
# signed-in USER (see rate_limit.user_or_ip_key), not per IP: a majlis is several
# phones on one home connection, and they would otherwise share one budget.
NOTEBOOK_KEEP_RATE_LIMIT = "30/minute"

# The word of the day (Kalimat al-yawm, كلمة اليوم): one QuizWord per day, the same for
# everyone, found from its hint ladder. The day turns at midnight in Makkah: Saudi
# Arabia keeps UTC+3 all year (no DST), but the zone name, not a fixed offset, says why.
DAILY_WORD_TIMEZONE = "Asia/Riyadh"
# Day #1, the Makkah day the word of the day went public (its first production deploy),
# so the first word players see reads #1. A day's number is (day - DAILY_WORD_EPOCH).days
# + 1, never below 1. Never move it once live: every shared "#N" line would change.
DAILY_WORD_EPOCH = date(2026, 10, 29)
# A word drawn for a day is not drawn again for this many days (unless that leaves none).
DAILY_WORD_NO_REPEAT_DAYS = 180
# Every player starts with the first rung of the ladder; viewing it writes nothing.
DAILY_WORD_INITIAL_HINTS = 1
# One row per player per day; the race-safe insert resolves its conflicts on these.
DAILY_WORD_PLAY_UNIQUE_COLUMNS = ("user_id", "day")
# The guesses a play keeps for the "your tries" list (the most recent ones); `attempts`
# still counts every one.
DAILY_WORD_GUESSES_KEPT = 20
DAILY_WORD_ANSWER_MAX_LENGTH = 100
# Per signed-in user (rate_limit.user_or_ip_key): one guess every two seconds is more
# than any person types. It protects the server, nothing more: 30 a minute still walks a
# theme's 17 to 53 words in under two minutes. What keeps such a walk from paying is the
# rule that a wrong try opens the next rung (DailyWordController.guess): it scores 1.
DAILY_WORD_GUESS_RATE_LIMIT = "30/minute"

# Samar riddles (GET /rooms/{id}/riddle): while a table waits, the vaguest rung of a
# random Kalimat word and its answer. Per signed-in user (rate_limit.user_or_ip_key): a
# lobby asks once when its panel shows and once per "another riddle", so this only
# bounds a script.
ROOM_RIDDLE_HINT_RUNG = 1
ROOM_RIDDLE_RATE_LIMIT = "20/minute"
# And per day: a riddle's answer comes from the words the NEXT word of the day is drawn
# from, so a script under the minute's limit must still not collect the whole table
# (about 190 words) in an afternoon. Several evenings of play stay well under it.
ROOM_RIDDLE_DAILY_LIMIT = "30/day"

# Rate limiting: the key of a request whose caller is signed in.
RATE_LIMIT_USER_KEY_PREFIX = "user:"

# Socket.IO handshake origins (ws/server.socket_allowed_origins, SEC F12): the CORS_ORIGINS
# entry that means "any origin" (development), which python-socketio reads the same way.
SOCKET_ALLOW_ALL_ORIGINS = "*"

# Production data safety (scripts/generate_fake_data.py, scripts/purge_seed_data.py).
# The MAJLISNA_ENV / ENVIRONMENT value of the production deployment (either one names it).
PRODUCTION_ENVIRONMENT = "production"
# Every `pg_dump -Fc` (custom-format) archive starts with these bytes.
PG_DUMP_CUSTOM_FORMAT_MAGIC = b"PGDMP"
# A destructive run on production needs a dump written less than this long ago.
PRODUCTION_DUMP_MAX_AGE_SECONDS = 3600
# The exit code of a run refused for production safety (argparse's usage-error code).
PRODUCTION_REFUSAL_EXIT_CODE = 2
# The address domains of seeded accounts: TEST_USERS (@test.com) and Faker's safe emails.
SEED_EMAIL_DOMAINS = ("test.com", "example.com", "example.org", "example.net")

# The commit the image was built from (/health `version`, the error tracker's release).
# The image's last build step writes it to this file (backend/Dockerfile,
# scripts/build-commit.sh): from the GIT_SHA build arg (CI), else from the clone's git
# metadata (Dokploy, which passes no build arg). Settings read it when the GIT_SHA variable
# names no commit. A commit is exactly 40 lowercase hex digits; anything else is unknown.
BUILD_COMMIT_FILE = Path("/app/GIT_SHA")
BUILD_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
UNKNOWN_BUILD_COMMIT = "unknown"
