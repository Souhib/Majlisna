import { memo, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ThreadClock } from "@/components/brand/ThreadClock"
import { serverNow } from "@/lib/server-clock"

/** How long before a still-expired timer may fire `onExpired` again. */
const EXPIRED_RETRY_MS = 15_000

interface PhaseTimerProps {
  timerStartedAt: string | null
  durationSeconds: number
  onExpired?: () => void
  className?: string
  /**
   * The prayer pause: while true the clock stands still (no tick, no thread movement)
   * and `onExpired` is never fired. It shows `frozenRemaining` when given (the server's
   * frozen countdown, `paused.remaining_seconds`), otherwise the time it last showed.
   * On resume the server moves `timerStartedAt` forward, so the clock simply continues
   * from where it stopped.
   */
  paused?: boolean
  frozenRemaining?: number | null
}

/**
 * The phase clock of every game: ticks every 500 ms from the server's start time, read
 * on the server's clock as this device estimates it (lib/server-clock), fires
 * `onExpired` once per timer window (see below), and renders the Samar thread clock
 * (<ThreadClock>: a contracting woven thread, five brass lozenges for the last five
 * seconds, a knot at zero, never red).
 */
export const PhaseTimer = memo(function PhaseTimer({
  timerStartedAt,
  durationSeconds,
  onExpired,
  className,
  paused = false,
  frozenRemaining = null,
}: PhaseTimerProps) {
  const { t } = useTranslation()
  // the server's clock (lib/server-clock): `timerStartedAt` is a server timestamp
  const [now, setNow] = useState(() => serverNow())

  useEffect(() => {
    // a paused clock does not tick; on resume it reads the clock afresh
    if (paused) return
    setNow(serverNow())
    const interval = setInterval(() => setNow(serverNow()), 500)
    return () => clearInterval(interval)
  }, [paused])

  const running = useMemo(() => {
    if (!timerStartedAt) return durationSeconds
    const startMs = new Date(timerStartedAt).getTime()
    const elapsedSec = (now - startMs) / 1000
    return Math.max(0, Math.ceil(durationSeconds - elapsedSec))
  }, [timerStartedAt, durationSeconds, now])
  const remaining =
    paused && frozenRemaining != null ? Math.max(0, Math.min(durationSeconds, Math.ceil(frozenRemaining))) : running

  // Fire onExpired ONCE per timer window (identified by start + duration).
  //
  // The old deps were [remaining, onExpired]. `onExpired` is a useCallback whose
  // deps include the React Query mutation object, which is a fresh object on
  // every render — so any re-render of the parent gave the effect a new identity
  // and re-fired it. And the handler itself calls invalidateQueries, which
  // re-renders the parent: a self-sustaining loop, one POST + one server
  // broadcast per cycle, for as long as the phase kept the timer expired.
  //
  // The retry window is a liveness valve, not a retry-as-fix: every player fires
  // this once per window, and if those calls fail the round would otherwise stall
  // until a reload. Re-arming after EXPIRED_RETRY_MS bounds the request rate.
  const onExpiredRef = useRef(onExpired)
  onExpiredRef.current = onExpired
  const firedWindowRef = useRef<string | null>(null)
  const firedAtRef = useRef(0)

  useEffect(() => {
    // a paused game's clock never runs out: the server answers "paused" anyway
    if (paused || remaining !== 0 || !onExpiredRef.current) return
    const window = `${timerStartedAt ?? "none"}:${durationSeconds}`
    const isNewWindow = firedWindowRef.current !== window
    if (!isNewWindow && now - firedAtRef.current < EXPIRED_RETRY_MS) return
    firedWindowRef.current = window
    firedAtRef.current = now
    onExpiredRef.current()
  }, [remaining, timerStartedAt, durationSeconds, now, paused])

  // the timer's name gives the figure its meaning: "Time left: 0:20"
  return <ThreadClock remaining={remaining} total={durationSeconds} label={t("ui.clock.label")} className={className} />
})
