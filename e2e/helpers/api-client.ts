import { expect } from "@playwright/test";
import { API_URL } from "./constants";

/**
 * `fetch` for the test helpers, without connection reuse. Bun keeps an idle pooled
 * socket for 300 s while uvicorn closes an idle connection after 5 s, so a request
 * sent on a pooled socket the server had just closed failed with ECONNRESET. On the
 * slow CI runner, where the gap between two helper calls often passes 5 s, that made
 * a full Codenames game flaky. A browser resends a request on a reused socket the
 * server closed; this client does not, so it simply never reuses one.
 */
export function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  return fetch(input, { ...init, keepalive: false });
}

/**
 * The same rule for Playwright's own request client (`context.request`, `page.request`,
 * the `request` fixture) when it calls the API: all of a worker's requests share one
 * keep-alive agent, and a sign-in sent on a pooled socket uvicorn had just closed failed
 * with "socket hang up" (8 workers, 2026-11-02). With this header the socket is closed
 * after the answer instead of going back to the pool, so no later request can pick it up.
 */
export const NO_SOCKET_REUSE = { Connection: "close" } as const;

// ─── Types ──────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  // No refresh_token: the server sets it as the httpOnly cookie only (SEC F13).
  token_type?: string;
  expires_in: number;
  user: {
    id: string;
    username: string;
    email: string;
  };
}

export interface RegisterResponse {
  id: string;
  username: string;
  email_address: string;
}

export interface RoomResponse {
  id: string;
  public_id: string;
  owner_id: string;
  password: string;
  users: { id: string; username: string }[];
}

/** The server's error envelope (schemas/error.error_response). */
export interface ApiErrorBody {
  error_key: string;
  message: string;
  details?: Record<string, unknown>;
}

// ─── HTTP Helpers ───────────────────────────────────────────

type Method = "GET" | "POST" | "PATCH" | "DELETE";

