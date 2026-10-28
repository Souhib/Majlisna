import { useTranslation } from "react-i18next"
import { currentLanguage } from "@/components/layout/language-switch"
import { cn } from "@/lib/utils"
import { READ_RAILS } from "./rails"

/**
 * "How the games play": one block per game, each the target of the home fihrist's
 * "How it plays" link (/about#undercover, #codenames, #kalimat, #quiz). A round in four
 * steps; the steps are a real sequence, so they are numbered. Brass hairlines, the
 * Arabic name in Amiri brass over the Latin name in Marcellus, as on the home page.
 */
type GameKey = "undercover" | "codenames" | "wordQuiz" | "mcqQuiz"

const GAMES: { key: GameKey; anchor: string; count: string; countKey: string }[] = [
  { key: "undercover", anchor: "undercover", count: "3–12", countKey: "home.fihrist.players" },
  { key: "codenames", anchor: "codenames", count: "4–10", countKey: "home.fihrist.playersTeams" },
  { key: "wordQuiz", anchor: "kalimat", count: "1+", countKey: "home.fihrist.soloOrTogether" },
  { key: "mcqQuiz", anchor: "quiz", count: "1+", countKey: "home.fihrist.soloOrTogether" },
]

const STEPS = ["step1", "step2", "step3", "step4"] as const

export function GameRules() {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"

  return (
    <section aria-labelledby="rules-title" className="grid gap-8">
      {/* the About page's two rails: titles and names at the start, reading text after */}
      <header className={cn(READ_RAILS, "items-baseline")}>
        <h2 id="rules-title" className="type-h3">
          {t("rules.title")}
        </h2>
        <p className="type-lede max-w-[52ch]">{t("rules.intro")}</p>
      </header>

      <div className="border-b border-line-brass">
        {GAMES.map(({ key, anchor, count, countKey }) => {
          const name = t(`games.${key}.name`)
          return (
            <article
              key={key}
              id={anchor}
              aria-labelledby={`${anchor}-title`}
              className={cn(READ_RAILS, "scroll-mt-[calc(var(--navh)+24px)] border-t border-line-brass py-8")}
            >
              <header className="grid content-start gap-1">
                {arabic ? null : (
                  <p className="type-arabic-name text-[44px]" aria-hidden="true">
                    <span lang="ar" dir="rtl">
                      {t(`home.fihrist.${key}.arabic`)}
                    </span>
                  </p>
                )}
                {/* the Arabic page shows the name with its kashida; the heading's name stays plain */}
                <h3 id={`${anchor}-title`} className={arabic ? "type-arabic-name text-[44px]" : "type-title text-[26px]"}>
                  {arabic ? (
                    <>
                      <span aria-hidden="true">{t(`home.fihrist.${key}.arabic`)}</span>
                      <span className="sr-only">{name}</span>
                    </>
                  ) : (
                    name
                  )}
                </h3>
                <p className="mt-2 text-[14px] text-muted-foreground">
                  <span dir="ltr" className="num bidi-isolate text-foreground">
                    {count}
                  </span>
                  {/* the gap belongs to the label: it follows the page's direction, the figure does not */}
                  <span className="ms-1.5">{t(countKey)}</span>
                </p>
              </header>
              <ol className="grid gap-3">
                {STEPS.map((step, i) => (
                  <li key={step} className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-baseline gap-2">
                    <span className="num text-[15px] font-medium text-brass" aria-hidden="true">
                      {i + 1}
                    </span>
                    <p className="max-w-[62ch] text-[16.5px] leading-relaxed text-pretty">{t(`rules.${key}.${step}`)}</p>
                  </li>
                ))}
              </ol>
            </article>
          )
        })}
      </div>
    </section>
  )
}
