import { type CSSProperties, useEffect, useLayoutEffect, useMemo, useRef } from "react"
import { useTranslation } from "react-i18next"
import { serverNow } from "@/lib/server-clock"
import { cn } from "@/lib/utils"

/**
 * ThreadClock: khayṭ, the woven thread that is the ONLY clock in the product.
 *
 * - running: the thread (undyed and goat-hair twill) is drawn back through the loom at the
 *   reading start, along a bare warp guide; the figures sit beside it in tabular Readex.
 * - last five seconds: it stops flowing. The thread collapses to a stub and five brass
 *   lozenges are stamped, one per second (220 ms each).
 * - zero: the thread is knotted. All five lozenges stand.
 * Urgency comes from the change of rhythm, NEVER from red, blinking or pulsing.
 *
 * How it moves (the loom): the thread is full length inside a clipped track and is placed by
 * a `transform`, never by its width (a width transition laid the page out every frame, and
 * stopped dead half of every second).
 * - Given `startedAt` and `durationMs`, ONE Web Animation per phase segment carries it from
 *   where it stands now to where it stands at five seconds left, linearly, on the compositor.
 *   It is re-created only when the start or the duration changes (the server moves the start
 *   on a resume); the prayer pause pauses it and plays it again, so the freeze is exact.
 * - Otherwise (`remaining` and `total` alone, reduced motion, or no Web Animations) it steps
 *   once a second from `--left` in the CSS.
 *
 * Display only: PhaseTimer owns the ticking and the expiry callback. role="timer"; a polite
 * live region speaks only at 30, 10 and 5 seconds, never every tick.
 *
 * <ThreadClock remaining={43} total={60} startedAt={start} durationMs={60_000} />
 * <ThreadClock remaining={3} total={15} label="Time to answer" />
 */
export interface ThreadClockProps {
  /**
   * Seconds left (0 = knotted). The figures and the lozenges show whole seconds; a fraction
   * (a pause's frozen countdown) only places the thread.
   */
  remaining: number
  /** The phase's full length in seconds. */
  total: number
  /**
   * The phase's start on the server's clock (ms since the epoch, or an ISO string). With
   * `durationMs` the thread runs as one continuous animation instead of stepping.
   */
  startedAt?: number | string | null
  /** The phase's full length in ms, with `startedAt`. */
  durationMs?: number
  /** The prayer pause: the thread stands exactly where it is until this is false again. */
  paused?: boolean
  /** What the clock measures, for assistive tech ("Time to vote"). */
  label?: string
  /** Hide the figures (when the time is printed elsewhere). */
  hideTime?: boolean
  className?: string
  style?: CSSProperties
}

const LAST = 5

/** The `id` of the thread's Web Animation (it lasts the whole phase: never wait for it). */
export const THREAD_ANIMATION_ID = "thread-clock"

export function formatClock(seconds: number) {
  const s = Math.max(0, Math.ceil(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

const SPOKEN_AT = new Set([30, 10, 5])

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

function toMs(startedAt: number | string | null | undefined): number | null {
  if (startedAt == null) return null
  const ms = typeof startedAt === "number" ? startedAt : Date.parse(startedAt)
  return Number.isFinite(ms) ? ms : null
}

/** The thread's place with `left` (0–1) of the phase still to run: what is spent has gone back into the loom. */
function threadAt(left: number, rtl: boolean) {
  const spent = Math.round((1 - left) * 100_000) / 1000
  return `translateX(${rtl || spent === 0 ? spent : -spent}%)`
}

export function ThreadClock({ remaining, total, startedAt, durationMs, paused = false, label, hideTime = false, className, style }: ThreadClockProps) {
  const { t, i18n } = useTranslation()
  const seconds = Math.max(0, Math.ceil(remaining))
  const left = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0
  const phase = seconds <= 0 ? "done" : seconds <= LAST ? "last" : "running"
  const stamped = phase === "done" ? LAST : phase === "last" ? LAST - seconds : 0
  const time = formatClock(seconds)
  const announcement = useMemo(
    () => (SPOKEN_AT.has(seconds) ? t("ui.clock.secondsLeft", { count: seconds }) : seconds <= 0 ? t("ui.clock.timeUp") : ""),
    [seconds, t],
  )

  const threadRef = useRef<HTMLElement>(null)
  const animation = useRef<Animation | null>(null)
  // read when a segment starts, without restarting it on every tick
  const pausedRef = useRef(paused)
  pausedRef.current = paused
  const remainingRef = useRef(remaining)
  remainingRef.current = remaining

  const startMs = toMs(startedAt)
  const running = phase === "running"
  // the reading direction follows the language (<html dir>, set with it)
  const language = i18n.language

  // One segment: from where the thread stands now to where it stands at five seconds left.
  // A layout effect, so the first frame already shows the thread where the animation has it.
  useLayoutEffect(() => {
    const el = threadRef.current
    if (!running || !el || typeof el.animate !== "function" || startMs === null || !durationMs || durationMs <= 0) return
    if (prefersReducedMotion()) return
    // a clock mounted during a pause stands at the server's frozen countdown (its start is stale)
    const leftMs = pausedRef.current ? remainingRef.current * 1000 : durationMs - (serverNow() - startMs)
    const lastMs = LAST * 1000
    if (leftMs <= lastMs) return
    const rtl = el.closest("[dir]")?.getAttribute("dir") === "rtl"
    const run = el.animate([{ transform: threadAt(Math.min(1, leftMs / durationMs), rtl) }, { transform: threadAt(lastMs / durationMs, rtl) }], {
      duration: Math.min(durationMs, leftMs) - lastMs,
      easing: "linear",
      fill: "forwards",
    })
    // named, so a test waiting for the page's animations to settle can leave the clock out
    // (it runs for the whole phase)
    run.id = THREAD_ANIMATION_ID
    if (pausedRef.current) run.pause()
    animation.current = run
    return () => {
      run.cancel()
      if (animation.current === run) animation.current = null
    }
  }, [running, startMs, durationMs, language])

  // The prayer pause: the same animation stands still, then goes on.
  const wasPaused = useRef(paused)
  useEffect(() => {
    if (wasPaused.current === paused) return
    wasPaused.current = paused
    const run = animation.current
    if (!run) return
    if (paused) run.pause()
    else run.play()
  }, [paused])

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
          <path d="M1 7h3.2M9.8 7H13M4.2 7c0-2 1.2-3.2 2.8-3.2S9.8 5 9.8 7 8.6 10.2 7 10.2 4.2 9 4.2 7z" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      ) : null}
      <div className="track" aria-hidden="true">
        <i ref={threadRef} />
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
