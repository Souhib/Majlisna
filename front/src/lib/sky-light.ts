import { CalculationMethod, Coordinates, PrayerTimes } from "adhan"

/**
 * "Follow the sky" (DESIGN.md §7): the afternoon light from sunrise to Maghrib, the night
 * from Maghrib to sunrise, computed on the device from the stored prayer-times city with
 * the prayer times' own method (adhan, Muslim World League, as hooks/use-prayer-times.ts).
 * Nothing here asks the network or the location API.
 *
 * The pre-paint script in index.html cannot run adhan, so ThemeProvider stores the light
 * and the week of turns ahead (`majlisna-sky-light`) and the script walks them: a page
 * opened days later still opens in the sky's light, and one opened after the last turn
 * kept (a week away) falls back to the device's light until the app has looked again.
 */

export type SkyLight = "light" | "dark"

/** A turn of the light: from `at` (ms since the epoch) the page is in `light`. */
export interface SkyTurn {
  at: number
  light: SkyLight
}

/** The light now, and the turns after it, in order and alternating. */
export interface SkySchedule {
  light: SkyLight
  turns: SkyTurn[]
}

/** localStorage: `{"light":"light","turns":[[<ms>,"dark"],[<ms>,"light"],…]}`, read by index.html. */
export const SKY_LIGHT_KEY = "majlisna-sky-light"
/** How many days of turns are kept ahead for the pre-paint script. */
export const SKY_SCHEDULE_DAYS = 7
/** The other sky is fetched this long before the light turns (the home page only). */
export const SKY_PRELOAD_LEAD_MS = 10 * 60_000

const DAY_MS = 24 * 60 * 60_000

function isLight(value: unknown): value is SkyLight {
  return value === "light" || value === "dark"
}

function validInstant(date: Date | undefined): number | null {
  const at = date?.getTime()
  return typeof at === "number" && Number.isFinite(at) ? at : null
}

/**
 * The sky's light at `now` and its turns for the next `days` days, or null where the sky
 * has no turn in that time (a polar night or day) or the coordinates are not a place.
 * Sunrise turns it to the afternoon, Maghrib to the night.
 */
export function skySchedule(coords: { lat: number; lng: number }, now: number, days = SKY_SCHEDULE_DAYS): SkySchedule | null {
  if (!Number.isFinite(coords.lat) || !Number.isFinite(coords.lng)) return null
  const place = new Coordinates(coords.lat, coords.lng)
  const params = CalculationMethod.MuslimWorldLeague()
  const events: SkyTurn[] = []
  // From the day before (the city's date may be behind the device's) to a week ahead
  for (let d = -1; d <= days; d++) {
    const date = new Date(now + d * DAY_MS)
    const times = new PrayerTimes(place, date, params)
    const sunrise = validInstant(times.sunrise)
    const maghrib = validInstant(times.maghrib)
    if (sunrise !== null) events.push({ at: sunrise, light: "light" })
    if (maghrib !== null) events.push({ at: maghrib, light: "dark" })
  }
  events.sort((a, b) => a.at - b.at)

  let light: SkyLight | null = null
  const turns: SkyTurn[] = []
  for (const event of events) {
    if (event.at <= now) {
      light = event.light
      continue
    }
    // the light before the first turn ahead, when the window holds no earlier one
    if (light === null) light = event.light === "light" ? "dark" : "light"
    const last = turns.at(-1)?.light ?? light
    if (event.light !== last && event.at > (turns.at(-1)?.at ?? now)) turns.push(event)
  }
  if (light === null || turns.length === 0) return null
  return { light, turns }
}

/** The light at `at`, or null past the last turn the schedule knows (the light is then not known). */
export function lightAt(schedule: SkySchedule, at: number): SkyLight | null {
  let light = schedule.light
  for (const turn of schedule.turns) {
    if (turn.at > at) return light
    light = turn.light
  }
  return null
}

/** The first turn after `at`, or null when the schedule knows none. */
export function nextTurn(schedule: SkySchedule, at: number): SkyTurn | null {
  return schedule.turns.find((turn) => turn.at > at) ?? null
}

/** The stored record, as the pre-paint script reads it. */
export function serializeSkySchedule(schedule: SkySchedule): string {
  return JSON.stringify({ light: schedule.light, turns: schedule.turns.map((t) => [t.at, t.light]) })
}

export function writeSkyRecord(schedule: SkySchedule) {
  try {
    localStorage.setItem(SKY_LIGHT_KEY, serializeSkySchedule(schedule))
  } catch {
    // blocked storage: the next load falls back to the device's light until the app looks
  }
}

export function clearSkyRecord() {
  try {
    localStorage.removeItem(SKY_LIGHT_KEY)
  } catch {
    // blocked storage: nothing was stored
  }
}

export function readSkyRecord(): SkySchedule | null {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(SKY_LIGHT_KEY) ?? "null")
    if (!raw || typeof raw !== "object") return null
    const { light, turns } = raw as { light?: unknown; turns?: unknown }
    if (!isLight(light) || !Array.isArray(turns)) return null
    const parsed: SkyTurn[] = []
    for (const turn of turns) {
      if (!Array.isArray(turn) || typeof turn[0] !== "number" || !isLight(turn[1])) return null
      parsed.push({ at: turn[0], light: turn[1] })
    }
    return { light, turns: parsed }
  } catch {
    return null
  }
}

/** What "Follow the sky" knows now: the theme control words it, the home hero preloads from it. */
export interface SkyStatus {
  /** The stored prayer-times city, null when none is stored (the sky then follows the device). */
  city: string | null
  /** The city's time zone, when known, to write the next turn's time. */
  timezone?: string
  /** The sky's light now, null without a city (or where the sky has no turn). */
  light: SkyLight | null
  /** The next turn of the light, null without a city. */
  next: SkyTurn | null
}

export const NO_SKY: SkyStatus = { city: null, light: null, next: null }

/** A stored city as `loadStoredCity()` returns it. */
interface StoredCity {
  city: string
  lat: number
  lng: number
  timezone?: string
}

/** The status for a stored city at `now`, from its schedule (computed here when not given). */
export function skyStatus(city: StoredCity | null, now: number, schedule: SkySchedule | null = city ? skySchedule(city, now) : null): SkyStatus {
  if (!city) return NO_SKY
  if (!schedule) return { ...NO_SKY, city: city.city, timezone: city.timezone }
  return { city: city.city, timezone: city.timezone, light: lightAt(schedule, now), next: nextTurn(schedule, now) }
}

export function sameSkyStatus(a: SkyStatus, b: SkyStatus): boolean {
  return a.city === b.city && a.timezone === b.timezone && a.light === b.light && a.next?.at === b.next?.at && a.next?.light === b.next?.light
}

/**
 * A turn's time for the theme control: 24-hour, Western digits, in the city's own time
 * zone when it is known (like the prayer chip).
 */
export function formatSkyTime(at: number, timezone?: string): string {
  const options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
  try {
    return new Intl.DateTimeFormat("en-GB", timezone ? { ...options, timeZone: timezone } : options).format(at)
  } catch {
    // an unknown time zone string from an old stored city
    return new Intl.DateTimeFormat("en-GB", options).format(at)
  }
}
