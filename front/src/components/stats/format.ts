import type { AchievementWithProgress } from "@/api/generated"
import type { LozengeState, Team } from "@/components/brand"

/**
 * Pure helpers shared by the player's space (stats, game detail, profile, leaderboard).
 * Kept free of React so they are unit-tested on their own (`__tests__/format.test.ts`).
 */

type T = (key: string, opts?: Record<string, unknown>) => string

/** The four games' display names (DESIGN.md §10), keyed by the API's `GameType`. */
export const GAME_NAME_KEY: Record<string, string> = {
  undercover: "games.undercover.name",
  codenames: "games.codenames.name",
  word_quiz: "games.wordQuiz.name",
  mcq_quiz: "games.mcqQuiz.name",
}

export function gameName(type: string | null | undefined, t: T): string {
  if (!type) return ""
  const key = GAME_NAME_KEY[type]
  return key ? t(key) : type
}

/** The API's role values → their translated names (Undercover and Codenames). */
const ROLE_KEY: Record<string, string> = {
  civilian: "games.undercover.roles.civilian",
  undercover: "games.undercover.roles.undercover",
  mr_white: "games.undercover.roles.mrWhite",
  spymaster: "games.codenames.roles.spymaster",
  operative: "games.codenames.roles.operative",
}

export function roleName(role: string | null | undefined, t: T): string {
  if (!role) return ""
  const key = ROLE_KEY[role]
  return key ? t(key) : role
}

/**
 * The mark beside a role (sketch D, "the vote"): Civilian undyed, Undercover madder,
 * Mr. White a dashed (empty) lozenge. Codenames roles have no dye of their own: the
 * team carries the colour, the role is a word.
 */
export function roleLozenge(role: string | null | undefined): LozengeState | null {
  if (role === "civilian") return "undyed"
  if (role === "undercover") return "madder"
  if (role === "mr_white") return "open"
  return null
}

/** Codenames: the API still says red/blue; on screen they are madder ▲ and indigo ◆. */
export function teamOf(team: string | null | undefined): Extract<Team, "madder" | "indigo"> | null {
  if (team === "red") return "madder"
  if (team === "blue") return "indigo"
  return null
}

/** A revealed card's identity → the glyph that names it without colour. */
export function cardGlyph(cardType: string | null | undefined): Team {
  if (cardType === "red") return "madder"
  if (cardType === "blue") return "indigo"
  if (cardType === "assassin") return "assassin"
  return "bystander"
}

export function teamName(team: string | null | undefined, t: T): string {
  if (team === "red") return t("game.codenames.teams.red")
  if (team === "blue") return t("game.codenames.teams.blue")
  return team ?? ""
}

/** How a finished game ended, in words. `winner` is "civilians" | "undercovers" | "red" | "blue" | a username. */
export function winnerLine(type: string, winner: string | null | undefined, t: T): string | null {
  if (!winner) return null
  if (type === "undercover") {
    if (winner === "civilians") return t("stats.result.civilians")
    if (winner === "undercovers") return t("stats.result.undercovers")
  }
  if (type === "codenames" && (winner === "red" || winner === "blue")) {
    return t("stats.result.team", { team: teamName(winner, t) })
  }
  return t("stats.result.player", { name: winner })
}

/** Seconds → "12 min 4 s" / "40 s" in the page's language; "—" when unknown. */
export function formatDuration(seconds: number | null | undefined, t: T): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) return "—"
  const total = Math.round(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  if (m === 0) return t("stats.durationS", { s })
  return t("stats.durationMS", { m, s })
}

/** Elapsed time between two ISO timestamps, in seconds (null when either is missing). */
export function secondsBetween(start: string | null | undefined, end: string | null | undefined): number | null {
  if (!start || !end) return null
  const ms = new Date(end).getTime() - new Date(start).getTime()
  return Number.isFinite(ms) && ms >= 0 ? ms / 1000 : null
}

/** A whole-number percentage (0–100) of `part` in `whole`; 0 when there is nothing to divide. */
export function percentOf(part: number, whole: number): number {
  if (!whole || whole <= 0) return 0
  return Math.round((part / whole) * 100)
}

