import { Link, useLocation } from "@tanstack/react-router"
import { ArrowUpRight, Github, Heart, Linkedin, Mail } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Lockup } from "@/components/brand"
import { trackEvent } from "@/lib/analytics"

/**
 * The footer: a quiet colophon under Qandil's rule. The lockup, one line on what the
 * place is, the pages (Credits included: the image licences live there), the two
 * charities (not on the home page nor on About, whose own sections already name them),
 * who made it, and the small print. Hidden on game screens (__root.tsx).
 */
const CHARITIES = [
  { name: "Human Appeal", href: "https://humanappeal.fr/", org: "human-appeal" },
  { name: "Ummah Charity", href: "https://ummahcharity.org/", org: "ummah-charity" },
] as const

/** Pages with their own charities section: the footer does not repeat it under them. */
const PAGES_THAT_NAME_THE_CHARITIES = new Set(["/", "/about"])

const SOCIAL = [
  { href: "https://github.com/Souhib", icon: Github, label: "GitHub" },
  { href: "https://www.linkedin.com/in/souhib-trabelsi/", icon: Linkedin, label: "LinkedIn" },
  { href: "mailto:souhib.t@icloud.com", icon: Mail, label: "Email" },
] as const

export function Footer() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const showCharities = !PAGES_THAT_NAME_THE_CHARITIES.has(pathname.replace(/\/+$/, "") || "/")

  return (
    <footer className="samar-footer">
      <div className="samar-footer-inner">
        <Link to="/" aria-label={t("nav.homeLabel")} className="nav-lockup text-lockup">
          <Lockup size={34} />
        </Link>
        <p className="footer-tagline">{t("footer.tagline")}</p>

        <nav aria-label={t("footer.pages")}>
          <ul className="footer-row footer-pages">
            <li>
              <Link to="/">{t("nav.play")}</Link>
            </li>
            <li>
              <Link to="/rooms">{t("nav.rooms")}</Link>
            </li>
            <li>
              <Link to="/challenges">{t("nav.challenges")}</Link>
            </li>
            <li>
              <Link to="/leaderboard">{t("nav.leaderboard")}</Link>
            </li>
            <li>
              <Link to="/about">{t("nav.about")}</Link>
            </li>
            <li>
              <Link to="/credits">{t("footer.credits")}</Link>
            </li>
            <li>
              <Link to="/privacy">{t("privacy.link")}</Link>
            </li>
          </ul>
        </nav>

        {showCharities ? (
          <div className="footer-row">
            <span className="footer-label">{t("home.charity.badge")}</span>
            <ul className="footer-row">
              {CHARITIES.map((c) => (
                <li key={c.org}>
                  <a
                    href={c.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => trackEvent("charity-click", { org: c.org })}
                  >
                    {c.name}
                    <ArrowUpRight className="size-3.5 rtl-flip" aria-hidden="true" />
                    <span className="sr-only">{t("ui.opensInNewTab")}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="footer-row">
          <span>
            {t("footer.madeBy")} <Link to="/about">{t("about.name")}</Link>
          </span>
          <span className="footer-social">
            {SOCIAL.map((s) => {
              const external = s.href.startsWith("http")
              return (
                <a
                  key={s.label}
                  href={s.href}
                  aria-label={s.label}
                  target={external ? "_blank" : undefined}
                  rel={external ? "noopener noreferrer" : undefined}
                  onClick={() => trackEvent("social-click", { platform: s.label.toLowerCase() })}
                >
                  <s.icon aria-hidden="true" />
                </a>
              )
            })}
          </span>
        </div>

        <p className="footer-small">
          <span className="num">{t("footer.copyright", { year: new Date().getFullYear() })}</span>
          <span aria-hidden="true" className="mx-2.5 inline-block size-1 rotate-45 bg-brass align-middle opacity-80" />
          <Trans
            i18nKey="footer.madeWithLove"
            components={{ heart: <Heart className="inline size-3 align-[-1px] text-brass" role="img" aria-label={t("footer.love")} /> }}
          />
        </p>
      </div>
    </footer>
  )
}