/** A request that returns the raw Response: it never throws on a non-2xx. */
export async function rawRequest(
  method: Method,
  path: string,
  body?: Record<string, unknown>,
  token?: string,
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return apiFetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** A request that must succeed: a non-2xx throws with the status and the body. */
async function requestJSON<T>(
  method: Method,
  path: string,
  body?: Record<string, unknown>,
  token?: string,
): Promise<T> {
  const res = await rawRequest(method, path, body, token);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${method} ${path} failed (${res.status}): ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const postJSON = <T>(path: string, body: Record<string, unknown>, token?: string) =>
  requestJSON<T>("POST", path, body, token);
const getJSON = <T>(path: string, token?: string) => requestJSON<T>("GET", path, undefined, token);
const patchJSON = <T>(path: string, body: Record<string, unknown>, token?: string) =>
  requestJSON<T>("PATCH", path, body, token);

/** POST that returns the raw Response (does NOT throw on non-2xx). */
export function rawPost(path: string, body: Record<string, unknown>, token?: string): Promise<Response> {
  return rawRequest("POST", path, body, token);
}

/** PATCH that returns the raw Response (does NOT throw on non-2xx). */
export function rawPatch(path: string, body: Record<string, unknown>, token?: string): Promise<Response> {
  return rawRequest("PATCH", path, body, token);
}

/** GET that returns the raw Response (does NOT throw on non-2xx). */
export function rawGet(path: string, token?: string): Promise<Response> {
  return rawRequest("GET", path, undefined, token);
}

/**
 * Assert a refusal by its exact status and error key. `res.ok === false` also holds for
 * a 500 or a 422, which is exactly the class of bug a refusal test must not take for a
 * pass (TQ-07).
 */
export async function expectApiError(res: Response, status: number, errorKey: string): Promise<ApiErrorBody> {
  const text = await res.text();
  expect(res.status, `expected ${status} ${errorKey}, got ${res.status}: ${text}`).toBe(status);
  const body = JSON.parse(text) as ApiErrorBody;
  expect(body.error_key, text).toBe(errorKey);
  return body;
}

// ─── Auth API ───────────────────────────────────────────────

export async function apiLogin(email: string, password: string): Promise<LoginResponse> {
  return postJSON<LoginResponse>("/api/v1/auth/login", { email, password });
}

export async function apiRegister(username: string, email: string, password: string): Promise<RegisterResponse> {
  return postJSON<RegisterResponse>("/api/v1/auth/register", {
    username,
    email_address: email,
    password,
  });
}

/** `GET /auth/me`, raw: a test of a signed-out token reads the 401 itself. */
export function rawGetMe(token: string): Promise<Response> {
  return rawGet("/api/v1/auth/me", token);
}

// ─── User API ───────────────────────────────────────────────

/** A player's stats row (read-only: an account with no game reads zeros). */
export interface UserStatsRow {
  total_games_played: number;
  total_games_won: number;
  total_games_lost: number;
  undercover_games_played: number;
  undercover_games_won: number;
  games_hosted: number;
  rooms_created: number;
}

/** A player's stats, read by a signed-in player (owner decision, 8 November 2026): any token will do. */
export async function apiGetUserStats(userId: string, token: string): Promise<UserStatsRow> {
  return getJSON<UserStatsRow>(`/api/v1/stats/users/${userId}/stats`, token);
}

/** One achievement as a player's achievements page reads it (signed in, like the stats). */
export interface AchievementRow {
  code: string;
  name: string;
  unlocked: boolean;
  progress: number;
  threshold: number;
}

/** Every achievement with this player's progress and whether it is unlocked. */
export async function apiGetUserAchievements(userId: string, token: string): Promise<AchievementRow[]> {
  return getJSON<AchievementRow[]>(`/api/v1/stats/users/${userId}/achievements`, token);
}

/** The codes this player has unlocked. */
export async function apiUnlockedAchievements(userId: string, token: string): Promise<string[]> {
  return (await apiGetUserAchievements(userId, token)).filter((a) => a.unlocked).map((a) => a.code);
}

export interface GameHistoryEntry {
  id: string;
  type: string;
  start_time: string;
  end_time: string | null;
  number_of_players: number;
  winner: string | null;
  user_role: string | null;
  user_won: boolean | null;
  game_status: string | null;
}

/** A player's game history, as their own /stats page reads it. */
export async function apiGetGameHistory(userId: string, token: string): Promise<GameHistoryEntry[]> {
  return getJSON<GameHistoryEntry[]>(`/api/v1/games/user/${userId}`, token);
}

// ─── Room API ───────────────────────────────────────────────

export async function apiCreateRoom(
  token: string,
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz" = "undercover",
): Promise<RoomResponse> {
  return postJSON<RoomResponse>("/api/v1/rooms", { game_type: gameType }, token);
}

/**
 * Fetch a room, with its PIN filled in from the members-only share-link endpoint.
 *
 * `GET /rooms/{id}` deliberately no longer returns `password`: the room view is a
 * public-ish representation and leaking the PIN there would defeat the point of
 * having one. The PIN is served by `GET /rooms/{id}/share-link`, which requires
 * membership. Tests still need `roomDetails.password` to have other players join,
 * so this helper merges the two calls.
 */
export async function apiGetRoom(roomId: string, token: string): Promise<RoomResponse> {
  const room = await getJSON<RoomResponse>(`/api/v1/rooms/${roomId}`, token);
  const { password } = await apiGetShareLink(roomId, token);
  return { ...room, password };
}

export interface RoomStateResponse {
  id: string;
  public_id: string;
  password: string;
  owner_id: string;
  active_game_id: string | null;
  game_type: string | null;
  type: string;
  players: { user_id: string; username: string; is_connected: boolean; is_host: boolean; is_spectator: boolean }[];
}

/** The lobby's own read: the roster, the PIN, the active game. */
export async function apiGetRoomState(roomId: string, token: string): Promise<RoomStateResponse> {
  return getJSON<RoomStateResponse>(`/api/v1/rooms/${roomId}/state`, token);
}

/**
 * Join a room by code + PIN.
 *
 * `userId` is accepted for readability at the call sites but is NOT sent: the
 * server takes the joining identity from the JWT, and RoomJoin is declared with
 * `extra="forbid"`, so an extra `user_id` in the body is a hard 422.
 */
export async function apiJoinRoom(
  publicRoomId: string,
  userId: string,
  password: string,
  token: string,
): Promise<RoomResponse> {
  void userId;
  return patchJSON<RoomResponse>("/api/v1/rooms/join", { public_room_id: publicRoomId, password }, token);
}

/** The same join, raw: a refusal test reads the status and the key itself. */
export function rawJoinRoom(publicRoomId: string, password: string, token: string): Promise<Response> {
  return rawPatch("/api/v1/rooms/join", { public_room_id: publicRoomId, password }, token);
}

/** Leave a room. `userId` is accepted but not sent — see apiJoinRoom. */
export async function apiLeaveRoom(roomId: string, userId: string, token: string): Promise<void> {
  void userId;
  await patchJSON("/api/v1/rooms/leave", { room_id: roomId }, token);
}

/**
 * The host kicks a player ("Remove"): out of the room (and of its game, when one is
 * running), with no ban and the same PIN: they may come back. The host can still ban them
 * afterwards (they are listed by apiListRemovals until they sit down again).
 */
export async function apiKickPlayer(roomId: string, userId: string, hostToken: string): Promise<void> {
  await patchJSON(`/api/v1/rooms/${roomId}/kick`, { user_id: userId }, hostToken);
}

/**
 * The host bans a player, seated or removed earlier and not seated again: kept out (join,
 * spectate, invites) until lifted, their room invites deleted, and a new PIN (a seated
 * player's seat goes, like a kick). Answers the ban (201).
 */
export async function apiBanPlayer(
  roomId: string,
  userId: string,
  hostToken: string,
): Promise<{ user_id: string; username: string; banned_at: string }> {
  return postJSON(`/api/v1/rooms/${roomId}/bans`, { user_id: userId }, hostToken);
}

/** The players the host banned from the room (host only; a kick is not listed). */
export async function apiListBans(
  roomId: string,
  hostToken: string,
): Promise<{ user_id: string; username: string; banned_at: string }[]> {
  return getJSON(`/api/v1/rooms/${roomId}/bans`, hostToken);
}

/** The players the host removed (a kick) who are neither banned nor seated again, newest first (host only). */
export async function apiListRemovals(
  roomId: string,
  hostToken: string,
): Promise<{ user_id: string; username: string; removed_at: string }[]> {
  return getJSON(`/api/v1/rooms/${roomId}/removals`, hostToken);
}

/** The host's rematch: back to the lobby, the running game (if any) cancelled. */
export async function apiRematch(roomId: string, hostToken: string): Promise<{ room_id: string; status: string }> {
  return postJSON(`/api/v1/rooms/${roomId}/rematch`, {}, hostToken);
}

/** A chat line in the room's lobby. */
export async function apiSendChatMessage(roomId: string, message: string, token: string): Promise<void> {
  await postJSON(`/api/v1/rooms/${roomId}/messages`, { message }, token);
}

// ─── Game Start API ─────────────────────────────────────────

export async function apiStartGame(
  roomId: string,
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz",
  token: string,
): Promise<{ game_id: string; room_id: string }> {
  const pathMap: Record<string, string> = {
    undercover: `/api/v1/undercover/games/${roomId}/start`,
    word_quiz: `/api/v1/wordquiz/games/${roomId}/start`,
    codenames: `/api/v1/codenames/games/${roomId}/start`,
    mcq_quiz: `/api/v1/mcqquiz/games/${roomId}/start`,
  };
  return postJSON(pathMap[gameType], {}, token);
}

// ─── Undercover Game API ────────────────────────────────────

export interface UndercoverGameState {
  my_role: string;
  my_word: string;
  is_alive: boolean;
  players: {
    user_id: string;
    username: string;
    is_alive: boolean;
    is_mayor?: boolean;
  }[];
  eliminated_players: { user_id: string; username: string; role: string }[];
  turn_number: number;
  has_voted: boolean;
  room_id?: string;
  is_host?: boolean;
  votes?: Record<string, string>;
  winner?: string | null;
  turn_phase?: string;
  round_resolved?: boolean;
  ready_players?: string[];
  ready_count?: number;
  ready_quorum?: number;
  is_ready?: boolean;
  mr_white_guesser?: string | null;
  description_order?: { user_id: string; username: string }[];
  current_describer_index?: number;
  descriptions?: Record<string, string>;
  my_word_hint?: string | null;
  timer_started_at?: string | null;
  word_explanations?: {
    civilian_word: string;
    undercover_word: string;
  } | null;
  paused?: GamePause | null;
  can_pause?: boolean;
  can_resume?: boolean;
}

// ─── Prayer Pause API (all four games) ──────────────────────

/** A game the host paused for the prayer (GamePause in the backend). */
export interface GamePause {
  by_user_id: string;
  by_username: string;
  since: string;
  reason: string;
  remaining_seconds: number | null;
  paused_for_seconds: number;
  anyone_can_resume_at: string;
}

export type PausableGame = "undercover" | "codenames" | "wordquiz" | "mcqquiz";

export async function apiPauseGame(game: PausableGame, gameId: string, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/${game}/games/${gameId}/pause`, {}, token);
}

export async function apiResumeGame(game: PausableGame, gameId: string, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/${game}/games/${gameId}/resume`, {}, token);
}

export async function apiGetUndercoverState(gameId: string, token: string): Promise<UndercoverGameState> {
  return getJSON<UndercoverGameState>(`/api/v1/undercover/games/${gameId}/state`, token);
}

export async function apiSubmitDescription(gameId: string, word: string, token: string): Promise<void> {
  await postJSON(`/api/v1/undercover/games/${gameId}/describe`, { word }, token);
}

export async function apiSubmitVote(gameId: string, votedFor: string, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/undercover/games/${gameId}/vote`, { voted_for: votedFor }, token);
}

/** The host's "next round", or any other alive player's "I'm ready" (owner rule (d)). */
export async function apiNextRound(
  gameId: string,
  roomId: string,
  token: string,
): Promise<{ advanced: boolean; ready_count: number; ready_quorum: number; ready_players: string[] }> {
  return postJSON(`/api/v1/undercover/games/${gameId}/next-round`, { room_id: roomId }, token);
}

// ─── Codenames Game API ────────────────────────────────────

export interface CodenamesBoardState {
  board: {
    word: string;
    card_type: string | null;
    revealed: boolean;
  }[];
  players: {
    user_id: string;
    username: string;
    team: "red" | "blue";
    role: "spymaster" | "operative";
  }[];
  current_team: "red" | "blue";
  current_turn: {
    team: "red" | "blue";
    clue_word: string | null;
    clue_number: number;
    guesses_made: number;
    max_guesses: number;
    card_votes?: Record<string, number>;
  };
  red_remaining: number;
  blue_remaining: number;
  status: string;
  winner: string | null;
  room_id?: string;
  is_host?: boolean;
  paused?: GamePause | null;
}

export async function apiGetCodenamesBoard(gameId: string, token: string): Promise<CodenamesBoardState> {
  return getJSON<CodenamesBoardState>(`/api/v1/codenames/games/${gameId}/board`, token);
}

export async function apiGiveClue(
  gameId: string,
  clueWord: string,
  clueNumber: number,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/codenames/games/${gameId}/clue`, { clue_word: clueWord, clue_number: clueNumber }, token);
}

