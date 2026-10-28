import { type CSSProperties, memo } from "react"
import { useTranslation } from "react-i18next"
import { formatClock } from "@/components/brand"
import { Figure } from "@/components/games/shared/quiz-utils"
import { cn } from "@/lib/utils"

/**
 * The band a right answer lands in, from the share of the clock already spent. Mirrors
 * the server (`mcqquiz_game.submit_answer`): 1 point + round(2 × time left), so the
 * first quarter pays 3, the middle half 2, the last quarter 1.
 */
export function bandFor(elapsedRatio: number): 3 | 2 | 1 {
  if (elapsedRatio <= 0.25) return 3
  if (elapsedRatio < 0.75) return 2
  return 1
}

const BANDS = [3, 2, 1] as const

interface ScoreBandsProps {
  /** Share of the clock spent now (0–1), while you have not locked in. */
  elapsedRatio?: number | null
  /** Share of the clock spent when you locked in (0–1), once you have. */
  lockedRatio?: number | null
  /** Seconds left on the clock when you locked in ("locked in at 0:09"). */
  lockedRemaining?: number | null
  /** The band to mark when the server has said it (your points, once revealed). */
  band?: 3 | 2 | 1 | null
  /** Revealed, and your answer was not the right one: no band is yours (the lock-in
   *  time stays, unmarked). */
  missed?: boolean
}

/**
 * The Quiz's three score bands (sketch C, D): +3 for the first quarter of the clock, +2
 * for the middle half, +1 for the last. Before you answer, the band you are in is brass
 * and says "now"; once you lock in, a thread runs from the start to the moment you did,
 * with a lozenge on it, and the band says "locked in at 0:09". The bands are a picture
 * of the rule: the sentence for screen readers says the same thing in words.
 */
export const ScoreBands = memo(function ScoreBands({
  elapsedRatio,
  lockedRatio,
  lockedRemaining,
  band,
  missed = false,
}: ScoreBandsProps) {
  const { t } = useTranslation()
  const locked = lockedRatio != null
  const lockedBand = locked ? bandFor(lockedRatio) : null
  // the server's word (your points) wins over your own clock when both are known; a
  // wrong answer earns no band, whatever the clock said
  const hit = missed ? null : (band ?? (locked ? lockedBand : elapsedRatio != null ? bandFor(elapsedRatio) : null))
  const lockLabelOn = missed ? lockedBand : hit
  const at = locked ? Math.max(0.02, Math.min(1, lockedRatio)) : null

  return (
    <div>
      <p className="sr-only">
        {t("game.quiz.mcq.bandsRule")}
        {locked && lockedRemaining != null ? ` ${t("game.quiz.mcq.lockedSr", { count: Math.ceil(lockedRemaining) })}` : null}
      </p>
      <div
        className="score-bands"
        aria-hidden="true"
        style={at != null ? ({ "--at": at } as CSSProperties) : undefined}
        data-testid="quiz-score-bands"
      >
        {BANDS.map((value) => {
          const isHit = hit === value
          const wide = value === 2
          return (
            <span key={value} data-hit={isHit || undefined}>
              <span>
                <Figure>+{value}</Figure>
                {isHit && !locked && elapsedRatio != null ? <span> · {t("game.quiz.kalimat.now")}</span> : null}
                {lockLabelOn === value && locked && lockedRemaining != null ? (
                  <>
                    {" · "}
                    <span className={cn(!wide && "max-sm:hidden")}>{t("game.quiz.mcq.lockedAt")} </span>
                    <Figure>{formatClock(lockedRemaining)}</Figure>
                  </>
                ) : null}
              </span>
            </span>
          )
        })}
        {at != null ? (
          <>
            <i className="lock-thread" />
            <i className="lock-mark" />
          </>
        ) : null}
      </div>
    </div>
  )
})
