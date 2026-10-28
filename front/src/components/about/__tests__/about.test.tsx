import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { AboutIntro } from "../AboutIntro"
import { MakerSection } from "../MakerSection"
import { SupportCharities } from "../SupportCharities"

const trackEvent = vi.fn()
vi.mock("@/lib/analytics", () => ({ trackEvent: (...args: unknown[]) => trackEvent(...args) }))

describe("AboutIntro", () => {
  it("is the page's h1, with what Majlisna is under it", () => {
    render(<AboutIntro />)
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("about.title")
    expect(screen.getByText("about.games")).toBeInTheDocument()
    expect(screen.getByText("about.languages")).toBeInTheDocument()
  })
})

describe("SupportCharities", () => {
  it("links both charities in a new tab and counts the click", () => {
    // Prepare
    render(<SupportCharities />)
    const links = screen.getAllByRole("link")

    // Act
    fireEvent.click(links[0])

    // Assert
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["https://humanappeal.fr/", "https://ummahcharity.org/"])
    for (const a of links) expect(a).toHaveAttribute("rel", "noopener noreferrer")
    expect(trackEvent).toHaveBeenCalledWith("charity-click", { org: "human-appeal" })
  })
})

describe("MakerSection", () => {
  it("keeps the maker's links, his portrait and the mentoring offer", () => {
    // Prepare
    trackEvent.mockClear()
    render(<MakerSection />)
    const contact = within(screen.getByRole("heading", { name: "about.contactMe" }).parentElement as HTMLElement)

    // Act
    fireEvent.click(contact.getByRole("link", { name: /GitHub/ }))

    // Assert
    expect(contact.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "mailto:souhib.t@icloud.com",
      "tel:+33643142020",
      "https://www.linkedin.com/in/souhib-trabelsi/",
      "https://github.com/Souhib",
    ])
    expect(trackEvent).toHaveBeenCalledWith("social-click", { platform: "github" })
    expect(screen.getByRole("img", { name: "about.portraitAlt" })).toHaveAttribute("src", "/souhib.jpeg")
    const mentoring = within(screen.getByRole("region", { name: "about.mentoringTitle" }))
    expect(mentoring.getByRole("link", { name: /souhib\.t@icloud\.com/ })).toHaveAttribute("href", "mailto:souhib.t@icloud.com")
    expect(mentoring.getByRole("link", { name: /\+33 6 43 14 20 20/ })).toHaveAttribute("href", "tel:+33643142020")
    // five jobs, two schools, every skill
    expect(screen.getAllByText(/^about\.experience.+Title$/)).toHaveLength(5)
    expect(screen.getByText("about.educationEpitech")).toBeInTheDocument()
    expect(screen.getByText("Scikit-learn")).toBeInTheDocument()
  })
})
