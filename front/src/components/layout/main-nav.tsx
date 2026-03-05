import { Link, useLocation } from "@tanstack/react-router"
import { BookOpen, Globe, LogOut, Menu, Moon, Sun, Trophy, User, UserCircle, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/providers/AuthProvider"
import { useTheme } from "@/providers/ThemeProvider"
import { cn } from "@/lib/utils"
import { PrayerTimesNav } from "@/components/prayer-times/PrayerTimesNav"

function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  // Determine the effective (resolved) theme
  const effectiveTheme =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme

  const toggle = () => {
    setTheme(effectiveTheme === "light" ? "dark" : "light")
  }

  // Show Sun when in dark (click → light), Moon when in light (click → dark)
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

function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const currentLang = i18n.language?.startsWith("ar") ? "ar" : "en"

  const toggle = () => {
    const newLang = currentLang === "en" ? "ar" : "en"
    i18n.changeLanguage(newLang)
    localStorage.setItem("ipg-language", newLang)
    document.documentElement.dir = newLang === "ar" ? "rtl" : "ltr"
    document.documentElement.lang = newLang
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="flex items-center gap-1 rounded-md p-2 text-muted-foreground hover:text-primary hover:bg-secondary transition-colors"
      aria-label={`Switch to ${currentLang === "en" ? "Arabic" : "English"}`}
    >
      <Globe className="h-4 w-4" />
      <span className="text-xs font-medium">{currentLang === "en" ? "ع" : "EN"}</span>
    </button>
  )
}

export function MainNav() {
  const { t } = useTranslation()
  const { isAuthenticated, user, logout } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const navLinks = [
    { to: "/", label: t("nav.home"), icon: BookOpen },
    ...(isAuthenticated
      ? [
          { to: "/rooms" as const, label: t("nav.rooms"), icon: BookOpen },
          { to: "/leaderboard" as const, label: t("nav.leaderboard"), icon: Trophy },
          { to: "/profile" as const, label: t("nav.profile"), icon: User },
        ]
      : []),
    { to: "/about" as const, label: t("nav.about"), icon: UserCircle },
  ]

  return (
    <nav className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 font-bold text-xl text-primary">
          <BookOpen className="h-6 w-6" />
          <span>IPG</span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-6">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "text-sm font-medium transition-colors hover:text-primary",
                location.pathname === link.to ? "text-primary" : "text-muted-foreground",
              )}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Prayer times + Theme toggle + Auth buttons */}
        <div className="hidden md:flex items-center gap-3">
          <PrayerTimesNav />
          <LanguageSwitcher />
          <ThemeToggle />
          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{user?.username}</span>
              <button
                type="button"
                onClick={logout}
                className="flex items-center gap-1 text-sm text-muted-foreground hover:text-destructive transition-colors"
              >
                <LogOut className="h-4 w-4" />
                {t("nav.logout")}
              </button>
            </div>
          ) : (
            <>
              <Link
                to="/auth/login"
                className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors"
              >
                {t("nav.login")}
              </Link>
              <Link
                to="/auth/register"
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                {t("nav.register")}
              </Link>
            </>
          )}
        </div>

        {/* Mobile menu button */}
        <button
          type="button"
          className="md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t bg-background px-4 py-4 space-y-3">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="block text-sm font-medium text-muted-foreground hover:text-primary"
              onClick={() => setMobileOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <div className="flex items-center gap-2 py-1">
            <PrayerTimesNav />
          </div>
          <div className="flex items-center gap-2 py-1">
            <LanguageSwitcher />
            <ThemeToggle />
            <span className="text-xs text-muted-foreground">{t("nav.theme")}</span>
          </div>
          {isAuthenticated ? (
            <button
              type="button"
              onClick={() => {
                logout()
                setMobileOpen(false)
              }}
              className="block text-sm font-medium text-destructive"
            >
              {t("nav.logout")}
            </button>
          ) : (
            <div className="space-y-2 pt-2 border-t">
              <Link
                to="/auth/login"
                className="block text-sm font-medium text-muted-foreground"
                onClick={() => setMobileOpen(false)}
              >
                {t("nav.login")}
              </Link>
              <Link
                to="/auth/register"
                className="block text-sm font-medium text-primary"
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
