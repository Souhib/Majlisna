import { Link, useLocation } from "@tanstack/react-router"
import { BookOpen, Check, ChevronDown, Flame, LogOut, Menu, Moon, Sun, Trophy, User, Users, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/providers/AuthProvider"
import { useTheme } from "@/providers/ThemeProvider"
import { cn } from "@/lib/utils"
import { PrayerTimesNav } from "@/components/prayer-times/PrayerTimesNav"

function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  const effectiveTheme =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme

  const toggle = () => {
    setTheme(effectiveTheme === "light" ? "dark" : "light")
  }

  const Icon = effectiveTheme === "dark" ? Sun : Moon

  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-md p-2 text-muted-foreground hover:text-primary hover:bg-secondary transition-colors"
      aria-label={`Switch to ${effectiveTheme === "light" ? "dark" : "light"} mode`}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}

const LANGUAGES = [
  { code: "en", fullName: "English", flag: "\u{1F1EC}\u{1F1E7}", dir: "ltr" },
  { code: "fr", fullName: "Fran\u00E7ais", flag: "\u{1F1EB}\u{1F1F7}", dir: "ltr" },
  { code: "ar", fullName: "\u0627\u0644\u0639\u0631\u0628\u064A\u0629", flag: "\u{1F1E6}\u{1F1EA}", dir: "rtl" },
] as const

function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const currentLang = LANGUAGES.find((l) => l.code === (i18n.language?.startsWith("ar") ? "ar" : i18n.language?.startsWith("fr") ? "fr" : "en")) || LANGUAGES[0]

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  const changeLanguage = (langCode: string) => {
    const lang = LANGUAGES.find((l) => l.code === langCode)
    if (!lang) return
    i18n.changeLanguage(lang.code)
    localStorage.setItem("ipg-language", lang.code)
    document.documentElement.dir = lang.dir
    document.documentElement.lang = lang.code
    setOpen(false)
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-muted-foreground hover:text-primary hover:bg-secondary transition-colors"
        aria-label="Switch language"
      >
        <span aria-hidden="true">{currentLang.flag}</span>
        <span lang={currentLang.code}>{currentLang.fullName}</span>
        <ChevronDown className="h-3 w-3 opacity-50" />
      </button>

      {open && (
        <div className="absolute end-0 top-full mt-2 w-44 rounded-xl border bg-popover p-1.5 shadow-lg z-50">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              onClick={() => changeLanguage(lang.code)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                i18n.language?.startsWith(lang.code)
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary",
              )}
            >
              <span aria-hidden="true">{lang.flag}</span>
              <span lang={lang.code} className="flex-1 text-start">{lang.fullName}</span>
              {i18n.language?.startsWith(lang.code) && <Check className="h-4 w-4 text-primary" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function UserMenu() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  const initial = user?.username?.charAt(0).toUpperCase() ?? "?"

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-full bg-primary/10 pe-2.5 ps-0.5 py-0.5 text-sm font-medium text-primary hover:bg-primary/20 transition-colors"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
          {initial}
        </span>
        <span className="max-w-[80px] truncate">{user?.username}</span>
        <ChevronDown className="h-3 w-3 opacity-60" />
      </button>

      {open && (
        <div className="absolute end-0 top-full mt-2 w-48 rounded-xl border bg-popover p-1.5 shadow-lg z-50">
          <Link
            to="/profile"
            className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            onClick={() => setOpen(false)}
          >
            <User className="h-4 w-4" />
            {t("nav.profile")}
          </Link>
          <Link
            to="/friends"
            className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            onClick={() => setOpen(false)}
          >
            <Users className="h-4 w-4" />
            {t("nav.friends")}
          </Link>
          <div className="my-1 border-t" />
          <button
            type="button"
            onClick={() => {
              logout()
              setOpen(false)
            }}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            {t("nav.logout")}
          </button>
        </div>
      )}
    </div>
  )
}

export function MainNav() {
  const { t } = useTranslation()
  const { isAuthenticated, logout } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const centerLinks = isAuthenticated
    ? [
        { to: "/rooms" as const, label: t("nav.rooms"), icon: BookOpen },
        { to: "/challenges" as const, label: t("nav.challenges"), icon: Flame },
        { to: "/leaderboard" as const, label: t("nav.leaderboard"), icon: Trophy },
      ]
    : []

  return (
    <nav className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-md">
      {/* 3-column grid: logo | center nav | actions — center column is truly centered */}
      <div className="mx-auto grid h-14 max-w-7xl grid-cols-[1fr_auto_1fr] items-center px-4">
        {/* Left — Logo */}
        <div className="flex items-center">
          <Link to="/" className="flex items-center gap-2 font-bold text-lg text-primary">
            <BookOpen className="h-5 w-5" />
            <span>IPG</span>
          </Link>
        </div>

        {/* Center — Nav links */}
        <div className="hidden md:flex items-center gap-1">
          {centerLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                location.pathname === link.to || location.pathname.startsWith(link.to + "/")
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-primary hover:bg-secondary",
              )}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Right — Actions */}
        <div className="hidden md:flex items-center justify-end gap-1">
          <PrayerTimesNav />
          <LanguageSwitcher />
          <ThemeToggle />
          {isAuthenticated ? (
            <UserMenu />
          ) : (
            <div className="flex items-center gap-2 ms-1">
              <Link
                to="/auth/login"
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-primary hover:bg-secondary transition-colors"
              >
                {t("nav.login")}
              </Link>
              <Link
                to="/auth/register"
                className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                {t("nav.register")}
              </Link>
            </div>
          )}
        </div>

        {/* Mobile menu button */}
        <div className="flex items-center justify-end md:hidden col-start-3">
          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t bg-background px-4 py-3 space-y-1">
          {isAuthenticated && (
            <>
              {[
                { to: "/rooms" as const, label: t("nav.rooms"), icon: BookOpen },
                { to: "/challenges" as const, label: t("nav.challenges"), icon: Flame },
                { to: "/leaderboard" as const, label: t("nav.leaderboard"), icon: Trophy },
                { to: "/profile" as const, label: t("nav.profile"), icon: User },
                { to: "/friends" as const, label: t("nav.friends"), icon: Users },
              ].map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    location.pathname === link.to
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-primary hover:bg-secondary",
                  )}
                  onClick={() => setMobileOpen(false)}
                >
                  <link.icon className="h-4 w-4" />
                  {link.label}
                </Link>
              ))}
            </>
          )}
          <div className="flex items-center gap-1 py-1">
            <PrayerTimesNav />
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
          {isAuthenticated ? (
            <>
              <div className="border-t my-1" />
              <button
                type="button"
                onClick={() => {
                  logout()
                  setMobileOpen(false)
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors"
              >
                <LogOut className="h-4 w-4" />
                {t("nav.logout")}
              </button>
            </>
          ) : (
            <div className="border-t my-1 pt-2 flex gap-2">
              <Link
                to="/auth/login"
                className="flex-1 rounded-lg border px-3 py-2 text-center text-sm font-medium text-muted-foreground hover:text-primary transition-colors"
                onClick={() => setMobileOpen(false)}
              >
                {t("nav.login")}
              </Link>
              <Link
                to="/auth/register"
                className="flex-1 rounded-lg bg-primary px-3 py-2 text-center text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                onClick={() => setMobileOpen(false)}
              >
                {t("nav.register")}
              </Link>
            </div>
          )}
        </div>
      )}
    </nav>
  )
}
