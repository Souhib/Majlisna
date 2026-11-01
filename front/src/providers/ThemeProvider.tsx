import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react"
import { loadStoredCity } from "@/components/prayer-times/CitySelector"
import { announceResolvedTheme, type ResolvedTheme } from "@/hooks/use-resolved-theme"
import { dur } from "@/lib/motion"
import {
  clearSkyRecord,
  lightAt,
  NO_SKY,
  sameSkyStatus,
  serializeSkySchedule,
  skySchedule,
  skyStatus,
  type SkySchedule,
  type SkyStatus,
  type SkyTurn,
  writeSkyRecord,
} from "@/lib/sky-light"
import { canViewTransition, withViewTransition } from "@/lib/view-transition"

/**
 * The light of the page (DESIGN.md §1, §7). Four choices:
 *
 * - "light" / "dark": the afternoon or the night, always. An explicit choice wins.
 * - "system": the device's light (the default, until the player chooses).
 * - "sky" (Follow the sky): the afternoon from sunrise to Maghrib, the night from Maghrib
 *   to sunrise, computed on the device from the stored prayer-times city (lib/sky-light.ts).
 *   Without a stored city it follows the device's light and says so (the theme control);
 *   it never asks the network or the location API by itself.
 *
 * The class drives Tailwind's `dark:` variant; `data-theme` drives the Samar tokens in
 * index.css (and lets a section re-theme its subtree with its own data-theme). index.html
 * applies the same rule before first paint (for the sky, from the week of turns stored in
 * `majlisna-sky-light`), so there is no flash.
 *
 * When the sky turns with the page open, the app's one ceremony plays: the page crossfades
 * to the new light through a view transition at --dur-ceremony (index.css,
 * `:root[data-sky-turn]`). Never while a game is on the table (a game route with no
 * colophon yet): the turn waits for the colophon or the lobby, then a ceremony's length
 * more so the colophon lands first. A view transition takes the pointer for its whole
 * length (every press lands on <html>), so the ceremony also waits for a quiet moment (no
 * press, key, wheel or touch for SKY_QUIET_MS), and a press during it ends it at once. At
 * once under reduced motion, in a hidden tab, without view transitions, and whenever the
 * light changes for another reason than the sky turning (a page load, a choice, a new city,
 * the device's light).
 */
export type Theme = "light" | "dark" | "system" | "sky"

const THEMES: readonly Theme[] = ["light", "dark", "system", "sky"]
const THEME_KEY = "majlisna-theme"

/** How often the sky choice looks again: a city stored meanwhile (the prayer chip, another tab), a timer a sleeping device delayed. */
export const SKY_CHECK_MS = 30_000
/** While a turn waits (a game on the table, a page in use), how often it looks again. */
export const SKY_HOLD_CHECK_MS = 1_000
/** The ceremony starts only once the page has been still this long (no press, key, wheel or touch). */
export const SKY_QUIET_MS = 2_000
/** What counts as using the page. */
const INPUT_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const
/** setTimeout's ceiling (2³¹−1 ms); a turn is never further than a day away anyway. */
const MAX_TIMEOUT_MS = 2_147_483_647

export type { SkyStatus } from "@/lib/sky-light"

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  /** The sky's status while "sky" is the choice; NO_SKY otherwise. */
  sky: SkyStatus
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

function readStoredTheme(fallback: Theme): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return THEMES.includes(stored as Theme) ? (stored as Theme) : fallback
  } catch {
    return fallback
  }
}

