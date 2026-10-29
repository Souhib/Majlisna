import { createFileRoute, Link } from "@tanstack/react-router"
import { Trans, useTranslation } from "react-i18next"
import { READ_RAILS } from "@/components/about/rails"
import { Lozenge } from "@/components/brand"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/privacy")({
  component: PrivacyPage,
})

/**
 * The privacy policy, in Read mode, on the About page's two rails (titles at the start,
 * the text after them at a reading measure). The text is `privacy.sections` in each
 * locale, a list of `{ title, body }`: a body of one paragraph reads as a paragraph,
 * a body of several is a list of items, each behind a brass lozenge. Two marks may
 * appear in the strings: `<b>` (an item's lead term) and `<profile>` (a link to the
 * profile page, where the account is edited and deleted).
 *
 * The policy describes the code as it is: every flow it names (prayer-time location
 * services, browser storage, cookies, providers) was checked in the code, and a change
 * to one of them changes this text (front/CLAUDE.md, "Privacy").
 */
const CONTACT_EMAIL = "souhib.t@icloud.com"

const BRASS_LINK = "font-medium text-brass underline decoration-line-brass-strong underline-offset-[5px] hover:decoration-brass"

interface PrivacySection {
  title: string
  body: string[]
}

function Text({ i18nKey }: { i18nKey: string }) {
  return (
    <Trans
      i18nKey={i18nKey}
      components={{
        b: <strong className="font-medium text-foreground" />,
        profile: <Link to="/profile" className={BRASS_LINK} />,
      }}
    />
  )
}

function SectionBody({ index, body }: { index: number; body: string[] }) {
  const key = (j: number) => `privacy.sections.${index}.body.${j}`
  if (body.length === 1) {
    return (
      <p className="type-body max-w-[60ch] text-pretty">
        <Text i18nKey={key(0)} />
      </p>
    )
  }
  return (
    <ul className="grid max-w-[60ch] gap-3.5">
      {body.map((paragraph, j) => (
        <li key={paragraph} className="type-body flex gap-3 text-pretty">
          {/* one line high, so the lozenge sits on the item's first line in every script */}
          <span aria-hidden="true" className="flex h-[1lh] shrink-0 items-center">
            <Lozenge size={6} />
          </span>
          <span className="min-w-0">
            <Text i18nKey={key(j)} />
          </span>
        </li>
      ))}
    </ul>
  )
}

function PrivacyPage() {
  const { t } = useTranslation()
  const raw = t("privacy.sections", { returnObjects: true })
  const sections = Array.isArray(raw) ? (raw as PrivacySection[]) : []

  return (
    <div className="page-wrap py-[clamp(48px,7vw,104px)]">
      <div className="mx-auto max-w-[62rem]">
        <header className={READ_RAILS}>
          <div className="grid content-start gap-3">
            <h1 className="type-h2">{t("privacy.title")}</h1>
            <p className="text-[14px] text-muted-foreground">{t("privacy.updated")}</p>
          </div>
          <p className="type-lede max-w-[54ch] md:pt-2">{t("privacy.intro")}</p>
        </header>

        <Separator className="my-[clamp(40px,5vw,72px)]" />

        <div className="border-b border-line">
          {sections.map((section, i) => (
            <section
              key={section.title}
              aria-labelledby={`privacy-section-${i}`}
              className={cn(READ_RAILS, "border-t border-line py-7 first:border-t-0 first:pt-0 md:py-8")}
            >
              <h2 id={`privacy-section-${i}`} className="type-title text-[24px] text-pretty md:pt-0.5">
                {section.title}
              </h2>
              <SectionBody index={i} body={section.body} />
            </section>
          ))}
        </div>

        <div className={cn(READ_RAILS, "mt-8")}>
          <p className="type-body text-pretty md:col-start-2">
            {t("privacy.contact")}{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className={BRASS_LINK}>
              <span dir="ltr" className="bidi-isolate">
                {CONTACT_EMAIL}
              </span>
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}
