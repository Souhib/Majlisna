import type { GamePause, TimerExpiredAction } from "@/api/generated"

/** The four games, as their routers are named (`/api/v1/{game}/games/{id}/pause`). */
export type PauseGame = "undercover" | "codenames" | "wordquiz" | "mcqquiz"

/** What every game state carries about the prayer pause (all optional on the wire). */
export interface PauseFields {
  paused?: GamePause | null
  can_pause?: boolean
  can_resume?: boolean
}

/**
 * The timer-expired answers that mean "stop firing for this timer window": the game is
 * paused (its clocks stand still until the resume moves them), or the round has already
 * been resolved by someone else. Anything else may be worth reporting again.
 */
const STOP_ACTIONS: ReadonlySet<TimerExpiredAction> = new Set<TimerExpiredAction>(["paused", "round_already_resolved"])

export function isTimerStopAction(action: unknown): boolean {
  return typeof action === "string" && STOP_ACTIONS.has(action as TimerExpiredAction)
}

/**
 * True when a move was refused because the game is paused (409 `errors.api.gamePaused`):
 * the page was a beat behind the pause, so it should fetch the state that shows the veil.
 */
export function isGamePausedError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false
  const response = (error as { response?: { status?: number; data?: unknown } }).response
  if (response?.status !== 409) return false
  const data = response.data as { error_key?: unknown; error?: unknown } | null | undefined
  return data?.error_key === "errors.api.gamePaused" || data?.error === "GamePausedError"
}

/**
 * How far into its timed phase the game was when it was paused, in seconds: the phase's
 * length minus the server's frozen countdown. Null when the server says the phase has no
 * running timer, or the length is unknown.
 */
export function elapsedAtPause(pause: GamePause | null | undefined, durationSeconds: number): number | null {
  if (!pause || pause.remaining_seconds == null || !(durationSeconds > 0)) return null
  return Math.max(0, Math.min(durationSeconds, durationSeconds - pause.remaining_seconds))
}

/**
 * A wall-clock time as the table reads it aloud: 24-hour, Western digits, in every
 * language (DESIGN.md, "Type"). The device's own time zone.
 */
export function formatWallClock(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date)
}

/**
 * Milliseconds until the pause stops being the host's alone, measured on the SERVER's
 * clock (`anyone_can_resume_at - since - paused_for_seconds`), so a device whose clock is
 * off by minutes still asks again at the right moment. Null once that moment has passed.
 */
export function msUntilAnyoneCanResume(pause: GamePause): number | null {
  const since = Date.parse(pause.since)
  const anyone = Date.parse(pause.anyone_can_resume_at)
  if (Number.isNaN(since) || Number.isNaN(anyone)) return null
  const left = anyone - since - (pause.paused_for_seconds ?? 0) * 1000
  return left > 0 ? left : null
}
