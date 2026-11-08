import { render, screen, within } from "@testing-library/react"
import i18next from "i18next"
import { type ComponentType, type ReactNode } from "react"
import { initReactI18next } from "react-i18next"
import { beforeAll, describe, expect, it, vi } from "vitest"
import { PASSWORD_MIN_LENGTH, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH } from "@/components/auth/validation"
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

const { Route } = await import("@/routes/terms")
const TermsPage = (Route as unknown as { options: { component: ComponentType } }).options.component

const LOCALES = { en, fr, ar }
type Lang = keyof typeof LOCALES
interface Section {
  title: string
  body: string[]
}

/** A paragraph as the reader sees it: the marks are markup, not text. */
const plain = (s: string) => s.replace(/<\/?(b|profile|privacy|terms)>/g, "")
const squash = (s: string | null) => (s ?? "").replace(/\s+/g, " ").trim()

/** The terms of each locale, typed: the test fails to compile until they exist. */
const termsOf = (lang: Lang) => (LOCALES[lang] as unknown as { terms: { title: string; updated: string; sections: Section[] } }).terms

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en }, fr: { translation: fr }, ar: { translation: ar } },
    interpolation: { escapeValue: false },
  })
})

describe.each(["en", "fr", "ar"] as Lang[])("the terms page in %s", (lang) => {
  const terms = termsOf(lang)

  it("renders every section of the locale, each under its own heading, dated 8 November 2026", async () => {
    // Prepare
    await i18next.changeLanguage(lang)

    // Act
    render(<TermsPage />)

    // Assert: the title, the date, then one region per section with all its paragraphs
    expect(terms.updated).toBe({ en: "Last updated: 8 November 2026", fr: "Dernière mise à jour : 8 novembre 2026", ar: "آخر تحديث: 8 نوفمبر 2026" }[lang])
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(terms.title)
    // (the matcher collapses the French no-break spaces, so the expectation is collapsed too)
    expect(screen.getByText(squash(terms.updated))).toBeInTheDocument()
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(terms.sections.map((s) => s.title))
    for (const section of terms.sections) {
      const region = screen.getByRole("region", { name: section.title })
      for (const paragraph of section.body) expect(squash(region.textContent)).toContain(squash(plain(paragraph)))
      // several paragraphs read as a list of items, one paragraph as a paragraph
      expect(within(region).queryAllByRole("listitem")).toHaveLength(section.body.length > 1 ? section.body.length : 0)
    }
    expect(document.body.textContent).not.toMatch(/<\/?(b|profile|privacy|terms)>/)
  })

  it("links the privacy policy, the profile page (where an account is deleted) and the contact address", async () => {
    // Prepare
    await i18next.changeLanguage(lang)

    // Act
    render(<TermsPage />)

    // Assert
    expect(screen.getAllByRole("link").filter((a) => a.getAttribute("href") === "/privacy").length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByRole("link").filter((a) => a.getAttribute("href") === "/profile")).toHaveLength(1)
    expect(screen.getByRole("link", { name: "souhib.t@icloud.com" })).toHaveAttribute("href", "mailto:souhib.t@icloud.com")
  })

  it("reads in the page's direction, the address always left to right", async () => {
    // Prepare: the root layout sets <html dir> from i18n.dir() (__root.tsx)
    await i18next.changeLanguage(lang)

    // Act
    render(<TermsPage />)

    // Assert
    expect(i18next.dir(lang)).toBe(lang === "ar" ? "rtl" : "ltr")
    expect(screen.getByText("souhib.t@icloud.com")).toHaveAttribute("dir", "ltr")
  })

  it("states the account rules the server enforces: the password and username lengths", () => {
    // Prepare: the account section (the code: backend constants, mirrored in validation.ts)
    const account = terms.sections[1].body.join(" ")

    // Assert
    expect(account).toMatch(new RegExp(`\\b${PASSWORD_MIN_LENGTH}\\b`))
    expect(account).toMatch(new RegExp(`\\b${USERNAME_MIN_LENGTH}\\b`))
    expect(account).toMatch(new RegExp(`\\b${USERNAME_MAX_LENGTH}\\b`))
    for (const forbidden of ["@", "/", "\\"]) expect(account).toContain(forbidden)
  })

  it("says who reads your username and bio as the code shows them: signed-in players, and anyone on the leaderboard", () => {
    // Prepare: GET /profiles/users/{id} needs a token and routes/_auth/players/$userId.tsx is
    // behind sign-in (owner decision, 8 November 2026); the public leaderboard names its players
    const whatYouWrite = terms.sections[5].body.join(" ")

    // Assert
    expect(whatYouWrite).toMatch(
      {
        en: /signed-in players see your username and your bio on your profile, anyone can see your username on the leaderboard if you rank in it/,
        fr: /les joueurs connectés voient votre pseudo et votre bio sur votre profil, tout le monde peut voir votre pseudo au classement si vous y figurez/,
        ar: /ويرى اللاعبون المسجّلون اسمك ونبذتك في ملفك الشخصي، ويستطيع أي أحد رؤية اسمك في لوحة المتصدرين إن ظهرت فيها/,
      }[lang],
    )
    expect(whatYouWrite).not.toMatch({ en: /public profile/, fr: /profil public/, ar: /ملفك الشخصي العام/ }[lang])
  })

  it("never claims a scholarly review of the religious content (PRODUCT.md, Evidence on Hand)", () => {
    // Prepare
    const religious = terms.sections.map((s) => s.body.join(" ")).join(" ")

    // Assert: not a fatwa, and not reviewed by scholars
    expect(religious).toMatch({ en: /not a fatwa/, fr: /ni une fatwa/, ar: /ليست فتوى/ }[lang])
    expect(religious).toMatch({ en: /have not been reviewed by scholars/, fr: /n’ont pas été relus par des savants/, ar: /لم يراجعها العلماء/ }[lang])
  })
})

describe("the terms of use", () => {
  it("names no law, court, arbitration, liability cap, minimum age or company: the owner has not decided them", () => {
    // Prepare: the English reference text (fr and ar translate it)
    const text = [en.terms.intro, ...en.terms.sections.flatMap((s) => [s.title, ...s.body])].join(" ")

    // Assert: these come from the owner, never from a guess (remove a word here when he decides it)
    expect(text).not.toMatch(/\blaw\b|court|jurisdiction|arbitrat|liabilit|years old|minimum age|company/i)
  })
})
