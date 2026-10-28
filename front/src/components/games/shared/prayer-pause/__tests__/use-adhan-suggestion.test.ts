import { act, renderHook } from "@testing-library/react"
import { CalculationMethod, Coordinates, PrayerTimes } from "adhan"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// The host's stored city (null = none chosen).
let mockCity: { city: string; lat: number; lng: number } | null = null
vi.mock("@/components/prayer-times/CitySelector", () => ({
  loadStoredCity: () => mockCity,
}))

const { ADHAN_CHECK_MS, ADHAN_SUGGESTION_WINDOW_MS, useAdhanSuggestion } = await import("../use-adhan-suggestion")

const MECCA = { city: "Mecca", lat: 21.4225, lng: 39.8262 }
/** ʿAṣr in Mecca on a fixed day, computed the way the hook computes it. */
const ASR = new PrayerTimes(new Coordinates(MECCA.lat, MECCA.lng), new Date(2026, 9, 28, 12, 0), CalculationMethod.MuslimWorldLeague()).asr

function check() {
  act(() => {
    vi.advanceTimersByTime(ADHAN_CHECK_MS)
  })
}

describe("useAdhanSuggestion (the adhan suggestion's timing)", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    sessionStorage.clear()
    mockCity = MECCA
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("offers the host the pause when the adhan arrives during the game", () => {
    // Prepare: half a minute before ʿAṣr
    vi.setSystemTime(ASR.getTime() - 30_000)
    const { result } = renderHook(() => useAdhanSuggestion({ gameId: "g1", canPause: true, paused: false }))
    expect(result.current.prayer).toBeNull()

    // Act: the time comes (the hook looks every 15 s)
    check()
    check()

    // Assert
    expect(result.current.prayer?.key).toBe("asr")
  })

  it("is answered once per prayer per game: Not now holds across a reload, not across games", () => {
    vi.setSystemTime(ASR.getTime() + 60_000)
    const first = renderHook(() => useAdhanSuggestion({ gameId: "g1", canPause: true, paused: false }))
    expect(first.result.current.prayer?.key).toBe("asr")

    act(() => first.result.current.answer())
    expect(first.result.current.prayer).toBeNull()

    // the page reloads: same game, same prayer
    first.unmount()
    const again = renderHook(() => useAdhanSuggestion({ gameId: "g1", canPause: true, paused: false }))
    expect(again.result.current.prayer).toBeNull()

    // another game at the same table is a new game
    const other = renderHook(() => useAdhanSuggestion({ gameId: "g2", canPause: true, paused: false }))
    expect(other.result.current.prayer?.key).toBe("asr")
  })

  it("lets the moment pass: nothing once the window after the adhan has closed", () => {
    vi.setSystemTime(ASR.getTime() + ADHAN_SUGGESTION_WINDOW_MS - 10_000)
    const { result } = renderHook(() => useAdhanSuggestion({ gameId: "g1", canPause: true, paused: false }))
    expect(result.current.prayer?.key).toBe("asr")

    check()

    expect(result.current.prayer).toBeNull()
  })

  it("says nothing to a player who cannot pause", () => {
    vi.setSystemTime(ASR.getTime() + 60_000)
    const { result } = renderHook(() => useAdhanSuggestion({ gameId: "g1", canPause: false, paused: false }))

    expect(result.current.prayer).toBeNull()
  })

  it("says nothing without a stored city", () => {
    mockCity = null
    vi.setSystemTime(ASR.getTime() + 60_000)
    const { result } = renderHook(() => useAdhanSuggestion({ gameId: "g1", canPause: true, paused: false }))

    expect(result.current.prayer).toBeNull()
  })

  it("counts a pause during the window as the answer: it does not come back after the resume", () => {
    vi.setSystemTime(ASR.getTime() + 60_000)
    const { result, rerender } = renderHook((props: { canPause: boolean; paused: boolean }) => useAdhanSuggestion({ gameId: "g1", ...props }), {
      initialProps: { canPause: true, paused: false },
    })
    expect(result.current.prayer?.key).toBe("asr")

    // the host paused from the header, prayed, and resumed within the window
    rerender({ canPause: false, paused: true })
    rerender({ canPause: true, paused: false })

    expect(result.current.prayer).toBeNull()
  })
})
