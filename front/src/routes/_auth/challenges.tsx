import { createFileRoute, Link } from "@tanstack/react-router"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useGetActiveChallengesApiV1ChallengesActiveGet } from "@/api/generated"
import type { ActiveChallenge } from "@/api/generated"
import { Lozenge, Seal } from "@/components/brand"
import { gameName, percentOf, timeLeft } from "@/components/stats/format"
import { PageHeader } from "@/components/stats/PlayerSpace"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/challenges")({
  component: ChallengesPage,
})

function ChallengesPage() {
  const { t } = useTranslation()
  const { user } = useAuth()

  const { data: challenges = [], isLoading } = useGetActiveChallengesApiV1ChallengesActiveGet({
    query: { enabled: !!user?.id },
  }) as { data: ActiveChallenge[] | undefined; isLoading: boolean }

  const daily = useMemo(() => challenges.filter((c) => c.challenge_type === "daily"), [challenges])
  const weekly = useMemo(() => challenges.filter((c) => c.challenge_type === "weekly"), [challenges])
  const done = challenges.filter((c) => c.completed).length

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <PageHeader title={t("challenges.title")} lede={challenges.length > 0 ? t("challenges.doneCount", { done, total: challenges.length }) : undefined} />

      {isLoading ? (
        <div className="grid gap-[clamp(16px,2vw,24px)] lg:grid-cols-2" aria-busy="true">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : challenges.length === 0 ? (
        <Panel>
          <EmptyState
            titleAs="h2"
            title={t("challenges.emptyTitle")}
            description={t("challenges.noChallenges")}
            action={
              <Button asChild>
                <Link to="/rooms">{t("stats.findRoom")}</Link>
              </Button>
            }
          />
        </Panel>
      ) : (
        <div className="grid items-start gap-[clamp(16px,2vw,24px)] lg:grid-cols-2">
          {daily.length > 0 ? <ChallengeList id="daily" title={t("challenges.daily")} items={daily} /> : null}
          {weekly.length > 0 ? <ChallengeList id="weekly" title={t("challenges.weekly")} items={weekly} /> : null}
        </div>
      )}
    </div>
  )
}

/**
 * One period's challenges in a hairline list. The period's end is said once in the
 * header (they share it); a row repeats it only when it differs.
 */
function ChallengeList({ id, title, items }: { id: string; title: string; items: ActiveChallenge[] }) {
  const { t } = useTranslation()
  const ends = items.map((c) => c.expires_at)
  const first = [...ends].sort()[0]
  const shared = ends.every((e) => e === first)

  return (
    <Panel aria-labelledby={`ch-${id}`}>
      <PanelHeader
        className="mb-2"
        title={<span id={`ch-${id}`}>{title}</span>}
        sub={first ? t("challenges.expiresIn", { time: timeLeft(first, t) }) : undefined}
      />
      <ul>
        {items.map((c) => (
          <ChallengeRow key={c.id} c={c} showExpiry={!shared} />
        ))}
      </ul>
    </Panel>
  )
}

function ChallengeRow({ c, showExpiry }: { c: ActiveChallenge; showExpiry: boolean }) {
  const { t } = useTranslation()
  const text = t(`challenges.items.${c.code}`, { defaultValue: c.description })
  const current = Math.min(c.progress, c.target_count)
  const meta = [c.game_type ? gameName(c.game_type, t) : t("challenges.anyGame"), showExpiry ? timeLeft(c.expires_at, t) : null].filter(Boolean).join(" · ")

  return (
    <li className="grid gap-2.5 border-t border-line py-3.5 first:border-t-0">
      <div className="flex items-start gap-3">
        <span className="grid size-[22px] shrink-0 place-items-center pt-0.5">
          {c.completed ? <Seal size={22} pressed={false} /> : <Lozenge state="open" size={10} />}
        </span>
        <div className="grid min-w-0 flex-1 gap-0.5">
          <p className="text-[15.5px] font-medium leading-snug">{text}</p>
          <p className="type-meta">{meta}</p>
        </div>
        {c.completed ? (
          <span className="shrink-0 text-[13px] font-medium text-brass">{t("challenges.completed")}</span>
        ) : (
          <span dir="ltr" className="num bidi-isolate shrink-0 text-[13.5px] text-muted-foreground">
            {current} / {c.target_count}
          </span>
        )}
      </div>
      {c.completed ? null : (
        <Progress
          value={percentOf(current, c.target_count)}
          aria-label={t("challenges.progressLabel", { name: text, current, target: c.target_count })}
          className="ms-[34px] w-auto"
        />
      )}
    </li>
  )
}
