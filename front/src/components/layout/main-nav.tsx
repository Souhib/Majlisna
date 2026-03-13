import { Link, useLocation } from "@tanstack/react-router"
import { BookOpen, Check, ChevronDown, Flame, LogOut, Menu, Moon, Sun, User, Users, X } from "lucide-react"
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
      className="rounded-xl p-2 text-muted-foreground hover:text-primary hover:bg-glow transition-all duration-200"
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
        className="flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-sm font-medium text-muted-foreground hover:text-primary hover:bg-glow transition-all duration-200"
        aria-label="Switch language"
      >
        <span aria-hidden="true">{currentLang.flag}</span>
        <span lang={currentLang.code}>{currentLang.fullName}</span>
        <ChevronDown className={cn("h-3 w-3 opacity-50 transition-transform duration-200", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute end-0 top-full mt-2 w-44 glass rounded-2xl p-1.5 shadow-xl shadow-black/5 animate-scale-in z-50">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              onClick={() => changeLanguage(lang.code)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-all duration-150",
                i18n.language?.startsWith(lang.code)
                  ? "bg-primary/10 text-primary font-medium"
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
        className="flex items-center gap-1.5 rounded-full bg-primary/10 pe-3 ps-0.5 py-0.5 text-sm font-medium text-primary hover:bg-primary/15 transition-all duration-200"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/80 text-xs font-bold text-primary-foreground ring-2 ring-primary/20">
          {initial}
        </span>
        <span className="max-w-[80px] truncate">{user?.username}</span>
        <ChevronDown className={cn("h-3 w-3 opacity-60 transition-transform duration-200", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute end-0 top-full mt-2 w-48 glass rounded-2xl p-1.5 shadow-xl shadow-black/5 animate-scale-in z-50">
          <Link
            to="/profile"
            className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-150"
            onClick={() => setOpen(false)}
          >
            <User className="h-4 w-4" />
            {t("nav.profile")}
          </Link>
          <Link
            to="/friends"
            className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-150"
            onClick={() => setOpen(false)}
          >
            <Users className="h-4 w-4" />
            {t("nav.friends")}
          </Link>
          <div className="my-1 border-t border-border/50" />
          <button
            type="button"
            onClick={() => {
              logout()
              setOpen(false)
            }}
            className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-destructive hover:bg-destructive/10 transition-all duration-150"
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
  const navRef = useRef<HTMLElement>(null)

  // Close mobile menu on outside click
  useEffect(() => {
    if (!mobileOpen) return
    const handler = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setMobileOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [mobileOpen])

  const centerLinks = isAuthenticated
    ? [
        { to: "/rooms" as const, label: t("nav.rooms"), icon: BookOpen },
        { to: "/challenges" as const, label: t("nav.challenges"), icon: Flame },
      ]
    : []

  return (
    <nav ref={navRef} className="sticky top-0 z-50 border-b border-border/50 bg-background/70 backdrop-blur-xl">
      {/* Gradient bottom border accent */}
      <div
        className="absolute bottom-0 inset-x-0 h-px"
        style={{
          background: "linear-gradient(90deg, transparent, var(--gradient-start) 20%, var(--gradient-end) 80%, transparent)",
          opacity: 0.2,
        }}
      />

      {/* 3-column grid: logo | center nav | actions */}
      <div className="mx-auto grid h-14 max-w-7xl grid-cols-[1fr_auto_1fr] items-center px-4">
        {/* Left — Logo */}
        <div className="flex items-center">
          <Link to="/" className="flex items-center gap-2.5 font-bold text-lg group">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/80 text-primary-foreground transition-transform duration-200 group-hover:scale-105">
              <BookOpen className="h-4 w-4" />
            </div>
            <span className="gradient-text font-extrabold tracking-tight">IPG</span>
          </Link>
        </div>

        {/* Center — Nav links */}
        <div className="hidden md:flex items-center gap-1">
          {centerLinks.map((link) => {
            const isActive = location.pathname === link.to || location.pathname.startsWith(link.to + "/")
            return (
              <Link
                key={link.to}
                to={link.to}
                className={cn(
                  "relative rounded-xl px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
                  isActive
                    ? "text-primary"
                    : "text-muted-foreground hover:text-primary hover:bg-glow",
                )}
              >
                {link.label}
                {/* Animated active indicator */}
                {isActive && (
                  <span className="absolute inset-x-2 -bottom-[calc(0.5rem+1px)] h-0.5 rounded-full bg-gradient-to-r from-primary to-accent" />
                )}
              </Link>
            )
          })}
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
                className="rounded-xl px-3.5 py-1.5 text-sm font-medium text-muted-foreground hover:text-primary hover:bg-glow transition-all duration-200"
              >
                {t("nav.login")}
              </Link>
              <Link
                to="/auth/register"
                className="rounded-xl bg-gradient-to-r from-primary to-primary/90 px-4 py-1.5 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg hover:shadow-primary/30 hover:-translate-y-px transition-all duration-200"
              >
                {t("nav.register")}
              </Link>
            </div>
          )}
        </div>

        {/* Mobile: prayer times + menu button */}
        <div className="flex items-center justify-end gap-1 md:hidden col-start-3">
          <PrayerTimesNav />
          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
            className="rounded-xl p-2 text-muted-foreground hover:text-primary hover:bg-glow transition-all duration-200"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-border/50 bg-background/95 backdrop-blur-xl px-4 py-3 space-y-1 animate-slide-up">
          {isAuthenticated && (
            <>
              {[
                { to: "/rooms" as const, label: t("nav.rooms"), icon: BookOpen },
                { to: "/challenges" as const, label: t("nav.challenges"), icon: Flame },
                { to: "/profile" as const, label: t("nav.profile"), icon: User },
                { to: "/friends" as const, label: t("nav.friends"), icon: Users },
              ].map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={cn(
                    "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150",
                    location.pathname === link.to
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-primary hover:bg-glow",
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
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
          {isAuthenticated ? (
            <>
              <div className="border-t border-border/50 my-1" />
              <button
                type="button"
                onClick={() => {
                  logout()
                  setMobileOpen(false)
                }}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium text-destructive hover:bg-destructive/10 transition-all duration-150"
              >
                <LogOut className="h-4 w-4" />
                {t("nav.logout")}
              </button>
            </>
          ) : (
            <div className="border-t border-border/50 my-1 pt-2 flex gap-2">
              <Link
                to="/auth/login"
                className="flex-1 rounded-xl border border-border/50 px-3 py-2.5 text-center text-sm font-medium text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-200"
                onClick={() => setMobileOpen(false)}
              >
                {t("nav.login")}
              </Link>
              <Link
                to="/auth/register"
                className="flex-1 rounded-xl bg-gradient-to-r from-primary to-primary/90 px-3 py-2.5 text-center text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 transition-all duration-200"
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
