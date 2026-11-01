import { type CSSProperties, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useGetGameHistoryApiV1StatsUsersUserIdHistoryGet } from "@/api/generated"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { type DayRecord, fillDays, latnLocale } from "./format"

const DAYS = 30
/** Every seventh day, counted back from today, names its date under the axis. */
const LABEL_EVERY = 7
/** Losses: the muted wool of the legend. */
const LOSS_TINT = "bg-[color-mix(in_oklch,var(--text-muted)_50%,transparent)]"

/** The smallest of 1, 2, 5 × 10ⁿ that is at least `raw`. */
function niceStep(raw: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  return [1, 2, 5, 10].map((m) => m * magnitude).find((step) => step >= raw) ?? 10 * magnitude
}

/** The top of the scale and its lines: whole games, one line per game up to 5, then about four. */
function scaleFor(busiest: number): { top: number; ticks: number[] } {
  const step = busiest <= 5 ? 1 : niceStep(busiest / 4)
  const top = Math.max(1, Math.ceil(busiest / step) * step)
  const ticks: number[] = []
  for (let v = 0; v <= top; v += step) ticks.push(v)
  return { top, ticks }
}

const share = (n: number, top: number) => `${(n / top) * 100}%`

/**
 * Where a date label sits under day `i`: centred on it, or held to the plot's start or end
 * near the edges so it is never cut off. Logical insets, so Arabic's mirrored axis needs no
 * code (day 0 is at the inline start in both directions).
 */
function labelAnchor(i: number): { style: CSSProperties; className: string } {
  if (i < 3) return { style: { insetInlineStart: share(i, DAYS) }, className: "" }
  if (i > DAYS - 4) return { style: { insetInlineEnd: share(DAYS - 1 - i, DAYS) }, className: "" }
  return { style: { insetInlineStart: share(i + 0.5, DAYS) }, className: "-translate-x-1/2 rtl:translate-x-1/2" }
}

/**
 * Where a day's tip sits: beside its bar, never on it (after it in the first half of the
 * month, before it in the second), its middle level with the bar's top, kept inside the plot.
 */
function tipAnchor(i: number, games: number, top: number): CSSProperties {
  const bottom = `clamp(0px, calc(${share(games, top)} - 2.25rem), calc(100% - 4.5rem))`
  if (i < DAYS / 2) return { insetInlineStart: share(i + 1, DAYS), bottom }
  return { insetInlineEnd: share(DAYS - i, DAYS), bottom }
}

/**
 * The last 30 days, one bar per day: wins in brass at the foot, losses in muted wool above
 * them, every day on one scale. Every day keeps its slot (fillDays), so a quiet fortnight
 * shows as one. Drawn with the page's own elements and tokens (it follows the light and the
 * direction by itself; chart.js weighed 52 kB gzip for it). The picture is an image with a
 * summary for its name; a table carries the same numbers for assistive tech; a pointer on a
 * day shows its figures.
 */
