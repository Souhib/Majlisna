import { API_URL } from "./constants";

// ─── Types ──────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
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

// ─── HTTP Helpers ───────────────────────────────────────────

async function postJSON<T>(
  path: string,
  body: Record<string, unknown>,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} failed (${res.status}): ${text}`);
  }

  return res.json();
}

async function getJSON<T>(path: string, token?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, { headers });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GET ${path} failed (${res.status}): ${text}`);
  }

  return res.json();
}

// ─── Auth API ───────────────────────────────────────────────

export async function apiLogin(
  email: string,
  password: string,
): Promise<LoginResponse> {
  return postJSON<LoginResponse>("/api/v1/auth/login", { email, password });
}

export async function apiRegister(
  username: string,
  email: string,
  password: string,
): Promise<RegisterResponse> {
  return postJSON<RegisterResponse>("/api/v1/auth/register", {
    username,
    email_address: email,
    password,
  });
}

export async function apiRefreshToken(
  refreshToken: string,
): Promise<{ access_token: string; refresh_token: string }> {
  const res = await fetch(
    `${API_URL}/api/v1/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`,
    { method: "POST" },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token refresh failed (${res.status}): ${text}`);
  }

  return res.json();
}

// ─── Room API ───────────────────────────────────────────────

export async function apiCreateRoom(
  token: string,
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz" = "undercover",
): Promise<RoomResponse> {
  return postJSON<RoomResponse>(
    "/api/v1/rooms",
    { game_type: gameType },
    token,
  );
}

export async function apiGetRoom(
  roomId: string,
  token: string,
): Promise<RoomResponse> {
  return getJSON<RoomResponse>(`/api/v1/rooms/${roomId}`, token);
}

export async function apiJoinRoom(
  publicRoomId: string,
  userId: string,
  password: string,
  token: string,
): Promise<RoomResponse> {
  return patchJSON<RoomResponse>(
    "/api/v1/rooms/join",
    { public_room_id: publicRoomId, user_id: userId, password },
    token,
  );
}

// ─── Room Leave API ─────────────────────────────────────────

async function patchJSON<T>(
  path: string,
  body: Record<string, unknown>,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PATCH ${path} failed (${res.status}): ${text}`);
  }

  return res.json();
}

export async function apiLeaveRoom(
  roomId: string,
  userId: string,
  token: string,
): Promise<void> {
  await patchJSON(
    "/api/v1/rooms/leave",
    { room_id: roomId, user_id: userId },
    token,
  );
}

/**
 * Ensure a user is not in any room before creating/joining a new one.
 * Fetches all rooms and leaves any the user is currently in.
 */
export async function apiLeaveAllRooms(
  userId: string,
  token: string,
): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const rooms = await getJSON<RoomResponse[]>("/api/v1/rooms", token);
      const myRooms = rooms.filter((r) => r.users?.some((u) => u.id === userId));
      if (myRooms.length === 0) return; // Clean
      for (const room of myRooms) {
        await apiLeaveRoom(room.id, userId, token).catch(() => {});
      }
    } catch {
      // Token might be expired, rooms endpoint might fail
      return;
    }
  }
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
  description_order?: { user_id: string; username: string }[];
  current_describer_index?: number;
  descriptions?: Record<string, string>;
}

export async function apiGetUndercoverState(
  gameId: string,
  token: string,
): Promise<UndercoverGameState> {
  return getJSON<UndercoverGameState>(
    `/api/v1/undercover/games/${gameId}/state`,
    token,
  );
}

export async function apiSubmitDescription(
  gameId: string,
  word: string,
  token: string,
): Promise<void> {
  await postJSON(
    `/api/v1/undercover/games/${gameId}/describe`,
    { word },
    token,
  );
}

// ─── Undercover Vote & Next Round API ──────────────────────

export async function apiSubmitVote(
  gameId: string,
  votedFor: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/undercover/games/${gameId}/vote`,
    { voted_for: votedFor },
    token,
  );
}

export async function apiNextRound(
  gameId: string,
  roomId: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/undercover/games/${gameId}/next-round`,
    { room_id: roomId },
    token,
  );
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
}

export async function apiGetCodenamesBoard(
  gameId: string,
  token: string,
): Promise<CodenamesBoardState> {
  return getJSON<CodenamesBoardState>(
    `/api/v1/codenames/games/${gameId}/board`,
    token,
  );
}

export async function apiGiveClue(
  gameId: string,
  clueWord: string,
  clueNumber: number,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/codenames/games/${gameId}/clue`,
    { clue_word: clueWord, clue_number: clueNumber },
    token,
  );
}

export async function apiGuessCard(
  gameId: string,
  cardIndex: number,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/codenames/games/${gameId}/guess`,
    { card_index: cardIndex },
    token,
  );
}

