import { fireEvent, render, screen, within } from "@testing-library/react"
import { type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@tanstack/react-router", () => ({
  useLocation: () => ({ pathname: "/rooms" }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ isAuthenticated: true, user: { id: "u1", username: "Maryam", email: "maryam@example.com" }, logout: vi.fn() }),
}))

vi.mock("@/providers/ThemeProvider", () => ({ useTheme: () => ({ setTheme: vi.fn() }) }))
vi.mock("@/components/prayer-times/PrayerTimesNav", () => ({ PrayerTimesNav: () => null }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))

import { MainNav } from "../main-nav"

describe("MainNav: the Kunnash entry", () => {
  it("is in the menu sheet, next to Profile and Friends", async () => {
    // Prepare
    render(<MainNav />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "nav.menu" }))

    // Assert
    const sheet = await screen.findByRole("dialog")
    expect(within(sheet).getByRole("link", { name: "notebook.nav" })).toHaveAttribute("href", "/notebook")
    expect(within(sheet).getByRole("link", { name: "nav.profile" })).toBeInTheDocument()
  })

  it("is in the account menu, between Profile and Friends", async () => {
    // Prepare
    render(<MainNav />)

    // Act: Radix opens the menu from the keyboard
    const trigger = screen.getByTestId("user-menu-trigger")
    trigger.focus()
    fireEvent.keyDown(trigger, { key: "Enter" })

    // Assert
    const menu = await screen.findByRole("menu")
    const items = within(menu).getAllByRole("menuitem").map((i) => [i.textContent, i.getAttribute("href")])
    expect(items).toEqual([
      ["nav.profile", "/profile"],
      ["notebook.nav", "/notebook"],
      ["nav.friends", "/friends"],
      ["nav.logout", null],
    ])
  })

  it("is not in the desktop nav row (its fit was measured)", () => {
    render(<MainNav />)
    const row = screen.getAllByRole("navigation", { name: "nav.mainLabel" })[0]
    expect(within(row).queryByRole("link", { name: "notebook.nav" })).not.toBeInTheDocument()
  })
})
