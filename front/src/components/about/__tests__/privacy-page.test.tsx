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

  it("names what the tab keeps in a room as well as in a game: the samar riddle on screen", () => {
    // sessionStorage `majlisna-riddle:<room>:<scope>` is written in the lobby too, not only in a game
    const tab = privacy.sections[3].body[2]
    expect(tab).toMatch(
      { en: /^<b>In a room and during a game:<\/b>/, fr: /^<b>Dans un salon et pendant une partie\u00a0:<\/b>/, ar: /^<b>في الغرفة وفي أثناء اللعب:<\/b>/ }[
        lang
      ],
    )
    expect(tab).toMatch({ en: /riddle/, fr: /énigme/, ar: /اللغز/ }[lang])
  })

  it("says who sees the profile as the code shows it: the username and bio to anyone, the country and picture once signed in", () => {
    // Prepare: GET /profiles/users/{id} asks for no token (username, bio, games played) and
    // routes/players/$userId.tsx renders it signed out; GET /users/{id} (country, picture) needs one
    const profile = privacy.sections[4].body[0]

    // Assert
    expect(profile).toMatch(
      {
        en: /^Anyone, signed in or not, can see your public profile: your username, your bio and how many games you have played\./,
        fr: /^Tout le monde, connecté ou non, peut voir votre profil public : votre pseudo, votre bio et le nombre de parties que vous avez jouées\./,
        ar: /^يستطيع أي أحد، وإن لم يسجّل الدخول، رؤية ملفك الشخصي العام: اسم المستخدم والنبذة وعدد الألعاب التي لعبتها\./,
      }[lang],
    )
    expect(profile).toMatch(
      {
        en: /Your country and your profile picture are shown only to signed-in players\./,
        fr: /Votre pays et votre photo de profil ne sont montrés qu’aux joueurs connectés\./,
        ar: /أما بلدك وصورة ملفك فلا يراهما إلا اللاعبون المسجّلون\./,
      }[lang],
    )
  })

  it("is dated 7 November 2026, the day it last changed what it says about your data", () => {
    // (the profile's visibility, corrected to what the code shows)
    expect(privacy.updated).toBe({ en: "Last updated: 7 November 2026", fr: "Dernière mise à jour : 7 novembre 2026", ar: "آخر تحديث: 7 نوفمبر 2026" }[lang])
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

  it("links the terms of use, once, after the contact address", async () => {
    // Prepare
    await i18next.changeLanguage(lang)

    // Act
    render(<PrivacyPage />)

    // Assert
    const links = screen.getAllByRole("link")
    const terms = links.filter((a) => a.getAttribute("href") === "/terms")
    expect(terms).toHaveLength(1)
    expect(links.indexOf(terms[0])).toBeGreaterThan(links.indexOf(screen.getByRole("link", { name: "souhib.t@icloud.com" })))
  })
})
