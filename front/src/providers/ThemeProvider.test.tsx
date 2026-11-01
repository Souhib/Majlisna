import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"
import { SKY_LIGHT_KEY } from "@/lib/sky-light"
import { SKY_CHECK_MS, SKY_HOLD_CHECK_MS, SKY_QUIET_MS, ThemeProvider, useSkyTurn, useTheme } from "./ThemeProvider"

/**
 * "Follow the sky" (DESIGN.md §7): the afternoon from sunrise to Maghrib, the night from
 * Maghrib to sunrise, computed on the device from the stored prayer-times city. When the
 * light turns with the page open, the app's one ceremony plays (a root crossfade of
 * --dur-ceremony through a view transition), never during a game on the table, at once
 * under reduced motion. A view transition takes the pointer for its whole length (every
 * press lands on <html>), so the turn waits for a quiet moment and a press ends it at
 * once. An explicit light or night always wins.
 *
 * Makkah, 1 November 2026: Maghrib at 14:45 UTC, sunrise the next day at 03:24 UTC.
 */
const MAKKAH = { city: "Makkah", lat: 21.4225, lng: 39.8262, timezone: "Asia/Riyadh" }
const NOON = Date.parse("2026-11-01T12:00:00Z")
const MAGHRIB = Date.parse("2026-11-01T14:45:00Z")
const CEREMONY_MS = 1100

let start: Mock
let skyTurnDuringTransition: boolean[] = []
const media = { dark: true, reduce: false, listeners: new Set<() => void>() }

function stubMedia() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      get matches() {
        if (query.includes("prefers-reduced-motion")) return media.reduce
        if (query.includes("prefers-color-scheme: dark")) return media.dark
        return false
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, l: () => void) => media.listeners.add(l),
      removeEventListener: (_: string, l: () => void) => media.listeners.delete(l),
      addListener: (l: () => void) => media.listeners.add(l),
      removeListener: (l: () => void) => media.listeners.delete(l),
      dispatchEvent: () => true,
    })),
  )
}

function storeCity(city = MAKKAH) {
  localStorage.setItem("majlisna-city", city.city)
  localStorage.setItem("majlisna-coordinates", JSON.stringify({ lat: city.lat, lng: city.lng, timezone: city.timezone }))
}

function Probe() {
  const { theme, sky, setTheme } = useTheme()
  const light = useResolvedTheme()
  const turn = useSkyTurn()
  return (
    <div>
      <p data-testid="theme">{theme}</p>
      <p data-testid="light">{light}</p>
      <p data-testid="sky-city">{sky.city ?? "none"}</p>
      <p data-testid="sky-next">{turn ? `${turn.light}@${turn.at}` : "none"}</p>
      <button type="button" onClick={() => setTheme("light")}>
        afternoon
      </button>
      <button type="button" onClick={() => setTheme("sky")}>
        sky
      </button>
    </div>
  )
}

function mount(theme: string | null) {
  if (theme) localStorage.setItem("majlisna-theme", theme)
  return render(
    <ThemeProvider defaultTheme="system">
      <Probe />
    </ThemeProvider>,
  )
}

const onScreen = () => document.documentElement.dataset.theme

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms)
  })
  // the view transition's update runs after the browser captured the old state
  await act(async () => {})
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOON)
  media.dark = true
  media.reduce = false
  media.listeners.clear()
  stubMedia()
  skyTurnDuringTransition = []
  start = vi.fn((update: () => void) => {
    skyTurnDuringTransition.push(document.documentElement.hasAttribute("data-sky-turn"))
    return { finished: Promise.resolve().then(update) }
  })
  Object.defineProperty(document, "startViewTransition", { configurable: true, writable: true, value: start })
  document.documentElement.dataset.theme = "dark"
  document.documentElement.className = "dark"
  window.history.pushState({}, "", "/")
})

