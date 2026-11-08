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

  it("says who sees the profile as the code shows it: signed-in players only, and the leaderboard is public", () => {
    // Prepare: GET /profiles/users/{id}, GET /users/{id} and the /stats/users/{id}/... reads need a
    // token, and routes/_auth/players/$userId.tsx is behind sign-in (owner decision, 8 November
    // 2026); GET /stats/leaderboard needs none (username, games played and won, win rate, streaks)
    const profile = privacy.sections[4].body[0]

    // Assert
    expect(profile).toMatch(
      {
        en: /^Your profile \(your username, your bio, your country, your profile picture and how many games you have played\), your statistics and your achievements are shown only to signed-in players\./,
        fr: /^Votre profil \(votre pseudo, votre bio, votre pays, votre photo de profil et le nombre de parties que vous avez jouées\), vos statistiques et vos succès ne sont montrés qu’aux joueurs connectés\./,
        ar: /^لا يرى ملفك الشخصي \(اسم المستخدم والنبذة وبلدك وصورة ملفك وعدد الألعاب التي لعبتها\) ولا إحصاءاتك وإنجازاتك إلا اللاعبون المسجّلون\./,
      }[lang],
    )
    expect(profile).toMatch({ en: /The leaderboard is public/, fr: /Le classement est public/, ar: /أما لوحة المتصدرين فمتاحة للجميع/ }[lang])
    expect(profile).not.toMatch({ en: /signed in or not/, fr: /connecté ou non/, ar: /وإن لم يسجّل الدخول/ }[lang])
  })

  it("is dated 8 November 2026, the day it last changed what it says about your data", () => {
    // (the profile behind sign-in, owner decision)
    expect(privacy.updated).toBe({ en: "Last updated: 8 November 2026", fr: "Dernière mise à jour : 8 novembre 2026", ar: "آخر تحديث: 8 نوفمبر 2026" }[lang])
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
