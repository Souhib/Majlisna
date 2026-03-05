import os

# Room constants
ROOM_PASSWORD_LENGTH = 4
ROOM_PUBLIC_ID_LENGTH = 5

# Game constants
MIN_PLAYERS_FOR_GAME = 3

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

# Auth constants
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Socket.IO event names
EVENT_ROOM_STATUS = "room_status"
EVENT_NEW_USER_JOINED = "new_user_joined"
EVENT_NEW_ROOM_CREATED = "new_room_created"
EVENT_YOU_LEFT = "you_left"
EVENT_USER_LEFT = "user_left"
EVENT_ROLE_ASSIGNED = "role_assigned"
EVENT_GAME_STARTED = "game_started"
EVENT_NOTIFICATION = "notification"
EVENT_PLAYER_ELIMINATED = "player_eliminated"
EVENT_YOU_DIED = "you_died"
EVENT_GAME_OVER = "game_over"
EVENT_VOTE_CASTED = "vote_casted"
EVENT_WAITING_OTHER_VOTES = "waiting_other_votes"
EVENT_ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
EVENT_ERROR = "error"

# Codenames Socket.IO event names
EVENT_CODENAMES_GAME_STARTED = "codenames_game_started"
EVENT_CODENAMES_CLUE_GIVEN = "codenames_clue_given"
EVENT_CODENAMES_CARD_REVEALED = "codenames_card_revealed"
EVENT_CODENAMES_TURN_ENDED = "codenames_turn_ended"
EVENT_CODENAMES_GAME_OVER = "codenames_game_over"

# Disconnect / reconnect constants
DISCONNECT_GRACE_PERIOD_SECONDS = int(os.getenv("DISCONNECT_GRACE_PERIOD_SECONDS", "120"))

# Disconnect / reconnect event names
EVENT_PLAYER_DISCONNECTED = "player_disconnected"
EVENT_PLAYER_RECONNECTED = "player_reconnected"
EVENT_PLAYER_LEFT_PERMANENTLY = "player_left_permanently"
EVENT_OWNER_CHANGED = "owner_changed"
EVENT_GAME_CANCELLED = "game_cancelled"
EVENT_UNDERCOVER_GAME_STATE = "undercover_game_state"
EVENT_DESCRIPTION_SUBMITTED = "description_submitted"
EVENT_DESCRIPTIONS_COMPLETE = "descriptions_complete"
EVENT_YOUR_TURN_TO_DESCRIBE = "your_turn_to_describe"
EVENT_TURN_STARTED = "turn_started"
