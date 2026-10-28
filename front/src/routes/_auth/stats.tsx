import { createFileRoute, Link } from "@tanstack/react-router"
import { ChevronRight, Users } from "lucide-react"
import { lazy, Suspense, useState } from "react"
import { useTranslation } from "react-i18next"
import { useGetGamesByUserApiV1GamesUserUserIdGet, useGetUserStatsApiV1StatsUsersUserIdStatsGet } from "@/api/generated"
import type { GameHistoryEntry, UserStats } from "@/api/generated"
import { Lozenge } from "@/components/brand"
import { DurationStats } from "@/components/stats/DurationStats"
import { gameName, latnLocale, percentOf, roleLozenge, roleName } from "@/components/stats/format"
import { GameDetailModal } from "@/components/stats/GameDetailModal"
import { Figures, PageHeader, ResultChip } from "@/components/stats/PlayerSpace"
import { RoleDistributionChart } from "@/components/stats/RoleDistributionChart"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/providers/AuthProvider"

// chart.js is only needed here: keep it out of the main bundle
const WinLossChart = lazy(() => import("@/components/stats/WinLossChart").then((m) => ({ default: m.WinLossChart })))

export const Route = createFileRoute("/_auth/stats")({
  component: StatsPage,
})

function StatsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [selected, setSelected] = useState<{ id: string; type: string } | null>(null)

  const { data: stats, isLoading: statsLoading } = useGetUserStatsApiV1StatsUsersUserIdStatsGet(
    { user_id: user?.id ?? "" },
    { query: { enabled: !!user?.id } },
  ) as { data: UserStats | undefined; isLoading: boolean }

  const { data: games = [], isLoading: gamesLoading } = useGetGamesByUserApiV1GamesUserUserIdGet(
    { user_id: user?.id ?? "" },
    undefined,
    { query: { enabled: !!user?.id } },
  ) as { data: GameHistoryEntry[] | undefined; isLoading: boolean }

  const header = (
    <PageHeader
      title={t("stats.title")}
      end={
        <Button asChild variant="secondary" size="sm">
          <Link to="/achievements">{t("achievements.title")}</Link>
        </Button>
      }
    />
  )

  if (statsLoading || gamesLoading) {
    return (
      <div className="page-wrap py-[clamp(32px,5vw,72px)]" aria-busy="true">
        {header}
        <Skeleton className="h-[106px] w-full" />
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
      </div>
    )
  }

  const played = stats?.total_games_played ?? 0
  const won = stats?.total_games_won ?? 0

  if (played === 0 && games.length === 0) {
    return (
      <div className="page-wrap py-[clamp(32px,5vw,72px)]">
        {header}
        <Panel>
          <EmptyState
            titleAs="h2"
            title={t("stats.noGames")}
            description={t("stats.noGamesBody")}
            action={
              <Button asChild>
                <Link to="/rooms">{t("stats.findRoom")}</Link>
              </Button>
            }
          />
        </Panel>
      </div>
    )
  }

  const byGame = [
    { type: "undercover", played: stats?.undercover_games_played ?? 0, won: stats?.undercover_games_won ?? 0 },
    { type: "codenames", played: stats?.codenames_games_played ?? 0, won: stats?.codenames_games_won ?? 0 },
  ]

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      {header}

      <div className="grid gap-[clamp(16px,2vw,24px)]">
        <Figures
          items={[
            { key: "played", label: t("stats.gamesPlayed"), value: played },
            { key: "won", label: t("stats.gamesWon"), value: won },
            { key: "rate", label: t("stats.winRate"), value: `${percentOf(won, played)}%` },
            {
              key: "streak",
              label: t("stats.currentStreak"),
              value: stats?.current_win_streak ?? 0,
              note: t("stats.longestNote", { n: stats?.longest_win_streak ?? 0 }),
            },
          ]}
        />

        <div className="grid items-start gap-[clamp(16px,2vw,24px)] lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
          {user?.id ? (
            <Suspense fallback={<Skeleton className="h-[318px] w-full" />}>
              <WinLossChart userId={user.id} />
            </Suspense>
          ) : null}
          {stats ? (
            <RoleDistributionChart
              timesCivilian={stats.times_civilian ?? 0}
              timesUndercover={stats.times_undercover ?? 0}
              timesMrWhite={stats.times_mr_white ?? 0}
              timesSpymaster={stats.times_spymaster ?? 0}
              timesOperative={stats.times_operative ?? 0}
              civilianWins={stats.civilian_wins ?? 0}
              undercoverWins={stats.undercover_wins ?? 0}
              mrWhiteWins={stats.mr_white_wins ?? 0}
              spymasterWins={stats.spymaster_wins ?? 0}
              operativeWins={stats.operative_wins ?? 0}
            />
          ) : null}
        </div>

        <div className="grid items-start gap-[clamp(16px,2vw,24px)] lg:grid-cols-2">
          <Panel aria-labelledby="bygame-title">
            <PanelHeader title={<span id="bygame-title">{t("stats.byGame")}</span>} />
            <table className="w-full border-collapse text-[15px]">
              <thead>
                <tr className="type-meta">
                  <th scope="col" className="pb-2 text-start font-normal">
                    <span className="sr-only">{t("stats.game")}</span>
                  </th>
                  <th scope="col" className="pb-2 ps-4 text-end font-normal">
                    {t("stats.gamesPlayed")}
                  </th>
                  <th scope="col" className="pb-2 ps-4 text-end font-normal">
                    {t("stats.gamesWon")}
                  </th>
                  <th scope="col" className="pb-2 ps-4 text-end font-normal">
                    {t("stats.winRate")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {byGame.map((g) => (
                  <tr key={g.type} className="border-t border-line">
                    <th scope="row" className="py-3 text-start font-medium">
                      {gameName(g.type, t)}
                    </th>
                    <td className="num py-3 ps-4 text-end">{g.played}</td>
                    <td className="num py-3 ps-4 text-end">{g.won}</td>
                    <td className="num py-3 ps-4 text-end text-muted-foreground">{percentOf(g.won, g.played)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <dl className="mt-4 grid gap-2 border-t border-line pt-4 text-[14.5px]">
              {[
                { key: "longest", label: t("stats.longestStreak"), value: stats?.longest_win_streak ?? 0 },
                { key: "rooms", label: t("stats.roomsCreated"), value: stats?.rooms_created ?? 0 },
                { key: "hosted", label: t("stats.gamesHosted"), value: stats?.games_hosted ?? 0 },
              ].map((row) => (
                <div key={row.key} className="flex items-baseline justify-between gap-3">
                  <dt className="text-muted-foreground">{row.label}</dt>
                  <dd className="num font-medium">{row.value}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          {user?.id ? <DurationStats userId={user.id} /> : null}
        </div>

        <RecentGames games={games} onOpen={(g) => setSelected({ id: g.id, type: g.type })} />
      </div>

      {selected ? <GameDetailModal gameId={selected.id} gameType={selected.type} onClose={() => setSelected(null)} /> : null}
    </div>
  )
}

/**
 * The player's last games, newest first. A finished game opens its summary; a game still
 * being played has none yet (the server refuses it until the end), so its row is not a
 * button.
 */
function RecentGames({ games, onOpen }: { games: GameHistoryEntry[]; onOpen: (g: GameHistoryEntry) => void }) {
  const { t, i18n } = useTranslation()
  const locale = latnLocale(i18n.language)
  const thisYear = new Date().getFullYear()

  return (
    <Panel flush aria-labelledby="recent-title">
      <PanelHeader className="mb-0 px-4 pb-3 pt-4 sm:px-[22px] sm:pt-[22px]" title={<span id="recent-title">{t("stats.recentGames")}</span>} />
      {games.length === 0 ? (
        <p className="border-t border-line px-4 py-8 text-center text-muted-foreground sm:px-[22px]">{t("stats.noGames")}</p>
      ) : (
        <ul>
          {games.map((game) => {
            const finished = game.game_status !== "in_progress" && Boolean(game.end_time)
            const date = new Date(game.start_time)
            const when = date.toLocaleDateString(locale, {
              day: "numeric",
              month: "short",
              ...(date.getFullYear() !== thisYear ? { year: "numeric" } : {}),
            })
            const mark = roleLozenge(game.user_role)
            const body = (
              <>
                <span className="grid min-w-0 flex-1 gap-1">
                  <span className="font-medium">{gameName(game.type, t)}</span>
                  <span className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[13.5px] text-muted-foreground">
                    <span className="num">{when}</span>
                    {game.user_role ? (
                      <span className="inline-flex items-center gap-1.5">
                        {mark ? <Lozenge state={mark} size={8} /> : null}
                        {roleName(game.user_role, t)}
                      </span>
                    ) : null}
                    <span className="inline-flex items-center gap-1">
                      <Users className="size-3.5" aria-hidden="true" />
                      <span className="sr-only">{t("stats.playerCount", { count: game.number_of_players })}</span>
                      <span className="num" aria-hidden="true">
                        {game.number_of_players}
                      </span>
                    </span>
                  </span>
                </span>
                <ResultChip won={game.user_won} finished={finished} />
              </>
            )
            return (
              <li key={game.id} className="border-t border-line">
                {finished ? (
                  <button
                    type="button"
                    onClick={() => onOpen(game)}
                    aria-haspopup="dialog"
                    className="flex w-full items-center gap-3 px-4 py-3.5 text-start transition-colors duration-(--dur-state) hover:bg-[color-mix(in_oklch,var(--brass)_7%,transparent)] focus-visible:-outline-offset-2 sm:px-[22px]"
                  >
                    {body}
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground rtl-flip" aria-hidden="true" />
                  </button>
                ) : (
                  <div className="flex items-center gap-3 px-4 py-3.5 sm:px-[22px] sm:pe-[52px]">{body}</div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
