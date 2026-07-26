import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense, useState } from "react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/providers/AuthProvider"
import { useGetUserStatsApiV1StatsUsersUserIdStatsGet, useGetGamesByUserApiV1GamesUserUserIdGet } from "@/api/generated"
import { DurationStats } from "@/components/stats/DurationStats"
import { GameDetailModal } from "@/components/stats/GameDetailModal"

const WinLossChart = lazy(() => import("@/components/stats/WinLossChart").then((m) => ({ default: m.WinLossChart })))
const RoleDistributionChart = lazy(() =>
  import("@/components/stats/RoleDistributionChart").then((m) => ({ default: m.RoleDistributionChart })),
)

interface UserStatsData {
  total_games_played: number
  total_games_won: number
  total_games_lost: number
  undercover_games_played: number
  undercover_games_won: number
  codenames_games_played: number
  codenames_games_won: number
  times_civilian: number
  times_undercover: number
  times_mr_white: number
  civilian_wins: number
  undercover_wins: number
  mr_white_wins: number
  times_spymaster: number
  times_operative: number
  spymaster_wins: number
  operative_wins: number
  current_win_streak: number
  longest_win_streak: number
  rooms_created: number
  games_hosted: number
}

interface GameHistoryEntry {
  id: string
  type: "undercover" | "codenames"
  start_time: string
  end_time: string | null
  number_of_players: number
  winner: string | null
  user_role: string | null
  user_won: boolean | null
  game_status: string | null
}

export const Route = createFileRoute("/_auth/stats")({
  component: StatsPage,
})

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="glass rounded-2xl p-5 hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-extrabold tracking-tight mt-1 font-mono tabular-nums gradient-text">{value}</p>
    </div>
  )
}

function StatsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null)
  const [selectedGameType, setSelectedGameType] = useState<"undercover" | "codenames">("undercover")

  const { data: stats, isLoading: statsLoading } = useGetUserStatsApiV1StatsUsersUserIdStatsGet(
    { user_id: user?.id ?? "" },
    { query: { enabled: !!user?.id } },
  ) as { data: UserStatsData | undefined; isLoading: boolean }

  const { data: games = [] as GameHistoryEntry[], isLoading: gamesLoading } = useGetGamesByUserApiV1GamesUserUserIdGet(
    { user_id: user?.id ?? "" },
    undefined,
    { query: { enabled: !!user?.id } },
  ) as { data: GameHistoryEntry[] | undefined; isLoading: boolean }

  const isLoading = statsLoading || gamesLoading

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8 animate-slide-up">
        <div className="h-8 w-40 rounded-xl bg-muted animate-pulse mb-8" />
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass rounded-2xl p-5">
              <div className="h-3 w-16 rounded bg-muted animate-pulse mb-2" />
              <div className="h-6 w-12 rounded bg-muted animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  const winRate =
    stats && stats.total_games_played > 0
      ? `${Math.round((stats.total_games_won / stats.total_games_played) * 100)}%`
      : "0%"

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 animate-slide-up">
      <h1 className="text-3xl font-extrabold tracking-tight gradient-text mb-8">{t("stats.title")}</h1>

      {/* Overview */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-4 mb-8">
        <StatCard label={t("stats.gamesPlayed")} value={stats?.total_games_played ?? 0} />
        <StatCard label={t("stats.gamesWon")} value={stats?.total_games_won ?? 0} />
        <StatCard label={t("stats.winRate")} value={winRate} />
        <StatCard label={t("stats.currentStreak")} value={stats?.current_win_streak ?? 0} />
      </div>

      {/* Charts */}
      {user?.id && (
        <div className="grid gap-6 md:grid-cols-2 mb-8">
          <Suspense fallback={null}>
            <WinLossChart userId={user.id} />
          </Suspense>
          <Suspense fallback={null}>
            {stats && (
              <RoleDistributionChart
                timesCivilian={stats.times_civilian}
                timesUndercover={stats.times_undercover}
                timesMrWhite={stats.times_mr_white}
                timesSpymaster={stats.times_spymaster}
                timesOperative={stats.times_operative}
              />
            )}
          </Suspense>
        </div>
      )}

      {/* Duration Stats */}
      {user?.id && (
        <div className="mb-8">
          <DurationStats userId={user.id} />
        </div>
      )}

      {/* Undercover */}
      <h2 className="text-xl font-extrabold tracking-tight mb-4">{t("games.undercover.name")}</h2>
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3 mb-8">
        <StatCard label={t("stats.gamesPlayed")} value={stats?.undercover_games_played ?? 0} />
        <StatCard label={t("stats.gamesWon")} value={stats?.undercover_games_won ?? 0} />
        <StatCard label={t("stats.longestStreak")} value={stats?.longest_win_streak ?? 0} />
      </div>

      {/* Codenames */}
      <h2 className="text-xl font-extrabold tracking-tight mb-4">{t("games.codenames.name")}</h2>
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3 mb-8">
        <StatCard label={t("stats.gamesPlayed")} value={stats?.codenames_games_played ?? 0} />
        <StatCard label={t("stats.gamesWon")} value={stats?.codenames_games_won ?? 0} />
        <StatCard label={t("stats.roomsCreated")} value={stats?.rooms_created ?? 0} />
      </div>

      {/* Recent Games */}
      <h2 className="text-xl font-extrabold tracking-tight mb-4">{t("stats.recentGames")}</h2>
      {games.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("stats.noGames")}</p>
      ) : (
        <div className="space-y-2">
          {games.map((game) => (
            <button
              type="button"
              key={game.id}
              onClick={() => {
                setSelectedGameId(game.id)
                setSelectedGameType(game.type)
              }}
              className="w-full flex items-center justify-between glass rounded-2xl px-5 py-3.5 hover:-translate-y-0.5 hover:shadow-lg border-border/30 transition-all duration-200 text-left"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">
                  {game.type === "undercover" ? "🕵️" : "🔤"}
                </span>
                <div>
                  <p className="text-sm font-medium">
                    {game.type === "undercover"
                      ? t("games.undercover.name")
                      : t("games.codenames.name")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(game.start_time).toLocaleDateString()} &middot;{" "}
                    <span className="font-mono tabular-nums">{game.number_of_players}</span> {t("room.players").toLowerCase()}
                    {game.user_role && (
                      <> &middot; <span className="capitalize">{game.user_role}</span></>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {game.user_won === true && (
                  <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary-on-tint">
                    {t("stats.won")}
                  </span>
                )}
                {game.user_won === false && (
                  <span className="rounded-full bg-destructive/10 px-3 py-1 text-xs font-bold text-destructive-on-tint">
                    {t("stats.lost")}
                  </span>
                )}
                {game.user_won === null && !game.end_time && (
                  <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary-on-tint">
                    {t("stats.inProgress")}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Game Detail Modal */}
      {selectedGameId && (
        <GameDetailModal
          gameId={selectedGameId}
          gameType={selectedGameType}
          onClose={() => setSelectedGameId(null)}
        />
      )}
    </div>
  )
}
