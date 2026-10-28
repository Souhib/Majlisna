import { BookOpen } from "lucide-react"
import {
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { Lozenge, SaduBand, Seal } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { inkDuration, REREAD } from "@/lib/motion"
import { cn } from "@/lib/utils"

/**
 * The lawh (sketch D third phone, C right column): the tablet that carries a player's word.
 *
 * - At rest it is bare warp with a brass seal: nothing of the word is in the DOM.
 * - Press and hold (pointer, or Space/Enter on the focused tablet): the seal's ring fills
 *   for HOLD_MS, then the word is written in, in its own reading direction (`ink`). The
 *   first reading takes the authored time, every re-read is quick (REREAD).
 * - Let go: the word fades away (a fade, never a sweep: some words are sacred names).
 * - "I can't hold: show until I hide it" pins it open for players who cannot keep a
 *   finger down (and for assistive tech: an AT click on the tablet does the same).
 *
 * The tablet is the same for every role: Civilians and Undercovers are not told which
 * side they are on (the canonical rule), they only see their word. Mr. White's tablet
 * shows a dashed page saying he has no word, because he has to bluff.
 */

export interface LawhWord {
  /** The word in Arabic script (vocalized when we have it). */
  arabic?: string | null
  /** The Latin form: the transliteration the server stores ("Hilm"). */
  latin: string
}

export const HOLD_MS = 240
/** The two quiet controls under the tablet: links that wrap, 44 px tall on touch. */
const TOOL = "max-w-full whitespace-normal text-center leading-snug pointer-coarse:min-h-11"
const FADE_MS = 120

const ARABIC_SCRIPT = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/
/** Harakat, Qur'anic marks and the tatweel: they take no width of their own. */
const MARKS = /[ؐ-ًؚ-ٰٟۖ-ۭـ\s]/g

export function isArabicScript(text: string) {
  return ARABIC_SCRIPT.test(text)
}

/** Scale factor for long words (multi-word names) so they stay on the tablet. */
export function wordFit(text: string) {
  const n = text.replace(MARKS, "").length
  if (n <= 5) return 1
  if (n <= 8) return 0.82
  if (n <= 12) return 0.64
  return 0.5
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

/** The face of a word: Arabic in Amiri, the transliteration under it (not in the Arabic UI). */
export function LawhWordFace({
  word,
  meaning,
  arabicUi,
}: {
  word: LawhWord
  meaning?: string | null
  arabicUi: boolean
}) {
  const arabic = word.arabic?.trim() || null
  const shown = arabic ?? word.latin
  return (
    <>
      <span
        className="lawh-word"
        data-script={arabic ? "ar" : "latin"}
        lang={arabic ? "ar" : undefined}
        dir={arabic ? "rtl" : "auto"}
        style={{ "--lawh-fit": wordFit(shown) } as CSSProperties}
      >
        {shown}
      </span>
      {arabic && !arabicUi ? <span className="lawh-tr">{word.latin}</span> : null}
      {meaning ? <span className="lawh-gloss">{meaning}</span> : null}
    </>
  )
}

export interface LawhProps {
  round: number
  /** The player's word; null for Mr. White, who has none. */
  word: LawhWord | null
  /** How many times the word has been read this game (kept by the page). */
  reads: number
  onRead: () => void
  /** The word's meaning in the UI language (the hint). */
  hint?: string | null
  /** The player asked for the meaning: it is printed under the word from then on. */
  meaningShown?: boolean
  /** Called when the meaning popover opens (records the hint view). */
  onMeaningOpen?: () => void
  className?: string
}

export function Lawh({ round, word, reads, onRead, hint, meaningShown = false, onMeaningOpen, className }: LawhProps) {
  const { t, i18n } = useTranslation()
  const arabicUi = (i18n.language ?? "").startsWith("ar")
  const [progress, setProgress] = useState(0)
  const [held, setHeld] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [fading, setFading] = useState(false)
  const rafRef = useRef<number | null>(null)
  const keyHeldRef = useRef(false)
  const inkRef = useRef(0.64)
  const shown = held || pinned

  const readsRef = useRef(reads)
  readsRef.current = reads
  const onReadRef = useRef(onRead)
  onReadRef.current = onRead

  const display = word ? word.arabic?.trim() || word.latin : t("game.undercover.lawh.noWord")

  // The ink is timed when a reveal begins (before that render): the first reading is
  // written at the authored pace, every re-read quickly.
  const beginReveal = useCallback(() => {
    inkRef.current = readsRef.current === 0 ? inkDuration(display) : REREAD
  }, [display])

  // A read is counted at the moment the word appears. A layout effect, so the fade-out
  // starts in the same frame the word is taken away.
  const wasShown = useRef(false)
  useLayoutEffect(() => {
    if (shown && !wasShown.current) onReadRef.current()
    if (!shown && wasShown.current && !prefersReducedMotion()) {
      setFading(true)
      const timer = setTimeout(() => setFading(false), FADE_MS)
      wasShown.current = shown
      return () => clearTimeout(timer)
    }
    wasShown.current = shown
    return undefined
  }, [shown])

  const stopPress = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    setProgress(0)
  }, [])

  const startPress = useCallback(() => {
    if (pinned || held || rafRef.current !== null) return
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / HOLD_MS)
      if (p >= 1) {
        rafRef.current = null
        beginReveal()
        setProgress(0)
        setHeld(true)
        return
      }
      setProgress(p)
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [pinned, held, beginReveal])

  const release = useCallback(() => {
    keyHeldRef.current = false
    stopPress()
    setHeld(false)
  }, [stopPress])

  // A held tablet never stays open behind the player's back.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") release()
    }
    document.addEventListener("visibilitychange", onHide)
    window.addEventListener("blur", release)
    return () => {
      document.removeEventListener("visibilitychange", onHide)
      window.removeEventListener("blur", release)
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [release])

  const onPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // capture is a nicety (synthetic events have no live pointer)
    }
    startPress()
  }
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== " " && e.key !== "Enter") return
    e.preventDefault()
    if (e.repeat || keyHeldRef.current) return
    keyHeldRef.current = true
    startPress()
  }
  const onKeyUp = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== " " && e.key !== "Enter") return
    e.preventDefault()
    release()
  }
  // Pointer and key presses are handled above. A click with no pointer behind it
  // (detail 0) comes from assistive tech, which cannot "hold": it pins the word open.
  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    if (e.detail !== 0 || keyHeldRef.current) return
    if (!pinned) beginReveal()
    setPinned(!pinned)
  }

  const togglePinned = () => {
    stopPress()
    if (!pinned && !held) beginReveal()
    setHeld(false)
    setPinned(!pinned)
  }

  const state = shown ? "shown" : progress > 0 ? "pressing" : "rest"
  const act = pinned
    ? t("game.undercover.lawh.pinnedAct")
    : held
      ? t("game.undercover.lawh.holding")
      : t("game.undercover.lawh.hold")
  const readsLabel = reads === 0 ? t("game.undercover.lawh.notRead") : t("game.undercover.lawh.reads", { count: reads })
  // the ink follows the reading direction of what is written: the word's own script, or
  // (Mr. White's page) the interface's
  const inkDir = (word ? isArabicScript(display) : arabicUi) ? "to left" : "to right"

  return (
    <div className={cn("lawh-wrap", className)}>
      <button
        type="button"
        className="lawh"
        data-state={state}
        aria-label={shown ? t("game.undercover.lawh.labelShown") : t("game.undercover.lawh.labelRest")}
        onPointerDown={onPointerDown}
        onPointerUp={release}
        onPointerCancel={release}
        onLostPointerCapture={() => {
          if (!keyHeldRef.current) release()
        }}
        onKeyDown={onKeyDown}
        onKeyUp={onKeyUp}
        onClick={onClick}
        onContextMenu={(e) => e.preventDefault()}
      >
        <span className="lawh-top">
          <span>{t("game.undercover.lawh.round", { round })}</span>
          <span className="num">{readsLabel}</span>
        </span>
        <span className="lawh-face" data-rest={!shown && !fading ? "" : undefined}>
          {shown || fading ? (
            <span
              className={cn("lawh-text", shown ? "ink" : "lawh-fading")}
              style={{ "--ink-dur": `${inkRef.current}s`, "--ink-dir": inkDir } as CSSProperties}
            >
              {word ? (
                <LawhWordFace word={word} meaning={meaningShown ? hint : null} arabicUi={arabicUi} />
              ) : (
                <span className="lawh-blank">
                  <span className="lawh-blank-title">{t("game.undercover.lawh.noWord")}</span>
                  <span className="lawh-gloss">{t("game.undercover.lawh.noWordNote")}</span>
                </span>
              )}
            </span>
          ) : (
            <Seal size={64} progress={progress} pressed={false} ground="var(--surface-2)" />
          )}
        </span>
        <span className="lawh-act">
          <span className="lawh-ring" aria-hidden="true" />
          {act}
        </span>
        <SaduBand />
      </button>

      {/* A button's content is presentational (its name is the aria-label above), so the
          word is spoken from here, outside it, while it shows. */}
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {shown ? <SpokenWord word={word} meaning={meaningShown ? hint : null} arabicUi={arabicUi} /> : null}
      </p>

      <div className="flex max-w-full flex-wrap items-center justify-center gap-x-6 gap-y-1">
        <Button variant="link" size="sm" className={TOOL} onClick={togglePinned}>
          {pinned ? t("game.undercover.lawh.hideAgain") : t("game.undercover.lawh.cantHold")}
        </Button>
        {/* Offered on every tablet, with or without a meaning: a button that only some
            players have would tell the table who Mr. White is. */}
        <MeaningPopover
          text={word ? hint || t("game.undercover.lawh.noMeaning") : t("game.undercover.lawh.noWordMeaning")}
          note={word && hint ? t("game.undercover.lawh.meaningNote") : null}
          onOpen={word && hint ? onMeaningOpen : undefined}
        />
      </div>
    </div>
  )
}

