export const API_URL = process.env.API_URL || "http://localhost:5049";
export const FRONTEND_URL =
  process.env.FRONTEND_URL || "http://localhost:3049";

// ─── Test Accounts (seeded by generate_fake_data.py) ───────
// Only TEST_ADMIN and TEST_USER are still used, read-only (login, page visits). A spec
// that changes an account (password, deletion, a room seat) registers its own with
// generateTestAccounts() from test-setup.ts: the seeded ones are shared by every worker.

export const TEST_ADMIN = {
  email: process.env.TEST_ADMIN_EMAIL || "admin@test.com",
  password: process.env.TEST_ADMIN_PASSWORD || "admin123",
} as const;

export const TEST_USER = {
  email: process.env.TEST_USER_EMAIL || "user@test.com",
  password: process.env.TEST_USER_PASSWORD || "user1234",
} as const;

// ─── localStorage Keys (must match front/src/lib/auth.ts) ──

/**
 * What the page keeps of a session. The refresh token is NOT among them: the server sets
 * it as an httpOnly cookie (SEC F13), so no script can read it. `legacyRefreshToken` is
 * where the old client kept it; the specs only ever check that it stays empty.
 */
export const STORAGE_KEYS = {
  token: "majlisna-token",
  tokenExpiry: "majlisna-token-expiry",
  userData: "majlisna-user-data",
  sessionMarker: "majlisna-session",
  legacyRefreshToken: "majlisna-refresh-token",
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
  wordquizGame: (id: string) => `/game/wordquiz/${id}`,
  mcqquizGame: (id: string) => `/game/mcqquiz/${id}`,
  profile: "/profile",
  leaderboard: "/leaderboard",
  challenges: "/challenges",
  friends: "/friends",
} as const;
