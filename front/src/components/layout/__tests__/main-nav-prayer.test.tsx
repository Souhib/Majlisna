import { act, fireEvent, render, screen } from "@testing-library/react"
import { type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const routerState = vi.hoisted(() => ({ pathname: "/rooms" }))
vi.mock("@tanstack/react-router", () => ({
  useLocation: () => ({ pathname: routerState.pathname }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ isAuthenticated: false, user: null, logout: vi.fn() }) }))
vi.mock("@/providers/ThemeProvider", () => ({ useTheme: () => ({ setTheme: vi.fn() }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))

// Each mounted chip runs its own copy of the prayer logic (and used to ask ipapi.co).
vi.mock("@/components/prayer-times/PrayerTimesNav", () => ({ PrayerTimesNav: () => <span data-testid="prayer-chip" /> }))
const city = vi.hoisted(() => ({ autoDetectLocationByIP: vi.fn(async () => null), loadStoredCity: vi.fn((): null | object => null) }))
vi.mock("@/components/prayer-times/CitySelector", () => city)

import { MainNav } from "../main-nav"

/** A viewport of `width` CSS px, as matchMedia reports it. */
function viewport(width: number) {
  const listeners = new Set<() => void>()
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => {
      const min = /min-width:\s*(\d+)px/.exec(query)
      const max = /max-width:\s*(\d+)px/.exec(query)
      const matches = (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]))
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: (_: string, l: () => void) => listeners.add(l),
        removeEventListener: (_: string, l: () => void) => listeners.delete(l),
        addListener: (l: () => void) => listeners.add(l),
        removeListener: (l: () => void) => listeners.delete(l),
        dispatchEvent: () => true,
      }
    }),
  )
  return { resize: (next: number) => ((width = next), listeners.forEach((l) => l())) }
}

describe("MainNav: one prayer chip per viewport", () => {
  beforeEach(() => {
    routerState.pathname = "/rooms"
    city.autoDetectLocationByIP.mockClear()
    city.loadStoredCity.mockReturnValue(null)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("at 390 px, mounts only the menu sheet's chip (the desktop one is not hidden, it is absent)", async () => {
    // Prepare
    viewport(390)
    render(<MainNav />)
    expect(screen.queryAllByTestId("prayer-chip")).toHaveLength(0)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "nav.menu" }))

    // Assert
    await screen.findByRole("dialog")
    expect(screen.getAllByTestId("prayer-chip")).toHaveLength(1)
  })

  it("at 1440 px, mounts the nav row's chip once", () => {
    // Prepare / Act
    viewport(1440)
    render(<MainNav />)

    // Assert
    expect(screen.getAllByTestId("prayer-chip")).toHaveLength(1)
  })

  it("mounts the row's chip from 1180 px, where the row shows (Tailwind's max-[1180px] is width < 1180px)", () => {
    // Prepare / Act
    viewport(1180)
    render(<MainNav />)

    // Assert
    expect(screen.getAllByTestId("prayer-chip")).toHaveLength(1)
  })

  it("follows the viewport across the 1180 px breakpoint", () => {
    // Prepare
    const screenSize = viewport(1440)
    render(<MainNav />)

    // Act
    act(() => screenSize.resize(1000))

    // Assert
    expect(screen.queryAllByTestId("prayer-chip")).toHaveLength(0)
  })

  it("still detects the city on a phone, where no chip is mounted: the adhan suggestion reads it", () => {
    // Prepare / Act
    viewport(390)
    render(<MainNav />)

    // Assert
    expect(city.autoDetectLocationByIP).toHaveBeenCalledTimes(1)
  })

  it("asks nothing when a city is stored", () => {
    // Prepare
    city.loadStoredCity.mockReturnValue({ city: "Makkah", lat: 21.42, lng: 39.83 })
    viewport(390)

    // Act
    render(<MainNav />)

    // Assert
    expect(city.autoDetectLocationByIP).not.toHaveBeenCalled()
  })
})

describe("MainNav: the scroll state", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    Reflect.deleteProperty(window, "scrollY")
  })

  it("reads the scroll position before the DOM exists, never again in the mount effect (a forced layout)", () => {
    // Prepare: count every read of window.scrollY
    viewport(1440)
    routerState.pathname = "/"
    let scrollY = 0
    const reads = vi.fn(() => scrollY)
    Object.defineProperty(window, "scrollY", { configurable: true, get: reads })

    // Act
    render(<MainNav />)
    const readsAtMount = reads.mock.calls.length
    scrollY = 120
    act(() => {
      window.dispatchEvent(new Event("scroll"))
    })

    // Assert: one read for the first render, then the scroll listener does the rest
    expect(readsAtMount).toBe(1)
    expect(document.querySelector("header.samar-nav")).toHaveAttribute("data-over-sky", "false")
  })
})
