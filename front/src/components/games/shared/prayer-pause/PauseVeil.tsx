import { type RefObject, useEffect, useId, useLayoutEffect, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import type { GamePause } from "@/api/generated"
import { ThreadClock, formatClock } from "@/components/brand/ThreadClock"
import { Button } from "@/components/ui/button"
import { formatWallClock, msUntilAnyoneCanResume } from "./pause-utils"

/** How often the "· 4 min" of the by-line is brought up to date (it reads in minutes). */
const MINUTE_TICK_MS = 15_000

export interface PauseLayerProps {
  /** The server's pause, or null while the game runs. */
  pause: GamePause | null
  /** The server's `can_resume` for this caller. */
  canResume: boolean
  onResume: () => void
  resuming?: boolean
  /** Whether this caller is the room's host (the note differs when a pause outlasted them). */
  isHost?: boolean
  /** Spectators never resume: they are not promised a time. */
  isSpectator?: boolean
  currentUserId?: string
  /** The paused phase's full length in seconds (the still thread's scale); 0 when untimed. */
  clockTotal?: number
  /** Ask the server again: called once, when the pause stops being the host's alone. */
  onRefresh?: () => void
  /** The game under the veil (made inert by the page, `tabIndex={-1}`): focus goes back there on resume. */
  gameRef?: RefObject<HTMLElement | null>
}

/**
 * The prayer pause, as every seat sees it (وقفة الصلاة).
 *
 * While the game is paused the veil lies over the whole game area: the page makes the
 * game underneath `inert` and the veil says why ("The majlis pauses for ṣalāh"), who
 * paused it and for how long, where the clock stopped (a still thread, never ticking),
 * and either Resume or who will resume and from when anyone may.
 *
 * Polite with focus and speech: the veil takes focus only when it was in the game (or
 * nowhere), so a player in the nav is not pulled away, and is then told once through a
 * status line instead. Lifting the veil says "The game resumes" once and hands focus back
 * to the game. The minute count is not a live region.
 */
export function PauseLayer({ pause, ...veil }: PauseLayerProps) {
  const { t } = useTranslation()
  const [message, setMessage] = useState("")
  const wasPausedRef = useRef(!!pause)

  // What last had focus in the game, so the resume can hand it back. Read from focus
  // events, not at the pause: the browser may already have moved focus off the game
  // when it turned inert. Focus inside the veil keeps the memory; anywhere else clears it.
  const lastInGameRef = useRef<HTMLElement | null>(null)
  const { gameRef } = veil
  useEffect(() => {
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null
      if (!target || target.closest("[data-pause-veil]")) return
      const game = gameRef?.current
      lastInGameRef.current = game && target !== game && game.contains(target) ? target : null
    }
    document.addEventListener("focusin", onFocusIn)
    return () => document.removeEventListener("focusin", onFocusIn)
  }, [gameRef])

  useEffect(() => {
    const isPaused = !!pause
    if (isPaused === wasPausedRef.current) return
    wasPausedRef.current = isPaused
    const resumed = t("pause.resumed")
    // On a new pause the veil (whose effect ran first) may have just set its own line:
    // only an old "The game resumes" is cleared.
    setMessage((current) => (isPaused ? (current === resumed ? "" : current) : resumed))
  }, [pause, t])

  return (
    <>
      <p className="sr-only" role="status">
        {message}
      </p>
      {pause ? <PauseVeil key={pause.since} pause={pause} onAnnounce={setMessage} lastInGameRef={lastInGameRef} {...veil} /> : null}
    </>
  )
}

interface PauseVeilProps extends Omit<PauseLayerProps, "pause"> {
  pause: GamePause
  /** Told once through the page's status line when the veil does not take focus. */
  onAnnounce?: (message: string) => void
  /** What last had focus in the game (kept by PauseLayer): focus returns there on resume. */
  lastInGameRef?: RefObject<HTMLElement | null>
}

