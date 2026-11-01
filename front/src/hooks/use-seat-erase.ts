import { type RefObject, useLayoutEffect, useRef } from "react"
import { bezier, dur, ease, erase } from "@/lib/motion"

/**
 * ERASE, the motion grammar's third gesture (DESIGN.md §7): a seat that empties ON SCREEN
 * recedes instead of jumping. The lists that hold seats (Undercover's two tables, the lobby's
 * roster) render the receded state themselves, from the first frame (CSS on `data-out` /
 * `data-away`: the name at `--erase-ink`, the lozenge at `--erase-mark`); this hook only plays
 * the change, with Web Animations on opacity alone:
 *
 * - a seat that empties: its name (`[data-erase="ink"]`) and lozenge (`[data-erase="mark"]`)
 *   go from full ink to their receded level over `--dur-authored` on `--ease-ink`, its new
 *   status line (`[data-erase="note"]`, "Eliminated · Civilian", "away · 9:58") fades in over
 *   `--dur-state`;
 * - a seat whose player comes back (the lobby): name and lozenge return in `--dur-state`;
 * - reduced motion: one `--dur-state` opacity change, linear.
 *
 * Never on the first render (a page load shows what is, nothing moves), never for a state
 * that did not change (a refetch, a socket push): the previous state is a ref, as the pages'
 * `previousPhaseRef`. Each seat is the element carrying `data-seat="<id>"` inside `rootRef`.
 * Nothing waits at opacity 0: no fill holds a frame, so without Web Animations (or once they
 * end) the CSS's receded state is what shows.
 */
export interface SeatPresence {
  id: string
  /** The seat is empty: eliminated, or its player away. */
  out: boolean
}

export const ERASE_ANIMATION_ID = "seat-erase"

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

/** Plays a seat's change: `out` erases it, otherwise it is restored. */
export function playSeatChange(seat: Element, out: boolean, reduced = prefersReducedMotion()) {
  const state = dur.state * 1000
  const gesture: KeyframeAnimationOptions = reduced
    ? { duration: state, easing: "linear" }
    : out
      ? { duration: dur.authored * 1000, easing: bezier(ease.ink) }
      : { duration: state, easing: bezier(ease.out) }
  for (const part of seat.querySelectorAll<HTMLElement>("[data-erase]")) {
    if (typeof part.animate !== "function") return
    const kind = part.dataset.erase
    let run: Animation
    if (kind === "note") {
      // a status that disappears (a player back) simply goes; one that arrives fades in
      if (!out) continue
      run = part.animate([{ opacity: 0 }, { opacity: 1 }], reduced ? gesture : { duration: state, easing: bezier(ease.out) })
    } else {
      const receded = kind === "mark" ? erase.mark : erase.ink
      run = part.animate(out ? [{ opacity: 1 }, { opacity: receded }] : [{ opacity: receded }, { opacity: 1 }], gesture)
    }
    run.id = ERASE_ANIMATION_ID
  }
}

/**
 * `quiet`: record the seats without playing (a list about to leave the screen with its seats,
 * e.g. the vote's list once the vote is complete: the verdict that replaces it tells the seat).
 */
export function useSeatErase(rootRef: RefObject<HTMLElement | null>, seats: readonly SeatPresence[], quiet = false) {
  const previous = useRef<Map<string, boolean> | null>(null)
  const latest = useRef(seats)
  latest.current = seats
  // the effect runs when a seat's state changes, never for a new array of the same seats
  const key = seats.map((s) => `${s.id}:${s.out ? 1 : 0}`).join("|")

  useLayoutEffect(() => {
    const before = previous.current
    const now = new Map(latest.current.map((s) => [s.id, s.out]))
    previous.current = now
    const root = rootRef.current
    if (!before || !root || quiet) return
    const reduced = prefersReducedMotion()
    for (const el of root.querySelectorAll<HTMLElement>("[data-seat]")) {
      const id = el.dataset.seat ?? ""
      const was = before.get(id)
      const is = now.get(id)
      if (was === undefined || is === undefined || was === is) continue
      playSeatChange(el, is, reduced)
    }
  }, [key, rootRef, quiet])
}
