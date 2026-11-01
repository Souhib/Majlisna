import type { RoomRiddle, WordQuizCategory } from "@/api/generated"

/**
 * The samar riddle's rules, without a screen (`SamarRiddle.tsx` draws them).
 *
 * While a table waits (the lobby, a pause between two questions of The Quiz) each member is
 * asked the vaguest rung of a Kalimat word (`GET /rooms/{id}/riddle`). Its answer comes on a
 * tap after `RIDDLE_REVEAL_AFTER_MS`, or when the game starts. The lobby follows the table
 * into the game at once and a question's results give way to the next question, so "when
 * the game starts" can only be read at the NEXT wait of that room: the riddle still on
 * screen when the table moved on is kept in the tab and comes back as "the last riddle".
 *
 * The tab keeps one record per room and per scope (the lobby, or one Quiz game), so a
 * remount or a reload shows the same riddle and asks nothing: no request but the first.
 */

/** The answer is offered on a tap once the riddle has been on screen this long. */
export const RIDDLE_REVEAL_AFTER_MS = 30_000

/** The lobby's scope, and its one wait (a game starting ends it: `answerRoomRiddle`). */
export const LOBBY_RIDDLE_SCOPE = "lobby"

/** One Quiz game's scope; each of its questions is a wait of its own. */
export const gameRiddleScope = (gameId: string) => `game:${gameId}`

const KEY_PREFIX = "majlisna-riddle:"

export interface ShownRiddle {
  riddle: RoomRiddle
  /** The language it was read in: its words are of that language. */
  lang: string
  /** The wait it belongs to: the lobby, or the question The Quiz's results are about. */
  waitKey: string
  /** When it was first shown (ms since the epoch), for the delay before its answer. */
  shownAt: number
  revealed: boolean
}

export interface RiddleRecord {
  current: ShownRiddle | null
  /** The riddle of the wait before, unanswered then: "The last riddle, “…”, was Ibrahim." */
  last: { riddle: RoomRiddle; lang: string } | null
}

const EMPTY: RiddleRecord = { current: null, last: null }

const storageKey = (roomId: string, scope: string) => `${KEY_PREFIX}${roomId}:${scope}`

function isRiddle(value: unknown): value is RoomRiddle {
  if (!value || typeof value !== "object") return false
  const riddle = value as Record<string, unknown>
  const answer = riddle.answer as Record<string, unknown> | null | undefined
  return typeof riddle.id === "string" && typeof riddle.hint === "string" && !!answer && typeof answer.word_display === "string"
}

function readShown(value: unknown): ShownRiddle | null {
  if (!value || typeof value !== "object") return null
  const shown = value as Record<string, unknown>
  if (!isRiddle(shown.riddle) || typeof shown.lang !== "string" || typeof shown.waitKey !== "string" || typeof shown.shownAt !== "number") return null
  return { riddle: shown.riddle, lang: shown.lang, waitKey: shown.waitKey, shownAt: shown.shownAt, revealed: shown.revealed === true }
}

function readLast(value: unknown): RiddleRecord["last"] {
  if (!value || typeof value !== "object") return null
  const last = value as Record<string, unknown>
  return isRiddle(last.riddle) && typeof last.lang === "string" ? { riddle: last.riddle, lang: last.lang } : null
}

/** The record the tab keeps for this room and scope; empty when there is none or storage is refused. */
export function readRiddleRecord(roomId: string, scope: string): RiddleRecord {
  try {
    const raw = sessionStorage.getItem(storageKey(roomId, scope))
    if (!raw) return EMPTY
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const current = readShown(parsed.current)
    const last = readLast(parsed.last)
    // a record with a malformed riddle in it is no record
    if ((parsed.current && !current) || (parsed.last && !last)) return EMPTY
    return { current, last }
  } catch {
    return EMPTY
  }
}

export function writeRiddleRecord(roomId: string, scope: string, record: RiddleRecord): void {
  try {
    sessionStorage.setItem(storageKey(roomId, scope), JSON.stringify(record))
  } catch {
    // storage refused (a private window): the riddle lives as long as the panel
  }
}

/** The table moved on: the riddle on screen is answered at the next wait (unless already read). */
function answered(record: RiddleRecord): RiddleRecord {
  const { current } = record
  if (!current) return record
  return { current: null, last: current.revealed ? null : { riddle: current.riddle, lang: current.lang } }
}

/**
 * What a panel opening on `waitKey` in `lang` shows of the record: the same riddle while the
 * wait is the same (a remount, a reload); the riddle of an earlier wait as the last one, and
 * a new riddle to ask; nothing read in another language.
 */
export function settleRiddleRecord(record: RiddleRecord, waitKey: string, lang: string): RiddleRecord {
  let next = record.current && record.current.waitKey !== waitKey ? answered(record) : record
  if (next.current && next.current.lang !== lang) next = { ...next, current: null }
  if (next.last && next.last.lang !== lang) next = { ...next, last: null }
  return next
}

/** The lobby's game has started: called by `useRoomLobby` as it follows the table into the game. */
export function answerRoomRiddle(roomId: string): void {
  const record = readRiddleRecord(roomId, LOBBY_RIDDLE_SCOPE)
  if (record.current) writeRiddleRecord(roomId, LOBBY_RIDDLE_SCOPE, answered(record))
}

/** "While you wait: who is it?" for a person, "where" for a place, "what" for anything else (Kalimat's own rule). */
export function riddleAskKey(category: WordQuizCategory | null | undefined): string {
  if (category === "prophets" || category === "companions") return "room.riddle.askWho"
  if (category === "places") return "room.riddle.askWhere"
  return "room.riddle.askWhat"
}
