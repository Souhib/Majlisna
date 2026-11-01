import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// The interface language of the test; every component reads it from useTranslation.
const i18nState = vi.hoisted(() => ({ language: "en" }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: i18nState.language, changeLanguage: vi.fn() } }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: "3rdParty", init: vi.fn() },
}))

import { CitySelector, GEO_FAILED_AT_KEY, GEO_RETRY_AFTER_MS, autoDetectLocationByIP } from "../CitySelector"
import { PrayerTimesNav } from "../PrayerTimesNav"

const IPAPI = "https://ipapi.co/json/"

function requestsTo(fetchMock: ReturnType<typeof vi.fn>, prefix: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).startsWith(prefix))
}

describe("IP auto-detection", () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    localStorage.clear()
    i18nState.language = "en"
    fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it("remembers a failed request: remounting the chip within 24 h asks ipapi.co nothing", async () => {
    // Prepare: ipapi.co answers 429 without a CORS header, which the page sees as a network error
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))
    const first = render(<PrayerTimesNav />)
    await waitFor(() => expect(requestsTo(fetchMock, IPAPI)).toHaveLength(1))
    await waitFor(() => expect(localStorage.getItem(GEO_FAILED_AT_KEY)).not.toBeNull())
    first.unmount()

    // Act: the next page load, an hour later
    const now = Date.now()
    vi.spyOn(Date, "now").mockReturnValue(now + 60 * 60 * 1000)
    render(<PrayerTimesNav />)
    await new Promise((resolve) => setTimeout(resolve, 20))

    // Assert
    expect(requestsTo(fetchMock, IPAPI)).toHaveLength(1)
  })

  it("counts a refused answer (429) as a failure, and asks again once the day has passed", async () => {
    // Prepare: a readable 429 (no JSON body), remembered as a failure
    fetchMock.mockResolvedValue(new Response("Please contact us for a trial account", { status: 429 }))
    const failedAt = Date.now()
    vi.spyOn(Date, "now").mockReturnValue(failedAt)
    expect(await autoDetectLocationByIP()).toBeNull()
    expect(Number(localStorage.getItem(GEO_FAILED_AT_KEY))).toBe(failedAt)

    // Act: once within the day, once after it
    vi.spyOn(Date, "now").mockReturnValue(failedAt + GEO_RETRY_AFTER_MS - 1)
    await autoDetectLocationByIP()
    const beforeTheDayEnds = requestsTo(fetchMock, IPAPI).length
    vi.spyOn(Date, "now").mockReturnValue(failedAt + GEO_RETRY_AFTER_MS + 1)
    await autoDetectLocationByIP()

    // Assert
    expect(beforeTheDayEnds).toBe(1)
    expect(requestsTo(fetchMock, IPAPI)).toHaveLength(2)
  })

  it("asks once for every caller of the same page load, and stores the city it finds", async () => {
    // Prepare
    fetchMock.mockResolvedValue(Response.json({ city: "Makkah", latitude: 21.42, longitude: 39.83, timezone: "Asia/Riyadh" }))

    // Act: the nav and the chip both want a city at once
    const [a, b] = await Promise.all([autoDetectLocationByIP(), autoDetectLocationByIP()])

    // Assert
    expect(requestsTo(fetchMock, IPAPI)).toHaveLength(1)
    expect(a).toEqual({ city: "Makkah", lat: 21.42, lng: 39.83, timezone: "Asia/Riyadh" })
    expect(b).toEqual(a)
    expect(localStorage.getItem("majlisna-city")).toBe("Makkah")
    expect(localStorage.getItem(GEO_FAILED_AT_KEY)).toBeNull()
  })
})

describe("CitySelector: the interface language", () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    localStorage.clear()
    i18nState.language = "ar"
    fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
    i18nState.language = "en"
  })

  it("searches the cities in the interface language", async () => {
    // Prepare
    fetchMock.mockResolvedValue(Response.json({ results: [] }))
    render(<CitySelector onSelect={vi.fn()} />)

    // Act
    fireEvent.change(screen.getByRole("searchbox", { name: "prayer.searchCity" }), { target: { value: "Makkah" } })

    // Assert
    await waitFor(() => expect(requestsTo(fetchMock, "https://geocoding-api.open-meteo.com/")).toHaveLength(1))
    const url = new URL(String(requestsTo(fetchMock, "https://geocoding-api.open-meteo.com/")[0][0]))
    expect(url.searchParams.get("language")).toBe("ar")
    expect(url.searchParams.get("name")).toBe("Makkah")
  })

  it("names the device's position in the interface language, and says 'My location' in it when no name is found", async () => {
    // Prepare: the position is granted, Nominatim fails, Open-Meteo gives the time zone
    const getCurrentPosition = vi.fn((resolve: PositionCallback) => resolve({ coords: { latitude: 36.8, longitude: 10.18 } } as GeolocationPosition))
    vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } })
    fetchMock.mockImplementation((url: string) =>
      url.startsWith("https://nominatim.openstreetmap.org/")
        ? Promise.reject(new TypeError("Failed to fetch"))
        : Promise.resolve(Response.json({ timezone: "Africa/Tunis" })),
    )
    const onSelect = vi.fn()
    render(<CitySelector onSelect={onSelect} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "prayer.useMyLocation" }))

    // Assert: the request asked for Arabic names, the fallback is the translated key
    await waitFor(() => expect(onSelect).toHaveBeenCalled())
    const [, init] = requestsTo(fetchMock, "https://nominatim.openstreetmap.org/")[0]
    expect(new Headers((init as RequestInit).headers).get("Accept-Language")).toBe("ar")
    expect(onSelect).toHaveBeenCalledWith({ city: "prayer.myLocation", lat: 36.8, lng: 10.18, timezone: "Africa/Tunis" })
    expect(screen.getByText("prayer.myLocation")).toBeInTheDocument()
    expect(localStorage.getItem("majlisna-city")).toBe("prayer.myLocation")
  })
})
