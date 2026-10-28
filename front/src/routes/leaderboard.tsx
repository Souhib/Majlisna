import { createFileRoute, Link } from "@tanstack/react-router"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useGetLeaderboardApiV1StatsLeaderboardGet } from "@/api/generated"
import type { LeaderboardEntry } from "@/api/generated"
import { Lozenge } from "@/components/brand"
import { type LeaderboardSort as SortField, phoneColumns, SORT_COLUMN, type LeaderboardColumn as Column } from "@/components/stats/format"
import { PageHeader, Segmented } from "@/components/stats/PlayerSpace"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/leaderboard")({
  component: LeaderboardPage,
})

function LeaderboardPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [sortField, setSortField] = useState<SortField>("total_games_won")

  const { data: entries = [], isLoading } = useGetLeaderboardApiV1StatsLeaderboardGet({ stat_field: sortField, limit: 50 }) as {
    data: LeaderboardEntry[] | undefined
    isLoading: boolean
  }

  const onPhone = phoneColumns(sortField)
  const columns: { key: Column; label: string; value: (e: LeaderboardEntry) => string | number }[] = [
    { key: "wins", label: t("leaderboard.wins"), value: (e) => e.total_games_won },
    { key: "games", label: t("leaderboard.games"), value: (e) => e.total_games_played },
    { key: "rate", label: t("leaderboard.winRate"), value: (e) => `${Math.round(e.win_rate)}%` },
    { key: "streak", label: t("leaderboard.streak"), value: (e) => e.longest_win_streak },
  ]
  const folded = columns.filter((c) => !onPhone.has(c.key))
  const sortedOn = SORT_COLUMN[sortField]

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <div className="mx-auto max-w-[60rem]">
        <PageHeader title={t("leaderboard.title")} lede={t("leaderboard.lede")} />

        <Segmented<SortField>
          label={t("leaderboard.sortBy")}
          value={sortField}
          onChange={setSortField}
          className="mb-5 w-full sm:w-fit sm:min-w-[26rem]"
          options={[
            { value: "total_games_won", label: t("leaderboard.wins") },
            { value: "win_rate", label: t("leaderboard.winRate") },
            { value: "longest_win_streak", label: t("leaderboard.streak") },
          ]}
        />

        <Panel flush>
          <table data-testid="leaderboard" className="w-full border-collapse text-[15px]">
            <caption className="sr-only">{t("leaderboard.caption", { sort: columns.find((c) => c.key === sortedOn)?.label })}</caption>
            <thead>
              <tr className="type-meta border-b border-line">
                <th scope="col" className="py-3 pe-3 ps-4 text-start font-normal whitespace-nowrap sm:ps-[22px]">
                  <span className="sr-only sm:not-sr-only">{t("leaderboard.rank")}</span>
                </th>
                <th scope="col" className="w-full py-3 pe-2 text-start font-normal">
                  {t("leaderboard.player")}
                </th>
                {columns.map((c) => (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={c.key === sortedOn ? "descending" : undefined}
                    className={cn(
                      "py-3 ps-2 pe-4 text-end font-normal whitespace-nowrap sm:pe-0 sm:ps-8 sm:last:pe-[22px]",
                      !onPhone.has(c.key) && "hidden sm:table-cell",
                      c.key === sortedOn && "font-medium text-foreground",
                    )}
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                [0, 1, 2, 3, 4].map((i) => (
                  <tr key={i} className="border-t border-line first:border-t-0">
                    <td colSpan={6} className="px-4 py-4 sm:px-[22px]">
                      <Skeleton className="h-5 w-full" />
                    </td>
                  </tr>
                ))
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      titleAs="p"
                      title={t("leaderboard.noPlayers")}
                      action={
                        <Button asChild variant="secondary">
                          <Link to="/rooms">{t("stats.findRoom")}</Link>
                        </Button>
                      }
                    />
                  </td>
                </tr>
              ) : (
                entries.map((entry, index) => {
                  const me = entry.user_id === user?.id
                  return (
                    <tr
                      key={entry.user_id}
                      aria-current={me ? "true" : undefined}
                      className={cn("border-t border-line first:border-t-0", me && "bg-[color-mix(in_oklch,var(--brass)_9%,var(--surface))]")}
                    >
                      <td className="py-3 pe-3 ps-4 align-middle sm:ps-[22px]">
                        <span
                          className={cn(
                            "num inline-flex items-center gap-1.5 text-[15px]",
                            // brass only on the viewer's own row: the podium is ink
                            me ? "font-medium text-brass" : index < 3 ? "font-medium text-foreground" : "text-muted-foreground",
                          )}
                        >
                          {index === 0 ? <Lozenge state={me ? "brass" : "ink"} size={7} /> : null}
                          {index + 1}
                        </span>
                      </td>
                      <td className="w-full max-w-0 py-3 pe-2 align-middle">
                        <Link
                          to="/players/$userId"
                          params={{ userId: entry.user_id }}
                          className={cn(
                            "-my-2 flex min-h-11 flex-col justify-center rounded-sm py-1 underline-offset-[5px] hover:underline hover:decoration-line-brass-strong",
                            me && "text-brass",
                          )}
                        >
                          <span className="flex min-w-0 items-baseline gap-2">
                            <span dir="auto" className="truncate font-medium">
                              {entry.username}
                            </span>
                            {me ? <span className="shrink-0 text-[12.5px] font-medium">{t("leaderboard.you")}</span> : null}
                          </span>
                          {/* the figures a phone has no column for */}
                          <span className="flex flex-wrap gap-x-3 text-[12.5px] leading-snug text-muted-foreground sm:hidden">
                            {folded.map((c) => (
                              <span key={c.key} className="whitespace-nowrap">
                                {c.label}{" "}
                                <span dir="ltr" className="num bidi-isolate text-foreground">
                                  {c.value(entry)}
                                </span>
                              </span>
                            ))}
                          </span>
                        </Link>
                      </td>
                      {columns.map((c) => (
                        <td
                          key={c.key}
                          className={cn(
                            "num py-3 ps-2 pe-4 text-end align-middle whitespace-nowrap sm:pe-0 sm:ps-8 sm:last:pe-[22px]",
                            !onPhone.has(c.key) && "hidden sm:table-cell",
                            c.key === sortedOn ? "font-medium text-foreground" : "text-muted-foreground",
                          )}
                        >
                          <span dir="ltr" className="bidi-isolate">
                            {c.value(entry)}
                          </span>
                        </td>
                      ))}
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  )
}
