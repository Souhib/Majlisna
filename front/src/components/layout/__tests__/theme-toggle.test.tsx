import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// the interpolations matter here: the sky's note names its time and its city
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key} ${JSON.stringify(options)}` : key),
    i18n: { language: "en" },
  }),
}))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))

import { trackEvent } from "@/lib/analytics"
import { ThemeProvider } from "@/providers/ThemeProvider"
import { ThemeToggle } from "../theme-toggle"

/**
 * The theme control (DESIGN.md §6b, §7): the afternoon, the night, and "Follow the sky".
 * The menu sheet sets them out as three pressed-or-not buttons, the nav row as a menu of
 * three radio items. The sky's choice says what it will do: the next turn and its time in
 * the city, or, with no city stored, that it follows the device until one is chosen.
 *
 * Makkah, 1 November 2026: Maghrib at 14:45 UTC (17:45 in Riyadh).
 */
const NOON = Date.parse("2026-11-01T12:00:00Z")
const EVENING = Date.parse("2026-11-01T20:00:00Z")

function storeCity() {
  localStorage.setItem("majlisna-city", "Makkah")
  localStorage.setItem("majlisna-coordinates", JSON.stringify({ lat: 21.4225, lng: 39.8262, timezone: "Asia/Riyadh" }))
}

function mount(theme: string | null, labelled: boolean) {
  if (theme) localStorage.setItem("majlisna-theme", theme)
  return render(
    <ThemeProvider>
      <ThemeToggle labelled={labelled} />
    </ThemeProvider>,
  )
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(NOON)
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query.includes("prefers-color-scheme: dark"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  )
  vi.mocked(trackEvent).mockClear()
})

afterEach(() => {
  localStorage.clear()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe("ThemeToggle in the menu sheet", () => {
  it("offers the afternoon, the night and the sky, the current choice pressed", () => {
    // Act
    mount("dark", true)

    // Assert
    const group = screen.getByRole("group", { name: "nav.theme" })
    const buttons = within(group).getAllByRole("button")
    expect(buttons.map((b) => b.textContent)).toEqual(["nav.themeChoices.light", "nav.themeChoices.dark", "nav.themeChoices.sky"])
    expect(buttons.map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"])
  })

  it("presses nothing while the device decides (no choice made yet)", () => {
    // Act
    mount(null, true)

    // Assert
    const buttons = within(screen.getByRole("group", { name: "nav.theme" })).getAllByRole("button")
    expect(buttons.every((b) => b.getAttribute("aria-pressed") === "false")).toBe(true)
  })

  it("chooses to follow the sky: stored, pressed, counted", async () => {
    // Prepare
    mount("dark", true)

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "nav.themeChoices.sky" }))
    })

    // Assert
    expect(localStorage.getItem("majlisna-theme")).toBe("sky")
    expect(screen.getByRole("button", { name: "nav.themeChoices.sky" })).toHaveAttribute("aria-pressed", "true")
    expect(trackEvent).toHaveBeenCalledWith("theme-change", { theme: "sky" })
  })

  it("says, with no city stored, that the sky choice follows the device until one is chosen", () => {
    // Act
    mount("sky", true)

    // Assert: the note describes the sky's button, whose name stays the choice
    expect(screen.getByText("nav.skyNote.noCity")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "nav.themeChoices.sky" })).toHaveAccessibleDescription("nav.skyNote.noCity")
  })

  it("names the next turn, in the city's own time, before and after the sky is chosen", async () => {
    // Prepare
    storeCity()
    const { unmount } = mount("light", true)

    // Assert: a preview while the afternoon is chosen
    expect(screen.getByText('nav.skyNote.toNight {"time":"17:45","city":"Makkah"}')).toBeInTheDocument()
    unmount()

    // Act: following the sky, in the evening
    vi.setSystemTime(EVENING)
    mount("sky", true)

    // Assert
    expect(screen.getByText('nav.skyNote.toDay {"time":"06:24","city":"Makkah"}')).toBeInTheDocument()
  })
})

describe("ThemeToggle in the nav row", () => {
  it("is a menu named by the current choice, holding the same three choices", async () => {
    // Prepare
    mount("dark", false)
    const trigger = screen.getByRole("button", { name: 'nav.themeCurrent {"choice":"nav.themeChoices.dark"}' })

    // Act: Radix opens a menu from the keyboard
    trigger.focus()
    fireEvent.keyDown(trigger, { key: "Enter" })

    // Assert
    const menu = await screen.findByRole("menu")
    const items = within(menu).getAllByRole("menuitemradio")
    expect(items).toHaveLength(3)
    expect(items.map((i) => i.getAttribute("aria-checked"))).toEqual(["false", "true", "false"])
    // the sky's item is named by its choice and described by its note
    expect(within(menu).getByRole("menuitemradio", { name: "nav.themeChoices.sky" })).toBe(items[2])
    expect(items[2]).toHaveAccessibleDescription("nav.skyNote.noCity")

    // Act
    await act(async () => {
      fireEvent.click(items[2])
    })

    // Assert
    expect(localStorage.getItem("majlisna-theme")).toBe("sky")
    expect(trackEvent).toHaveBeenCalledWith("theme-change", { theme: "sky" })
    expect(screen.getByRole("button", { name: 'nav.themeCurrent {"choice":"nav.themeChoices.sky"}' })).toBeInTheDocument()
  })
})

describe("ThemeToggle in the nav row: the sky's preview is read when the menu opens (review F3)", () => {
  async function openMenu() {
    const trigger = screen.getByRole("button", { name: /nav\.themeCurrent/ })
    trigger.focus()
    fireEvent.keyDown(trigger, { key: "Enter" })
    return screen.findByRole("menu")
  }

  async function closeMenu() {
    fireEvent.keyDown(await screen.findByRole("menu"), { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull())
  }

  const skyItem = (menu: HTMLElement) => within(menu).getByRole("menuitemradio", { name: "nav.themeChoices.sky" })

  it("names the city stored since the nav mounted (the first visit's IP lookup stores it a moment later)", async () => {
    // Prepare: the nav row mounts with no city, and its menu is opened once
    mount("light", false)
    expect(skyItem(await openMenu())).toHaveAccessibleDescription("nav.skyNote.noCity")
    await closeMenu()

    // Act: a city is stored, then the menu is opened again (the control never unmounted)
    storeCity()
    const menu = await openMenu()

    // Assert
    expect(skyItem(menu)).toHaveAccessibleDescription('nav.skyNote.toNight {"time":"17:45","city":"Makkah"}')
  })

  it("announces the next turn, not one that has passed while the page stayed open", async () => {
    // Prepare: noon in Makkah, the note announces Maghrib
    storeCity()
    mount("light", false)
    expect(skyItem(await openMenu())).toHaveAccessibleDescription('nav.skyNote.toNight {"time":"17:45","city":"Makkah"}')
    await closeMenu()

    // Act: the evening comes, the menu is opened again
    vi.setSystemTime(EVENING)
    const menu = await openMenu()

    // Assert: the next turn is the sunrise
    expect(skyItem(menu)).toHaveAccessibleDescription('nav.skyNote.toDay {"time":"06:24","city":"Makkah"}')
  })
})