export async function apiGuessCard(gameId: string, cardIndex: number, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/codenames/games/${gameId}/guess`, { card_index: cardIndex }, token);
}

export async function apiEndTurn(gameId: string, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/codenames/games/${gameId}/end-turn`, {}, token);
}

// ─── Word Quiz Game API ────────────────────────────────────

export interface WordQuizGameState {
  game_id: string;
  room_id: string;
  is_host: boolean;
  is_spectator: boolean;
  current_round: number;
  total_rounds: number;
  round_phase: string;
  hints_revealed: number;
  hints: string[];
  turn_duration_seconds: number;
  hint_interval_seconds: number;
  round_started_at: string | null;
  players: {
    user_id: string;
    username: string;
    total_score: number;
    current_round_answered: boolean;
    current_round_points: number;
    answered_at_hint: number | null;
  }[];
  my_answered: boolean;
  my_points: number;
  my_attempts_left: number | null;
  my_rungs_lost: number;
  max_attempts: number;
  round_results: {
    user_id: string;
    username: string;
    answered_at_hint: number | null;
    points: number;
    attempts?: number;
    typed_answer?: string | null;
  }[];
  correct_answer: string | null;
  winner: string | null;
  winner_ids?: string[] | null;
  leaderboard: {
    user_id: string;
    username: string;
    total_score: number;
  }[];
  game_over: boolean;
  paused?: GamePause | null;
}

