import { memo } from "react"
import { useTranslation } from "react-i18next"
import { SaduBand, TeamGlyph } from "@/components/brand"
import { type TeamId, teamWool } from "./model"

interface GameOverTransitionProps {
  show: boolean
  winner?: TeamId | null
}

/**
 * The game's one ceremony (≈1.1 s, once): the board is veiled, the winning wool is
 * shown as a woven tile with its glyph, "Game Over" and who won, and a madd band is
 * woven from the reading start. Then the colophon takes over.
 *
 * Mounts and unmounts at once (no exit animation, no presence wrapper): the colophon's
 * own "Game Over" heading must never be on screen at the same time as this one.
 */
export const GameOverTransition = memo(function GameOverTransition({ show, winner }: GameOverTransitionProps) {
  const { t } = useTranslation()
  if (!show) return null
  const wool = winner ? teamWool(winner) : null

  return (
    <div className="cn-veil" role="status">
      <div className="grid justify-items-center gap-4 text-center">
        {wool ? (
          <span className="cn-veil-tile seal-press" data-team={wool} aria-hidden="true">
            <TeamGlyph team={wool} size={22} />
          </span>
        ) : null}
        <h2 className="type-h3">{t("game.gameOver")}</h2>
        {winner ? <p className="type-lede">{t("game.codenames.over.title", { team: t(`game.codenames.teams.${winner}`) })}</p> : null}
        <SaduBand className="cn-veil-band mt-2" />
      </div>
    </div>
  )
})
