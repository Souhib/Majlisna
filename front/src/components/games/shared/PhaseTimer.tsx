import { Timer } from "lucide-react"
import { memo, useEffect, useMemo, useRef, useState } from "react"
import { cn } from "@/lib/utils"

/** How long before a still-expired timer may fire `onExpired` again. */
const EXPIRED_RETRY_MS = 15_000

interface PhaseTimerProps {
  timerStartedAt: string | null
  durationSeconds: number
  onExpired?: () => void
  className?: string
}

export const PhaseTimer = memo(function PhaseTimer({
  timerStartedAt,
  durationSeconds,
  onExpired,
  className,
}: PhaseTimerProps) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(interval)
  }, [])

  const remaining = useMemo(() => {
    if (!timerStartedAt) return durationSeconds
    const startMs = new Date(timerStartedAt).getTime()
    const elapsedSec = (now - startMs) / 1000
    return Math.max(0, Math.ceil(durationSeconds - elapsedSec))
  }, [timerStartedAt, durationSeconds, now])

  const progress = useMemo(() => {
    if (!timerStartedAt || !durationSeconds) return 100
    const startMs = new Date(timerStartedAt).getTime()
    const elapsedSec = (now - startMs) / 1000
    return Math.max(0, Math.min(100, ((durationSeconds - elapsedSec) / durationSeconds) * 100))
  }, [timerStartedAt, durationSeconds, now])

  // Fire onExpired ONCE per timer window (identified by start + duration).
  //
  // The old deps were [remaining, onExpired]. `onExpired` is a useCallback whose
  // deps include the React Query mutation object, which is a fresh object on
  // every render — so any re-render of the parent gave the effect a new identity
  // and re-fired it. And the handler itself calls invalidateQueries, which
  // re-renders the parent: a self-sustaining loop, one POST + one server
  // broadcast per cycle, for as long as the phase kept the timer expired.
  //
  // The retry window is a liveness valve, not a retry-as-fix: only the host
  // fires this, so if the single call fails the round would otherwise stall
  // until a reload. Re-arming after EXPIRED_RETRY_MS bounds the request rate.
  const onExpiredRef = useRef(onExpired)
  onExpiredRef.current = onExpired
  const firedWindowRef = useRef<string | null>(null)
  const firedAtRef = useRef(0)

  useEffect(() => {
    if (remaining !== 0 || !onExpiredRef.current) return
    const window = `${timerStartedAt ?? "none"}:${durationSeconds}`
    const isNewWindow = firedWindowRef.current !== window
    if (!isNewWindow && now - firedAtRef.current < EXPIRED_RETRY_MS) return
    firedWindowRef.current = window
    firedAtRef.current = now
    onExpiredRef.current()
  }, [remaining, timerStartedAt, durationSeconds, now])

  const isLow = remaining <= 10
  const isCritical = remaining <= 5

  const minutes = Math.floor(remaining / 60)
  const seconds = remaining % 60
  const display = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, "0")}` : `${seconds}s`

  // SVG circular ring props
  const size = 48
  const strokeWidth = 3
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference * (1 - progress / 100)

  return (
    <div role="timer" aria-live="polite" aria-label={`${display} remaining`} className={cn("flex items-center gap-3", className)}>
      {/* Circular SVG countdown ring */}
      <div className={cn("relative flex-shrink-0 rounded-full", isCritical && "animate-glow-pulse")}>
        <svg width={size} height={size} className="-rotate-90">
          {/* Background ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--muted)"
            strokeWidth={strokeWidth}
          />
          {/* Progress ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={isCritical ? "oklch(0.55 0.22 25)" : isLow ? "oklch(0.75 0.15 75)" : "var(--primary)"}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className="transition-[stroke-dashoffset] duration-500"
          />
        </svg>
        {/* Timer icon in center */}
        <div className="absolute inset-0 flex items-center justify-center">
          <Timer
            className={cn(
              "h-4 w-4",
              isCritical ? "text-red-500 animate-pulse" : isLow ? "text-amber-500" : "text-muted-foreground",
            )}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span
          className={cn(
            "text-sm font-mono font-bold tabular-nums tracking-tight",
            isCritical ? "text-red-500" : isLow ? "text-amber-500" : "text-foreground",
          )}
        >
          {display}
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500",
              isCritical ? "bg-red-500" : isLow ? "bg-amber-500" : "bg-gradient-to-r from-primary to-accent",
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  )
})
