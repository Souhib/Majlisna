import { memo, type ReactNode, type Ref } from "react"
import { useTranslation } from "react-i18next"
import { formatClock } from "@/components/brand"
import { Figure } from "@/components/games/shared/quiz-utils"

interface HintDisplayProps {
  /** Only the hints released so far: the server withholds the rest. */
  hints: string[]
  hintsRevealed: number
  /** The ladder's full length (`state.max_hints`), never `hints.length`. */
  maxHints: number
  /** Seconds until the next hint arrives; null when none will before the round ends. */
  nextHintIn?: number | null
  /**
   * What the next hidden rung offers instead of its bare warp: the word of the day's
   * "Another hint: 5 points instead of 6" (a hint there is asked for, not released by a clock).
   */
  offer?: ReactNode
  /** The tag of the rung in play. Default "now"; the word of the day says "found". */
  nowTag?: ReactNode
  /** No rung is in play any more (a word given up): every revealed rung reads as passed. */
  settled?: boolean
  /** The rung in play can take focus (tabindex -1), for a page that moves focus to a new hint. */
  focusableNow?: boolean
  listRef?: Ref<HTMLOListElement>
}

/**
 * Kalimat's ladder (sketch C, D): one rung per hint, from the vaguest at the top to the
 * most specific at the bottom. Each rung's lozenge carries what a right answer is worth
 * while it is the newest hint (6 down to 1). Passed rungs strike their worth and recede;
 * the hint in play is brass and says "now"; hidden rungs are bare warp, and the next
 * one says when it arrives. A new hint is written in, in the reading direction.
 *
 * The word of the day (`components/daily`) uses the same ladder: its next rung carries
 * the `offer` to reveal it, and once the day is over the rung it was found at says so
 * (`nowTag`), or nothing is in play (`settled`, given up).
 */
export const HintDisplay = memo(function HintDisplay({
  hints,
  hintsRevealed,
  maxHints,
  nextHintIn,
  offer,
  nowTag,
  settled = false,
  focusableNow = false,
  listRef,
}: HintDisplayProps) {
  const { t } = useTranslation()
  const shown = Math.min(hintsRevealed, hints.length)

  return (
    <ol ref={listRef} className="hint-ladder" aria-label={t("game.quiz.kalimat.ladder")}>
      {Array.from({ length: maxHints }, (_, i) => {
        const number = i + 1
        const worth = maxHints - i
        const state = number < shown || (settled && number === shown) ? "past" : number === shown ? "now" : "hidden"
        const isNext = state === "hidden" && number === shown + 1
        const timed = isNext && nextHintIn != null
        const offered = isNext && offer != null
        return (
          <li
            key={number}
            className="hint-rung"
            data-state={state}
            data-rung={number}
            aria-current={state === "now" ? "step" : undefined}
            tabIndex={focusableNow && state === "now" ? -1 : undefined}
          >
            <span className="rung-worth" aria-hidden="true">
              <span>{worth}</span>
            </span>
            <span className="min-w-0">
              <span className="sr-only">{t("game.quiz.kalimat.rungLabel", { number, total: maxHints, points: worth })} </span>
              {state === "hidden" ? (
                offered ? (
                  <span className="rung-offer">{offer}</span>
                ) : (
                  <>
                    <span className="rung-warp" aria-hidden="true" />
                    <span className="sr-only">{t("game.quiz.kalimat.notYet")}</span>
                  </>
                )
              ) : (
                <>
                  <span className="rung-text ink block">{hints[i]}</span>
                </>
              )}
            </span>
            <span className="rung-tag">
              {state === "now" ? (nowTag ?? t("game.quiz.kalimat.now")) : null}
              {timed ? (
                <>
                  {t("game.quiz.kalimat.nextIn")} <Figure>{formatClock(nextHintIn)}</Figure>
                </>
              ) : null}
            </span>
          </li>
        )
      })}
    </ol>
  )
})
