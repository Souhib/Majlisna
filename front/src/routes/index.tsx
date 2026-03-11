import { createFileRoute, Link } from "@tanstack/react-router"
import { motion } from "motion/react"
import { BookOpen, ExternalLink, Grid2x2, Heart, Shield, Users } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/providers/AuthProvider"

const charities = [
  {
    name: "Human Appeal",
    url: "https://humanappeal.org.uk/donate",
    description: "home.charity.humanAppealDesc",
    color: "from-emerald-500/15 to-teal-500/15",
    borderColor: "border-emerald-500/20 hover:border-emerald-500/40",
    textColor: "text-emerald-700 dark:text-emerald-400",
    btnColor: "bg-emerald-600 hover:bg-emerald-700 text-white",
  },
  {
    name: "Ummah Charity",
    url: "https://ummahcharity.org.uk/donate",
    description: "home.charity.ummahCharityDesc",
    color: "from-sky-500/15 to-indigo-500/15",
    borderColor: "border-sky-500/20 hover:border-sky-500/40",
    textColor: "text-sky-700 dark:text-sky-400",
    btnColor: "bg-sky-600 hover:bg-sky-700 text-white",
  },
] as const

export const Route = createFileRoute("/")({
  component: HomePage,
})

function HomePage() {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()

  return (
    <div className="relative mx-auto max-w-7xl px-4 py-20">
      {/* Mesh gradient background */}
      <div className="pointer-events-none absolute inset-0 -top-20 overflow-hidden">
        <div className="absolute left-1/4 top-0 h-[500px] w-[500px] rounded-full bg-primary/8 blur-[120px]" />
        <div className="absolute right-1/4 top-20 h-[400px] w-[400px] rounded-full bg-accent/8 blur-[100px]" />
        <div className="absolute left-1/2 top-40 h-[300px] w-[300px] -translate-x-1/2 rounded-full bg-primary/5 blur-[80px]" />
      </div>

      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative text-center"
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="inline-flex items-center gap-2 rounded-full border border-border/30 bg-primary/10 px-5 py-2 mb-8 shadow-sm"
        >
          <BookOpen className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold text-primary tracking-wide">Learn & Play</span>
        </motion.div>

        <h1 className="text-7xl font-extrabold tracking-tighter gradient-text sm:text-8xl animate-scale-in">
          {t("home.title")}
        </h1>

        <p className="mt-8 text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed animate-slide-up">
          {t("home.subtitle")}
        </p>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-12 flex items-center justify-center gap-4"
        >
          {isAuthenticated ? (
            <>
              <Link
                to="/rooms/create"
                className="rounded-2xl bg-gradient-to-r from-primary to-primary/90 px-8 py-3.5 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
              >
                {t("home.createRoom")}
              </Link>
              <Link
                to="/rooms"
                className="rounded-2xl border border-border/50 bg-secondary/80 px-8 py-3.5 text-sm font-semibold text-secondary-foreground shadow-sm hover:bg-secondary hover:-translate-y-0.5 hover:shadow-md transition-all duration-200"
              >
                {t("home.joinRoom")}
              </Link>
            </>
          ) : (
            <>
              <Link
                to="/auth/register"
                className="rounded-2xl bg-gradient-to-r from-primary to-primary/90 px-8 py-3.5 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
              >
                {t("home.playNow")}
              </Link>
              <Link
                to="/auth/login"
                className="rounded-2xl border border-border/50 bg-secondary/80 px-8 py-3.5 text-sm font-semibold text-secondary-foreground shadow-sm hover:bg-secondary hover:-translate-y-0.5 hover:shadow-md transition-all duration-200"
              >
                {t("nav.login")}
              </Link>
            </>
          )}
        </motion.div>
      </motion.div>

      {/* Games Section */}
      <div className="relative mt-20 grid gap-8 md:grid-cols-2 max-w-4xl mx-auto">
        {/* Undercover */}
        <motion.div
          initial={{ opacity: 0, y: 25 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="glass rounded-2xl border border-border/30 p-8 card-hover hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="rounded-2xl bg-primary/10 p-3">
              <Shield className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight">{t("games.undercover.name")}</h2>
          </div>
          <p className="text-muted-foreground leading-relaxed">
            {t("games.undercover.description")}
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              {t("games.undercover.roles.civilian")}
            </span>
            <span className="rounded-full bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive">
              {t("games.undercover.roles.undercover")}
            </span>
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              {t("games.undercover.roles.mrWhite")}
            </span>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm text-muted-foreground">
            <Users className="h-4 w-4" />
            <span className="font-mono tabular-nums">3-12</span>
            <span>players</span>
          </div>
        </motion.div>

        {/* Codenames */}
        <motion.div
          initial={{ opacity: 0, y: 25 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.65 }}
          className="glass rounded-2xl border border-border/30 p-8 card-hover hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="rounded-2xl bg-accent/10 p-3">
              <Grid2x2 className="h-6 w-6 text-accent" />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight">{t("games.codenames.name")}</h2>
          </div>
          <p className="text-muted-foreground leading-relaxed">
            {t("games.codenames.description")}
          </p>
          <div className="mt-6 flex gap-2">
            <span className="rounded-full bg-red-100 dark:bg-red-900/30 px-3 py-1 text-xs font-medium text-red-700 dark:text-red-400">
              {t("games.codenames.teams.red")}
            </span>
            <span className="rounded-full bg-blue-100 dark:bg-blue-900/30 px-3 py-1 text-xs font-medium text-blue-700 dark:text-blue-400">
              {t("games.codenames.teams.blue")}
            </span>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-sm text-muted-foreground">
            <Users className="h-4 w-4" />
            <span className="font-mono tabular-nums">4-10</span>
            <span>players</span>
          </div>
        </motion.div>
      </div>

      {/* Support Section */}
      <motion.div
        initial={{ opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.8 }}
        className="relative mt-24 max-w-4xl mx-auto"
      >
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-4 py-1.5 mb-4">
            <Heart className="h-3.5 w-3.5 text-accent" />
            <span className="text-xs font-semibold text-accent tracking-wide">{t("home.charity.badge")}</span>
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight gradient-text sm:text-4xl">
            {t("home.charity.title")}
          </h2>
          <p className="mt-3 text-muted-foreground max-w-lg mx-auto">
            {t("home.charity.subtitle")}
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {charities.map((charity) => (
            <a
              key={charity.name}
              href={charity.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`group flex flex-col glass rounded-2xl border ${charity.borderColor} p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl`}
            >
              <div className={`inline-flex w-fit rounded-xl bg-gradient-to-br ${charity.color} p-3 mb-4`}>
                <Heart className={`h-5 w-5 ${charity.textColor}`} />
              </div>
              <h3 className="text-lg font-extrabold tracking-tight mb-2">{charity.name}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed mb-5 flex-1">
                {t(charity.description)}
              </p>
              <span className={`inline-flex items-center gap-2 rounded-xl ${charity.btnColor} px-5 py-2.5 text-sm font-semibold shadow-md transition-all duration-200 group-hover:shadow-lg group-hover:gap-3 self-start`}>
                {t("home.charity.donate")}
                <ExternalLink className="h-3.5 w-3.5" />
              </span>
            </a>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
