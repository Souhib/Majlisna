import { ArrowUpRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { trackEvent } from "@/lib/analytics"

/**
 * The two charities the home page has always pointed to, set as two quiet columns under
 * a hairline (no tinted cards, no coloured buttons). Clicks are counted in Umami as
 * before (`charity-click`).
 */
const CHARITIES = [
  { name: "Human Appeal", href: "https://humanappeal.fr/", org: "human-appeal", desc: "home.charity.humanAppealDesc" },
  { name: "Ummah Charity", href: "https://ummahcharity.org/", org: "ummah-charity", desc: "home.charity.ummahCharityDesc" },
] as const

export function SupportSection() {
  const { t } = useTranslation()
  return (
    <section className="home-sec pt-0" aria-labelledby="support-title">
      <div className="home-wrap">
        <header className="home-sec-head">
          <h2 id="support-title">{t("home.charity.title")}</h2>
          <p>{t("home.charity.subtitle")}</p>
        </header>
        <ul className="support-list">
          {CHARITIES.map((c) => (
            <li key={c.org}>
              <h3>{c.name}</h3>
              <p>{t(c.desc)}</p>
              <a
                href={c.href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => trackEvent("charity-click", { org: c.org })}
                className="inline-flex w-fit items-center gap-2 py-1.5 text-[15px] font-medium text-brass underline-offset-[5px] hover:underline max-[760px]:min-h-11 pointer-coarse:min-h-11"
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
