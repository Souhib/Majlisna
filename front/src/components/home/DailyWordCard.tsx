import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Seal } from "@/components/brand"
import { categoryKey, DAILY_ARABIC_NAME, isFinished, stakes } from "@/components/daily/daily"
import { useDailyWordQuery } from "@/components/daily/use-daily-word"
import { Figure } from "@/components/games/shared/quiz-utils"
import { currentLanguage } from "@/components/layout/language-switch"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

/**
 * The word of the day on the home page, between the hero and the four games: the
 * Arabic name in Amiri brass with the Latin one under it, the day's number and theme,
 * and one rung of the ladder, then the way to /today:
 *
 * - not started (or signed out): hint 1, worth 6, and "Find today’s word";
 * - under way: the latest hint the player opened, worth what a right answer is worth
 *   now, and "Continue today’s word";
 * - over: hint 1, and how it went ("You found it · 4 points", or "You gave up today’s
 *   word") over "See today’s word".
 *
 * It reads the same query as the page (`useDailyWordQuery`), so opening /today from
 * here is instant. A read that fails leaves no card: the home is not the place to
 * report it, the page is.
 */
export function DailyWordCard() {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"
  const { query } = useDailyWordQuery()
  const state = query.data

  if (!state && query.isError) return null

  const category = state ? categoryKey(state.category) : null
  const finished = isFinished(state?.status)
  const playing = state?.status === "playing"
  // the rung shown: where a player under way stands, else the first one everybody gets
  const rung = state && playing ? Math.min(state.hints_revealed, state.hints.length) : 1
  const worth = state ? (playing ? stakes(state).now : state.max_hints) : 0
  const hint = state?.hints[rung - 1]

  return (
    <section className="home-daily" aria-labelledby="home-daily-title">
      <div className="home-wrap">
        <div className="home-daily-card panel-nodes" aria-busy={!state || undefined}>
          <div className="hd-name">
            {arabic ? (
              <h2 id="home-daily-title" className="ar">
                {t("daily.name")}
              </h2>
            ) : (
              <>
                <p className="ar" aria-hidden="true">
                  <span lang="ar" dir="rtl">
                    {DAILY_ARABIC_NAME}
                  </span>
                </p>
                <h2 id="home-daily-title">{t("daily.name")}</h2>
              </>
            )}
            {state ? (
              <p className="hd-meta">
                <Figure>{t("daily.number", { number: state.number })}</Figure>
                {category ? (
                  <>
                    {" "}
                    <span aria-hidden="true" className="hd-dot" /> {t(category)}
                  </>
                ) : null}
              </p>
            ) : (
              <Skeleton className="mt-2 h-4 w-32" aria-hidden="true" />
            )}
          </div>

          <div className="hd-hint">
            {state && hint ? (
              <>
                <p className="sr-only">{t("game.quiz.kalimat.rungLabel", { number: rung, total: state.max_hints, points: worth })}</p>
                <div className="hint-rung" data-state="now">
                  <span className="rung-worth" aria-hidden="true">
                    <span>{worth}</span>
                  </span>
                  <span className="rung-text min-w-0">{hint}</span>
                  <span className="rung-tag" aria-hidden="true">
                    {t("daily.home.rung", { number: rung })}
                  </span>
                </div>
              </>
            ) : (
              <Skeleton className="h-[52px] w-full" aria-hidden="true" />
            )}
          </div>

          <div className="hd-cta">
            {state?.status === "solved" ? (
              <p className="hd-note">
                <Seal size={16} pressed={false} />
                <span className="num">{t("daily.home.solved", { count: state.score ?? 0 })}</span>
              </p>
            ) : null}
            {state?.status === "gave_up" ? <p className="hd-note">{t("daily.home.gaveUp")}</p> : null}
            <Button
              asChild
              variant={finished ? "secondary" : "primary"}
              className="h-auto min-h-12 max-w-full whitespace-normal py-3 text-start min-[2200px]:min-h-14 min-[2200px]:text-[17px]"
              iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
            >
              <Link to="/today">{finished ? t("daily.home.see") : playing ? t("daily.home.continue") : t("daily.home.find")}</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}
