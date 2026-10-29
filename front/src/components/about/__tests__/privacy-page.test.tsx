import { render, screen, within } from "@testing-library/react"
import i18next from "i18next"
import { type ComponentType, type ReactNode } from "react"
import { initReactI18next } from "react-i18next"
import { beforeAll, describe, expect, it, vi } from "vitest"
import ar from "@/i18n/locales/ar.json"
import en from "@/i18n/locales/en.json"
import fr from "@/i18n/locales/fr.json"

// The real strings (the setup file mocks react-i18next to print keys): the page reads its
// sections from the locale, so the test does too, in the three languages.
vi.unmock("react-i18next")

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

const { Route } = await import("@/routes/privacy")
const PrivacyPage = (Route as unknown as { options: { component: ComponentType } }).options.component

const LOCALES = { en, fr, ar }
type Lang = keyof typeof LOCALES

/** A paragraph as the reader sees it: the `<b>` and `<profile>` marks are markup, not text. */
const plain = (s: string) => s.replace(/<\/?(b|profile)>/g, "")
const squash = (s: string | null) => (s ?? "").replace(/\s+/g, " ").trim()

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en }, fr: { translation: fr }, ar: { translation: ar } },
    interpolation: { escapeValue: false },
  })
})

describe.each(["en", "fr", "ar"] as Lang[])("the privacy page in %s", (lang) => {
  const privacy = LOCALES[lang].privacy

  it("renders every section of the locale, each under its own heading", async () => {
    // Prepare
    await i18next.changeLanguage(lang)

    // Act
    render(<PrivacyPage />)

    // Assert: the title, the date, then one region per section with all its paragraphs
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(privacy.title)
    // (the matcher collapses the French no-break spaces, so the expectation is collapsed too)
    expect(screen.getByText(squash(privacy.updated))).toBeInTheDocument()
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(privacy.sections.map((s) => s.title))
    for (const section of privacy.sections) {
      const region = screen.getByRole("region", { name: section.title })
      for (const paragraph of section.body) expect(squash(region.textContent)).toContain(squash(plain(paragraph)))
      // several paragraphs read as a list of items, one paragraph as a paragraph
      expect(within(region).queryAllByRole("listitem")).toHaveLength(section.body.length > 1 ? section.body.length : 0)
    }
    expect(document.body.textContent).not.toMatch(/<\/?(b|profile)>/)
  })

  it("links the profile page and the contact address", async () => {
    // Prepare
    await i18next.changeLanguage(lang)

    // Act
    render(<PrivacyPage />)

    // Assert
    const rights = screen.getByRole("region", { name: privacy.sections[8].title })
    expect(within(rights).getByRole("link")).toHaveAttribute("href", "/profile")
    expect(screen.getByRole("link", { name: "souhib.t@icloud.com" })).toHaveAttribute("href", "mailto:souhib.t@icloud.com")
  })
})
