from datetime import date

# Room constants
ROOM_PASSWORD_LENGTH = 4
ROOM_PUBLIC_ID_LENGTH = 5
PUBLIC_ID_GENERATION_ATTEMPTS = 10  # Retries before giving up on a free room code

# Bounds for host-configurable room settings. Without them a host could set a
# 10-million-round quiz or a negative timer and wedge (or DoS) the room.
MIN_TIMER_SECONDS = 0  # 0 means "no time limit"
MAX_TIMER_SECONDS = 600
MIN_QUIZ_ROUNDS = 1
MAX_QUIZ_ROUNDS = 50
MIN_HINT_INTERVAL_SECONDS = 3
MAX_HINT_INTERVAL_SECONDS = 120
MAX_CUSTOM_WORD_PACKS = 20

# Game constants
MIN_PLAYERS_FOR_GAME = 3
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

# Auth constants
# NOTE: token lifetimes live in settings.py (access_token_expire_minutes /
# refresh_token_expire_days) — do not duplicate them here.
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1
EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt truncates at 72 bytes

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
# deliberately NOT cached; see StatsController.get_user_stats.
CACHE_TTL_GAME_CONTENT_SECONDS = 3600  # Words, term pairs, packs, quiz questions
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

# Auth providers
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

# Rate limiting: the key of a request whose caller is signed in.
RATE_LIMIT_USER_KEY_PREFIX = "user:"
