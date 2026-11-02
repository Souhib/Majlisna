import { execFileSync } from "child_process";

/**
 * Reads from the E2E PostgreSQL (`majlisna-e2e-db`, docker-compose.e2e.yml).
 *
 * For a secret the API keeps until the player has finished, such as today's word of the
 * day: a spec that solved it from an API answer would only show that the API leaks it.
 * The database is the source of truth, so the spec reads it there, as a player who
 * already knew the word would type it.
 *
 * `execFileSync` with an argument list, not a shell string, so the SQL needs no shell
 * quoting. Use it for SELECTs; mutations go through the API like a player. The three
 * exceptions stand in for what the stack cannot do on demand: `dbPlantPasswordResetToken`
 * for the mail it never sends, `dbMakeGoogleOnly` for a sign-in with Google, `dbSetRoomCode`
 * for a room code the draw hands out once in a while.
 */

const DB_CONTAINER = "majlisna-e2e-db";

export function dbQuery(sql: string): string {
  return execFileSync(
    "docker",
    ["exec", DB_CONTAINER, "psql", "-U", "majlisna", "-d", "majlisna", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
    { encoding: "utf8", timeout: 15_000 },
  ).trim();
}

/** One row as JSON: the query must return a single `json_build_object(...)` column. */
export function dbQueryJson<T>(sql: string): T | null {
  const out = dbQuery(sql);
  return out ? (JSON.parse(out) as T) : null;
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const UUID = /^[0-9a-f-]{36}$/i;

/** A value checked to be a YYYY-MM-DD day before it goes into SQL. */
function sqlDay(day: string): string {
  if (!ISO_DAY.test(day)) throw new Error(`not a YYYY-MM-DD day: ${day}`);
  return `'${day}'`;
}

function sqlUuid(id: string): string {
  if (!UUID.test(id)) throw new Error(`not a UUID: ${id}`);
  return `'${id}'`;
}

// ─── Kalimat ────────────────────────────────────────────────

/** The word a Kalimat game's current round is looking for, from its `live_state`. */
export function dbWordQuizCurrentWord(gameId: string): string {
  const word = dbQuery(`SELECT live_state -> 'current_word' ->> 'word_en' FROM game WHERE id = ${sqlUuid(gameId)}`);
  if (!word) throw new Error(`no current word for Kalimat game ${gameId}`);
  return word;
}

// ─── The word of the day ────────────────────────────────────

export interface DailyWordRow {
  word_en: string;
  word_ar: string | null;
  word_fr: string | null;
  /** The stored label ("Islamic Concepts"), as QuizWord keeps it. */
  category: string;
  /** The English text of each rung, "1" to "6". */
  hints_en: Record<string, string>;
}

/** The QuizWord drawn for `day` (a Makkah day), or null when nobody has asked for it yet. */
export function dbDailyWord(day: string): DailyWordRow | null {
  return dbQueryJson<DailyWordRow>(`
    SELECT json_build_object(
      'word_en', q.word_en,
      'word_ar', q.word_ar,
      'word_fr', q.word_fr,
      'category', q.category,
      'hints_en', (SELECT json_object_agg(rung.key, rung.value ->> 'en') FROM json_each(q.hints::json) AS rung)
    )
    FROM daily_word d JOIN quiz_word q ON q.id = d.quiz_word_id
    WHERE d.day = ${sqlDay(day)}`);
}

export interface DailyWordPlayRow {
  hints_revealed: number;
  attempts: number;
  guesses: string[];
  solved: boolean;
  gave_up: boolean;
  score: number | null;
}

/**
 * A player's Kunnash rows as stored: `game_type` is a native PostgreSQL ENUM holding
 * the member NAME (`DAILY_WORD`), while the API answers its value (`daily_word`).
 */
export function dbNotebookEntries(userId: string): { term: string; game_type: string; source_game_id: string | null }[] {
  const out = dbQuery(`
    SELECT coalesce(json_agg(json_build_object('term', n.term, 'game_type', n.game_type, 'source_game_id', n.source_game_id)), '[]')
    FROM notebook_entry n
    WHERE n.user_id = ${sqlUuid(userId)}`);
  return JSON.parse(out);
}

/** A player's play of `day`, or null before their first move. */
export function dbDailyWordPlay(userId: string, day: string): DailyWordPlayRow | null {
  return dbQueryJson<DailyWordPlayRow>(`
    SELECT json_build_object(
      'hints_revealed', p.hints_revealed,
      'attempts', p.attempts,
      'guesses', p.guesses,
      'solved', p.solved_at IS NOT NULL,
      'gave_up', p.gave_up,
      'score', p.score
    )
    FROM daily_word_play p
    WHERE p.user_id = ${sqlUuid(userId)} AND p.day = ${sqlDay(day)}`);
}

// ─── Games ──────────────────────────────────────────────────

/**
 * A game's stored status, as the enum NAME PostgreSQL keeps (`IN_PROGRESS`, `FINISHED`,
 * `CANCELLED`): what the database holds, whatever an endpoint chooses to show.
 */
export function dbGameStatus(gameId: string): string {
  const status = dbQuery(`SELECT game_status FROM game WHERE id = ${sqlUuid(gameId)}`);
  if (!status) throw new Error(`no game ${gameId}`);
  return status;
}

/** The index of The Quiz's right choice for the question now open (never sent while it is). */
export function dbMcqCorrectIndex(gameId: string): number {
  const index = dbQuery(`SELECT live_state -> 'current_question' ->> 'correct_answer_index' FROM game WHERE id = ${sqlUuid(gameId)}`);
  if (index === "") throw new Error(`no open question in MCQ game ${gameId}`);
  return Number(index);
}

// ─── Accounts ───────────────────────────────────────────────

/** Whether an account row still exists. */
export function dbUserExists(userId: string): boolean {
  return dbQuery(`SELECT count(*) FROM "user" WHERE id = ${sqlUuid(userId)}`) === "1";
}

/** How an account signs in, as stored: `auth_provider` ("email" = it has a password of its own) and its Google subject. */
export function dbUserSignIn(userId: string): { auth_provider: string; google_sub: string | null } | null {
  return dbQueryJson(`SELECT json_build_object('auth_provider', auth_provider, 'google_sub', google_sub) FROM "user" WHERE id = ${sqlUuid(userId)}`);
}

const GOOGLE_SUB = /^[0-9]{10,32}$/;

/**
 * The bcrypt hash of a random value thrown away when it was made: the password of an account
 * created by "Continue with Google" is such a sentinel, one nobody ever saw.
 */
const SENTINEL_PASSWORD_HASH = "$2b$12$QeY7s.TjTWTQqmSiZ23gReE5NfNvrtVzpcTAU2m321zgNOqSTgTUO";

/**
 * Turn a freshly registered account into a Google-only one, the state "Continue with Google"
 * creates: `auth_provider` google, a `google_sub`, a sentinel password. The second write this
 * module makes: the stack's Google client id is a placeholder, so no sign-in with Google can
 * complete here. Its sessions stay signed in, as a Google sign-in's would.
 */
export function dbMakeGoogleOnly(userId: string, googleSub: string): void {
  if (!GOOGLE_SUB.test(googleSub)) throw new Error(`not a Google subject: ${googleSub}`);
  const updated = dbQuery(`
    UPDATE "user"
    SET auth_provider = 'google', google_sub = '${googleSub}', password = '${SENTINEL_PASSWORD_HASH}'
    WHERE id = ${sqlUuid(userId)}
    RETURNING id`);
  if (updated.split("\n").filter((line) => UUID.test(line)).length !== 1) throw new Error(`expected one account ${userId}, got: ${updated}`);
}

// ─── Rooms ──────────────────────────────────────────────────

const ROOM_CODE = /^[0-9A-Z]{5}$/;

/**
 * Give a fresh room a code the server's draw could have given it (five of A-Z0-9), for a
 * spec about a code of a rare shape: one that reads as a number, like 3E182, comes about
 * once in 2,000 rooms. Fails loudly when another room holds the code (it is unique).
 */
export function dbSetRoomCode(roomId: string, code: string): void {
  if (!ROOM_CODE.test(code)) throw new Error(`not a room code: ${code}`);
  const updated = dbQuery(`UPDATE room SET public_id = '${code}' WHERE id = ${sqlUuid(roomId)} RETURNING id`);
  if (updated.split("\n").filter((line) => UUID.test(line)).length !== 1) throw new Error(`expected one room ${roomId}, got: ${updated}`);
}

/** A user's password-reset tokens as stored: the sha256 digest of the link's token, never the token. */
export function dbPasswordResetTokens(userId: string): { token: string; used: boolean }[] {
  const out = dbQuery(`
    SELECT coalesce(json_agg(json_build_object('token', t.token, 'used', t.used)), '[]')
    FROM passwordresettoken t
    WHERE t.user_id = ${sqlUuid(userId)}`);
  return JSON.parse(out);
}

const RESET_TOKEN = /^[A-Za-z0-9_-]{16,64}$/;

/**
 * Stand in for the mailbox: the one write this module makes.
 *
 * "Forgot password?" mails a link carrying a token, and the E2E stack sends no mail (no
 * RESEND_API_KEY). The database holds only the token's sha256 digest (SEC F06), so the
 * link cannot be read back from it either. The spec therefore replaces the digest of the
 * row the page just made with the digest of a token it knows, in the same way the server
 * stores one (`token_digest`: sha256 hex of the UTF-8 token), and follows the link a
 * player would have received. Only the user's single unused row is touched, and the
 * expiry the server set is kept.
 */
export function dbPlantPasswordResetToken(userId: string, token: string): void {
  if (!RESET_TOKEN.test(token)) throw new Error(`not a url-safe token: ${token}`);
  const updated = dbQuery(`
    UPDATE passwordresettoken
    SET token = encode(sha256(convert_to('${token}', 'UTF8')), 'hex')
    WHERE user_id = ${sqlUuid(userId)} AND used = false
    RETURNING id`);
  // psql prints the RETURNING rows, then the command tag ("UPDATE 1")
  if (updated.split("\n").filter((line) => UUID.test(line)).length !== 1) throw new Error(`expected one unused reset token for ${userId}, got: ${updated}`);
}

/** The text of each rung of `day`'s word in one language ("en", "fr", "ar"), "1" to "6". */
export function dbDailyWordHints(day: string, lang: "en" | "fr" | "ar"): Record<string, string> {
  if (!["en", "fr", "ar"].includes(lang)) throw new Error(`not a language: ${lang}`);
  const out = dbQuery(`
    SELECT json_object_agg(rung.key, rung.value ->> '${lang}')
    FROM daily_word d JOIN quiz_word q ON q.id = d.quiz_word_id, json_each(q.hints::json) AS rung
    WHERE d.day = ${sqlDay(day)}`);
  if (!out) throw new Error(`no daily word for ${day}`);
  return JSON.parse(out);
}

// ─── Samar riddles ──────────────────────────────────────────

export interface RiddleWordRow {
  word_en: string;
  category: string;
  /** Rung 1 of the word's ladder in English: what the riddle asks. */
  hint1_en: string;
}

/** The Kalimat word a samar riddle was drawn from (the riddle's id is the word's). */
export function dbRiddleWord(quizWordId: string): RiddleWordRow {
  const row = dbQueryJson<RiddleWordRow>(`
    SELECT json_build_object('word_en', q.word_en, 'category', q.category, 'hint1_en', q.hints::json -> '1' ->> 'en')
    FROM quiz_word q WHERE q.id = ${sqlUuid(quizWordId)}`);
  if (!row) throw new Error(`no quiz_word ${quizWordId}`);
  return row;
}
