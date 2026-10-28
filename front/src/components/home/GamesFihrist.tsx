import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { SaduBand } from "@/components/brand"
import { currentLanguage } from "@/components/layout/language-switch"

/**
 * Section B, "Four games, one gathering." (sketch: Khatt's fihrist, without photographs).
 * Each row: a brass index drawn from the game's own piece, the Arabic name large in Amiri
 * brass with its kashida, the Latin name under it in Marcellus, the rule, one honest
 * example line, the player count in Readex figures, and "How it plays". Above 1100 px the
 * four rows share one subgrid, so every description starts right after the widest name.
 * Brass hairlines with lozenge nodes; one madd band closes the list.
 */

/* The brass marks, one size, one 1.5 px stroke (sketch section B). */
function MarkUndercover() {
  // the held tablet (lawh): bare warp, a seal, a woven foot
  return (
    <svg className="mark" viewBox="0 0 56 56" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="8.75" y="11.75" width="38.5" height="32.5" rx="2" />
      <path d="M14.75 16.5v17M19.75 16.5v17M36.25 16.5v17M41.25 16.5v17" />
      <path d="M28 19.25l5.25 5.25L28 29.75 22.75 24.5z" fill="currentColor" />
      <path d="M8.75 37.25h38.5" />
      <path d="M8.75 37.25h38.5v5a2 2 0 0 1-2 2H10.75a2 2 0 0 1-2-2z" fill="currentColor" fillOpacity=".55" stroke="none" />
      <path d="M15 40.75h3M25 40.75h6M38 40.75h3" strokeLinecap="round" />
    </svg>
  )
}

function MarkCodenames() {
  // a corner of the board: two revealed cards, one still to find
  return (
    <svg className="mark" viewBox="0 0 56 56" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="6.75" y="12.75" width="12.5" height="9" rx="1" />
      <rect x="21.75" y="12.75" width="12.5" height="9" rx="1" fill="currentColor" />
      <rect x="36.75" y="12.75" width="12.5" height="9" rx="1" />
      <rect x="6.75" y="24.25" width="12.5" height="9" rx="1" />
      <rect x="21.75" y="24.25" width="12.5" height="9" rx="1" />
      <rect x="36.75" y="24.25" width="12.5" height="9" rx="1" fill="currentColor" />
      <rect x="6.75" y="35.75" width="12.5" height="9" rx="1" strokeDasharray="2.5 2" />
      <rect x="21.75" y="35.75" width="12.5" height="9" rx="1" />
      <rect x="36.75" y="35.75" width="12.5" height="9" rx="1" />
    </svg>
  )
}

function MarkKalimat() {
  // the hint ladder: one rung lit, the last two still dotted
  return (
    <svg className="mark" viewBox="0 0 56 56" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M13 8.5l4 4-4 4-4-4z" />
      <path d="M13 19.5l4 4-4 4-4-4z" fill="currentColor" />
      <path d="M13 30.5l4 4-4 4-4-4zM13 41.5l4 4-4 4-4-4z" />
      <path d="M22.5 12.5h25M22.5 23.5h25" />
      <path d="M22.5 34.5h25M22.5 45.5h25" strokeDasharray="1.5 3" />
    </svg>
  )
}

function MarkQuiz() {
  // the scoring bands over four lettered choices
  return (
    <svg className="mark" viewBox="0 0 56 56" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="6.75" y="8.75" width="42.5" height="8" />
      <path d="M17.4 8.75v8M38.6 8.75v8" />
      <path d="M6.75 8.75h10.65v8H6.75z" fill="currentColor" />
      <path d="M11 22.5l3.5 3.5-3.5 3.5-3.5-3.5zM11 42.5l3.5 3.5-3.5 3.5-3.5-3.5z" />
      <path d="M11 32.5l3.5 3.5-3.5 3.5-3.5-3.5z" fill="currentColor" />
      <path d="M19.5 26h29.75M19.5 36h29.75M19.5 46h29.75" />
    </svg>
  )
}

