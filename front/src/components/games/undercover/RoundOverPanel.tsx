import { ArrowRight, Check } from "lucide-react"
import { memo, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { focusIsFree, focusTitle } from "@/hooks/use-phase-focus"
import { type LawhWord } from "./Lawh"
import { Verdict, type VerdictRound } from "./Verdict"

interface RoundOverPanelProps {
  /** The round that just resolved (its vote_history entry). */
  round: VerdictRound | null
  roundNumber: number
  currentUserId?: string
  myWord?: LawhWord | null
  /** The host forces the next round ("Next round"). */
  isHost: boolean
  /** An alive player who is not the host: marks themselves ready ("I’m ready"). */
  canMarkReady: boolean
  /** This player's mark is in. */
  isReady: boolean
  /** How many of the players asked are ready, and how many are asked (every alive player but the host). */
  readyCount: number
  readyQuorum: number
  /** The next-round request (the host's, or the ready mark) is on its way. */
  isStarting: boolean
  /** The one next-round call: the host's "Next round", or a player's "I’m ready". */
  onNextRound: () => void
}

/**
 * The round is counted (sketch D fourth phone): "The table chose Bilal.", his tablet turned
 * over, who voted for whom, and what comes next (owner rule (d), the ready quorum):
 *
 * - the host: "Next round", which opens it at once (the E2E helper clicks exactly that);
 * - an alive player who is not the host: "I’m ready", then "You are ready…" once marked;
 * - everyone (an eliminated player and a spectator see only this): "2 of 3 ready", a
 *   polite live region. The next round opens when every alive player but the host is ready.
 *
 * The server keeps the turn in "voting" until then, so this is the only place that call is
 * offered. Carries data-testid="elimination-overlay" (the E2E helpers wait for it). Nobody
 * on this screen says "Waiting for…": the helpers read that line as "this player has voted".
 */
export const RoundOverPanel = memo(function RoundOverPanel({
  round,
  roundNumber,
  currentUserId,
  myWord,
  isHost,
  canMarkReady,
  isReady,
  readyCount,
  readyQuorum,
  isStarting,
  onNextRound,
}: RoundOverPanelProps) {
  const { t } = useTranslation()
  const actRef = useRef<HTMLDivElement>(null)
  const readyLineRef = useRef<HTMLParagraphElement>(null)
  const markedHere = useRef(isReady)

  // "I'm ready" is replaced by the line that says so: the focus it held goes there, not to
  // <body> (only when the mark is made here, never on a page loaded already marked).
  useEffect(() => {
    if (isReady && !markedHere.current && readyLineRef.current && actRef.current && focusIsFree(actRef.current)) {
      focusTitle(readyLineRef.current)
    }
    markedHere.current = isReady
  }, [isReady])

  const marksReady = !isHost && canMarkReady
  const action =
    !isHost && !marksReady && readyQuorum <= 0 ? null : (
      <div ref={actRef} className="grid justify-items-center gap-2.5 lg:justify-items-start">
        {isHost ? (
          <Button
            size="lg"
            className="w-full sm:w-auto"
            loading={isStarting}
            onClick={onNextRound}
            iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
          >
            {t("game.undercover.nextRound")}
          </Button>
        ) : marksReady && !isReady ? (
          <Button size="lg" className="w-full sm:w-auto" loading={isStarting} onClick={onNextRound} iconStart={<Check aria-hidden="true" />}>
            {t("game.undercover.verdict.imReady")}
          </Button>
        ) : marksReady ? (
          <p ref={readyLineRef} className="flex max-w-[42ch] items-start gap-2 text-[15px] leading-normal text-pretty text-muted-foreground outline-none">
            <Check className="mt-1 size-4 shrink-0 text-brass" aria-hidden="true" />
            <span>{t("game.undercover.verdict.youAreReady")}</span>
          </p>
        ) : null}
        {readyQuorum > 0 ? (
          <p role="status" aria-live="polite" className="text-[13px] leading-snug text-muted-foreground tabular-nums">
            {/* `count` picks the plural form (prêt / prêts, جاهز / جاهزان / جاهزون): DESIGN.md §10 */}
            {t("game.undercover.verdict.readyCount", { count: readyCount, ready: readyCount, total: readyQuorum })}
          </p>
        ) : null}
      </div>
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
