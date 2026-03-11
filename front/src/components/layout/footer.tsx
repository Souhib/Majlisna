import { Link } from "@tanstack/react-router"
import { BookOpen, ExternalLink, Github, Heart, Linkedin, Mail, User } from "lucide-react"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "motion/react"

function IslamicPattern() {
  return (
    <svg
      className="absolute inset-0 h-full w-full opacity-[0.04] dark:opacity-[0.06]"
      aria-hidden="true"
    >
      <defs>
        <pattern id="footer-geo" x="0" y="0" width="60" height="60" patternUnits="userSpaceOnUse">
          {/* 8-pointed star motif */}
          <path
            d="M30 5 L35 25 L55 30 L35 35 L30 55 L25 35 L5 30 L25 25 Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
          />
          <circle cx="30" cy="30" r="8" fill="none" stroke="currentColor" strokeWidth="0.3" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#footer-geo)" />
    </svg>
  )
}

export function Footer() {
  const { t } = useTranslation()
  const shouldReduceMotion = useReducedMotion()

  return (
    <footer className="relative mt-auto overflow-hidden bg-card/80 backdrop-blur-sm">
      <IslamicPattern />

      {/* Gradient top divider */}
      <div
        className="absolute top-0 inset-x-0 h-px"
        style={{
          background: "linear-gradient(90deg, transparent, var(--gradient-start) 20%, var(--gradient-end) 80%, transparent)",
          opacity: 0.35,
        }}
      />

      <div className="relative mx-auto max-w-7xl px-4 py-12">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.2fr_0.8fr_0.8fr_1.5fr]">
          {/* Brand column */}
          <div>
            <Link to="/" className="inline-flex items-center gap-2.5 group">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/80 text-primary-foreground transition-transform duration-200 group-hover:scale-105">
                <BookOpen className="h-5 w-5" />
              </div>
              <span className="text-lg font-extrabold tracking-tight gradient-text">
                Islamic Party Games
              </span>
            </Link>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground max-w-xs">
              {t("home.subtitle")}
            </p>
          </div>

          {/* Quick links */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/70 mb-4">
              {t("nav.rooms") ? "Navigation" : "Navigation"}
            </h3>
            <nav className="flex flex-col gap-3">
              {[
                { to: "/rooms" as const, label: t("nav.rooms") },
                { to: "/challenges" as const, label: t("nav.challenges") },
                { to: "/leaderboard" as const, label: t("nav.leaderboard") },
                { to: "/about" as const, label: t("nav.about") },
              ].map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className="text-sm text-muted-foreground transition-all duration-200 hover:text-primary hover:translate-x-0.5 w-fit"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>

          {/* Support */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/70 mb-4">
              {t("home.charity.badge")}
            </h3>
            <nav className="flex flex-col gap-3">
              <a
                href="https://humanappeal.org.uk/donate"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-all duration-200 hover:text-emerald-600 dark:hover:text-emerald-400 hover:translate-x-0.5 w-fit"
              >
                Human Appeal
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href="https://ummahcharity.org.uk/donate"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-all duration-200 hover:text-sky-600 dark:hover:text-sky-400 hover:translate-x-0.5 w-fit"
              >
                Ummah Charity
                <ExternalLink className="h-3 w-3" />
              </a>
            </nav>
          </div>

          {/* Developer teaser */}
          <motion.div
            initial={shouldReduceMotion ? {} : { opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/70 mb-4">
              {t("about.title")}
            </h3>
            <Link
              to="/about"
              className="group flex items-start gap-4 glass rounded-2xl p-4 transition-all duration-300 hover:shadow-lg hover:shadow-primary/5 card-hover"
            >
              <div className="relative shrink-0">
                <div className="absolute -inset-1 rounded-full bg-gradient-to-br from-primary/40 to-accent/30 opacity-0 blur-md transition-opacity duration-300 group-hover:opacity-100" />
                <img
                  src="/souhib.jpeg"
                  alt={t("about.name")}
                  className="relative h-12 w-12 rounded-full object-cover ring-2 ring-primary/20 group-hover:ring-primary/40 transition-all duration-300"
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors duration-200">
                    {t("about.name")}
                  </span>
                  <span className="rounded-full bg-gradient-to-r from-primary/15 to-accent/15 px-2 py-0.5 text-[10px] font-medium text-primary">
                    {t("about.role")}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground line-clamp-2">
                  {t("about.projectDescription")}
                </p>
                <span className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-all duration-200 group-hover:opacity-100">
                  <User className="h-3 w-3" />
                  {t("nav.about")}
                  <span aria-hidden="true" className="transition-transform duration-200 group-hover:translate-x-0.5">&rarr;</span>
                </span>
              </div>
            </Link>

            {/* Social links */}
            <div className="mt-4 flex items-center gap-3">
              {[
                { href: "https://github.com/Souhib", icon: Github, label: "GitHub" },
                { href: "https://www.linkedin.com/in/souhib-trabelsi/", icon: Linkedin, label: "LinkedIn" },
                { href: "mailto:souhib.t@icloud.com", icon: Mail, label: "Email" },
              ].map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  target={link.href.startsWith("http") ? "_blank" : undefined}
                  rel={link.href.startsWith("http") ? "noopener noreferrer" : undefined}
                  aria-label={link.label}
                  className="flex h-9 w-9 items-center justify-center rounded-xl glass text-muted-foreground transition-all duration-200 hover:text-primary hover:shadow-md hover:shadow-primary/10 hover:-translate-y-0.5"
                >
                  <link.icon className="h-3.5 w-3.5" />
                </a>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Bottom bar */}
        <div className="mt-10 flex flex-col items-center gap-3 border-t border-border/30 pt-6 sm:flex-row sm:justify-between">
          <p className="text-xs text-muted-foreground/60">
            &copy; {new Date().getFullYear()} IPG &mdash; Islamic Party Games
          </p>
          <p className="flex items-center gap-1 text-xs text-muted-foreground/60">
            Made with <Heart className="h-3 w-3 text-destructive/60" aria-label="love" /> for the Ummah
          </p>
        </div>
      </div>
    </footer>
  )
}
