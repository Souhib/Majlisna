/**
 * View Transitions for phase changes (describe → vote, round → round, game → colophon),
 * replacing `AnimatePresence mode="wait"`, which held an empty screen for the length
 * of the exit before the next phase could mount.
 *
 * - Feature-detected: without `document.startViewTransition` (Firefox < 144, older
 *   Safari) the update simply runs. Nothing waits.
 * - Reduced motion keeps the crossfade: index.css shortens it to 120 ms and drops the
 *   group movement, so the phase swap is an opacity change, never a hard cut (DESIGN §7,
 *   "opacity kept").
 * - A view transition blocks input for its duration (clicks go to the pseudo-elements),
 *   so keep them short (the CSS in index.css runs the root crossfade at --dur-state,
 *   180 ms) and never start one in the middle of an interaction.
 * - React must commit synchronously inside the callback or the browser snapshots the
 *   old DOM twice: the update runs inside `flushSync`.
 *
 * Usage:
 *   withViewTransition(() => setPhase(next))         // local state
 *   const phase = useViewTransitionValue(state.phase)  // server-derived state
 */
import { useEffect, useRef, useState } from "react"
import { flushSync } from "react-dom"

type StartViewTransition = (update: () => void) => { finished: Promise<void> }

function getStarter(): StartViewTransition | null {
  if (typeof document === "undefined") return null
  const start = (document as Document & { startViewTransition?: StartViewTransition }).startViewTransition
  if (typeof start !== "function") return null
  return start.bind(document)
}

/** True when this browser can run a view transition right now. */
export function canViewTransition() {
  return getStarter() !== null
}

/**
 * Run a state update inside a view transition when the browser supports it; otherwise
 * run it directly. Returns a promise that settles when the transition finishes.
 */
export function withViewTransition(update: () => void): Promise<void> {
  const start = getStarter()
  if (!start) {
    update()
    return Promise.resolve()
  }
  const transition = start(() => {
    flushSync(update)
  })
  return transition.finished.catch(() => undefined)
}

/**
 * Follow a server-derived value (e.g. `state.phase`) through a view transition: the
 * returned value lags the input by one transition, so the browser can snapshot the
 * old phase before React renders the new one. Without support it follows immediately.
 *
 * The first real value (the state arriving after a load, `null` → "playing") is adopted at
 * once, with no transition: a page load is a route change, and route changes do not animate.
 *
 *   const phase = useViewTransitionValue(serverState.phase)
 *   return phase === "voting" ? <VotingPhase /> : <DescriptionPhase />
 */
export function useViewTransitionValue<T>(value: T): T {
  const [shown, setShown] = useState(value)
  const latest = useRef(value)
  latest.current = value
  useEffect(() => {
    if (Object.is(value, shown)) return
    if (shown == null) {
      setShown(value)
      return
    }
    void withViewTransition(() => setShown(latest.current))
  }, [value, shown])
  // nothing shown yet: the value itself, in this very render
  return canViewTransition() && shown != null ? shown : value
}