export async function apiEndTurn(
  gameId: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/codenames/games/${gameId}/end-turn`,
    {},
    token,
  );
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
  round_results: {
    user_id: string;
    username: string;
    answered_at_hint: number | null;
    points: number;
  }[];
  correct_answer: string | null;
  winner: string | null;
  leaderboard: {
    user_id: string;
    username: string;
    total_score: number;
  }[];
  game_over: boolean;
}

export async function apiGetWordQuizState(
  gameId: string,
  token: string,
): Promise<WordQuizGameState> {
  return getJSON<WordQuizGameState>(
    `/api/v1/wordquiz/games/${gameId}/state`,
    token,
  );
}

export async function apiSubmitWordQuizAnswer(
  gameId: string,
  answer: string,
  token: string,
): Promise<{ correct: boolean; points_earned: number; hint_number: number }> {
  return postJSON(
    `/api/v1/wordquiz/games/${gameId}/answer`,
    { answer },
    token,
  );
}

export async function apiWordQuizTimerExpired(
  gameId: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/wordquiz/games/${gameId}/timer-expired`,
    {},
    token,
  );
}

export async function apiWordQuizNextRound(
  gameId: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/wordquiz/games/${gameId}/next-round`,
    {},
    token,
  );
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
  leaderboard: {
    user_id: string;
    username: string;
    total_score: number;
  }[];
  game_over: boolean;
}

export async function apiGetMCQQuizState(
  gameId: string,
  token: string,
  lang = "en",
): Promise<MCQQuizGameState> {
  return getJSON<MCQQuizGameState>(
    `/api/v1/mcqquiz/games/${gameId}/state?lang=${lang}`,
    token,
  );
}

export async function apiSubmitMCQQuizAnswer(
  gameId: string,
  choiceIndex: number,
  token: string,
): Promise<{ correct: boolean; points_earned: number }> {
  return postJSON(
    `/api/v1/mcqquiz/games/${gameId}/answer`,
    { choice_index: choiceIndex },
    token,
  );
}

export async function apiMCQQuizTimerExpired(
  gameId: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/mcqquiz/games/${gameId}/timer-expired`,
    {},
    token,
  );
}

export async function apiMCQQuizNextRound(
  gameId: string,
  token: string,
): Promise<Record<string, unknown>> {
  return postJSON(
    `/api/v1/mcqquiz/games/${gameId}/next-round`,
    {},
    token,
  );
}

// ─── Raw HTTP helpers (for error testing) ──────────────────

/**
 * POST that returns the raw Response (does NOT throw on non-2xx).
 * Use this in error tests to check status codes.
 */
export async function rawPost(
  path: string,
  body: Record<string, unknown>,
  token?: string,
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

/**
 * PATCH that returns the raw Response (does NOT throw on non-2xx).
 * Use this in error tests to check status codes.
 */
export async function rawPatch(
  path: string,
  body: Record<string, unknown>,
  token?: string,
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  });
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

export async function apiGetFriends(
  token: string,
): Promise<{ user_id: string; username: string; status: string }[]> {
  return getJSON("/api/v1/friends", token);
}

export async function apiGetPendingRequests(
  token: string,
): Promise<{ user_id: string; username: string; status: string; friendship_id: string }[]> {
  return getJSON("/api/v1/friends/pending", token);
}

// ─── Challenge API ──────────────────────────────────────────

export async function apiSeedChallenges(
  token: string,
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${token}`,
  };
  const res = await fetch(`${API_URL}/api/v1/challenges/seed`, {
    method: "POST",
    headers,
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST /api/v1/challenges/seed failed (${res.status}): ${text}`);
  }
}

export async function apiGetActiveChallenges(
  token: string,
): Promise<{ id: string; code: string; description: string; challenge_type: string; progress: number; completed: boolean }[]> {
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
    mcq_quiz_turn_duration?: number;
  },
  token: string,
): Promise<Record<string, unknown>> {
  return patchJSON(`/api/v1/rooms/${roomId}/settings`, settings, token);
}

// ─── Health Checks ──────────────────────────────────────────

export async function waitForBackend(
  maxRetries = 60,
  delayMs = 2000,
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await fetch(`${API_URL}/health`);
      if (res.ok) return;
    } catch {
      // Connection refused, keep retrying
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error(`Backend not healthy after ${maxRetries} retries`);
}

export async function waitForFrontend(
  frontendUrl: string,
  maxRetries = 60,
  delayMs = 2000,
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await fetch(frontendUrl);
      if (res.ok) return;
    } catch {
      // Connection refused, keep retrying
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error(`Frontend not reachable after ${maxRetries} retries`);
}