/** What the tablet shows, as one sentence for a screen reader (each script in its own language). */
function SpokenWord({ word, meaning, arabicUi }: { word: LawhWord | null; meaning?: string | null; arabicUi: boolean }) {
  const { t } = useTranslation()
  if (!word) return <>{`${t("game.undercover.lawh.noWord")}. ${t("game.undercover.lawh.noWordNote")}`}</>
  const arabic = word.arabic?.trim() || null
  return (
    <>
      {arabic ? (
        <span lang="ar" dir="rtl">
          {arabic}
        </span>
      ) : null}
      {arabic && arabicUi ? null : `${arabic ? ", " : ""}${word.latin}`}
      {meaning ? `. ${meaning}` : null}
    </>
  )
}

/**
 * The word's meaning, one tap away (DESIGN.md §5: Popover is for word meanings). Opening it
 * counts as a hint view (achievements reward winning without one), so it stays a
 * deliberate act; once seen, the meaning is printed under the word on the tablet too.
 */
function MeaningPopover({ text, note, onOpen }: { text: string; note: string | null; onOpen?: () => void }) {
  const { t } = useTranslation()
  return (
    <Popover onOpenChange={(open) => (open ? onOpen?.() : undefined)}>
      <PopoverTrigger asChild>
        <Button
          variant="link"
          size="sm"
          className={TOOL}
          aria-label={t("game.hintButton")}
          iconStart={<BookOpen aria-hidden="true" />}
        >
          {t("game.hintButton")}
        </Button>
      </PopoverTrigger>
      <PopoverContent arrow side="top">
        <p className="type-nass text-[17px] leading-[1.55]">{text}</p>
        {note ? <p className="mt-2 type-meta">{note}</p> : null}
      </PopoverContent>
    </Popover>
  )
}

