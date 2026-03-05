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
  token: "ipg-token",
  refreshToken: "ipg-refresh-token",
  tokenExpiry: "ipg-token-expiry",
  userData: "ipg-user-data",
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
