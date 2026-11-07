import { Link } from "@tanstack/react-router"
import { type ReactNode } from "react"
import { Trans, useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { READ_RAILS } from "./rails"

/**
 * The privacy policy and the terms of use, in Read mode, on the About page's two rails
 * (titles at the start, the text after them at a reading measure). Each page's text is
 * `<ns>.title`, `.updated`, `.intro`, `.sections` and `.contact` in each locale, the
 * sections a list of `{ title, body }`: a body of one paragraph reads as a paragraph, a
 * body of several is a list of items, each behind a brass lozenge. The strings may carry
 * four marks: `<b>` (an item's lead term), `<profile>` (the profile page, where the account
 * is edited and deleted), `<privacy>` and `<terms>` (the two pages, linking each other).
 *
 * Both texts describe the code as it is, and a change to a flow they name changes them
 * (front/CLAUDE.md, "Privacy" and "Terms of use").
 */
const CONTACT_EMAIL = "souhib.t@icloud.com"

const BRASS_LINK = "font-medium text-brass underline decoration-line-brass-strong underline-offset-[5px] hover:decoration-brass"

export type LegalNamespace = "privacy" | "terms"

interface LegalSection {
  title: string
  body: string[]
}

/**
 * One string of the page, its marks turned into markup. `shouldUnescape`: Trans turns a
 * "<" that opens no known mark into "&lt;" before parsing, and only this prints it back
 * as "<" (the username rule lists the characters @ / \ < >).
 */
export function LegalText({ i18nKey }: { i18nKey: string }) {
  return (
    <Trans
      i18nKey={i18nKey}
      shouldUnescape
      components={{
        b: <strong className="font-medium text-foreground" />,
        profile: <Link to="/profile" className={BRASS_LINK} />,
        privacy: <Link to="/privacy" className={BRASS_LINK} />,
        terms: <Link to="/terms" className={BRASS_LINK} />,
      }}
    />
  )
}

function SectionBody({ ns, index, body }: { ns: LegalNamespace; index: number; body: string[] }) {
  const key = (j: number) => `${ns}.sections.${index}.body.${j}`
  if (body.length === 1) {
    return (
      <p className="type-body max-w-[60ch] text-pretty">
        <LegalText i18nKey={key(0)} />
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
            <LegalText i18nKey={key(j)} />
          </span>
        </li>
      ))}
    </ul>
  )
}

interface LegalPageProps {
  ns: LegalNamespace
  /** Lines under the contact line (the privacy policy's link to the terms). */
  after?: ReactNode
}

export function LegalPage({ ns, after }: LegalPageProps) {
  const { t } = useTranslation()
  const raw = t(`${ns}.sections`, { returnObjects: true })
  const sections = Array.isArray(raw) ? (raw as LegalSection[]) : []

  return (
    <div className="page-wrap py-[clamp(48px,7vw,104px)]">
      <div className="mx-auto max-w-[62rem]">
        <header className={READ_RAILS}>
          <div className="grid content-start gap-3">
            <h1 className="type-h2">{t(`${ns}.title`)}</h1>
            <p className="text-[14px] text-muted-foreground">{t(`${ns}.updated`)}</p>
          </div>
          <p className="type-lede max-w-[54ch] md:pt-2">{t(`${ns}.intro`)}</p>
        </header>

        <Separator className="my-[clamp(40px,5vw,72px)]" />

        <div className="border-b border-line">
          {sections.map((section, i) => (
            <section
              key={section.title}
              aria-labelledby={`${ns}-section-${i}`}
              className={cn(READ_RAILS, "border-t border-line py-7 first:border-t-0 first:pt-0 md:py-8")}
            >
              <h2 id={`${ns}-section-${i}`} className="type-title text-[24px] text-pretty md:pt-0.5">
                {section.title}
              </h2>
              <SectionBody ns={ns} index={i} body={section.body} />
            </section>
          ))}
        </div>

        <div className={cn(READ_RAILS, "mt-8")}>
          <div className="grid gap-3 md:col-start-2">
            <p className="type-body text-pretty">
              {t(`${ns}.contact`)}{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className={BRASS_LINK}>
                <span dir="ltr" className="bidi-isolate">
                  {CONTACT_EMAIL}
                </span>
              </a>
            </p>
            {after}
          </div>
        </div>
      </div>
    </div>
  )
}
