import { type CSSProperties, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

/**
 * ThreadClock: khayṭ, the woven thread that is the ONLY clock in the product.
 *
 * - running: the thread (undyed and goat-hair twill) contracts toward the reading start
 *   along a bare warp guide; the figures sit beside it in tabular Readex.
 * - last five seconds: it stops flowing. The thread collapses to a stub and five brass
 *   lozenges are stamped, one per second (220 ms each).
 * - zero: the thread is knotted. All five lozenges stand.
 * Urgency comes from the change of rhythm, NEVER from red, blinking or pulsing.
 *
 * Pure display: give it `remaining` and `total` seconds (PhaseTimer owns the ticking and
 * the expiry callback). role="timer"; a polite live region speaks only at 30, 10 and 5
 * seconds, never every tick.
 *
 * <ThreadClock remaining={43} total={60} />
 * <ThreadClock remaining={3} total={15} label="Time to answer" />
 */
export interface ThreadClockProps {
  /** Whole seconds left (0 = knotted). */
  remaining: number
  /** The phase's full length in seconds. */
  total: number
  /** What the clock measures, for assistive tech ("Time to vote"). */
  label?: string
  /** Hide the figures (when the time is printed elsewhere). */
  hideTime?: boolean
  className?: string
  style?: CSSProperties
}

const LAST = 5

export function formatClock(seconds: number) {
  const s = Math.max(0, Math.ceil(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

const SPOKEN_AT = new Set([30, 10, 5])

export function ThreadClock({ remaining, total, label, hideTime = false, className, style }: ThreadClockProps) {
  const { t } = useTranslation()
  const left = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0
  const phase = remaining <= 0 ? "done" : remaining <= LAST ? "last" : "running"
  const stamped = phase === "done" ? LAST : phase === "last" ? LAST - remaining : 0
  const time = formatClock(remaining)
  const announcement = useMemo(
    () => (SPOKEN_AT.has(remaining) ? t("ui.clock.secondsLeft", { count: remaining }) : remaining <= 0 ? t("ui.clock.timeUp") : ""),
    [remaining, t],
  )

  return (
    <div
      role="timer"
      aria-label={label ? `${label}: ${time}` : time}
      data-phase={phase}
      className={cn("thread-clock", className)}
      style={{ "--left": phase === "running" ? left : 0, ...style } as CSSProperties}
    >
      {phase === "done" ? (
        <svg className="knot" viewBox="0 0 14 14" aria-hidden="true">
          <path
            d="M1 7h3.2M9.8 7H13M4.2 7c0-2 1.2-3.2 2.8-3.2S9.8 5 9.8 7 8.6 10.2 7 10.2 4.2 9 4.2 7z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
          />
        </svg>
      ) : null}
      <div className="track" aria-hidden="true">
        <i />
      </div>
      {phase !== "running" ? (
        <span className="lozenges" aria-hidden="true">
          {Array.from({ length: LAST }, (_, i) => (
            <i key={i} data-on={i < stamped} />
          ))}
        </span>
      ) : null}
      {hideTime ? null : (
        <span className="time" aria-hidden="true">
          {time}
        </span>
      )}
      <span className="sr-only" aria-live="polite">
        {announcement}
      </span>
    </div>
  )
}
