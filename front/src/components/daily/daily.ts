import { type DailyWordAnswer, type DailyWordState, type DailyWordStatus, getDailyWordApiV1DailyWordGetQueryKey, wordQuizCategoryEnum } from "@/api/generated"
import { arabicOf } from "@/components/notebook/entries"
import { latnLocale } from "@/components/stats/format"

/**
 * Pure helpers of the word of the day (كلمة اليوم, /today), kept free of React so they
 * are unit-tested on their own (`__tests__/daily.test.ts`). The server owns every rule
 * (the day, the number, the score, the streaks); these only word what it sent.
 */

type T = (key: string, opts?: Record<string, unknown>) => string

/** The page's address as a shared line names it (no scheme: it reads as text). */
export const DAILY_SHARE_URL = "majlisna.app/today"

/**
 * The longest guess the server takes: `DAILY_WORD_ANSWER_MAX_LENGTH` in
 * backend/majlisna/api/constants.py (the generated schema says `.max(100)` too). The
 * field stops there, so a longer one never comes back as a bare 422.
 */
export const DAILY_WORD_ANSWER_MAX_LENGTH = 100

/** The name in Arabic, which leads the page and the home card in every language. */
export const DAILY_ARABIC_NAME = "كلمة اليوم"

/** Every query of the endpoint (any language, any viewer): TanStack matches key prefixes. */
export const DAILY_WORD_URL_KEY = [{ url: "/api/v1/daily-word" }] as const

/**
 * The day's state as one viewer sees it. The generated key holds only `lang`; the
 * viewer is added because a signed-out and a signed-in read of the same URL differ
 * (hint 1 only and no streak, against the player's own play), so a login or a logout
 * must never show the other one's cached state.
 */
export function dailyWordKey(lang: string, viewer: string | null) {
  return [...getDailyWordApiV1DailyWordGetQueryKey({ lang }), { viewer }] as const
}

export type DailyWordKey = ReturnType<typeof dailyWordKey>

export function isFinished(status: DailyWordStatus | null | undefined): boolean {
  return status === "solved" || status === "gave_up"
}

/**
 * What a right answer is worth now, and after one more hint (Kalimat's rule, the
 * server's `max_hints - hints_revealed + 1`): "Another hint: 5 points instead of 6". A
 * wrong try opens the next rung too, so it costs the same point. `next` is null when the
 * ladder has no rung left to reveal.
 */
export function stakes(state: Pick<DailyWordState, "max_hints" | "hints_revealed">): { now: number; next: number | null } {
  const now = Math.max(1, state.max_hints - state.hints_revealed + 1)
  return { now, next: state.hints_revealed < state.max_hints ? now - 1 : null }
}

/** "Wednesday 28 October 2026": the Makkah day the server names, in the interface language, Western digits. */
export function formatDailyDate(day: string, lang: string): string {
  // the day is a calendar date: read and written in UTC so no time zone moves it
  const date = new Date(`${day}T12:00:00Z`)
  if (Number.isNaN(date.getTime())) return ""
  return new Intl.DateTimeFormat(latnLocale(lang), { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(date)
}

/** "05:12:33" (hours, minutes, seconds), never below zero. */
export function formatCountdown(msLeft: number): string {
  const total = Math.max(0, Math.ceil(msLeft / 1000))
  const parts = [Math.floor(total / 3600), Math.floor((total % 3600) / 60), total % 60]
  return parts.map((n) => String(n).padStart(2, "0")).join(":")
}

/** The ISO 8601 duration of a countdown, for `<time dateTime>` ("PT5H12M33S"). */
export function countdownDuration(msLeft: number): string {
  const total = Math.max(0, Math.ceil(msLeft / 1000))
  return `PT${Math.floor(total / 3600)}H${Math.floor((total % 3600) / 60)}M${total % 60}S`
}

/** The theme's key in `game.quiz.kalimat.category` ("a prophet"), null for none or an unknown one. */
const CATEGORIES = new Set<string>(Object.values(wordQuizCategoryEnum))
export function categoryKey(category: string | null | undefined): string | null {
  return category && CATEGORIES.has(category) ? `game.quiz.kalimat.category.${category}` : null
}

/** The panel's question for a theme, as Kalimat asks it: a person or a place as such, anything else as a word. */
export function promptKey(category: string | null | undefined): string {
  if (category === "prophets" || category === "companions") return "game.quiz.kalimat.askWho"
  if (category === "places") return "game.quiz.kalimat.askWhere"
  return "game.quiz.kalimat.askWhat"
}

/** "found at hint 3 · 4 points", or "given up". Empty while the day is open. */
export function resultLine(state: Pick<DailyWordState, "status" | "hints_revealed" | "score">, t: T): string {
  if (state.status === "solved") {
    return `${t("daily.reveal.foundAt", { number: state.hints_revealed })} · ${t("game.quiz.kalimat.pointsSr", { count: state.score ?? 0 })}`
  }
  if (state.status === "gave_up") return t("daily.reveal.gaveUp")
  return ""
}

/**
 * The line "Share" copies: plain text, no emoji and never the answer.
 * "Majlisna · Word of the day #1 · found at hint 3 of 6 · majlisna.app/today"
 */
export function shareLine(state: Pick<DailyWordState, "status" | "number" | "hints_revealed" | "max_hints">, t: T): string {
  const base = { number: state.number, url: DAILY_SHARE_URL }
  if (state.status === "solved") return t("daily.share.solved", { ...base, hint: state.hints_revealed, total: state.max_hints })
  return t("daily.share.gaveUp", base)
}

export interface DailyTry {
  text: string
  /** The guess that found the word (the last one of a solved day). */
  right: boolean
}

/** The player's tries, oldest first (the server keeps the last 20); a solved day ends with the right one. */
export function triesOf(state: Pick<DailyWordState, "status" | "guesses">): DailyTry[] {
  const last = state.guesses.length - 1
  return state.guesses.map((text, i) => ({ text, right: state.status === "solved" && i === last }))
}

/**
 * How the answer reads: the Arabic headword (vocalised when the server has it), and
 * the word as Kalimat shows it in the interface language when that adds something. The
 * Arabic interface reads the Arabic alone, never a transliteration (DESIGN.md §8).
 */
export function answerForms(answer: DailyWordAnswer, arabicUi: boolean): { arabic?: string; display?: string; label: string } {
  const arabic = arabicOf(answer)
  const shown = answer.word_display.trim()
  const display = (arabicUi && arabic) || !shown || shown === arabic || shown === answer.word_ar ? undefined : shown
  return { arabic, display, label: arabicUi && arabic ? arabic : shown || arabic || "" }
}

/** Milliseconds from `now` until the next word is out (the server's `next_day_at`), never negative. */
export function msUntil(iso: string, now: number): number {
  const at = Date.parse(iso)
  return Number.isFinite(at) ? Math.max(0, at - now) : 0
}
