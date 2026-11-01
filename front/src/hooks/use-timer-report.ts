import { useCallback, useEffect, useRef } from "react"
import type { TimerExpiredAction } from "@/api/generated"
import { isTimerStopAction } from "@/components/games/shared/prayer-pause/pause-utils"

/** A non-host waits at least this long before reporting an expired timer… */
export const TIMER_REPORT_JITTER_MIN_MS = 1_000
/** …and at most this long (a uniform draw in between, so the table does not fire together). */
export const TIMER_REPORT_JITTER_MAX_MS = 2_000

/**
 * The timer-expired answers after which nothing changed on the server: no state moved,
 * so nothing is refetched. Everything else (`results`, `auto_end_turn`, `skip_to_voting`,
 * `auto_vote`, `mr_white_guess_timeout`, or an answer without an action) did change it.
 */
const NO_OP_ACTIONS: ReadonlySet<TimerExpiredAction> = new Set<TimerExpiredAction>([
  "paused",
  "timer_not_expired",
  "not_playing",
  "round_already_resolved",
  "none",
])

export function isTimerNoOpAction(action: unknown): boolean {
  return typeof action === "string" && NO_OP_ACTIONS.has(action as TimerExpiredAction)
}

interface TimerReportOptions {
  /** The host reports at once; every other player waits a jittered 1–2 s. */
  isHost: boolean
  /** The game is paused for the prayer: nothing is reported, and a waiting report is dropped. */
  paused: boolean
  /**
   * What the table is doing, as the server last said it (the phase and its clock's start,
   * e.g. `${round_phase}:${round_started_at}`). A waiting report is cancelled when it
   * changes: the `game_updated` that changed it is the table's answer, usually the
   * host's own report landing.
   */
  phaseKey: string
  /** The timer window (its server start): an answer that says stop (`isTimerStopAction`) silences it until a new one. */
  windowKey: string | null
  /** Sends `POST …/timer-expired`, resolving to the server's answer. */
  send: () => Promise<{ action?: unknown } | null | undefined>
  /** Re-reads the game state, after an answer that changed it. */
  onChanged: () => void
}

/**
 * The `onExpired` of a game page's PhaseTimer (BDP-03, the client half).
 *
 * Any player may report an expired timer (the server acts only once it has really run
 * out: gating it on the host stalled the game whenever the host's phone was locked). But
 * every clock reaches zero at the same instant, and a 12-player table sent 12 POSTs for
 * one change, 11 of them no-ops, each followed by a refetch.
 *
 * - The host reports at once.
 * - Everyone else waits `TIMER_REPORT_JITTER_MIN_MS`–`MAX_MS` and reports only if the
 *   phase is still the one that expired: once the host's report lands, its `game_updated`
 *   moves `phaseKey` on and the waiting report is dropped. If the host is away, the first
 *   player whose wait ends reports, and the others' are dropped the same way.
 * - One report at a time, none while paused; after a stop answer (`paused`,
 *   `round_already_resolved`) nothing more for that window (PhaseTimer's 15 s valve would
 *   otherwise ask again). No refetch follows a no-op answer (`isTimerNoOpAction`).
 */
export function useTimerReport({ isHost, paused, phaseKey, windowKey, send, onChanged }: TimerReportOptions): () => Promise<void> {
  const isHostRef = useRef(isHost)
  isHostRef.current = isHost
  const pausedRef = useRef(paused)
  pausedRef.current = paused
  const phaseRef = useRef(phaseKey)
  phaseRef.current = phaseKey
  const windowRef = useRef(windowKey)
  windowRef.current = windowKey
  const sendRef = useRef(send)
  sendRef.current = send
  const onChangedRef = useRef(onChanged)
  onChangedRef.current = onChanged

  const inFlightRef = useRef(false)
  const stoppedWindowRef = useRef<string | null>(null)
  const waitingRef = useRef<{ timer: ReturnType<typeof setTimeout>; phase: string } | null>(null)

  const dropWaiting = useCallback(() => {
    if (!waitingRef.current) return
    clearTimeout(waitingRef.current.timer)
    waitingRef.current = null
  }, [])

  // The phase moved on (a game_updated), or the game was paused: a waiting report has nothing left to say.
  useEffect(() => {
    if (waitingRef.current && (paused || waitingRef.current.phase !== phaseKey)) dropWaiting()
  }, [phaseKey, paused, dropWaiting])

  useEffect(() => dropWaiting, [dropWaiting])

  const reportNow = useCallback(async () => {
    const timerKey = windowRef.current
    if (inFlightRef.current || pausedRef.current) return
    if (timerKey !== null && stoppedWindowRef.current === timerKey) return
    inFlightRef.current = true
    try {
      const result = await sendRef.current()
      const action = result?.action
      if (isTimerStopAction(action)) stoppedWindowRef.current = timerKey
      if (!isTimerNoOpAction(action)) onChangedRef.current()
    } catch {
      // Ignore: another player's report may have resolved it, and the next one asks again
    } finally {
      inFlightRef.current = false
    }
  }, [])

  return useCallback(async () => {
    if (pausedRef.current) return
    if (isHostRef.current) return reportNow()
    if (waitingRef.current) return
    const phase = phaseRef.current
    const delay = TIMER_REPORT_JITTER_MIN_MS + Math.random() * (TIMER_REPORT_JITTER_MAX_MS - TIMER_REPORT_JITTER_MIN_MS)
    const timer = setTimeout(() => {
      waitingRef.current = null
      if (phaseRef.current !== phase || pausedRef.current) return
      void reportNow()
    }, delay)
    waitingRef.current = { timer, phase }
  }, [reportNow])
}
