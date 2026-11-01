import { Link, useLocation } from "@tanstack/react-router"
import { Book, ChevronDown, LogOut, Menu, User, Users } from "lucide-react"
import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { useTranslation } from "react-i18next"
import { Lockup } from "@/components/brand"
import { autoDetectLocationByIP, loadStoredCity } from "@/components/prayer-times/CitySelector"
import { PrayerTimesNav } from "@/components/prayer-times/PrayerTimesNav"
import { Avatar } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Separator } from "@/components/ui/separator"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"
import { useAuth } from "@/providers/AuthProvider"
import { LanguageSwitch } from "./language-switch"
import { ThemeToggle } from "./theme-toggle"

/**
 * The nav of the Samar sketch: the lockup (مجلسنا │ MAJLISNA) at the reading start, the
 * five links, then the prayer chip, the language switch, the theme toggle and the
 * account. Qandil's brass rule runs under it, broken by one lozenge.
 *
 * Over the home sky it has no ground of its own until the page scrolls; everywhere else
 * it is espresso with grain (`.samar-nav`, styles/shell.css). At 1180 px and below the
 * row collapses to the lockup and a "Menu" button that opens a sheet with everything.
 */
const LINKS = [
  { to: "/", key: "nav.play" },
  { to: "/rooms", key: "nav.rooms" },
  { to: "/challenges", key: "nav.challenges" },
  { to: "/leaderboard", key: "nav.leaderboard" },
  { to: "/about", key: "nav.about" },
] as const

/** The menu sheet also offers the word of the day, after Play (the wide row keeps its five links). */
const SHEET_LINKS = [LINKS[0], { to: "/today", key: "daily.nav" }, ...LINKS.slice(1)] as const

type NavPath = (typeof SHEET_LINKS)[number]["to"]

function isCurrent(pathname: string, to: NavPath) {
  if (to === "/") return pathname === "/"
  return pathname === to || pathname.startsWith(`${to}/`)
}

/**
 * True once the page has scrolled off its very top (the nav then takes its ground). The
 * first value is read before the DOM exists; reading scrollY again in the mount effect
 * forced the first full layout inside React's commit (FP-20), and any later change comes
 * with a scroll event.
 */
function useScrolled() {
  const [scrolled, setScrolled] = useState(() => typeof window !== "undefined" && window.scrollY > 4)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])
  return scrolled
}

/** Where the nav row shows everything: the complement of the `max-[1180px]:` classes
 *  that hide it (Tailwind compiles them to `not all and (min-width: 1180px)`). */
const WIDE_NAV = "(min-width: 1180px)"

