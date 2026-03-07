import { Timer } from "lucide-react"
import { memo, useEffect, useMemo, useState } from "react"
import { cn } from "@/lib/utils"

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

  // Fire onExpired once when timer reaches 0
  useEffect(() => {
    if (remaining === 0 && onExpired) {
      onExpired()
    }
  }, [remaining, onExpired])

  const isLow = remaining <= 10
  const isCritical = remaining <= 5

  const minutes = Math.floor(remaining / 60)
  const seconds = remaining % 60
  const display = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, "0")}` : `${seconds}s`

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Timer
        className={cn(
          "h-4 w-4",
          isCritical ? "text-red-500 animate-pulse" : isLow ? "text-amber-500" : "text-muted-foreground",
        )}
      />
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span
          className={cn(
            "text-sm font-mono font-semibold tabular-nums",
            isCritical ? "text-red-500" : isLow ? "text-amber-500" : "text-foreground",
          )}
        >
          {display}
        </span>
        <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500",
              isCritical ? "bg-red-500" : isLow ? "bg-amber-500" : "bg-primary",
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  )
})
