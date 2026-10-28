import { useTranslation } from "react-i18next"
import { useGetDurationStatsApiV1StatsUsersUserIdDurationGet } from "@/api/generated"
import type { GameDurationStats } from "@/api/generated"
import { formatClock } from "@/components/brand"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { formatDuration, gameName } from "./format"
import { type Figure, Figures } from "./PlayerSpace"

/**
 * A duration as the colophon writes it: a clock for the eye ("6:13", never broken across
 * lines) and a sentence for screen readers ("6 min 13 s"). "3 min 13 s" used to wrap its
 * "s" onto a line of its own in the figures, and disagreed with the colophon's "6:13".
 */
function Duration({ seconds }: { seconds: number | null | undefined }) {
  const { t } = useTranslation()
  if (!seconds || seconds <= 0) return <>—</>
  const whole = Math.round(seconds)
  return (
    <>
      <span className="sr-only">{formatDuration(whole, t)}</span>
      <time dateTime={`PT${whole}S`} aria-hidden="true" className="num whitespace-nowrap">
        {formatClock(whole)}
      </time>
    </>
  )
}

/** How long the player's games last: average, fastest, longest, and per game. */
export function DurationStats({ userId }: { userId: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useGetDurationStatsApiV1StatsUsersUserIdDurationGet({ user_id: userId }) as {
    data: GameDurationStats | undefined
    isLoading: boolean
  }

  if (isLoading) {
    return (
      <Panel>
        <Skeleton className="mb-4 h-5 w-36" />
        <Skeleton className="h-20 w-full" />
      </Panel>
    )
  }
  if (!data || data.total_games_with_duration === 0) return null

  const items: Figure[] = [
    { key: "avg", label: t("stats.avgDuration"), value: <Duration seconds={data.average_seconds} /> },
    { key: "fast", label: t("stats.fastestGame"), value: <Duration seconds={data.fastest_seconds} /> },
    { key: "long", label: t("stats.longestGame"), value: <Duration seconds={data.longest_seconds} /> },
    { key: "n", label: t("stats.gamesTracked"), value: data.total_games_with_duration },
  ]
  const perGame = [
    { type: "undercover", seconds: data.undercover_avg_seconds },
    { type: "codenames", seconds: data.codenames_avg_seconds },
  ].filter((g) => typeof g.seconds === "number" && g.seconds > 0)

  return (
    <Panel aria-labelledby="duration-title">
      <PanelHeader title={<span id="duration-title">{t("stats.gameDuration")}</span>} />
      <Figures items={items} framed={false} size="md" className="-mx-4 grid-cols-2 sm:-mx-[22px] lg:grid-cols-4" />
      {perGame.length > 0 ? (
        <dl className="mt-4 grid gap-x-8 gap-y-2 border-t border-line pt-4 text-[14.5px] sm:grid-cols-2">
          {perGame.map((g) => (
            <div key={g.type} className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">{t("stats.avgFor", { game: gameName(g.type, t) })}</dt>
              <dd className="font-medium">
                <Duration seconds={g.seconds} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </Panel>
  )
}
