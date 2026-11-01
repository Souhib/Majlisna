import { memo } from "react"
import { useTranslation } from "react-i18next"
import { SaduBand, TeamGlyph } from "@/components/brand"
import { type TeamId, teamWool } from "./model"

interface GameOverTransitionProps {
  show: boolean
  winner?: TeamId | null
}

/**
 * The game's one ceremony, once: the board is veiled, the winning wool is shown as a
 * woven tile with its glyph, "Game Over" and who won, and a madd band is woven from the
 * reading start. Then the colophon takes over.
 *
 * Its timing is `useCodenamesGame`'s (F3): the veil comes only once the decisive card's
 * colour and selvedge are woven (640 ms, `--dur-authored`), so the card that ended the
 * game is seen; it holds for the band's weave (`--dur-ceremony`, 1100 ms) plus 180 ms to
 * read, not the 3 s it used to block the screen for; under reduced motion it comes at
 * once and holds 600 ms. It lifts through a view transition, in the same commit that
 * mounts the colophon, which then takes focus on its title.
 *
 * No exit animation, no presence wrapper: the colophon's own "Game Over" heading must
 * never be in the DOM at the same time as this one (the view transition crossfades the
 * two snapshots instead).
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