function deviceLight(): ResolvedTheme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function reducedMotion(): boolean {
  return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

function screenLight(): ResolvedTheme | null {
  const light = document.documentElement.dataset.theme
  return light === "light" || light === "dark" ? light : null
}

/**
 * Finish at once the transitions a change of light has just started. The whole page restyles,
 * and every `transition-colors` on it (the nav's links, the buttons, the prayer chip, the code
 * tiles) would run from the old light to the new one: tens of non-composited colour transitions
 * on the main thread, and under the sky's ceremony controls still fading from the afternoon
 * inside the crossfade. `getAnimations()` brings the style up to date, which starts them
 * (pending until the next frame); a transition already running before the change, and every
 * other animation, is left alone.
 */
function finishLightTransitions() {
  for (const animation of document.getAnimations?.() ?? []) {
    if ("transitionProperty" in animation && animation.pending) animation.finish()
  }
}

/**
 * Put a light on <html> (class + data-theme), then tell every reader in this same task. A
 * change of light ends the colour transitions it starts (`finishLightTransitions`): the
 * tokens' at once, then, a microtask later, those of React's re-render of the light's readers
 * (`useResolvedTheme` is a synchronous store: inside the ceremony's `flushSync`, or at the end
 * of the effect, its commit comes first), e.g. the Register button's variant. Both passes run
 * before the browser captures the new light. The same light again (a page load after the
 * pre-paint script) asks the style for nothing.
 */
function applyLight(light: ResolvedTheme) {
  const root = document.documentElement
  const changed = root.dataset.theme !== light || !root.classList.contains(light)
  root.classList.remove("light", "dark")
  root.classList.add(light)
  root.dataset.theme = light
  announceResolvedTheme()
  if (!changed) return
  finishLightTransitions()
  queueMicrotask(finishLightTransitions)
}

/**
 * End the ceremony now: finish the view transition's own animations (on its pseudo-elements),
 * so the next press reaches the page. The new light is already in place under them.
 */
function finishSkyCeremony() {
  for (const animation of document.getAnimations?.() ?? []) {
    const pseudo = (animation.effect as KeyframeEffect | null)?.pseudoElement
    if (pseudo?.startsWith("::view-transition")) animation.finish()
  }
}

/**
 * A game is on the table: a game route whose end is not on screen yet. The four game
 * pages mark their colophon's title `data-colophon-title` (their usePhaseFocus target).
 */
function isTableBusy(): boolean {
  return window.location.pathname.startsWith("/game/") && !document.querySelector("[data-colophon-title]")
}

function placeOf(city: ReturnType<typeof loadStoredCity>) {
  return city && Number.isFinite(city.lat) && Number.isFinite(city.lng) ? city : null
}

/**
 * How a light is put on screen: "now" (a page load, a choice, the device's light without a
 * city), "gentle" (no ceremony, but never under a game: a new city, a tab shown again) or
 * "ceremony" (the sky turned while the page was open).
 */
type How = "now" | "gentle" | "ceremony"
type Cause = "now" | "tick" | "gentle"

/** The "sky" choice at work: one per provider while it is chosen. */
class SkyFollower {
  private schedule: SkySchedule | null = null
  private scheduleKey = ""
  private written: string | null = null
  private lastCity: string | null | undefined = undefined
  private turning: ResolvedTheme | null = null
  private turnTimer: ReturnType<typeof setTimeout> | undefined
  private holdTimer: ReturnType<typeof setInterval> | undefined
  private settleTimer: ReturnType<typeof setTimeout> | undefined
  private checkTimer: ReturnType<typeof setInterval> | undefined
  private media: MediaQueryList | undefined
  private lastInputAt = Number.NEGATIVE_INFINITY
  private waitedForTable = false
  private stopped = false

  private readonly onStatus: (status: SkyStatus) => void

  constructor(onStatus: (status: SkyStatus) => void) {
    this.onStatus = onStatus
  }

  private readonly onVisible = () => {
    if (document.visibilityState === "visible") this.evaluate("gentle")
  }
  private readonly onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === "majlisna-city" || event.key === "majlisna-coordinates") this.evaluate("gentle")
  }
  private readonly onDevice = () => this.evaluate("gentle")
  private readonly onCheck = () => this.evaluate("tick")
  private readonly onInput = (event: Event) => {
    this.lastInputAt = Date.now()
    // the press itself landed on <html>; the next one reaches the page
    if (event.type === "pointerdown" && this.turning) finishSkyCeremony()
  }

  start() {
    this.evaluate("now")
    this.checkTimer = setInterval(this.onCheck, SKY_CHECK_MS)
    document.addEventListener("visibilitychange", this.onVisible)
    window.addEventListener("storage", this.onStorage)
    this.media = window.matchMedia?.("(prefers-color-scheme: dark)")
    this.media?.addEventListener?.("change", this.onDevice)
    for (const type of INPUT_EVENTS) window.addEventListener(type, this.onInput, { capture: true, passive: true })
  }

  stop() {
    this.stopped = true
    clearInterval(this.checkTimer)
    clearTimeout(this.turnTimer)
    this.clearHold()
    document.removeEventListener("visibilitychange", this.onVisible)
    window.removeEventListener("storage", this.onStorage)
    this.media?.removeEventListener?.("change", this.onDevice)
    for (const type of INPUT_EVENTS) window.removeEventListener(type, this.onInput, { capture: true })
  }

  private evaluate(cause: Cause) {
    if (this.stopped) return
    const now = Date.now()
    const city = loadStoredCity()
    const place = placeOf(city)
    const cityKey = place ? `${place.lat},${place.lng}` : null
    const key = cityKey ? `${cityKey}|${new Date(now).toDateString()}` : ""

    // adhan runs again only for a new city, a new day, or a schedule used up
    if (!place) this.schedule = null
    else if (key !== this.scheduleKey || !this.schedule || lightAt(this.schedule, now) === null) this.schedule = skySchedule(place, now)
    this.scheduleKey = key
    this.store(this.schedule)

    const status = skyStatus(place, now, this.schedule)
    const { light, next } = status
    this.onStatus(status)

    const cityChanged = this.lastCity !== undefined && cityKey !== this.lastCity
    this.lastCity = cityKey
    const how: How = cause === "now" || !light ? "now" : cause === "tick" && !cityChanged ? "ceremony" : "gentle"
    this.settle(light ?? deviceLight(), how)
    this.armTurn(next, now)
  }

  /** The week ahead for the pre-paint script, written only when it changes. */
  private store(schedule: SkySchedule | null) {
    const serialized = schedule ? serializeSkySchedule(schedule) : null
    if (serialized === this.written) return
    this.written = serialized
    if (schedule) writeSkyRecord(schedule)
    else clearSkyRecord()
  }

  private settle(target: ResolvedTheme, how: How) {
    if (this.turning === target) return
    if (screenLight() === target) {
      this.clearHold()
      return
    }
    if (how !== "now") {
      if (isTableBusy()) {
        this.waitedForTable = true
        this.hold()
        return
      }
      // the colophon is landing: the settle timer turns the light after it
      if (this.settleTimer !== undefined) return
    }
    if (how === "ceremony" && !reducedMotion() && document.visibilityState !== "hidden" && canViewTransition()) {
      // never in the middle of an interaction: the transition would take the next press
      if (Date.now() - this.lastInputAt < SKY_QUIET_MS) {
        this.hold()
        return
      }
      this.clearHold()
      this.ceremony(target)
      return
    }
    this.clearHold()
    applyLight(target)
  }

  /** The app's one ceremony: a root crossfade at --dur-ceremony (index.css, `:root[data-sky-turn]`). */
  private ceremony(target: ResolvedTheme) {
    const root = document.documentElement
    this.turning = target
    root.setAttribute("data-sky-turn", "")
    void withViewTransition(() => applyLight(target)).then(() => {
      root.removeAttribute("data-sky-turn")
      this.turning = null
    })
  }

  /**
   * Look again every SKY_HOLD_CHECK_MS: once the game has left the table, wait a ceremony's
   * length more for the colophon to land; a page in use is simply looked at again.
   */
  private hold() {
    if (this.holdTimer !== undefined) return
    this.holdTimer = setInterval(() => {
      if (isTableBusy()) {
        this.waitedForTable = true
        return
      }
      clearInterval(this.holdTimer)
      this.holdTimer = undefined
      if (!this.waitedForTable) {
        this.evaluate("tick")
        return
      }
      this.waitedForTable = false
      this.settleTimer = setTimeout(() => {
        this.settleTimer = undefined
        this.evaluate("tick")
      }, dur.ceremony * 1000)
    }, SKY_HOLD_CHECK_MS)
  }

  private clearHold() {
    clearInterval(this.holdTimer)
    this.holdTimer = undefined
    clearTimeout(this.settleTimer)
    this.settleTimer = undefined
    this.waitedForTable = false
  }

  private armTurn(next: SkyTurn | null, now: number) {
    clearTimeout(this.turnTimer)
    if (!next) return
    this.turnTimer = setTimeout(this.onCheck, Math.min(Math.max(0, next.at - now), MAX_TIMEOUT_MS))
  }
}