/** The three roles as they appear when a tablet turns over. */
export type RevealedRole = "civilian" | "undercover" | "mr_white"

const ROLE_KEY: Record<RevealedRole, string> = {
  civilian: "games.undercover.roles.civilian",
  undercover: "games.undercover.roles.undercover",
  mr_white: "games.undercover.roles.mrWhite",
}

export function roleLabelKey(role: string) {
  return ROLE_KEY[(role as RevealedRole) in ROLE_KEY ? (role as RevealedRole) : "civilian"]
}

/** The role's lozenge: undyed for a Civilian, madder for an Undercover, a dashed outline for Mr. White. */
export function RoleMark({ role, size = 10 }: { role: string; size?: number }) {
  if (role === "undercover") return <Lozenge state="madder" size={size} />
  if (role === "mr_white") return <Lozenge state="away" size={size} style={{ borderStyle: "dashed" }} />
  return <Lozenge state="undyed" size={size} />
}

/**
 * The tablet turned over (sketch D fourth phone): a seat has emptied, and everyone sees
 * the role it held. The other players' words stay hidden until the game ends (the server
 * never sends them), so the face says what was written there; on your own tablet, your word.
 */
export function TurnedLawh({
  name,
  round,
  role,
  word,
  band = true,
}: {
  name: string
  round: number
  role: string
  /** Your own word, when the tablet is yours. */
  word?: LawhWord | null
  /** The woven foot. Off where the player's own tablet already carries the screen's band. */
  band?: boolean
}) {
  const { t, i18n } = useTranslation()
  const arabicUi = (i18n.language ?? "").startsWith("ar")
  const held =
    role === "undercover"
      ? t("game.undercover.lawh.heldUndercover")
      : role === "mr_white"
        ? t("game.undercover.lawh.heldNone")
        : t("game.undercover.lawh.heldCivilian")
  return (
    <div className="lawh lawh-turned" data-role={role} role="group" aria-label={t("game.undercover.lawh.turnedLabel", { name })}>
      <div className="lawh-top">
        <b className="min-w-0 truncate">{name}</b>
        <span>{t("game.undercover.lawh.roundLower", { round })}</span>
      </div>
      <div className="lawh-role" data-role={role}>
        <i className="loz" aria-hidden="true" />
        {t(roleLabelKey(role))}
      </div>
      <div className="lawh-face">
        {word && role !== "mr_white" ? (
          <span className="lawh-text">
            <LawhWordFace word={word} arabicUi={arabicUi} />
          </span>
        ) : (
          <span className="lawh-text">
            <span className="lawh-held">{held}</span>
            {role !== "mr_white" ? <span className="lawh-gloss">{t("game.undercover.lawh.wordsAtEnd")}</span> : null}
          </span>
        )}
      </div>
      {band ? <SaduBand /> : null}
    </div>
  )
}
