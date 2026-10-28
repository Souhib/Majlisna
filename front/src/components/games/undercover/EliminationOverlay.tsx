import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { type LawhWord } from "./Lawh"
import { Verdict, type VoteEntry } from "./Verdict"

interface EliminationOverlayProps {
  round: number
  eliminatedUsername?: string
  eliminatedRole?: string
  eliminatedUserId?: string
  votes?: VoteEntry[]
  currentUserId?: string
  myWord?: LawhWord | null
  onDismiss: () => void
}

/**
 * The verdict for a player who missed it: their screen only saw the next round start, so
 * the round that emptied a seat is told here, at the top of the page, until they press
 * "Continue". Deliberately not modal: the new round is already running underneath and the
 * describer may need the composer right away. (When the round resolves on screen, the
 * verdict IS the round-over screen: RoundOverPanel.)
 */
export const EliminationOverlay = memo(function EliminationOverlay({
  round,
  eliminatedUsername,
  eliminatedRole,
  eliminatedUserId,
  votes,
  currentUserId,
  myWord,
  onDismiss,
}: EliminationOverlayProps) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border border-line-brass bg-surface p-4 sm:p-[22px]">
      <Verdict
        compact
        testId="elimination-overlay"
        round={{
          round,
          votes: votes ?? [],
          eliminated: eliminatedUsername ? { username: eliminatedUsername, role: eliminatedRole ?? "civilian", user_id: eliminatedUserId ?? "" } : null,
        }}
        currentUserId={currentUserId}
        myWord={myWord}
        action={
          <Button variant="secondary" className="w-full sm:w-auto" onClick={onDismiss}>
            {t("game.undercover.continueGame")}
          </Button>
        }
      />
    </div>
  )
})
