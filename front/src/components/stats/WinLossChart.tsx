import { BarElement, CategoryScale, Chart as ChartJS, LinearScale, Tooltip, type ChartOptions } from "chart.js"
import { useMemo } from "react"
import { Bar } from "react-chartjs-2"
import { useTranslation } from "react-i18next"
import { useGetGameHistoryApiV1StatsUsersUserIdHistoryGet } from "@/api/generated"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { currentLanguage } from "@/components/layout/language-switch"
import { type ResolvedTheme, useResolvedTheme } from "@/hooks/use-resolved-theme"
import { tokenColor } from "./chart-colors"
import { type DayRecord, fillDays, latnLocale } from "./format"

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

const DAYS = 30

/** The Samar tokens the chart draws with, read for the light now on screen. */
function chartColors(_light: ResolvedTheme) {
  return {
    win: tokenColor("--brass"),
    loss: tokenColor("--text-muted", 0.5),
    grid: tokenColor("--line"),
    tick: tokenColor("--text-muted"),
    text: tokenColor("--text"),
    surface: tokenColor("--popover-bg"),
    frame: tokenColor("--line-brass-strong"),
  }
}

/**
 * The last 30 days, one bar per day: wins in brass at the foot, losses in muted wool
 * above them. Every day keeps its slot (fillDays), so a quiet fortnight shows as one.
 * Colours are read from the Samar tokens and re-read when the light changes. The canvas
 * is an image with a summary for its name, and a table carries the same numbers for
 * assistive tech.
 */
export function WinLossChart({ userId }: { userId: string }) {
  const { t, i18n } = useTranslation()
  const theme = useResolvedTheme()
  const rtl = currentLanguage(i18n.language) === "ar"
  const { data = [], isLoading } = useGetGameHistoryApiV1StatsUsersUserIdHistoryGet({ user_id: userId }, { days: DAYS }) as {
    data: DayRecord[] | undefined
    isLoading: boolean
  }

  const days = useMemo(() => fillDays(data, DAYS), [data])
  const wins = days.reduce((n, d) => n + d.wins, 0)
  const losses = days.reduce((n, d) => n + d.losses, 0)
  const locale = latnLocale(i18n.language)
  const dayLabel = (iso: string, month: "short" | "long" = "short") =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString(locale, { month, day: "numeric", timeZone: "UTC" })

  const colors = useMemo(() => chartColors(theme), [theme])

  const options = useMemo<ChartOptions<"bar">>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { top: 4 } },
      scales: {
        x: {
          stacked: true,
          reverse: rtl,
          grid: { display: false },
          border: { color: colors.grid },
          ticks: {
            color: colors.tick,
            font: { family: "Readex Pro Variable", size: 11 },
            autoSkip: true,
            maxTicksLimit: 6,
            maxRotation: 0,
          },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          position: rtl ? "right" : "left",
          grid: { color: colors.grid },
          border: { display: false },
          ticks: { color: colors.tick, precision: 0, stepSize: 1, font: { family: "Readex Pro Variable", size: 11 } },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl,
          backgroundColor: colors.surface,
          borderColor: colors.frame,
          borderWidth: 1,
          titleColor: colors.text,
          bodyColor: colors.text,
          cornerRadius: 2,
          padding: 10,
          boxPadding: 4,
          titleFont: { family: "Readex Pro Variable", weight: 500 },
          bodyFont: { family: "Readex Pro Variable" },
        },
      },
    }),
    [colors, rtl],
  )

  if (isLoading) {
    return (
      <Panel>
        <Skeleton className="mb-4 h-5 w-40" />
        <Skeleton className="h-56 w-full" />
      </Panel>
    )
  }

  const chartData = {
    labels: days.map((d) => dayLabel(d.date)),
    datasets: [
      {
        label: t("stats.won"),
        data: days.map((d) => d.wins),
        backgroundColor: colors.win,
        borderRadius: 1,
        maxBarThickness: 18,
      },
      {
        label: t("stats.lost"),
        data: days.map((d) => d.losses),
        backgroundColor: colors.loss,
        borderRadius: 1,
        maxBarThickness: 18,
      },
    ],
  }
  const summary = t("stats.chartSummary", { wins, losses })
  const played = days.filter((d) => d.wins + d.losses > 0)

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
              <span aria-hidden="true" className="loz bg-[color-mix(in_oklch,var(--text-muted)_50%,transparent)] [--loz:8px]" />
              {t("stats.lost")} <b className="num font-medium text-foreground">{losses}</b>
            </li>
          </ul>
        }
      />
      {played.length === 0 ? (
        <p className="py-10 text-center text-[15px] text-muted-foreground">{t("stats.noRecentGames")}</p>
      ) : (
        <>
          <div className="h-56">
            <Bar data={chartData} options={options} role="img" aria-label={`${t("stats.last30")}: ${summary}`} />
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
