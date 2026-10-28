import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

/** True when the text holds Arabic letters (a revealed answer, a choice). */
export function isArabicScript(text: string | null | undefined) {
  return !!text && /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/.test(text)
}

/** `lang`/`dir` for a piece of content whose script we only learn at runtime. */
export function scriptAttrs(text: string | null | undefined) {
  return isArabicScript(text) ? ({ lang: "ar", dir: "rtl" } as const) : ({ dir: "auto" } as const)
}

/**
 * A signed score ("+3") or any figure that must read left to right in every language.
 * In an Arabic paragraph a bare "+3" is drawn "3+": the plus is a neutral and takes the
 * paragraph's direction, so the figure is isolated in its own LTR run (DESIGN.md §8).
 */
export function Figure({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <bdi dir="ltr" className={cn("num", className)}>
      {children}
    </bdi>
  )
}

/**
 * The wall clock, re-read every `intervalMs` while `enabled`. For the screens that
 * derive something from elapsed time between two server pushes (the score band you are
 * in, the seconds to the next hint). Stops ticking when disabled.
 */
export function useNow(enabled: boolean, intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!enabled) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [enabled, intervalMs])
  return now
}

/**
 * Competition ranks (1, 1, 3) over a list already sorted by score, descending: a tie
 * shares its place instead of being split by the order the server happened to send.
 */
export function competitionRanks(scores: number[]) {
  return scores.map((score) => 1 + scores.filter((other) => other > score).length)
}

/** "Maryam and Idris" / "Maryam et Idris" / "Maryam وIdris", in the reader's language. */
export function listFormat(names: string[], language: string) {
  try {
    return new Intl.ListFormat(language, { style: "long", type: "conjunction" }).format(names)
  } catch {
    return names.join(", ")
  }
}

/**
 * The server state as it was when the phase on screen was current.
 *
 * `useViewTransitionValue(state.round_phase)` lags the server by one render so the
 * browser can snapshot the old phase. During that render the page would draw the OLD
 * phase with the NEW state ("The answer was" with no answer, the next question laid out
 * as a reveal), and that frame is the one the crossfade fades out. Rendering the phase
 * from the state it belongs to keeps the outgoing frame true.
 */
export function useHeldForPhase<T extends { round_phase: string }>(state: T | null, phase: string | null): T | null {
  const [held, setHeld] = useState<T | null>(state)
  // "Storing information from previous renders": set during render, React re-renders at once.
  if (state && state.round_phase === phase && held !== state) setHeld(state)
  if (state && state.round_phase !== phase && held && held.round_phase === phase) return held
  return state
}
