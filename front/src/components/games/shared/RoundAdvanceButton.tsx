import { ArrowRight, Check } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface RoundAdvanceButtonProps {
  isHost: boolean
  isReady: boolean
  readyCount: number
  /** How many marks the round needs: every player but the host (`total_players`). */
  readyTotal?: number
  isAdvancing: boolean
  advanceLabel: string
  onAdvance: () => void
  /** Spectators watch: they neither mark themselves ready nor move the table on. */
  isSpectator?: boolean
  className?: string
}

/**
 * The results-phase action for both quizzes. The host advances the round; every
 * other player marks themselves ready, and the server advances once everyone but
 * the host is ready (`BaseGameController._ready_quorum`). The button used to exist
 * for the host only, so the documented ready system could never be used and an
 * absent host stalled the quiz between rounds.
 *
 * A line under the button always says where the table stands ("2 of 3 ready") and,
 * when the button is spent, why ("waiting for the others, or for the host").
 */
export const RoundAdvanceButton = memo(function RoundAdvanceButton({
  isHost,
  isReady,
  readyCount,
  readyTotal,
  isAdvancing,
  advanceLabel,
  onAdvance,
  isSpectator = false,
  className,
}: RoundAdvanceButtonProps) {
  const { t } = useTranslation()
  const count =
    readyTotal && readyTotal > 0
      ? t("game.quiz.readyOf", { count: readyCount, total: readyTotal })
      : readyCount > 0
        ? t("game.readyCount", { count: readyCount })
        : null

  if (isSpectator) {
    return (
      <p className={cn("text-[13px] text-muted-foreground", className)} aria-live="polite">
        {t("game.quiz.spectatorWaits")}
        {count ? <span> · {count}</span> : null}
      </p>
    )
  }

  const note = isHost ? (count ? t("game.quiz.hostNote", { status: count }) : null) : isReady ? t("game.quiz.readyNote") : t("game.quiz.notReadyNote")

  return (
    <div className={cn("grid gap-2", className)}>
      <Button
        block
        onClick={onAdvance}
        disabled={!isHost && isReady}
        loading={isAdvancing}
        iconStart={!isHost && isReady ? <Check aria-hidden="true" /> : undefined}
        iconEnd={isHost ? <ArrowRight className="rtl-flip" aria-hidden="true" /> : undefined}
      >
        {isHost ? advanceLabel : isReady ? t("game.readyWaiting") : t("game.readyUp")}
      </Button>
      <p className="text-center text-[13px] leading-snug text-muted-foreground" aria-live="polite">
        {!isHost && count ? (
          <>
            <span className="num">{count}</span>
            {note ? <span> · {note}</span> : null}
          </>
        ) : (
          note
        )}
      </p>
    </div>
  )
})
