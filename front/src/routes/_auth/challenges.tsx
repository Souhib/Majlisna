import { createFileRoute } from "@tanstack/react-router"
import { Calendar, CheckCircle2, Clock, Flame, Target, Trophy } from "lucide-react"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useGetActiveChallengesApiV1ChallengesActiveGet } from "@/api/generated"
import { useAuth } from "@/providers/AuthProvider"

interface ChallengeData {
  id: string
  code: string
  description: string
  challenge_type: string
  target_count: number
  game_type: string | null
  condition: string
  role: string | null
  progress: number
  completed: boolean
  assigned_at: string
  expires_at: string
}

export const Route = createFileRoute("/_auth/challenges")({
  component: ChallengesPage,
})

function getTimeRemaining(expiresAt: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const now = Date.now()
  const expires = new Date(expiresAt).getTime()
  const diff = expires - now

  if (diff <= 0) return t("challenges.time.expired")

  const hours = Math.floor(diff / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

  if (hours >= 24) {
    const days = Math.floor(hours / 24)
    return t("challenges.time.days", { d: days, h: hours % 24 })
  }
  if (hours > 0) return t("challenges.time.hours", { h: hours, m: minutes })
  return t("challenges.time.minutes", { m: minutes })
}

function ChallengesPage() {
  const { t } = useTranslation()
  const { user } = useAuth()

  const { data: challenges = [] as ChallengeData[], isLoading } = useGetActiveChallengesApiV1ChallengesActiveGet(
    { query: { enabled: !!user?.id } },
  ) as { data: ChallengeData[] | undefined; isLoading: boolean }

  const daily = useMemo(() => challenges.filter((c) => c.challenge_type === "daily"), [challenges])
  const weekly = useMemo(() => challenges.filter((c) => c.challenge_type === "weekly"), [challenges])

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8 animate-slide-up">
        <h1 className="text-3xl font-extrabold tracking-tight gradient-text mb-8">{t("challenges.title")}</h1>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5].map((i) => (
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
      <h1 className="text-3xl font-extrabold tracking-tight gradient-text mb-8">{t("challenges.title")}</h1>

      {challenges.length === 0 ? (
        <p className="text-muted-foreground">{t("challenges.noChallenges")}</p>
      ) : (
        <div className="space-y-8">
          {/* Daily Challenges */}
          {daily.length > 0 && (
            <section className="animate-scale-in">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-500/10">
                  <Flame className="h-4.5 w-4.5 text-orange-500" />
                </div>
                <h2 className="text-xl font-extrabold tracking-tight">{t("challenges.daily")}</h2>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {daily.map((challenge) => (
                  <ChallengeCard key={challenge.id} challenge={challenge} />
                ))}
              </div>
            </section>
          )}

          {/* Weekly Challenges */}
          {weekly.length > 0 && (
            <section className="animate-scale-in">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10">
                  <Calendar className="h-4.5 w-4.5 text-blue-500" />
                </div>
                <h2 className="text-xl font-extrabold tracking-tight">{t("challenges.weekly")}</h2>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {weekly.map((challenge) => (
                  <ChallengeCard key={challenge.id} challenge={challenge} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}

function ChallengeCard({ challenge }: { challenge: ChallengeData }) {
  const { t } = useTranslation()
  const progressPercent = Math.min((challenge.progress / challenge.target_count) * 100, 100)
  const timeRemaining = getTimeRemaining(challenge.expires_at, t)

  return (
    <div
      className={`card-hover rounded-2xl border p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
        challenge.completed
          ? "glass border-primary/30 shadow-md shadow-primary/10"
          : "glass border-border/30"
      }`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-xl ${
              challenge.completed
                ? "bg-primary/10 text-primary"
                : "bg-muted text-muted-foreground"
            }`}
          >
            {challenge.completed ? (
              <CheckCircle2 className="h-4.5 w-4.5" />
            ) : challenge.condition === "win" ? (
              <Trophy className="h-4.5 w-4.5" />
            ) : (
              <Target className="h-4.5 w-4.5" />
            )}
          </div>
          <div>
            <p className="font-extrabold tracking-tight text-sm leading-tight">{t(`challenges.items.${challenge.code}`, { defaultValue: challenge.description })}</p>
            {challenge.game_type && (
              <span className="text-[11px] text-muted-foreground">
                {challenge.game_type === "undercover" ? t("games.undercover.name") :
                 challenge.game_type === "codenames" ? t("games.codenames.name") :
                 challenge.game_type === "word_quiz" ? t("games.wordQuiz.name") : challenge.game_type}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Progress section */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span className="font-mono tabular-nums">
            {challenge.completed
              ? t("challenges.completed")
              : t("challenges.progress", {
                  current: challenge.progress,
                  target: challenge.target_count,
                })}
          </span>
          <span className="flex items-center gap-1 font-mono tabular-nums">
            <Clock className="h-3 w-3" />
            {timeRemaining}
          </span>
        </div>
        <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-200 ${
              challenge.completed ? "bg-gradient-to-r from-primary to-primary/80" : "bg-primary/40"
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Progress ring indicator */}
      {!challenge.completed && progressPercent > 0 && (
        <div className="mt-3 flex items-center justify-center">
          <svg className="h-8 w-8 -rotate-90" viewBox="0 0 32 32">
            <circle cx="16" cy="16" r="12" fill="none" strokeWidth="3" className="stroke-muted/30" />
            <circle
              cx="16" cy="16" r="12" fill="none" strokeWidth="3"
              className="stroke-primary"
              strokeLinecap="round"
              strokeDasharray={`${progressPercent * 0.754} 100`}
            />
          </svg>
          <span className="ml-2 text-xs font-mono tabular-nums text-muted-foreground">{Math.round(progressPercent)}%</span>
        </div>
      )}
    </div>
  )
}