interface ThemeProviderProps {
  children: ReactNode
  defaultTheme?: Theme
}

export function ThemeProvider({ children, defaultTheme = "system" }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme(defaultTheme))
  const [sky, setSky] = useState<SkyStatus>(NO_SKY)

  useEffect(() => {
    if (theme === "sky") {
      const follower = new SkyFollower((status) => setSky((prev) => (sameSkyStatus(prev, status) ? prev : status)))
      follower.start()
      return () => follower.stop()
    }
    clearSkyRecord()
    setSky(NO_SKY)
    if (theme !== "system") {
      applyLight(theme)
      return
    }
    applyLight(deviceLight())
    const media = window.matchMedia?.("(prefers-color-scheme: dark)")
    const onChange = () => applyLight(deviceLight())
    media?.addEventListener?.("change", onChange)
    return () => media?.removeEventListener?.("change", onChange)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // blocked storage: the choice holds for this visit only
    }
    setThemeState(next)
  }, [])

  const value = useMemo(() => ({ theme, setTheme, sky }), [theme, setTheme, sky])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return context
}

/**
 * The sky's next turn while "Follow the sky" is the choice and a city is stored; null
 * otherwise, and outside a provider (a component rendered on its own in a test).
 */
export function useSkyTurn(): SkyTurn | null {
  const context = useContext(ThemeContext)
  return context?.theme === "sky" ? context.sky.next : null
}
