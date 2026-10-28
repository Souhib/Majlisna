import { memo, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { DescriptionList, type DescriptionOrderEntry } from "./DescriptionList"

interface UndercoverPlayer {
  id: string
  username: string
  is_alive: boolean
  is_mayor?: boolean
}

interface VotingPhaseProps {
  players: UndercoverPlayer[]
  descriptions: Record<string, string>
  descriptionOrder: DescriptionOrderEntry[]
  isAlive: boolean
  isSpectator?: boolean
  hasVoted: boolean
  isSubmittingVote?: boolean
  selectedVote: string | null
  votedPlayers: string[]
  /** Roles of the seats that emptied, shown on their rows. */
  eliminated?: { user_id: string; role: string }[]
  currentUserId?: string
  onSelectPlayer: (playerId: string) => void
  onConfirmVote: () => void
}

/**
 * The vote. "Discuss and vote" is the heading the E2E helpers wait for. The table is ONE
 * list (DescriptionList): what each seat said, who has voted (never for whom: targets
 * are not in the payload until the round resolves), and, for a player who may vote, the
 * other seats as the candidates themselves (buttons named after the players, which the
 * helpers click with `button:has-text(<name>)`), then "Vote to eliminate". No second
 * grid of avatars. After voting, exactly one line says "Waiting for…" (the helpers read
 * it as "voted").
 */
export const VotingPhase = memo(function VotingPhase({
  players,
  descriptions,
  descriptionOrder,
  isAlive,
  isSpectator = false,
  hasVoted,
  isSubmittingVote = false,
  selectedVote,
  votedPlayers,
  eliminated,
  currentUserId,
  onSelectPlayer,
  onConfirmVote,
}: VotingPhaseProps) {
  const { t } = useTranslation()

  const alivePlayers = useMemo(() => players.filter((p) => p.is_alive), [players])
  const votedCount = alivePlayers.filter((p) => votedPlayers.includes(p.id)).length
  const chosen = players.find((p) => p.id === selectedVote)
  const canVote = isAlive && !isSpectator
  const choosing = canVote && !hasVoted

  return (
    <section aria-labelledby="uc-vote-title" className="grid gap-6">
      <div>
        <h2 id="uc-vote-title" className="type-title text-[26px] sm:text-[30px]">
          {t("game.undercover.discussAndVote")}
        </h2>
        {/* the instruction is for those who vote; the eliminated and spectators get their own line below */}
        {canVote && !hasVoted ? (
          <p className="mt-1.5 text-[15px] leading-normal text-muted-foreground">{t("game.undercover.selectPlayerToVote")}</p>
        ) : null}
      </div>

      <DescriptionList
        order={descriptionOrder}
        descriptions={descriptions}
        currentIndex={descriptionOrder.length}
        currentUserId={currentUserId}
        mode="voting"
        players={players}
        eliminated={eliminated}
        voted={votedPlayers}
        choice={choosing ? { selected: selectedVote, onSelect: onSelectPlayer } : undefined}
      />

      {!isAlive && !isSpectator ? (
        <div data-testid="you-are-eliminated" className="rounded-lg border border-line-brass bg-surface px-4 py-3.5">
          <p className="flex items-center gap-2.5 text-[15px] font-medium">
            <Lozenge state="away" size={9} />
            {t("game.undercover.youAreDead")}
          </p>
          <p className="mt-1 text-[14px] leading-normal text-muted-foreground">{t("game.undercover.deadNote")}</p>
        </div>
      ) : null}

      {canVote && hasVoted ? (
        <div role="status" className="rounded-lg border border-line-brass bg-surface px-4 py-3.5">
          <p className="flex items-center gap-2.5 text-[15px] font-medium">
            <Lozenge state="brass" size={9} />
            {chosen ? t("game.undercover.votedFor", { username: chosen.username }) : t("game.undercover.youHaveVoted")}
          </p>
          <p className="mt-1 text-[14px] leading-normal text-muted-foreground">{t("game.undercover.waitingForVotes")}</p>
        </div>
      ) : null}

      {choosing ? (
        <div className="grid gap-4">
          <div className="grid gap-2 sm:flex sm:items-center sm:gap-4">
            <Button size="lg" className="w-full sm:w-auto" onClick={onConfirmVote} disabled={!selectedVote} loading={isSubmittingVote}>
              {t("game.undercover.voteToEliminate")}
            </Button>
            {!selectedVote ? <p className="text-[13.5px] text-muted-foreground">{t("game.undercover.chooseFirst")}</p> : null}
          </div>
        </div>
      ) : null}

      {isSpectator ? <p className="text-[15px] text-muted-foreground">{t("game.undercover.spectatorVoting")}</p> : null}

      <p className="type-label num" aria-live="polite">
        {t("game.undercover.votesCast", { current: votedCount, total: alivePlayers.length })}
      </p>
    </section>
  )
})
