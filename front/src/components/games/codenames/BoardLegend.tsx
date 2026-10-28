import { memo } from "react"
import { useTranslation } from "react-i18next"
import { TeamGlyph } from "@/components/brand"

/**
 * How to read the cloth (sketch C, under the board): each team's woven edge and glyph,
 * the bystander's plain weave, the assassin's black cloth, and the outline teammates
 * draw when they point.
 */
export const BoardLegend = memo(function BoardLegend() {
  const { t } = useTranslation()
  return (
    <ul className="cn-legend" aria-label={t("game.codenames.legend.label")}>
      <li>
        <i aria-hidden="true" className="sw" style={{ background: "var(--band-teeth) left / auto 100% repeat-x" }} />
        <TeamGlyph team="madder" />
        {t("game.codenames.legend.madder")}
      </li>
      <li>
        <i aria-hidden="true" className="sw" style={{ background: "var(--band-ayn) left / auto 100% repeat-x" }} />
        <TeamGlyph team="indigo" />
        {t("game.codenames.legend.indigo")}
      </li>
      <li>
        <i aria-hidden="true" className="sw" style={{ background: "var(--band-plain) left / auto 100% repeat-x" }} />
        <TeamGlyph team="bystander" />
        {t("game.codenames.legend.bystander")}
      </li>
      <li>
        <i aria-hidden="true" className="sw" style={{ background: "var(--assassin)", boxShadow: "inset 0 0 0 1px var(--ember)" }} />
        <TeamGlyph team="assassin" />
        {t("game.codenames.legend.assassin")}
      </li>
      <li>
        <i aria-hidden="true" className="sw" style={{ outline: "1.5px dashed var(--brass)", outlineOffset: "-1.5px" }} />
        {t("game.codenames.legend.pointing")}
      </li>
    </ul>
  )
})
