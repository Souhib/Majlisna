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
 * quoting. Use it for SELECTs; mutations go through the API like a player. The one
 * exception, `dbPlantPasswordResetToken`, stands in for the mail the stack never sends.
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
