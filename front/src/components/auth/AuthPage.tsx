import { type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge, SaduBand, Wordmark } from "@/components/brand"
import { Panel } from "@/components/ui/panel"
import { cn } from "@/lib/utils"

/**
 * The frame of every auth page (log in, register, forgot, reset, verify): one panel on
 * the page ground, quiet and certain. A Marcellus title, the form, a hairline above the
 * way to the other form, and the panel's woven foot (the screen's one madd band).
 *
 * From 1024 px the panel shares the width with one quiet line of what Majlisna is: the
 * name (small, its kashida in ink with the madder thread, so the band at the foot stays
 * the only woven strip), the line, the four games and the three languages. It holds no
 * control, so it can sit at the reading start while the form comes first in the DOM and
 * in the tab order. Phones get the panel alone: the nav already carries the name.
 */
const GAMES = ["undercover", "codenames", "wordQuiz", "mcqQuiz"] as const
const LANGUAGES = [
  { lang: "en", dir: "ltr", name: "English" },
  { lang: "fr", dir: "ltr", name: "Français" },
  { lang: "ar", dir: "rtl", name: "العربية" },
] as const

function QuietList({ label, items }: { label: string; items: { key: string; node: ReactNode }[] }) {
  return (
    <ul aria-label={label} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[15px] leading-snug text-muted-foreground">
      {items.map(({ key, node }, i) => (
        <li key={key} className="inline-flex items-center gap-3">
          {/* the lozenge separates, it does not count: hidden from assistive tech */}
          {i > 0 ? <Lozenge size={5} /> : null}
          {node}
        </li>
      ))}
    </ul>
  )
}

function AuthAside({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <div className={cn("grid content-center justify-items-start gap-7", className)}>
      <Wordmark size={76} woven={false} stretch={1.25} label={null} className="text-lockup" />
      <p className="type-h3 max-w-[17ch] text-balance">{t("auth.aside.line")}</p>
      <div className="grid gap-2.5 border-t border-line-brass pt-5">
        <QuietList label={t("auth.aside.games")} items={GAMES.map((key) => ({ key, node: t(`games.${key}.name`) }))} />
        <QuietList
          label={t("auth.aside.languages")}
          items={LANGUAGES.map((l) => ({
            key: l.lang,
            node: (
              <span lang={l.lang} dir={l.dir} className="bidi-isolate">
                {l.name}
              </span>
            ),
          }))}
        />
      </div>
    </div>
  )
}

export interface AuthPageProps {
  title: ReactNode
  description?: ReactNode
  /** The way to the other form ("Don't have an account? Register"), under a hairline. */
  footer?: ReactNode
  children?: ReactNode
}

export function AuthPage({ title, description, footer, children }: AuthPageProps) {
  return (
    <div className="page-wrap grid min-h-[calc(100svh-var(--navh))] content-start py-6 sm:content-center sm:py-[clamp(40px,6vw,88px)]">
      <div className="mx-auto grid w-full max-w-[64rem] items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:gap-[clamp(56px,7vw,112px)]">
        <Panel
          flush
          aria-labelledby="auth-title"
          className="w-full max-w-[28rem] justify-self-center overflow-hidden lg:col-start-2 lg:row-start-1"
        >
          <div className="grid gap-7 px-5 pt-7 pb-8 sm:px-9 sm:pt-9 sm:pb-9">
            <header className="grid gap-2.5">
              <h1 id="auth-title" className="type-title">
                {title}
              </h1>
              {description ? <p className="text-[15.5px] leading-[1.55] text-pretty text-muted-foreground">{description}</p> : null}
            </header>
            {children}
          </div>
          {footer ? <div className="border-t border-line px-5 py-4 text-[15px] text-muted-foreground sm:px-9">{footer}</div> : null}
          <SaduBand height={10} />
        </Panel>
        <AuthAside className="hidden lg:col-start-1 lg:row-start-1 lg:grid" />
      </div>
    </div>
  )
}

/** The link at the foot of a panel: brass underline, 44 px tall on touch screens. */
export const authLinkClass =
  "inline-flex items-center font-medium text-foreground underline decoration-line-brass-strong underline-offset-[5px] hover:decoration-brass pointer-coarse:min-h-11"
