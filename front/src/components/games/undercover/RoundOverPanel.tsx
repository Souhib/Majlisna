import { ArrowRight } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { type LawhWord } from "./Lawh"
import { Verdict, type VerdictRound } from "./Verdict"

interface RoundOverPanelProps {
  /** The round that just resolved (its vote_history entry). */
  round: VerdictRound | null
  roundNumber: number
  currentUserId?: string
  myWord?: LawhWord | null
  isHost: boolean
  isStarting: boolean
  onNextRound: () => void
}

/**
 * The round is counted (sketch D fourth phone): "The table chose Bilal.", his tablet turned
 * over, who voted for whom, and "Next round" for the host. The server keeps the turn in
 * "voting" until the host calls next-round, so this is the only place that call is offered.
 *
 * Carries data-testid="elimination-overlay" (the E2E helpers wait for it). Nobody else on
 * this screen says "Waiting for…": the helpers read that line as "this player has voted".
 */
export const RoundOverPanel = memo(function RoundOverPanel({
  round,
  roundNumber,
  currentUserId,
  myWord,
  isHost,
  isStarting,
  onNextRound,
}: RoundOverPanelProps) {
  const { t } = useTranslation()
  const action = isHost ? (
    <Button size="lg" className="w-full sm:w-auto" loading={isStarting} onClick={onNextRound} iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
      {t("game.undercover.nextRound")}
    </Button>
  ) : (
    <p className="flex items-center justify-center gap-2.5 text-[15px] text-muted-foreground lg:justify-start" role="status">
      {t("game.undercover.verdict.hostStarts")}
    </p>
  )
  return (
    <Verdict
      testId="elimination-overlay"
      round={round ?? { round: roundNumber, votes: [], eliminated: null }}
      currentUserId={currentUserId}
      myWord={myWord}
      action={action}
    />
  )
})