export async function apiGetWordQuizState(gameId: string, token: string): Promise<WordQuizGameState> {
  return getJSON<WordQuizGameState>(`/api/v1/wordquiz/games/${gameId}/state`, token);
}

export async function apiSubmitWordQuizAnswer(
  gameId: string,
  answer: string,
  token: string,
): Promise<{ correct: boolean; points_earned: number; hint_number: number }> {
  return postJSON(`/api/v1/wordquiz/games/${gameId}/answer`, { answer }, token);
}

export async function apiWordQuizTimerExpired(gameId: string, token: string): Promise<{ action: string }> {
  return postJSON(`/api/v1/wordquiz/games/${gameId}/timer-expired`, {}, token);
}

export async function apiWordQuizNextRound(gameId: string, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/wordquiz/games/${gameId}/next-round`, {}, token);
}

// ─── MCQ Quiz Game API ──────────────────────────────────────

export interface MCQQuizGameState {
  game_id: string;
  room_id: string;
  is_host: boolean;
  is_spectator: boolean;
  current_round: number;
  total_rounds: number;
  round_phase: string;
  question: string | null;
  choices: string[];
  turn_duration_seconds: number;
  round_started_at: string | null;
  players: {
    user_id: string;
    username: string;
    total_score: number;
    current_round_answered: boolean;
    current_round_points: number;
  }[];
  my_answered: boolean;
  my_points: number;
  round_results: {
    user_id: string;
    username: string;
    choice_index: number | null;
    points: number;
    correct: boolean;
  }[];
  correct_answer_index: number | null;
  explanation: string | null;
  winner: string | null;
  winner_ids?: string[] | null;
  leaderboard: {
    user_id: string;
    username: string;
    total_score: number;
  }[];
  game_over: boolean;
  paused?: GamePause | null;
}

export async function apiGetMCQQuizState(gameId: string, token: string, lang = "en"): Promise<MCQQuizGameState> {
  return getJSON<MCQQuizGameState>(`/api/v1/mcqquiz/games/${gameId}/state?lang=${lang}`, token);
}

export async function apiSubmitMCQQuizAnswer(
  gameId: string,
  choiceIndex: number,
  token: string,
): Promise<{ correct: boolean; points_earned: number }> {
  return postJSON(`/api/v1/mcqquiz/games/${gameId}/answer`, { choice_index: choiceIndex }, token);
}

export async function apiMCQQuizTimerExpired(gameId: string, token: string): Promise<{ action: string }> {
  return postJSON(`/api/v1/mcqquiz/games/${gameId}/timer-expired`, {}, token);
}

export async function apiMCQQuizNextRound(gameId: string, token: string): Promise<Record<string, unknown>> {
  return postJSON(`/api/v1/mcqquiz/games/${gameId}/next-round`, {}, token);
}

// ─── Kunnash (notebook) API ─────────────────────────────────

export interface NotebookGameWord {
  word: string;
  word_display: string;
  word_ar: string | null;
  word_ar_vocalized: string | null;
  hint: string | null;
  kept: boolean;
  entry_id: string | null;
}

export interface NotebookEntry {
  id: string;
  word: string;
  word_display: string;
  game_type: string;
  word_ar: string | null;
  word_ar_vocalized: string | null;
  hint: string | null;
  source_game_id: string | null;
}

/** Every word a finished game dealt, with whether the caller kept it. */
export async function apiGetNotebookGameWords(
  gameId: string,
  token: string,
  lang = "en",
): Promise<{ game_id: string; game_type: string; words: NotebookGameWord[] }> {
  return getJSON(`/api/v1/notebook/games/${gameId}?lang=${lang}`, token);
}

/** The caller's notebook, newest first (the first page). */
export async function apiListNotebook(
  token: string,
  lang = "en",
): Promise<{ entries: NotebookEntry[]; total: number; next_cursor: string | null }> {
  return getJSON(`/api/v1/notebook?lang=${lang}&limit=50`, token);
}

// ─── Friend API ─────────────────────────────────────────────

export async function apiSendFriendRequest(
  addresseeId: string,
  token: string,
): Promise<{ friendship_id: string; status: string }> {
  return postJSON("/api/v1/friends/request", { addressee_id: addresseeId }, token);
}

export async function apiAcceptFriendRequest(
  friendshipId: string,
  token: string,
): Promise<{ friendship_id: string; status: string }> {
  return postJSON(`/api/v1/friends/${friendshipId}/accept`, {}, token);
}

export async function apiGetFriends(token: string): Promise<{ user_id: string; username: string; status: string }[]> {
  return getJSON("/api/v1/friends", token);
}

export async function apiGetPendingRequests(
  token: string,
): Promise<{ user_id: string; username: string; status: string; friendship_id: string }[]> {
  return getJSON("/api/v1/friends/pending", token);
}

// ─── Challenge API ──────────────────────────────────────────

export interface ActiveChallenge {
  id: string;
  code: string;
  description: string;
  challenge_type: string;
  target_count: number;
  game_type: string | null;
  condition: string;
  role: string | null;
  progress: number;
  completed: boolean;
}

export async function apiGetActiveChallenges(token: string): Promise<ActiveChallenge[]> {
  return getJSON("/api/v1/challenges/active", token);
}

// ─── Room Settings API ───────────────────────────────────────

export async function apiUpdateRoomSettings(
  roomId: string,
  settings: {
    description_timer?: number;
    voting_timer?: number;
    codenames_clue_timer?: number;
    codenames_guess_timer?: number;
    word_quiz_turn_duration?: number;
    word_quiz_hint_interval?: number;
    word_quiz_rounds?: number;
    mcq_quiz_turn_duration?: number;
    mcq_quiz_rounds?: number;
    enable_mr_white?: boolean;
    /** The host's game pick, which every member's lobby describes. */
    game_type?: "undercover" | "codenames" | "word_quiz" | "mcq_quiz";
  },
  token: string,
): Promise<Record<string, unknown>> {
  return patchJSON(`/api/v1/rooms/${roomId}/settings`, settings, token);
}

// ─── Spectator API ─────────────────────────────────────────

/**
 * Join a room as a spectator.
 *
 * The room PIN is required — spectating is not a way around the password. The
 * spectator cannot look it up themselves (`/share-link` is members-only), so it
 * has to be passed in, exactly like a real user receiving a share link.
 */
export async function apiJoinRoomAsSpectator(roomId: string, token: string, password: string): Promise<RoomResponse> {
  return patchJSON<RoomResponse>("/api/v1/rooms/join-spectator", { room_id: roomId, password }, token);
}

// ─── Share Link API ────────────────────────────────────────

export async function apiGetShareLink(roomId: string, token: string): Promise<{ public_id: string; password: string }> {
  return getJSON<{ public_id: string; password: string }>(`/api/v1/rooms/${roomId}/share-link`, token);
}

// ─── Health Checks ──────────────────────────────────────────

export async function waitForBackend(maxRetries = 60, delayMs = 2000): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await apiFetch(`${API_URL}/health`);
      if (res.ok) return;
    } catch {
      // Connection refused while the container starts: ask again
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error(`Backend not healthy after ${maxRetries} retries`);
}

export async function waitForFrontend(frontendUrl: string, maxRetries = 60, delayMs = 2000): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await apiFetch(frontendUrl);
      if (res.ok) return;
    } catch {
      // Connection refused while the container starts: ask again
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error(`Frontend not reachable after ${maxRetries} retries`);
}
