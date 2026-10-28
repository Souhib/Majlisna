import { Eye } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { TeamGlyph } from "@/components/brand"
import { teamWool } from "./model"

interface CodenamesMyInfoProps {
  myTeam: "red" | "blue" | "spectator"
  myRole: "spymaster" | "operative" | "spectator"
}

/**
 * Who you are at this table, under the game's name ("You are the Red
 * spymaster"). One sentence, one element: the E2E suite looks for "You are".
 */
export const CodenamesMyInfo = memo(function CodenamesMyInfo({ myTeam, myRole }: CodenamesMyInfoProps) {
  const { t } = useTranslation()

  if (myTeam === "spectator" || myRole === "spectator") {
    return (
      <p className="flex items-center gap-1.5 text-[13px] leading-tight text-muted-foreground">
        <Eye className="size-3.5 shrink-0" aria-hidden="true" />
        <span>{t("game.codenames.youWatch")}</span>
      </p>
    )
  }

  const team = t(`game.codenames.teams.${myTeam}`)
  return (
    <p className="flex items-center gap-1.5 text-[13px] leading-tight text-muted-foreground">
      <TeamGlyph team={teamWool(myTeam)} size={10} className="shrink-0" />
      <span>{myRole === "spymaster" ? t("game.codenames.youAreSpymaster", { team }) : t("game.codenames.youAreOperative", { team })}</span>
    </p>
  )
})