export function WinLossChart({ userId }: { userId: string }) {
  const { t, i18n } = useTranslation()
  const [active, setActive] = useState<number | null>(null)
  const { data = [], isLoading } = useGetGameHistoryApiV1StatsUsersUserIdHistoryGet({ user_id: userId }, { days: DAYS }) as {
    data: DayRecord[] | undefined
    isLoading: boolean
  }

  const days = useMemo(() => fillDays(data, DAYS), [data])
  const wins = days.reduce((n, d) => n + d.wins, 0)
  const losses = days.reduce((n, d) => n + d.losses, 0)
  const { top, ticks } = scaleFor(Math.max(0, ...days.map((d) => d.wins + d.losses)))
  const locale = latnLocale(i18n.language)
  const dayLabel = (iso: string, month: "short" | "long" = "short") =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString(locale, { month, day: "numeric", timeZone: "UTC" })

  if (isLoading) {
    return (
      <Panel>
        <Skeleton className="mb-4 h-5 w-40" />
        <Skeleton className="h-56 w-full" />
      </Panel>
    )
  }

  const summary = t("stats.chartSummary", { wins, losses })
  const played = days.filter((d) => d.wins + d.losses > 0)
  // a day without a game has no bar, and no tip
  const shown = active !== null && days[active].wins + days[active].losses > 0 ? days[active] : null

  return (
    <Panel aria-labelledby="winloss-title">
      <PanelHeader
        title={<span id="winloss-title">{t("stats.last30")}</span>}
        end={
          <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="loz bg-brass [--loz:8px]" />
              {t("stats.won")} <b className="num font-medium text-foreground">{wins}</b>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className={cn("loz [--loz:8px]", LOSS_TINT)} />
              {t("stats.lost")} <b className="num font-medium text-foreground">{losses}</b>
            </li>
          </ul>
        }
      />
      {played.length === 0 ? (
        <p className="py-10 text-center text-[15px] text-muted-foreground">{t("stats.noRecentGames")}</p>
      ) : (
        <>
          <div
            role="img"
            aria-label={`${t("stats.last30")}: ${summary}`}
            className="grid h-56 grid-cols-[auto_minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto] gap-x-2 pt-1"
          >
            {/* the scale, at the inline start */}
            <div className="relative w-5 text-[11px] text-muted-foreground">
              {ticks.map((v) => (
                <span key={v} className="num absolute end-0 translate-y-1/2 leading-none" style={{ bottom: share(v, top) }}>
                  {v}
                </span>
              ))}
            </div>
            <div className="relative border-b border-line" onPointerLeave={() => setActive(null)}>
              {ticks.slice(1).map((v) => (
                <span key={v} aria-hidden="true" className="absolute inset-x-0 border-t border-line" style={{ bottom: share(v, top) }} />
              ))}
              <ol className="absolute inset-0 flex">
                {days.map((d, i) => (
                  <li
                    key={d.date}
                    data-day={d.date}
                    className="flex h-full flex-1 flex-col-reverse items-center"
                    onPointerEnter={() => setActive(i)}
                    onPointerLeave={() => setActive((current) => (current === i ? null : current))}
                  >
                    {/* each bar 72% of its day's slot, 18 px at most */}
                    {d.wins > 0 ? (
                      <span data-part="won" className="w-[72%] max-w-[18px] rounded-[1px] bg-brass" style={{ height: share(d.wins, top) }} />
                    ) : null}
                    {d.losses > 0 ? (
                      <span data-part="lost" className={cn("w-[72%] max-w-[18px] rounded-[1px]", LOSS_TINT)} style={{ height: share(d.losses, top) }} />
                    ) : null}
                  </li>
                ))}
              </ol>
              {shown && active !== null ? (
                <div
                  data-testid="winloss-tip"
                  className="pointer-events-none absolute z-10 mx-1 whitespace-nowrap rounded-sm border border-line-brass-strong bg-popover px-2.5 py-2 text-[13px] text-foreground shadow-sm"
                  style={tipAnchor(active, shown.wins + shown.losses, top)}
                >
                  <p className="font-medium">{dayLabel(shown.date, "long")}</p>
                  <p className="flex items-center gap-2">
                    <span aria-hidden="true" className="loz bg-brass [--loz:7px]" />
                    {t("stats.won")} <b className="num font-medium">{shown.wins}</b>
                  </p>
                  <p className="flex items-center gap-2">
                    <span aria-hidden="true" className={cn("loz [--loz:7px]", LOSS_TINT)} />
                    {t("stats.lost")} <b className="num font-medium">{shown.losses}</b>
                  </p>
                </div>
              ) : null}
            </div>
            <span aria-hidden="true" />
            {/* the days, every seventh named, today last */}
            <div className="relative h-6 text-[11px] text-muted-foreground">
              {days.map((d, i) =>
                (DAYS - 1 - i) % LABEL_EVERY === 0 ? (
                  <span key={d.date} className={cn("absolute top-1.5 whitespace-nowrap leading-none", labelAnchor(i).className)} style={labelAnchor(i).style}>
                    {dayLabel(d.date)}
                  </span>
                ) : null,
              )}
            </div>
          </div>
          <table className="sr-only">
            <caption>{t("stats.last30")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("stats.day")}</th>
                <th scope="col">{t("stats.won")}</th>
                <th scope="col">{t("stats.lost")}</th>
              </tr>
            </thead>
            <tbody>
              {played.map((d) => (
                <tr key={d.date}>
                  <th scope="row">{dayLabel(d.date, "long")}</th>
                  <td>{d.wins}</td>
                  <td>{d.losses}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Panel>
  )
}
