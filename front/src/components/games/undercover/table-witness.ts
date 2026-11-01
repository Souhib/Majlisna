import { useLayoutEffect } from "react"
import type { VerdictTurn } from "./Verdict"

/**
 * Was the round's table on screen when the verdict arrived? (ANIM-2, the lawh turns over.)
 *
 * The verdict plays its turn only when the vote resolves in front of the player, never on a
 * page loaded on the verdict, a refetch or a socket push. The page swaps phases in one commit
 * (`useViewTransitionValue` → `flushSync`, or a plain render without view transitions), so
 * while the verdict renders for the first time the list it replaces (`DescriptionList`, the
 * describing or voting phase's table) is still mounted: its layout cleanup only runs in that
 * commit. A page load renders the verdict over the skeleton, with no table on screen. A vote
 * that finds Mr. White turns his tablet over in his guess's panel (`MrWhiteGuessPanel`, the
 * compact verdict everyone else reads while he guesses); the round-over screen after his
 * guess lists no table, so it plays nothing again.
 */
let tables = 0

/** Called by `DescriptionList`: the table is on screen while it is mounted. */
export function useTableOnScreen() {
  useLayoutEffect(() => {
    tables += 1
    return () => {
      tables -= 1
    }
  }, [])
}

/** Read once, while the verdict first renders (a lazy state initializer). */
export function tableIsOnScreen() {
  return tables > 0
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

/**
 * The turn a verdict rendering for the first time plays: "turn" when the vote resolved on
 * screen ("fade" under reduced motion), none otherwise. Read once, in a lazy state
 * initializer (`RoundOverPanel`, `MrWhiteGuessPanel`), never again.
 */
export function verdictTurnNow(): VerdictTurn | null {
  if (!tableIsOnScreen()) return null
  return prefersReducedMotion() ? "fade" : "turn"
}
