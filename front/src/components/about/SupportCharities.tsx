import { ArrowUpRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { trackEvent } from "@/lib/analytics"
import { READ_RAILS } from "./rails"

/**
 * The two charities, as the home page sets them: two quiet columns between hairlines, no
 * tinted cards, no coloured buttons. Clicks are still counted (`charity-click`).
 */
const CHARITIES = [
  { name: "Human Appeal", href: "https://humanappeal.fr/", org: "human-appeal", desc: "home.charity.humanAppealDesc" },
  { name: "Ummah Charity", href: "https://ummahcharity.org/", org: "ummah-charity", desc: "home.charity.ummahCharityDesc" },
] as const

export function SupportCharities() {
  const { t } = useTranslation()
  return (
    <section aria-labelledby="support-title" className={READ_RAILS}>
      <h2 id="support-title" className="type-h3">
        {t("home.charity.title")}
      </h2>
      <div className="grid gap-6">
        <p className="type-lede max-w-[52ch]">{t("home.charity.subtitle")}</p>
        <ul className="grid border-y border-line sm:grid-cols-2">
          {CHARITIES.map((c) => (
            <li
              key={c.org}
              className="grid content-start gap-2.5 py-6 not-first:border-t not-first:border-line sm:px-6 sm:first:ps-0 sm:not-first:border-t-0 sm:not-first:border-s sm:last:pe-0"
            >
              <h3 lang="en" className="font-display text-[24px] leading-tight">
                {c.name}
              </h3>
              <p className="max-w-[46ch] text-[15.5px] leading-relaxed text-pretty text-muted-foreground">{t(c.desc)}</p>
              <a
                href={c.href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => trackEvent("charity-click", { org: c.org })}
                className="inline-flex min-h-11 w-fit items-center gap-2 text-[15px] font-medium text-brass underline decoration-line-brass-strong underline-offset-[5px] hover:decoration-brass"
              >
                {t("home.charity.donate")}
                <span className="sr-only">
                  {c.name} {t("ui.opensInNewTab")}
                </span>
                <ArrowUpRight className="size-4 rtl-flip" aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
