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

# Undercover role distribution thresholds
UNDERCOVER_MR_WHITE_THRESHOLD_SMALL = 10  # < 10 players: 1 Mr. White
UNDERCOVER_MR_WHITE_THRESHOLD_MEDIUM = 15  # <= 15 players: 2 Mr. White
UNDERCOVER_MR_WHITE_COUNT_SMALL = 1
UNDERCOVER_MR_WHITE_COUNT_MEDIUM = 2
UNDERCOVER_MR_WHITE_COUNT_LARGE = 3
UNDERCOVER_RATIO = 4  # 1 undercover per 4 players
UNDERCOVER_MIN_COUNT = 2

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

# MCQ Quiz constants
MCQ_QUIZ_MIN_PLAYERS = 1
DEFAULT_MCQ_QUIZ_TURN_DURATION = 15
DEFAULT_MCQ_QUIZ_ROUNDS = 10

# Timer tolerance (seconds) — how early a timer-expired request is accepted
TIMER_EXPIRATION_TOLERANCE_SECONDS = 2

# Connection lifecycle constants (seconds)
HEARTBEAT_STALE_SECONDS = 20  # Mark disconnected after 20s without heartbeat
GRACE_PERIOD_SECONDS = 180  # Permanently remove after 180s of being disconnected (game only)
LOBBY_GRACE_PERIOD_SECONDS = 600  # Permanently remove after 600s (10 min) of being disconnected in lobby
DISCONNECT_CHECK_INTERVAL_SECONDS = 5  # How often the checker loop runs

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

# Auth providers
AUTH_PROVIDER_EMAIL = "email"
AUTH_PROVIDER_GOOGLE = "google"