export function PauseVeil({
  pause,
  canResume,
  onResume,
  resuming = false,
  isHost = false,
  isSpectator = false,
  currentUserId,
  clockTotal = 0,
  onRefresh,
  gameRef,
  onAnnounce,
  lastInGameRef,
}: PauseVeilProps) {
  const { t, i18n } = useTranslation()
  const titleId = useId()
  const byId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const pausedFor = usePausedFor(pause)

  const title = t("pause.title")
  const byYou = !!currentUserId && pause.by_user_id === currentUserId
  // the name keeps its own direction inside an Arabic line (U+2068 FSI … U+2069 PDI)
  const by = byYou ? t("pause.pausedByYou") : t("pause.pausedBy", { name: `\u2068${pause.by_username}\u2069` })
  const minutes = Math.floor(pausedFor / 60)
  const howLong = minutes < 1 ? t("pause.justNow") : t("pause.minutes", { count: minutes })

  // Take focus once, politely: only when it was in the game (now inert) or nowhere; a
  // player elsewhere (the nav) is told through the status line instead. Idempotent, as
  // StrictMode runs it twice: a second run finds focus already on the veil.
  const announceRef = useRef({ onAnnounce, text: `${title}. ${by}.` })
  announceRef.current = { onAnnounce, text: `${title}. ${by}.` }
  const previousRef = useRef<HTMLElement | null>(null)
  useLayoutEffect(() => {
    const node = dialogRef.current
    const game = gameRef?.current ?? null
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const onVeil = !!node && !!active && node.contains(active)
    if (!onVeil) {
      const focusWasInGame = !active || active === document.body || (!!game && game.contains(active))
      previousRef.current = focusWasInGame ? (active && active !== document.body ? active : (lastInGameRef?.current ?? null)) : null
      if (focusWasInGame) node?.focus({ preventScroll: true })
      else announceRef.current.onAnnounce?.(announceRef.current.text)
    }

    // On resume, focus goes back where it was (the answer being typed, the host's
    // control), or to the game. The cleanup runs while the veil is still in the document
    // and the game still inert (lifted in the same commit), so it waits one task, and
    // does nothing if the veil is still there (StrictMode re-running the effect).
    return () => {
      if (!node || !node.contains(document.activeElement)) return
      const previous = previousRef.current
      window.setTimeout(() => {
        if (node.isConnected) return
        if (previous?.isConnected) previous.focus({ preventScroll: true })
        if (document.activeElement !== previous) game?.focus({ preventScroll: true })
      }, 0)
    }
  }, [gameRef, lastInGameRef])

  // The pause stops being the host's alone at `anyone_can_resume_at`: ask the server
  // then (once) instead of guessing `can_resume` on this device's clock.
  const refreshRef = useRef(onRefresh)
  refreshRef.current = onRefresh
  useEffect(() => {
    if (canResume || isSpectator) return
    const wait = msUntilAnyoneCanResume(pause)
    if (wait == null) return
    const id = window.setTimeout(() => refreshRef.current?.(), wait + 1_000)
    return () => window.clearTimeout(id)
  }, [pause, canResume, isSpectator])

  const remaining = pause.remaining_seconds
  const showClock = remaining != null && remaining >= 0
  const isArabic = i18n.language?.startsWith("ar")

  return (
    <div className="absolute inset-0 z-30 animate-fade-in bg-[color-mix(in_oklch,var(--bg)_90%,transparent)]" data-testid="pause-veil" data-pause-veil="">
      <div className="sticky top-[calc(var(--navh)+16px)] px-4 pt-6 pb-8 sm:pt-12">
        <div
          ref={dialogRef}
          role="dialog"
          aria-labelledby={titleId}
          aria-describedby={byId}
          tabIndex={-1}
          className="panel-nodes relative mx-auto w-full max-w-[460px] rounded-lg border border-line-brass bg-surface text-center text-foreground outline-none focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-focus"
        >
          <div className="px-5 pt-7 pb-6 sm:px-8 sm:pt-8">
            <h2 id={titleId} className="type-panel text-[21px] leading-snug text-balance sm:text-[23px]">
              {title}
            </h2>
            {/* the Arabic name as the title's echo, under it (never an eyebrow above) */}
            {isArabic ? null : (
              <p lang="ar" dir="rtl" aria-hidden="true" className="type-arabic-name mt-0.5 text-[24px] leading-snug">
                {t("pause.name")}
              </p>
            )}
            <p id={byId} className="mt-2 text-[14.5px] text-muted-foreground">
              {by} · <span className="num">{howLong}</span>
            </p>

            {showClock ? (
              <div className="mx-auto mt-5 grid w-full max-w-[260px] justify-items-center gap-1.5" data-testid="pause-clock">
                <div aria-hidden="true" className="w-full">
                  <ThreadClock remaining={remaining} total={Math.max(clockTotal, remaining)} />
                </div>
                <p className="type-meta">
                  <span aria-hidden="true">{t("pause.clockWaits")}</span>
                  <span className="sr-only">{t("pause.clockWaitsAt", { time: formatClock(remaining) })}</span>
                </p>
              </div>
            ) : null}

            <div className="mt-6 grid justify-items-center gap-2.5">
              {canResume ? (
                <>
                  {!isHost ? <p className="text-[14px] leading-snug text-muted-foreground">{t("pause.anyoneMayResume")}</p> : null}
                  <Button onClick={onResume} loading={resuming} data-testid="pause-veil-resume">
                    {t("pause.resume")}
                  </Button>
                </>
              ) : (
                <p className="max-w-[46ch] text-[14px] leading-snug text-balance text-muted-foreground">
                  {isSpectator ? (
                    t("pause.hostResumes")
                  ) : (
                    <Trans
                      i18nKey="pause.hostResumesFrom"
                      values={{ time: formatWallClock(pause.anyone_can_resume_at) }}
                      components={{ clock: <bdi dir="ltr" className="num font-medium text-foreground" /> }}
                    />
                  )}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * Seconds the game has been paused: the server's `paused_for_seconds` (its own clock, no
 * skew), advanced on this device from the moment that value arrived.
 */
function usePausedFor(pause: GamePause): number {
  const base = pause.paused_for_seconds ?? 0
  const [anchor, setAnchor] = useState(() => ({ base, at: Date.now() }))
  const [now, setNow] = useState(() => Date.now())
  if (anchor.base !== base) setAnchor({ base, at: Date.now() })

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), MINUTE_TICK_MS)
    return () => window.clearInterval(id)
  }, [])

  return anchor.base + Math.max(0, (now - anchor.at) / 1000)
}
