import { memo } from "react"
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
}

/**
 * Kalimat's ladder (sketch C, D): one rung per hint, from the vaguest at the top to the
 * most specific at the bottom. Each rung's lozenge carries what a right answer is worth
 * while it is the newest hint (6 down to 1). Passed rungs strike their worth and recede;
 * the hint in play is brass and says "now"; hidden rungs are bare warp, and the next
 * one says when it arrives. A new hint is written in, in the reading direction.
 */
export const HintDisplay = memo(function HintDisplay({ hints, hintsRevealed, maxHints, nextHintIn }: HintDisplayProps) {
  const { t } = useTranslation()
  const shown = Math.min(hintsRevealed, hints.length)

  return (
    <ol className="hint-ladder" aria-label={t("game.quiz.kalimat.ladder")}>
      {Array.from({ length: maxHints }, (_, i) => {
        const number = i + 1
        const worth = maxHints - i
        const state = number < shown ? "past" : number === shown ? "now" : "hidden"
        const isNext = state === "hidden" && number === shown + 1 && nextHintIn != null
        return (
          <li key={number} className="hint-rung" data-state={state} aria-current={state === "now" ? "step" : undefined}>
            <span className="rung-worth" aria-hidden="true">
              <span>{worth}</span>
            </span>
            <span className="min-w-0">
              <span className="sr-only">{t("game.quiz.kalimat.rungLabel", { number, total: maxHints, points: worth })} </span>
              {state === "hidden" ? (
                <>
                  <span className="rung-warp" aria-hidden="true" />
                  <span className="sr-only">{t("game.quiz.kalimat.notYet")}</span>
                </>
              ) : (
                <>
                  <span className="rung-text ink block">{hints[i]}</span>
                </>
              )}
            </span>
            <span className="rung-tag">
              {state === "now" ? t("game.quiz.kalimat.now") : null}
              {isNext ? (
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
