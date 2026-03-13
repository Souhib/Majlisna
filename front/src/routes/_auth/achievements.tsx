import { createFileRoute } from "@tanstack/react-router"
import { Award, Lock } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/providers/AuthProvider"
import { useGetUserAchievementsApiV1StatsUsersUserIdAchievementsGet } from "@/api/generated"

interface AchievementData {
  code: string
  name: string
  description: string
  icon: string
  category: string
  tier: number
  threshold: number
  progress: number
  unlocked: boolean
  rarity_percentage: number | null
}

function getRarityLabel(rarity: number | null, t: (key: string) => string): { label: string; color: string } | null {
  if (rarity === null) return null
  if (rarity <= 1) return { label: t("achievements.rarity.mythic"), color: "text-red-500 bg-red-500/10" }
  if (rarity <= 5) return { label: t("achievements.rarity.legendary"), color: "text-purple-500 bg-purple-500/10" }
  if (rarity <= 15) return { label: t("achievements.rarity.epic"), color: "text-yellow-500 bg-yellow-500/10" }
  if (rarity <= 30) return { label: t("achievements.rarity.rare"), color: "text-blue-500 bg-blue-500/10" }
  return { label: t("achievements.rarity.common"), color: "text-muted-foreground bg-muted" }
}

const TIER_COLORS: Record<number, string> = {
  1: "border-amber-700/40 shadow-amber-700/10",
  2: "border-gray-400/40 shadow-gray-400/10",
  3: "border-yellow-500/40 shadow-yellow-500/10",
  4: "border-emerald-500/40 shadow-emerald-500/10",
  5: "border-purple-500/40 shadow-purple-500/10",
  6: "border-red-500/40 shadow-red-500/10",
}

const TIER_GLOW: Record<number, string> = {
  1: "hover:shadow-amber-700/20",
  2: "hover:shadow-gray-400/20",
  3: "hover:shadow-yellow-500/20",
  4: "hover:shadow-emerald-500/20",
  5: "hover:shadow-purple-500/20",
  6: "hover:shadow-red-500/20",
}

export const Route = createFileRoute("/_auth/achievements")({
  component: AchievementsPage,
})

function AchievementsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()

  const { data: achievements = [] as AchievementData[], isLoading } = useGetUserAchievementsApiV1StatsUsersUserIdAchievementsGet(
    { user_id: user?.id ?? "" },
    { query: { enabled: !!user?.id } },
  ) as { data: AchievementData[] | undefined; isLoading: boolean }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8 animate-slide-up">
        <h1 className="text-3xl font-extrabold tracking-tight gradient-text mb-8">{t("achievements.title")}</h1>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="glass rounded-2xl p-6 animate-pulse">
              <div className="h-10 w-10 rounded-xl bg-muted mb-3" />
              <div className="h-4 w-24 rounded bg-muted mb-2" />
              <div className="h-3 w-32 rounded bg-muted" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 animate-slide-up">
      <h1 className="text-3xl font-extrabold tracking-tight gradient-text mb-8">{t("achievements.title")}</h1>

      {achievements.length === 0 ? (
        <p className="text-muted-foreground">{t("achievements.noAchievements")}</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {achievements.map((achievement) => (
            <div
              key={achievement.code}
              className={`relative rounded-2xl border p-6 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
                achievement.unlocked
                  ? `glass ${TIER_COLORS[achievement.tier] || "border-primary/30"} ${TIER_GLOW[achievement.tier] || "hover:shadow-primary/20"} shadow-md`
                  : "bg-muted/20 border-border/30 opacity-60"
              }`}
            >
              {/* Lock overlay for locked achievements */}
              {!achievement.unlocked && (
                <div className="absolute inset-0 rounded-2xl bg-background/40 backdrop-blur-[1px] z-10 flex items-center justify-center">
                  <Lock className="h-8 w-8 text-muted-foreground/40" />
                </div>
              )}

              <div className="flex items-center gap-3 mb-2">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                    achievement.unlocked ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {achievement.unlocked ? (
                    <Award className="h-5 w-5" />
                  ) : (
                    <Lock className="h-5 w-5" />
                  )}
                </div>
                <div>
                  <h3 className="font-extrabold tracking-tight text-sm">{t(`achievements.items.${achievement.code}.name`, { defaultValue: achievement.name })}</h3>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-muted-foreground font-mono">
                      {t(`achievements.tiers.${achievement.tier}`)}
                    </span>
                    {(() => {
                      const rarity = getRarityLabel(achievement.rarity_percentage, t)
                      if (!rarity) return null
                      return (
                        <span className={`rounded-lg px-1.5 py-0.5 text-[9px] font-bold ${rarity.color}`}>
                          {rarity.label} ({achievement.rarity_percentage}%)
                        </span>
                      )
                    })()}
                  </div>
                </div>
              </div>
              <p className="text-xs text-muted-foreground mb-3">{t(`achievements.items.${achievement.code}.description`, { defaultValue: achievement.description })}</p>

              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>
                    {achievement.unlocked
                      ? t("achievements.unlocked")
                      : t("achievements.progress", {
                          current: Math.min(achievement.progress, achievement.threshold),
                          target: achievement.threshold,
                        })}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-200 ${
                      achievement.unlocked ? "bg-gradient-to-r from-primary to-primary/80" : "bg-primary/40"
                    }`}
                    style={{
                      width: `${Math.min((achievement.progress / achievement.threshold) * 100, 100)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