afterEach(() => {
  delete (document as { startViewTransition?: unknown }).startViewTransition
  localStorage.clear()
  document.body.innerHTML = ""
  document.documentElement.removeAttribute("data-sky-turn")
  window.history.pushState({}, "", "/")
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("ThemeProvider: Follow the sky", () => {
  it("opens in the sky's light at once (a page load is not a turn) and stores the week ahead for the pre-paint script", () => {
    // Prepare: the device says night, the sky over Makkah says afternoon
    storeCity()

    // Act
    mount("sky")

    // Assert
    expect(onScreen()).toBe("light")
    expect(document.documentElement).toHaveClass("light")
    expect(start).not.toHaveBeenCalled()
    expect(screen.getByTestId("sky-city")).toHaveTextContent("Makkah")
    expect(screen.getByTestId("sky-next")).toHaveTextContent(`dark@${MAGHRIB}`)
    const record = JSON.parse(localStorage.getItem(SKY_LIGHT_KEY) ?? "null")
    expect(record.light).toBe("light")
    expect(record.turns[0]).toEqual([MAGHRIB, "dark"])
  })

  it("turns to the night at Maghrib through the one ceremony, once", async () => {
    // Prepare
    storeCity()
    mount("sky")

    // Act: a minute before, then Maghrib
    await advance(MAGHRIB - NOON - 60_000)
    expect(onScreen()).toBe("light")
    await advance(60_000)

    // Assert: one view transition, run under the ceremony's hook, which then goes
    expect(start).toHaveBeenCalledTimes(1)
    expect(skyTurnDuringTransition).toEqual([true])
    expect(onScreen()).toBe("dark")
    expect(screen.getByTestId("light")).toHaveTextContent("dark")
    expect(document.documentElement.hasAttribute("data-sky-turn")).toBe(false)

    // Act: the page keeps looking at the sky; nothing replays
    await advance(5 * SKY_CHECK_MS)

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId("sky-next").textContent).toMatch(/^light@/)
  })

  it("turns at once under reduced motion", async () => {
    // Prepare
    media.reduce = true
    storeCity()
    mount("sky")

    // Act
    await advance(MAGHRIB - NOON)

    // Assert
    expect(onScreen()).toBe("dark")
    expect(start).not.toHaveBeenCalled()
  })

  it("holds the turn while a game is on the table, and turns once its colophon is there", async () => {
    // Prepare
    storeCity()
    window.history.pushState({}, "", "/game/undercover/g1")
    mount("sky")

    // Act: Maghrib comes in the middle of the game
    await advance(MAGHRIB - NOON + 10 * SKY_HOLD_CHECK_MS)

    // Assert: the game keeps its light
    expect(onScreen()).toBe("light")
    expect(start).not.toHaveBeenCalled()

    // Act: the game ends on screen
    const title = document.createElement("h2")
    title.setAttribute("data-colophon-title", "")
    document.body.append(title)
    await advance(SKY_HOLD_CHECK_MS)
    expect(start).not.toHaveBeenCalled() // the colophon lands first
    await advance(CEREMONY_MS)

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(onScreen()).toBe("dark")
  })

  it("waits for a quiet moment: a press just before Maghrib holds the ceremony until the page is still", async () => {
    // Prepare
    storeCity()
    mount("sky")
    await advance(MAGHRIB - NOON - 500)

    // Act: the player taps, then Maghrib comes
    window.dispatchEvent(new Event("pointerdown"))
    await advance(500)

    // Assert: not yet, the page is being used
    expect(start).not.toHaveBeenCalled()
    expect(onScreen()).toBe("light")

    // Act: the page has been still long enough
    await advance(SKY_QUIET_MS + SKY_HOLD_CHECK_MS)

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(onScreen()).toBe("dark")
  })

  it("ends the ceremony at once when the page is pressed during it", async () => {
    // Prepare: a transition that lasts until its animations end
    let endTransition: () => void = () => {}
    start.mockImplementation((update: () => void) => ({
      finished: Promise.resolve()
        .then(update)
        .then(() => new Promise<void>((resolve) => (endTransition = resolve))),
    }))
    const fade = { effect: { pseudoElement: "::view-transition-new(root)" }, finish: vi.fn(() => endTransition()) }
    const other = { effect: { pseudoElement: null }, finish: vi.fn() }
    Object.defineProperty(document, "getAnimations", { configurable: true, value: () => [fade, other] })
    storeCity()
    mount("sky")
    await advance(MAGHRIB - NOON)
    expect(document.documentElement.hasAttribute("data-sky-turn")).toBe(true)

    // Act
    await act(async () => {
      window.dispatchEvent(new Event("pointerdown"))
    })

    // Assert: the crossfade is finished, the night is there, the page is the player's again
    expect(fade.finish).toHaveBeenCalledTimes(1)
    expect(other.finish).not.toHaveBeenCalled()
    expect(onScreen()).toBe("dark")
    expect(document.documentElement.hasAttribute("data-sky-turn")).toBe(false)
    delete (document as { getAnimations?: unknown }).getAnimations
  })

  it("holds the turn until the player is back in the lobby", async () => {
    // Prepare
    storeCity()
    window.history.pushState({}, "", "/game/codenames/g2")
    mount("sky")
    await advance(MAGHRIB - NOON + SKY_HOLD_CHECK_MS)
    expect(onScreen()).toBe("light")

    // Act
    window.history.pushState({}, "", "/rooms/r1")
    await advance(SKY_HOLD_CHECK_MS + CEREMONY_MS)

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(onScreen()).toBe("dark")
  })

  it("without a stored city, says so and follows the device, asking neither the network nor the location", async () => {
    // Prepare
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const locate = vi.fn()
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition: locate } })
    media.dark = false

    // Act
    mount("sky")

    // Assert
    expect(onScreen()).toBe("light")
    expect(screen.getByTestId("sky-city")).toHaveTextContent("none")
    expect(screen.getByTestId("sky-next")).toHaveTextContent("none")
    expect(localStorage.getItem(SKY_LIGHT_KEY)).toBeNull()

    // Act: the device turns dark
    media.dark = true
    await act(async () => {
      for (const l of media.listeners) l()
    })

    // Assert: followed at once, like the device's own choice
    expect(onScreen()).toBe("dark")
    expect(start).not.toHaveBeenCalled()
    await advance(10 * SKY_CHECK_MS)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(locate).not.toHaveBeenCalled()
  })

  it("follows the sky once a city is stored (by the prayer chip, or another tab), at once", async () => {
    // Prepare
    media.dark = true
    mount("sky")
    expect(onScreen()).toBe("dark")

    // Act
    storeCity()
    await advance(SKY_CHECK_MS)

    // Assert: the afternoon over Makkah, without a ceremony (the city changed, not the sky)
    expect(onScreen()).toBe("light")
    expect(start).not.toHaveBeenCalled()
    expect(screen.getByTestId("sky-city")).toHaveTextContent("Makkah")
  })

  it("lets an explicit light or night win, and forgets the sky's record", async () => {
    // Prepare
    storeCity()
    localStorage.setItem(SKY_LIGHT_KEY, "{}")
    mount("dark")

    // Act
    await advance(MAGHRIB - NOON + 13 * 3_600_000)

    // Assert
    expect(onScreen()).toBe("dark")
    expect(start).not.toHaveBeenCalled()
    expect(localStorage.getItem(SKY_LIGHT_KEY)).toBeNull()
    expect(screen.getByTestId("sky-next")).toHaveTextContent("none")
  })

  it("applies a choice at once, the sky included", async () => {
    // Prepare
    storeCity()
    media.dark = true
    mount(null)
    expect(screen.getByTestId("theme")).toHaveTextContent("system")
    expect(onScreen()).toBe("dark")

    // Act
    await act(async () => {
      screen.getByRole("button", { name: "sky" }).click()
    })

    // Assert
    expect(localStorage.getItem("majlisna-theme")).toBe("sky")
    expect(onScreen()).toBe("light")

    // Act
    await act(async () => {
      screen.getByRole("button", { name: "afternoon" }).click()
    })

    // Assert
    expect(onScreen()).toBe("light")
    expect(localStorage.getItem(SKY_LIGHT_KEY)).toBeNull()
    expect(start).not.toHaveBeenCalled()
  })

  it("still renders when storage is blocked", () => {
    // Prepare
    // a stubbed global, not spies: on happy-dom's Storage (a Proxy) a spy is not restored
    // and the throwing storage outlived the test (CI, Node < 25)
    const blocked = () => {
      throw new Error("blocked")
    }
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked, removeItem: blocked, clear: () => {} })

    // Act
    mount(null)

    // Assert
    expect(screen.getByTestId("theme")).toHaveTextContent("system")
    expect(onScreen()).toBe("dark")
  })
})

