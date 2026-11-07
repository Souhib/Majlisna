import { render, screen } from "@testing-library/react"
import i18next from "i18next"
import { type ComponentType, type ReactNode } from "react"
import { initReactI18next } from "react-i18next"
import { beforeAll, describe, expect, it, vi } from "vitest"
import ar from "@/i18n/locales/ar.json"
import en from "@/i18n/locales/en.json"
import fr from "@/i18n/locales/fr.json"

/**
 * The sign-up page names what creating an account accepts: one sentence under the form,
 * linking the terms of use and the privacy policy (owner request, 3 November 2026), and no
 * checkbox. The real strings, in the three languages: the sentence is one Trans string
 * whose two links move with each language's word order.
 */
vi.unmock("react-i18next")

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useSearch: () => ({}) }),
  useNavigate: () => vi.fn(),
  Link: ({ children, to, className }: { children: ReactNode; to: string; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))
vi.mock("@/api/generated", () => ({
  useRegisterApiV1AuthRegisterPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLoginApiV1AuthLoginPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ login: vi.fn() }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))

const { Route } = await import("@/routes/auth/register")
const RegisterPage = (Route as unknown as { options: { component: ComponentType } }).options.component

const LOCALES = { en, fr, ar }
type Lang = keyof typeof LOCALES

const squash = (s: string | null) => (s ?? "").replace(/\s+/g, " ").trim()

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en }, fr: { translation: fr }, ar: { translation: ar } },
    interpolation: { escapeValue: false },
  })
})

describe.each(["en", "fr", "ar"] as Lang[])("the sign-up page in %s", (lang) => {
  it("says, under the form, that creating an account accepts the terms of use and the privacy policy", async () => {
    // Prepare
    await i18next.changeLanguage(lang)
    const sentence = (LOCALES[lang].auth as unknown as { acceptTerms: string }).acceptTerms

    // Act
    const { container } = render(<RegisterPage />)

    // Assert: one sentence after the form, its two links to the two pages, and no checkbox
    const terms = screen.getByRole("link", { name: squash(sentence.match(/<terms>(.*?)<\/terms>/)?.[1] ?? "") })
    const privacy = screen.getByRole("link", { name: squash(sentence.match(/<privacy>(.*?)<\/privacy>/)?.[1] ?? "") })
    expect(terms).toHaveAttribute("href", "/terms")
    expect(privacy).toHaveAttribute("href", "/privacy")
    const line = terms.closest("p")
    expect(line).not.toBeNull()
    expect(line).toContainElement(privacy)
    expect(squash(line?.textContent ?? "")).toBe(squash(sentence.replace(/<\/?(terms|privacy)>/g, "")))
    const form = container.querySelector("form")
    expect(form).not.toBeNull()
    expect(form?.contains(line)).toBe(false)
    expect(form?.compareDocumentPosition(line as Node)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(screen.queryByRole("checkbox")).toBeNull()
  })
})