export interface DayRecord {
  date: string
  wins: number
  losses: number
}

/**
 * The history endpoint lists only the days with a finished game. A chart of "the last
 * 30 days" must still give every day its slot, or a busy week and a quiet month look
 * alike. Days are UTC calendar days, the way the server buckets them (`end_time.date()`).
 */
export function fillDays(records: DayRecord[], days: number, now: Date = new Date()): DayRecord[] {
  const byDate = new Map(records.map((r) => [r.date, r]))
  const out: DayRecord[] = []
  const end = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(end - i * 86_400_000).toISOString().slice(0, 10)
    const r = byDate.get(date)
    out.push({ date, wins: r?.wins ?? 0, losses: r?.losses ?? 0 })
  }
  return out
}

export interface VoteLine {
  target: string
  voters: string[]
}

/**
 * A round's votes, grouped by who they named ("Maryam, Idris and Yusuf voted for Bilal",
 * sketch D), most-named first; ties keep the order the server listed them in.
 */
export function groupVotes(votes: { voter: string; target: string }[]): VoteLine[] {
  const lines: VoteLine[] = []
  for (const v of votes) {
    const line = lines.find((l) => l.target === v.target)
    if (line) line.voters.push(v.voter)
    else lines.push({ target: v.target, voters: [v.voter] })
  }
  return lines
    .map((l, i) => ({ l, i }))
    .sort((a, b) => b.l.voters.length - a.l.voters.length || a.i - b.i)
    .map(({ l }) => l)
}

/** Names joined the way the language joins them ("A, B and C", « A, B et C », «أ وب وج»). */
export function joinNames(names: string[], lang: string): string {
  try {
    return new Intl.ListFormat(lang, { style: "long", type: "conjunction" }).format(names)
  } catch {
    return names.join(", ")
  }
}

/** A locale tag that keeps Western digits (codes, scores and dates read aloud at mixed tables). */
export function latnLocale(lang: string): string {
  const base = (lang || "en").split("-")[0]
  return `${base}-u-nu-latn`
}

/** Time left until `expiresAt`, as the challenges page words it. */
export function timeLeft(expiresAt: string, t: T, now: number = Date.now()): string {
  const diff = new Date(expiresAt).getTime() - now
  if (!Number.isFinite(diff) || diff <= 0) return t("challenges.time.expired")
  const hours = Math.floor(diff / 3_600_000)
  const minutes = Math.floor((diff % 3_600_000) / 60_000)
  if (hours >= 24) return t("challenges.time.days", { d: Math.floor(hours / 24), h: hours % 24 })
  if (hours > 0) return t("challenges.time.hours", { h: hours, m: minutes })
  return t("challenges.time.minutes", { m: minutes })
}

/** Earned first, then the nearest to earning, then by tier. Stable for equal keys. */
export function orderAchievements(list: AchievementWithProgress[]): AchievementWithProgress[] {
  const ratio = (a: AchievementWithProgress) => (a.threshold > 0 ? Math.min(a.progress / a.threshold, 1) : 0)
  return list
    .map((a, i) => ({ a, i }))
    .sort((x, y) => Number(y.a.unlocked) - Number(x.a.unlocked) || ratio(y.a) - ratio(x.a) || x.a.tier - y.a.tier || x.i - y.i)
    .map(({ a }) => a)
}

export type LeaderboardSort = "total_games_won" | "win_rate" | "longest_win_streak"
export type LeaderboardColumn = "wins" | "games" | "rate" | "streak"

/** The column a sort is about: it stays on screen at every width. */
export const SORT_COLUMN: Record<LeaderboardSort, LeaderboardColumn> = {
  total_games_won: "wins",
  win_rate: "rate",
  longest_win_streak: "streak",
}

/**
 * Which figure columns a phone shows: wins always, plus the column being sorted on. The
 * others fold into a line under the player's name, so nothing is clipped at 390 px and
 * nothing has to scroll sideways.
 */
export function phoneColumns(sort: LeaderboardSort): Set<LeaderboardColumn> {
  return new Set<LeaderboardColumn>(["wins", SORT_COLUMN[sort]])
}
