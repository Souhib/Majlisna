export const API_URL = process.env.API_URL || "http://localhost:5049";
export const FRONTEND_URL =
  process.env.FRONTEND_URL || "http://localhost:3049";

// ─── Test Accounts (seeded by generate_fake_data.py) ───────
// Only TEST_ADMIN and TEST_USER are still used (by auth/profile tests).
// Game tests use generateTestAccounts() from test-setup.ts for per-test isolation.

export const TEST_ADMIN = {
  email: process.env.TEST_ADMIN_EMAIL || "admin@test.com",
  password: process.env.TEST_ADMIN_PASSWORD || "admin123",
} as const;

export const TEST_USER = {
  email: process.env.TEST_USER_EMAIL || "user@test.com",
  password: process.env.TEST_USER_PASSWORD || "user1234",
} as const;

// ─── localStorage Keys (must match front/src/lib/auth.ts) ──

export const STORAGE_KEYS = {
  token: "ibg-token",
  refreshToken: "ibg-refresh-token",
  tokenExpiry: "ibg-token-expiry",
  userData: "ibg-user-data",
} as const;

// ─── Frontend Routes ────────────────────────────────────────

export const ROUTES = {
  home: "/",
  login: "/auth/login",
  register: "/auth/register",
  rooms: "/rooms",
  createRoom: "/rooms/create",
  room: (id: string) => `/rooms/${id}`,
  undercoverGame: (id: string) => `/game/undercover/${id}`,
  codenamesGame: (id: string) => `/game/codenames/${id}`,
  profile: "/profile",
  leaderboard: "/leaderboard",
} as const;

// ─── Socket.IO Event Names ─────────────────────────────────

export const SOCKET_EVENTS = {
  // Room events
  ROOM_STATUS: "room_status",
  NEW_USER_JOINED: "new_user_joined",
  USER_LEFT: "user_left",
  ERROR: "error",

  // Connection events
  PLAYER_DISCONNECTED: "player_disconnected",
  PLAYER_RECONNECTED: "player_reconnected",
  PLAYER_LEFT_PERMANENTLY: "player_left_permanently",
  OWNER_CHANGED: "owner_changed",

  // Undercover events
  ROLE_ASSIGNED: "role_assigned",
  GAME_STARTED: "game_started",
  VOTE_CASTED: "vote_casted",
  PLAYER_ELIMINATED: "player_eliminated",
  GAME_OVER: "game_over",
  GAME_CANCELLED: "game_cancelled",
  UNDERCOVER_GAME_STATE: "undercover_game_state",
  YOU_DIED: "you_died",
  NOTIFICATION: "notification",
  WAITING_OTHER_VOTES: "waiting_other_votes",

  // Codenames events
  CODENAMES_GAME_STARTED: "codenames_game_started",
  CODENAMES_CLUE_GIVEN: "codenames_clue_given",
  CODENAMES_CARD_REVEALED: "codenames_card_revealed",
  CODENAMES_TURN_ENDED: "codenames_turn_ended",
  CODENAMES_GAME_OVER: "codenames_game_over",
} as const;
