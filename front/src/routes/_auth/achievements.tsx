import { createFileRoute, Link } from "@tanstack/react-router"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useGetUserAchievementsApiV1StatsUsersUserIdAchievementsGet } from "@/api/generated"
import type { AchievementWithProgress } from "@/api/generated"
import { Lozenge, Seal } from "@/components/brand"
import { orderAchievements, percentOf } from "@/components/stats/format"
import { PageHeader } from "@/components/stats/PlayerSpace"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel } from "@/components/ui/panel"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/achievements")({
  component: AchievementsPage,
})

/** The backend's categories, in the order a new player meets them. */
const CATEGORIES = ["beginner", "undercover_master", "codenames_master", "social", "streak", "special"] as const

type T = (key: string, opts?: Record<string, unknown>) => string

function AchievementsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()

  const { data: achievements = [], isLoading } = useGetUserAchievementsApiV1StatsUsersUserIdAchievementsGet(
    { user_id: user?.id ?? "" },
    { query: { enabled: !!user?.id } },
  ) as { data: AchievementWithProgress[] | undefined; isLoading: boolean }

  const groups = useMemo(() => {
    const known = new Set<string>(CATEGORIES)
    const order = [...CATEGORIES, ...new Set(achievements.map((a) => a.category).filter((c) => !known.has(c)))]
    return order
      .map((category) => ({ category, items: orderAchievements(achievements.filter((a) => a.category === category)) }))
      .filter((g) => g.items.length > 0)
  }, [achievements])

  const earned = achievements.filter((a) => a.unlocked).length

  if (isLoading) {
    return (
      <div className="page-wrap py-[clamp(32px,5vw,72px)]" aria-busy="true">
        <PageHeader title={t("achievements.title")} />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-[132px] w-full" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <PageHeader
        title={t("achievements.title")}
        lede={achievements.length > 0 ? t("achievements.earnedCount", { earned, total: achievements.length }) : undefined}
        end={
          achievements.length > 0 ? (
            <Progress
              value={percentOf(earned, achievements.length)}
              aria-label={t("achievements.earnedCount", { earned, total: achievements.length })}
              className="w-[min(18rem,80vw)]"
            />
          ) : null
        }
      />

      {achievements.length === 0 ? (
        <Panel>
          <EmptyState
            titleAs="h2"
            title={t("achievements.noAchievements")}
            action={
              <Button asChild>
                <Link to="/rooms">{t("stats.findRoom")}</Link>
              </Button>
            }
          />
        </Panel>
      ) : (
        <div className="grid gap-[clamp(32px,4vw,52px)]">
          {groups.map((g) => (
            <section key={g.category} aria-labelledby={`ach-${g.category}`}>
              <div className="mb-4 flex items-baseline justify-between gap-4 border-b border-line-brass pb-2.5">
                <h2 id={`ach-${g.category}`} className="type-title text-[clamp(22px,2vw,26px)]">
                  {t(`achievements.category.${g.category}`, { defaultValue: g.category })}
                </h2>
                <p className="type-meta">
                  <span dir="ltr" className="num bidi-isolate">
                    {g.items.filter((a) => a.unlocked).length} / {g.items.length}
                  </span>
                </p>
              </div>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {g.items.map((a) => (
                  <AchievementTile key={a.code} a={a} t={t} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * One achievement. Earned: the brass seal, pressed and still (a page of seals must not
 * all move at once). Not yet: an empty lozenge, the condition, and how far along.
 */
function AchievementTile({ a, t }: { a: AchievementWithProgress; t: T }) {
  const name = t(`achievements.items.${a.code}.name`, { defaultValue: a.name })
  const condition = t(`achievements.items.${a.code}.description`, { defaultValue: a.description })
  const current = Math.min(a.progress, a.threshold)
  // rarity as a plain share of players: the old bucket names (Mythic, Epic…) collided with the tier names
  const pct = a.rarity_percentage
  const meta = [
    t(`achievements.tiers.${a.tier}`, { defaultValue: "" }),
    pct === null || pct === undefined ? null : pct > 0 ? t("achievements.rarityLine", { pct }) : t("achievements.rarityNone"),
  ]
    .filter(Boolean)
    .join(" · ")

  return (
    <li
      className={cn(
        "flex gap-4 rounded-lg border bg-surface p-4",
        a.unlocked ? "border-line-brass" : "border-line",
      )}
    >
      <span className="grid size-11 shrink-0 place-items-center">
        {/* the seal's ring reaches past its box (a rotated square in a ring): 34 keeps it inside the 44 px slot */}
        {a.unlocked ? (
          <Seal size={34} pressed={false} />
        ) : (
          <Lozenge state="open" size={22} className="opacity-90" />
        )}
      </span>
      <div className="grid min-w-0 flex-1 content-start gap-1">
        <h3 className="text-[16px] font-medium leading-snug">{name}</h3>
        <p className="text-[14px] leading-snug text-muted-foreground text-pretty">{condition}</p>
        {meta ? <p className="type-meta mt-1">{meta}</p> : null}
        {a.unlocked ? (
          <p className="mt-2 text-[13px] font-medium text-brass">{t("achievements.unlocked")}</p>
        ) : (
          <div className="mt-2.5 flex items-center gap-3">
            <Progress
              value={percentOf(current, a.threshold)}
              aria-label={t("achievements.progressLabel", { name, current, target: a.threshold })}
              className="flex-1"
            />
            <span dir="ltr" className="num bidi-isolate shrink-0 text-[13px] text-muted-foreground">
              {current} / {a.threshold}
            </span>
          </div>
        )}
      </div>
    </li>
  )
}
