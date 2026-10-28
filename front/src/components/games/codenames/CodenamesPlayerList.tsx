import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge, TeamGlyph } from "@/components/brand"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { type CodenamesPlayer, type TeamId, teamWool } from "./model"

interface CodenamesPlayerListProps {
  players: CodenamesPlayer[]
  /** The team whose turn it is (named "playing now"). */
  currentTeam?: TeamId
  currentUserId?: string
  isFinished?: boolean
}

/**
 * The table, team by team: each team named by its woven swatch, its glyph and its
 * name (never by colour alone); the spymaster first, marked with an ink lozenge and the
 * word. Brass stays for what is yours: "your turn" on your team, never another team's
 * spymaster. Operatives carry no lozenge (the hollow "away" one read as disconnected).
 */
export const CodenamesPlayerList = memo(function CodenamesPlayerList({
  players,
  currentTeam,
  currentUserId,
  isFinished = false,
}: CodenamesPlayerListProps) {
  const { t } = useTranslation()
  if (players.length === 0) return null

  return (
    <Panel aria-labelledby="cn-players-title">
      <PanelHeader title={<span id="cn-players-title">{t("game.codenames.players")}</span>} titleAs="h2" className="mb-3" />
      <div className="grid grid-cols-2 gap-x-4 gap-y-5 min-[1100px]:grid-cols-1 min-[1100px]:in-data-[finished=true]:grid-cols-2">
        {(["red", "blue"] as const).map((team) => (
          <TeamColumn
            key={team}
            team={team}
            players={players.filter((p) => p.team === team)}
            playing={!isFinished && currentTeam === team}
            currentUserId={currentUserId}
            label={t(`game.codenames.teams.${team}`)}
          />
        ))}
      </div>
    </Panel>
  )
})

const TeamColumn = memo(function TeamColumn({
  players,
  team,
  label,
  playing,
  currentUserId,
}: {
  players: CodenamesPlayer[]
  team: TeamId
  label: string
  playing: boolean
  currentUserId?: string
}) {
  const { t } = useTranslation()
  const wool = teamWool(team)
  const ordered = [...players].sort((a, b) => Number(b.role === "spymaster") - Number(a.role === "spymaster"))
  const mine = !!currentUserId && players.some((p) => p.user_id === currentUserId)

  return (
    <section aria-labelledby={`cn-team-${team}`} className="min-w-0">
      <h3 id={`cn-team-${team}`} className="flex items-center gap-2 text-[14px] font-medium leading-tight">
        <i
          aria-hidden="true"
          className="block size-5 shrink-0 rounded-[1px]"
          style={{ background: `var(--band-${wool === "madder" ? "teeth" : "ayn"}) left / auto 100% repeat-x` }}
        />
        <TeamGlyph team={wool} className="text-muted-foreground" />
        <span className="truncate">{label}</span>
        {playing ? (
          <span className={cn("ms-auto shrink-0 text-[12px]", mine ? "font-medium text-brass" : "font-normal text-foreground")}>
            {mine ? t("game.codenames.yourTurnShort") : t("game.codenames.playingNow")}
          </span>
        ) : null}
      </h3>
      <ul className="mt-2 border-t border-line">
        {ordered.map((p) => {
          const me = p.user_id === currentUserId
          const spymaster = p.role === "spymaster"
          return (
            <li key={p.user_id} className="flex min-h-10 items-center gap-2.5 border-b border-line py-1.5">
              {/* the spymaster's mark is ink; an operative keeps the same indent without one */}
              {spymaster ? <Lozenge state="ink" size={7} /> : <span aria-hidden="true" className="w-[10px] shrink-0" />}
              <span className="min-w-0">
                <span className="flex min-w-0 items-baseline gap-1.5 text-[14px] leading-tight">
                  <span className={cn("min-w-0 truncate", me && "font-medium")} dir="auto">
                    {p.username}
                  </span>
                  {me ? <span className="shrink-0 text-[12px] text-muted-foreground">{t("game.codenames.you")}</span> : null}
                </span>
                <span className="block text-[12px] leading-tight text-muted-foreground">
                  {spymaster ? t("games.codenames.roles.spymaster") : t("games.codenames.roles.operative")}
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
})