/** Whether a media query matches, following it as the viewport changes. */
function useMediaQuery(query: string) {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query)
      list.addEventListener("change", onChange)
      return () => list.removeEventListener("change", onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

/**
 * The city of the prayer times, guessed from the IP once per page load while none is
 * stored, whatever the width: on a phone no chip is mounted until the menu opens, but a
 * running game's adhan suggestion reads the stored city (use-adhan-suggestion.ts). A
 * mounted chip shares the same request, and a failed one is not repeated for 24 h
 * (CitySelector.tsx).
 */
function useCityDetection() {
  useEffect(() => {
    if (!loadStoredCity()) void autoDetectLocationByIP()
  }, [])
}

function UserMenu() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const name = user?.username ?? ""

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button type="button" data-testid="user-menu-trigger" className="nav-account">
          <Avatar name={name || "?"} size={32} aria-hidden="true" />
          <span className="name" dir="auto">
            {name}
          </span>
          <span className="sr-only">{t("nav.accountMenu")}</span>
          <ChevronDown aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[13rem]">
        {user?.email ? <DropdownMenuLabel className="truncate">{user.email}</DropdownMenuLabel> : null}
        <DropdownMenuItem asChild>
          <Link to="/profile">
            <User aria-hidden="true" />
            {t("nav.profile")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/notebook">
            <Book aria-hidden="true" />
            {t("notebook.nav")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/friends">
            <Users aria-hidden="true" />
            {t("nav.friends")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout()} className="text-ember [&_svg]:text-ember!">
          <LogOut aria-hidden="true" />
          {t("nav.logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function MenuSheet({ pathname }: { pathname: string }) {
  const { t } = useTranslation()
  const { isAuthenticated, user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const firstLinkRef = useRef<HTMLAnchorElement>(null)

  // A link inside the sheet navigates: close it when the page changes.
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {/* A Radix trigger, so closing the sheet (Escape, Close, a link) hands focus back to it */}
      <SheetTrigger asChild>
        <Button variant="secondary" size="sm" className="hidden max-[1180px]:inline-flex" iconStart={<Menu aria-hidden="true" />}>
          {t("nav.menu")}
        </Button>
      </SheetTrigger>
      <SheetContent
        side="end"
        className="gap-6"
        // open on the first page link, not on the first button Radix finds (the prayer chip)
        onOpenAutoFocus={(e) => {
          if (!firstLinkRef.current) return
          e.preventDefault()
          firstLinkRef.current.focus()
        }}
        // any link in the sheet closes it, also the one to the page already open
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("a[href]")) setOpen(false)
        }}
      >
        <div className="pe-12">
          <SheetTitle className="sr-only">{t("nav.menu")}</SheetTitle>
          <SheetDescription className="sr-only">{t("nav.mainLabel")}</SheetDescription>
          <Link to="/" aria-label={t("nav.homeLabel")} className="nav-lockup">
            <Lockup size={30} />
          </Link>
        </div>

        <nav aria-label={t("nav.mainLabel")}>
          <ul className="menu-links">
            {SHEET_LINKS.map((link, i) => (
              <li key={link.to}>
                <Link ref={i === 0 ? firstLinkRef : undefined} to={link.to} aria-current={isCurrent(pathname, link.to) ? "page" : undefined}>
                  {t(link.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="grid gap-5">
          <div>
            <p className="menu-group-label">{t("prayer.prayerTimes")}</p>
            <PrayerTimesNav align="start" className="h-11" fallbackLabel={t("prayer.chooseCity")} />
          </div>
          <div>
            <p className="menu-group-label">{t("nav.language")}</p>
            <LanguageSwitch variant="full" />
          </div>
          <div>
            <p className="menu-group-label">{t("nav.theme")}</p>
            <ThemeToggle labelled />
          </div>
        </div>

        <Separator />

        {isAuthenticated ? (
          <div className="grid gap-2">
            <p className="flex items-center gap-3 text-[15px] text-foreground">
              <Avatar name={user?.username || "?"} size={36} aria-hidden="true" />
              <span className="min-w-0 truncate font-medium" dir="auto">
                {user?.username}
              </span>
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Button asChild variant="secondary" iconStart={<User aria-hidden="true" />}>
                <Link to="/profile">{t("nav.profile")}</Link>
              </Button>
              <Button asChild variant="secondary" iconStart={<Users aria-hidden="true" />}>
                <Link to="/friends">{t("nav.friends")}</Link>
              </Button>
              <Button asChild variant="secondary" iconStart={<Book aria-hidden="true" />} className="col-span-2">
                <Link to="/notebook">{t("notebook.nav")}</Link>
              </Button>
            </div>
            <Button
              variant="danger"
              block
              iconStart={<LogOut aria-hidden="true" />}
              onClick={() => {
                logout()
                setOpen(false)
              }}
            >
              {t("nav.logout")}
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <Button asChild variant="secondary">
              <Link to="/auth/login">{t("nav.login")}</Link>
            </Button>
            <Button asChild variant="primary">
              <Link to="/auth/register">{t("nav.register")}</Link>
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

export function MainNav() {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()
  const { pathname } = useLocation()
  const resolved = useResolvedTheme()
  const scrolled = useScrolled()
  const overSky = pathname === "/" && !scrolled
  // One prayer chip per viewport (FR-11): the row's from 1180 px, the menu sheet's below.
  // The row's used to stay mounted (only CSS-hidden) on phones, a second copy of its state
  // and of its requests next to the sheet's.
  const wide = useMediaQuery(WIDE_NAV)
  useCityDetection()

  // The browser's bar takes the nav's ground in the light on screen (index.html sets
  // the first value before paint; this follows a toggle).
  useEffect(() => {
    for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
      meta.removeAttribute("media")
      meta.content = resolved === "dark" ? "#1c1611" : "#fefefc"
    }
  }, [resolved])

  return (
    <header className="samar-nav" data-over-sky={overSky}>
      <div className="samar-nav-row">
        <Link to="/" aria-label={t("nav.homeLabel")} className="nav-lockup">
          <Lockup size="var(--lockup-size)" compactOnMobile />
        </Link>

        <nav aria-label={t("nav.mainLabel")} className="nav-links max-[1180px]:hidden">
          <ul>
            {LINKS.map((link) => (
              <li key={link.to}>
                <Link to={link.to} aria-current={isCurrent(pathname, link.to) ? "page" : undefined}>
                  {t(link.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="nav-end">
          {wide ? <PrayerTimesNav /> : null}
          <LanguageSwitch className="max-[1180px]:hidden" />
          <ThemeToggle className="max-[1180px]:hidden" />
          {isAuthenticated ? (
            <div className="max-[1180px]:hidden">
              <UserMenu />
            </div>
          ) : (
            <>
              <Link to="/auth/login" className="nav-login max-[1180px]:hidden">
                {t("nav.login")}
              </Link>
              <Button asChild size="sm" variant={resolved === "dark" ? "secondary" : "primary"} className="max-[1180px]:hidden">
                <Link to="/auth/register">{t("nav.register")}</Link>
              </Button>
            </>
          )}
          <MenuSheet pathname={pathname} />
        </div>
      </div>
    </header>
  )
}