type GameKey = "undercover" | "codenames" | "wordQuiz" | "mcqQuiz"

const ROWS: {
  key: GameKey
  anchor: string
  Mark: typeof MarkUndercover
  count: string
  countKey: string
}[] = [
  { key: "undercover", anchor: "undercover", Mark: MarkUndercover, count: "3–12", countKey: "home.fihrist.players" },
  { key: "codenames", anchor: "codenames", Mark: MarkCodenames, count: "4–10", countKey: "home.fihrist.playersTeams" },
  { key: "wordQuiz", anchor: "kalimat", Mark: MarkKalimat, count: "1+", countKey: "home.fihrist.soloOrTogether" },
  { key: "mcqQuiz", anchor: "quiz", Mark: MarkQuiz, count: "1+", countKey: "home.fihrist.soloOrTogether" },
]

function Sample({ game }: { game: GameKey }) {
  const { t } = useTranslation()
  const base = `home.fihrist.${game}`
  if (game === "undercover") {
    return (
      <p className="fihrist-sample">
        <span className="a" lang="ar" dir="rtl">
          حجّ
        </span>
        <span className="dot" aria-hidden="true" />
        <span className="a" lang="ar" dir="rtl">
          عمرة
        </span>{" "}
        <span className="ms-2">{t(`${base}.sample`)}</span>
      </p>
    )
  }
  if (game === "codenames") {
    return (
      <p className="fihrist-sample">
        <span className="k">{t(`${base}.clueLabel`)}</span>
        <span className="cl">{t(`${base}.clueWord`)}</span>
        <span className="n num">2</span>
        {t(`${base}.sample`)}
      </p>
    )
  }
  return (
    <p className="fihrist-sample">
      <span className="k">{t(`${base}.sampleLabel`)}</span>
      {t(`${base}.sample`)}
    </p>
  )
}

export function GamesFihrist() {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"

  return (
    <section className="home-sec" aria-labelledby="games-title">
      <div className="home-wrap">
        <header className="home-sec-head">
          <div>
            <h2 id="games-title">{t("home.fihrist.title")}</h2>
            {arabic ? null : (
              <p className="echo">
                <span lang="ar" dir="rtl">
                  {t("home.fihrist.echo")}
                </span>
              </p>
            )}
          </div>
          <p>{t("home.fihrist.intro")}</p>
        </header>

        <ol className="fihrist" data-arabic-only={arabic || undefined}>
          {ROWS.map(({ key, anchor, Mark, count, countKey }) => {
            const name = t(`games.${key}.name`)
            return (
              <li key={key} className="fihrist-entry">
                <Mark />
                <div className="ttl">
                  {arabic ? (
                    // the kashida is drawn, not read: the heading's name is the plain one
                    <h3 className="ar">
                      <span aria-hidden="true">{t(`home.fihrist.${key}.arabic`)}</span>
                      <span className="sr-only">{name}</span>
                    </h3>
                  ) : (
                    <>
                      <p className="ar" aria-hidden="true">
                        <span lang="ar" dir="rtl">
                          {t(`home.fihrist.${key}.arabic`)}
                        </span>
                      </p>
                      <h3>{name}</h3>
                    </>
                  )}
                </div>
                <div className="desc">
                  <p className="rule">{t(`home.fihrist.${key}.rule`)}</p>
                  <Sample game={key} />
                </div>
                <div className="meta">
                  <p className="count">
                    <span dir="ltr" className="bidi-isolate">
                      {count}
                    </span>
                    <small>{t(countKey)}</small>
                  </p>
                  <Link to="/about" hash={anchor} aria-label={t("home.fihrist.howItPlaysLabel", { game: name })}>
                    {t("home.fihrist.howItPlays")}
                    <ArrowRight className="rtl-flip" aria-hidden="true" />
                  </Link>
                </div>
              </li>
            )
          })}
        </ol>
        <SaduBand className="home-band" />
      </div>
    </section>
  )
}
