import { execFileSync } from "child_process";

/**
 * Read-only access to the E2E PostgreSQL (`majlisna-e2e-db`, docker-compose.e2e.yml).
 *
 * For a secret the API keeps until the player has finished, such as today's word of the
 * day: a spec that solved it from an API answer would only show that the API leaks it.
 * The database is the source of truth, so the spec reads it there, as a player who
 * already knew the word would type it.
 *
 * `execFileSync` with an argument list, not a shell string, so the SQL needs no shell
 * quoting. Use it only for SELECTs; mutations go through the API like a player.
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