/**
 * A change of light restyles the whole page, and every `transition-colors` on it (the nav's
 * links, the buttons, the prayer chip, the code tiles) would run from the old light to the new
 * one: tens of non-composited 180 ms colour transitions on the main thread, and under the sky's
 * ceremony controls still fading from the afternoon inside the crossfade (review RM-3). The
 * provider finishes the transitions the flip has just started, in the same task, and leaves
 * alone a transition already running and every other animation.
 */
describe("ThemeProvider: the light changes without the page's own colour transitions", () => {
  interface FakeAnimation {
    transitionProperty?: string
    animationName?: string
    pending: boolean
    effect: { pseudoElement: string | null }
    finish: Mock
  }
  let started: FakeAnimation
  let running: FakeAnimation
  let keyframed: FakeAnimation
  let finishedIn: (string | undefined)[]
  let getAnimations: Mock

  beforeEach(() => {
    finishedIn = []
    // a finished transition is no longer pending (and leaves the list a real browser returns)
    const recordLight = () => {
      finishedIn.push(document.documentElement.dataset.theme)
      started.pending = false
    }
    started = { transitionProperty: "border-top-color", pending: true, effect: { pseudoElement: null }, finish: vi.fn(recordLight) }
    running = { transitionProperty: "color", pending: false, effect: { pseudoElement: null }, finish: vi.fn() }
    keyframed = { animationName: "seal-press", pending: true, effect: { pseudoElement: null }, finish: vi.fn() }
    getAnimations = vi.fn(() => [started, running, keyframed])
    Object.defineProperty(document, "getAnimations", { configurable: true, value: getAnimations })
  })

  afterEach(() => {
    delete (document as { getAnimations?: unknown }).getAnimations
  })

  it("finishes the transitions a chosen light has just started, once the new light is on", async () => {
    // Prepare: the night
    mount("dark")
    getAnimations.mockClear()

    // Act: the player chooses the afternoon
    await act(async () => {
      screen.getByRole("button", { name: "afternoon" }).click()
    })

    // Assert
    expect(onScreen()).toBe("light")
    expect(started.finish).toHaveBeenCalledTimes(1)
    expect(finishedIn).toEqual(["light"])
    expect(running.finish).not.toHaveBeenCalled()
    expect(keyframed.finish).not.toHaveBeenCalled()
  })

  it("finishes too the transitions React's own re-render starts once the light is announced (the Register button's variant)", async () => {
    // Prepare: the flip's transitions first; then, once React has re-rendered the readers of
    // the light, the Register button's new variant starts its own
    mount("dark")
    const late: FakeAnimation = { transitionProperty: "background-color", pending: true, effect: { pseudoElement: null }, finish: vi.fn() }
    let calls = 0
    getAnimations.mockImplementation(() => (++calls === 1 ? [started, running, keyframed] : [running, keyframed, late]))

    // Act
    await act(async () => {
      screen.getByRole("button", { name: "afternoon" }).click()
    })

    // Assert: both passes ran, each finishing only what had just started
    expect(started.finish).toHaveBeenCalledTimes(1)
    expect(late.finish).toHaveBeenCalledTimes(1)
    expect(running.finish).not.toHaveBeenCalled()
    expect(keyframed.finish).not.toHaveBeenCalled()
  })

  it("finishes them inside the sky's ceremony, before the browser captures the new light", async () => {
    // Prepare
    storeCity()
    mount("sky")
    let duringTransition = false
    start.mockImplementation((update: () => void) => ({
      finished: Promise.resolve().then(() => {
        duringTransition = true
        update()
        duringTransition = false
      }),
    }))
    const inside: boolean[] = []
    // the load put the afternoon on (and finished its transitions, in both passes): the turn
    // starts a new one
    await act(async () => {})
    started.pending = true
    started.finish.mockImplementation(() => {
      inside.push(duringTransition)
      started.pending = false
    })

    // Act
    await advance(MAGHRIB - NOON)

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(onScreen()).toBe("dark")
    expect(inside).toEqual([true])
    expect(running.finish).not.toHaveBeenCalled()
  })

  it("asks for nothing when the light on screen is already the one applied (a page load)", () => {
    // Prepare: the pre-paint script already put the night on
    getAnimations.mockClear()

    // Act
    mount("dark")

    // Assert: no forced restyle at load, nothing finished
    expect(getAnimations).not.toHaveBeenCalled()
    expect(started.finish).not.toHaveBeenCalled()
  })
})

describe("useSkyTurn", () => {
  it("is null outside a ThemeProvider (the home hero rendered alone)", () => {
    // Prepare
    function Alone() {
      const turn = useSkyTurn()
      return <p data-testid="turn">{turn ? "turn" : "none"}</p>
    }

    // Act
    render(<Alone />)

    // Assert
    expect(screen.getByTestId("turn")).toHaveTextContent("none")
  })
})
