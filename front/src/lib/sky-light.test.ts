import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"
import { clearSkyRecord, formatSkyTime, lightAt, nextTurn, readSkyRecord, SKY_LIGHT_KEY, SKY_SCHEDULE_DAYS, skySchedule, writeSkyRecord } from "./sky-light"

/**
 * "Follow the sky" (DESIGN.md §7): the light is the afternoon from sunrise to Maghrib and
 * the night from Maghrib to sunrise, computed on the device from the stored city with the
 * prayer times' own method (adhan, Muslim World League). Makkah on 1 November 2026:
 * sunrise 03:24 UTC, Maghrib 14:45 UTC.
 */
const MAKKAH = { lat: 21.4225, lng: 39.8262 }
const NOON = Date.parse("2026-11-01T12:00:00Z")
const MAGHRIB = Date.parse("2026-11-01T14:45:00Z")
const EVENING = Date.parse("2026-11-01T20:00:00Z")
const HOUR = 3_600_000

const HTML = readFileSync(resolve(process.cwd(), "index.html"), "utf8")
const THEME_SCRIPT = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).find((s) => s.includes("majlisna-theme")) as string

/** What index.html's pre-paint script draws, at `now`, for the stored choice. */
function prePaint(theme: string | null, now: number, systemDark = true) {
  vi.setSystemTime(now)
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({ matches: systemDark && query.includes("dark"), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  )
  if (theme) localStorage.setItem("majlisna-theme", theme)
  const root = document.documentElement
  root.classList.remove("light", "dark")
  root.removeAttribute("data-theme")
  new Function(THEME_SCRIPT)()
  return root.dataset.theme
}

afterEach(() => {
  localStorage.clear()
  for (const l of document.head.querySelectorAll("link")) l.remove()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("skySchedule", () => {
  it("is the afternoon at noon, and turns to night at Maghrib", () => {
    // Act
    const schedule = skySchedule(MAKKAH, NOON)

    // Assert
    expect(schedule?.light).toBe("light")
    expect(schedule?.turns[0]).toEqual({ at: MAGHRIB, light: "dark" })
    expect(schedule?.turns[1]).toEqual({ at: Date.parse("2026-11-02T03:24:00Z"), light: "light" })
  })

  it("is the night after Maghrib, until sunrise", () => {
    // Act
    const schedule = skySchedule(MAKKAH, EVENING)

    // Assert
    expect(schedule?.light).toBe("dark")
    expect(schedule?.turns[0].light).toBe("light")
    expect(new Date(schedule?.turns[0].at ?? 0).toISOString()).toBe("2026-11-02T03:24:00.000Z")
  })

  it("keeps a week of turns ahead, alternating, all after now", () => {
    // Act
    const schedule = skySchedule(MAKKAH, NOON)
    const turns = schedule?.turns ?? []

    // Assert: day and night take turns, in order, for the whole week the page may sleep through
    expect(turns.length).toBeGreaterThanOrEqual(2 * SKY_SCHEDULE_DAYS)
    expect(turns.every((t) => t.at > NOON)).toBe(true)
    for (let i = 1; i < turns.length; i++) {
      expect(turns[i].at).toBeGreaterThan(turns[i - 1].at)
      expect(turns[i].light).not.toBe(turns[i - 1].light)
    }
    expect(turns.at(-1)?.at ?? 0).toBeGreaterThan(NOON + SKY_SCHEDULE_DAYS * 24 * HOUR)
  })

  it("has no schedule where the sky has no turn (a polar night) or the coordinates are not a place", () => {
    // Act / Assert
    expect(skySchedule({ lat: 78.2232, lng: 15.6267 }, Date.parse("2026-12-21T12:00:00Z"))).toBeNull()
    expect(skySchedule({ lat: Number.NaN, lng: 2 }, NOON)).toBeNull()
  })
})

describe("lightAt and nextTurn", () => {
  it("reads the light at any instant of the schedule, and nothing past its last turn", () => {
    // Prepare
    const schedule = skySchedule(MAKKAH, NOON)
    if (!schedule) throw new Error("no schedule")
    const last = schedule.turns.at(-1)?.at ?? 0

    // Act / Assert
    expect(lightAt(schedule, NOON)).toBe("light")
    expect(lightAt(schedule, MAGHRIB - 1)).toBe("light")
    expect(lightAt(schedule, MAGHRIB)).toBe("dark")
    expect(lightAt(schedule, EVENING)).toBe("dark")
    expect(lightAt(schedule, last)).toBeNull()
    expect(nextTurn(schedule, NOON)).toEqual({ at: MAGHRIB, light: "dark" })
    expect(nextTurn(schedule, MAGHRIB)?.light).toBe("light")
    expect(nextTurn(schedule, last)).toBeNull()
  })
})

describe("the stored record (majlisna-sky-light)", () => {
  it("round-trips, compactly, and is removed on request", () => {
    // Prepare
    const schedule = skySchedule(MAKKAH, NOON)
    if (!schedule) throw new Error("no schedule")

    // Act
    writeSkyRecord(schedule)
    const raw = JSON.parse(localStorage.getItem(SKY_LIGHT_KEY) ?? "null")
    const read = readSkyRecord()

    // Assert: [instant, light] pairs the pre-paint script can walk
    expect(raw.light).toBe("light")
    expect(raw.turns[0]).toEqual([MAGHRIB, "dark"])
    expect(read).toEqual(schedule)

    // Act
    clearSkyRecord()

    // Assert
    expect(localStorage.getItem(SKY_LIGHT_KEY)).toBeNull()
  })

  it("reads nothing from a malformed record or a blocked storage, and never throws", () => {
    // Prepare
    localStorage.setItem(SKY_LIGHT_KEY, "{not json")

    // Act / Assert
    expect(readSkyRecord()).toBeNull()
    localStorage.setItem(SKY_LIGHT_KEY, JSON.stringify({ light: "noon", turns: [[1, "dark"]] }))
    expect(readSkyRecord()).toBeNull()

    // a good record behind a storage that refuses to be read
    localStorage.setItem(SKY_LIGHT_KEY, JSON.stringify({ light: "dark", turns: [[1, "light"]] }))
    expect(readSkyRecord()).not.toBeNull()
    vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked")
    })
    vi.spyOn(localStorage, "setItem").mockImplementation(() => {
      throw new Error("blocked")
    })
    expect(readSkyRecord()).toBeNull()
    expect(() => writeSkyRecord({ light: "dark", turns: [{ at: 1, light: "light" }] })).not.toThrow()
  })
})

describe("index.html's pre-paint script, for the sky choice", () => {
  it("draws the light the record gives for now, past any number of turns, like lightAt", () => {
    // Prepare: the record written at noon
    vi.useFakeTimers()
    const schedule = skySchedule(MAKKAH, NOON)
    if (!schedule) throw new Error("no schedule")
    writeSkyRecord(schedule)

    // Act / Assert: the same answer as lightAt, the night or the afternoon, whatever the device says
    const instants = [NOON, MAGHRIB - 60_000, MAGHRIB + 60_000, EVENING, NOON + 2.5 * 24 * HOUR, NOON + 3 * 24 * HOUR]
    instants.forEach((at, i) => {
      expect(prePaint("sky", at, i % 2 === 0)).toBe(lightAt(schedule, at))
    })
    expect(new Set(instants.map((at) => lightAt(schedule, at)))).toEqual(new Set(["light", "dark"]))
  })

  it("falls back to the device's light when the record is missing, malformed or used up", () => {
    // Prepare
    vi.useFakeTimers()
    const schedule = skySchedule(MAKKAH, NOON)
    if (!schedule) throw new Error("no schedule")
    const pastLast = (schedule.turns.at(-1)?.at ?? 0) + HOUR

    // Act / Assert: no record
    expect(prePaint("sky", NOON, true)).toBe("dark")
    expect(prePaint("sky", NOON, false)).toBe("light")

    // a malformed one
    localStorage.setItem(SKY_LIGHT_KEY, "{oops")
    expect(prePaint("sky", NOON, false)).toBe("light")

    // a stale one: past its last turn, the light is not known
    writeSkyRecord(schedule)
    expect(prePaint("sky", pastLast, false)).toBe("light")
    expect(prePaint("sky", pastLast, true)).toBe("dark")
  })

  it("lets an explicit light or night win over a record", () => {
    // Prepare
    vi.useFakeTimers()
    const schedule = skySchedule(MAKKAH, NOON)
    if (!schedule) throw new Error("no schedule")
    writeSkyRecord(schedule)

    // Act / Assert
    expect(prePaint("dark", NOON, false)).toBe("dark")
    expect(prePaint("light", EVENING, true)).toBe("light")
  })
})

describe("formatSkyTime", () => {
  it("writes the turn as a 24-hour clock in the city's own time zone, Western digits", () => {
    // Act / Assert
    expect(formatSkyTime(MAGHRIB, "Asia/Riyadh")).toBe("17:45")
    expect(formatSkyTime(MAGHRIB, "Not/AZone")).toMatch(/^\d{2}:\d{2}$/)
  })
})
