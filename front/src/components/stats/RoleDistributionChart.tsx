import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { gameName, roleLozenge } from "./format"

interface RoleDistributionProps {
  timesCivilian: number
  timesUndercover: number
  timesMrWhite: number
  timesSpymaster: number
  timesOperative: number
  civilianWins?: number
  undercoverWins?: number
  mrWhiteWins?: number
  spymasterWins?: number
  operativeWins?: number
}

interface RoleRow {
  role: string
  labelKey: string
  times: number
  wins?: number
}

/**
 * The roles a player has held, as a table with a brass bar per row (five categories read
 * better as aligned bars than as a ring of five dyes). The table IS the data: every
 * figure is text, the bar is a picture of it. Roles keep their marks from the game:
 * Civilian undyed, Undercover madder, Mr. White an empty lozenge; Codenames roles carry
 * no dye of their own (the team does).
 */
export function RoleDistributionChart(props: RoleDistributionProps) {
  const { t } = useTranslation()
  const groups: { game: string; rows: RoleRow[] }[] = [
    {
      game: "undercover",
      rows: [
        { role: "civilian", labelKey: "games.undercover.roles.civilian", times: props.timesCivilian, wins: props.civilianWins },
        { role: "undercover", labelKey: "games.undercover.roles.undercover", times: props.timesUndercover, wins: props.undercoverWins },
        { role: "mr_white", labelKey: "games.undercover.roles.mrWhite", times: props.timesMrWhite, wins: props.mrWhiteWins },
      ],
    },
    {
      game: "codenames",
      rows: [
        { role: "spymaster", labelKey: "games.codenames.roles.spymaster", times: props.timesSpymaster, wins: props.spymasterWins },
        { role: "operative", labelKey: "games.codenames.roles.operative", times: props.timesOperative, wins: props.operativeWins },
      ],
    },
  ]
  const all = groups.flatMap((g) => g.rows)
  const total = all.reduce((n, r) => n + r.times, 0)
  if (total === 0) return null
  const max = Math.max(...all.map((r) => r.times), 1)
  const showWins = all.some((r) => r.wins !== undefined)

  return (
    <Panel aria-labelledby="roles-title">
      <PanelHeader title={<span id="roles-title">{t("stats.roleDistribution")}</span>} />
      <table className="w-full border-collapse text-[14.5px]">
        <thead>
          <tr className="type-meta">
            <th scope="col" className="pb-2 text-start font-normal">
              <span className="sr-only">{t("stats.role")}</span>
            </th>
            <td aria-hidden="true" />
            <th scope="col" className="pb-2 ps-4 text-end font-normal whitespace-nowrap">
              {t("stats.timesPlayed")}
            </th>
            {showWins ? (
              <th scope="col" className="pb-2 ps-4 text-end font-normal whitespace-nowrap">
                {t("stats.wins")}
              </th>
            ) : null}
          </tr>
        </thead>
        {groups.map((g) => (
          <tbody key={g.game}>
            <tr>
              <th scope="colgroup" colSpan={showWins ? 4 : 3} className="type-label pb-1.5 pt-4 text-start">
                {gameName(g.game, t)}
              </th>
            </tr>
            {g.rows.map((r) => {
              const mark = roleLozenge(r.role)
              return (
                <tr key={r.role} className="border-t border-line">
                  <th scope="row" className="py-2.5 pe-3 text-start font-normal">
                    <span className="flex items-center gap-2.5 whitespace-nowrap">
                      <span className="grid w-3 place-items-center">{mark ? <Lozenge state={mark} size={9} /> : null}</span>
                      {t(r.labelKey)}
                    </span>
                  </th>
                  <td className="w-full py-2.5" aria-hidden="true">
                    <span className="block h-1.5 w-full rounded-[1px] bg-line">
                      <span className={cn("block h-full rounded-[1px] bg-brass", r.times === 0 && "hidden")} style={{ width: `${(r.times / max) * 100}%` }} />
                    </span>
                  </td>
                  <td className="num py-2.5 ps-4 text-end font-medium">{r.times}</td>
                  {showWins ? <td className="num py-2.5 ps-4 text-end text-muted-foreground">{r.wins ?? 0}</td> : null}
                </tr>
              )
            })}
          </tbody>
        ))}
      </table>
    </Panel>
  )
}
