import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

const location = { pathname: "/" }
vi.mock("@tanstack/react-router", () => ({
  useLocation: () => location,
  Link: ({ children, to, className, ...rest }: { children: ReactNode; to: string; className?: string }) => (
    <a href={to} className={className} {...rest}>
      {children}
    </a>
  ),
}))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))

const { Footer } = await import("../footer")

describe("Footer", () => {
  it.each(["/", "/about", "/about/"])("leaves the charities to %s, which names them itself", (pathname) => {
    // Prepare
    location.pathname = pathname

    // Act
    render(<Footer />)

    // Assert
    expect(screen.queryByRole("link", { name: /Human Appeal/ })).toBeNull()
    expect(screen.queryByRole("link", { name: /Ummah Charity/ })).toBeNull()
  })

  it("links the terms of use right after the privacy policy", () => {
    // Prepare
    location.pathname = "/rooms"

    // Act
    render(<Footer />)

    // Assert: the two pages sit side by side in the footer's page list
    const pages = screen.getAllByRole("link").map((a) => a.getAttribute("href"))
    expect(pages).toContain("/terms")
    expect(pages.indexOf("/terms")).toBe(pages.indexOf("/privacy") + 1)
  })

  it.each(["/leaderboard", "/credits", "/rooms"])("names the two charities on %s", (pathname) => {
    // Prepare
    location.pathname = pathname

    // Act
    render(<Footer />)

    // Assert
    expect(screen.getByRole("link", { name: /Human Appeal/ })).toHaveAttribute("href", "https://humanappeal.fr/")
    expect(screen.getByRole("link", { name: /Ummah Charity/ })).toHaveAttribute("href", "https://ummahcharity.org/")
  })
})
