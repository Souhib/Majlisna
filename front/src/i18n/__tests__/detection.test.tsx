import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { i18n as I18n } from "i18next"
import type { ComponentType, ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import ar from "@/i18n/locales/ar.json"
import en from "@/i18n/locales/en.json"
import fr from "@/i18n/locales/fr.json"

/**
 * The app shell's language, booted for real: the i18n module as main.tsx imports it (the
 * detector, the lazy locale chunks), the root layout's <html dir/lang>, and the first-visit
 * dialog. The setup file mocks react-i18next to print keys; this file needs the real one.
 */
vi.unmock("react-i18next")

const location = vi.hoisted(() => ({ pathname: "/" }))
vi.mock("@tanstack/react-router", () => ({
  createRootRoute: (options: Record<string, unknown>) => ({ options }),
  Outlet: () => null,
  useLocation: () => location,
  useRouterState: () => location.pathname, // ErrorBoundary's page
}))
vi.mock("@tanstack/react-router-devtools", () => ({ TanStackRouterDevtools: () => null }))
vi.mock("@/components/layout/main-nav", () => ({ MainNav: () => null }))
vi.mock("@/components/layout/footer", () => ({ Footer: () => null }))
vi.mock("@/components/NotFound", () => ({ NotFound: () => null }))
vi.mock("@/components/ui/toaster", () => ({ Toaster: () => null }))
vi.mock("@/providers", () => {
  const Pass = ({ children }: { children: ReactNode }) => <>{children}</>
  return { AuthProvider: Pass, QueryProvider: Pass, ThemeProvider: Pass }
})

const STORAGE_KEY = "majlisna-language"
const FIRST_VISIT_KEY = "majlisna-first-visit-complete"
const GSI_SCRIPT = 'script[src^="https://accounts.google.com/gsi/client"]'

/** A browser that reports `languages` (navigator.languages; navigator.language is the first). */
function browserSays(languages: string[]) {
  vi.spyOn(window.navigator, "languages", "get").mockReturnValue(languages)
  vi.spyOn(window.navigator, "language", "get").mockReturnValue(languages[0])
}

/** Import the i18n module fresh, as a page load does, and wait for its first locale. */
async function boot(): Promise<I18n> {
  vi.resetModules()
  const { default: i18n, i18nReady } = await import("@/i18n")
  await i18nReady
  return i18n
}

/** Render the root layout and let its effects and any lazy chunk it asked for settle. */
async function renderShell() {
  const { Route } = await import("@/routes/__root")
  const RootLayout = (Route as unknown as { options: { component: ComponentType } }).options.component
  await act(async () => {
    render(<RootLayout />)
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

function resetDocument() {
  localStorage.clear()
  sessionStorage.clear()
  document.documentElement.dir = "ltr"
  document.documentElement.lang = "en"
}

beforeEach(resetDocument)

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  location.pathname = "/"
  resetDocument()
})

describe("language detection", () => {
  it("gives a regional Arabic browser (ar-SA) Arabic, right to left, stored as 'ar', even when the welcome dialog is dismissed", async () => {
    // Prepare: a first visit from a phone set to Arabic (Saudi Arabia)
    browserSays(["ar-SA"])
    const i18n = await boot()
    await renderShell()
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    // Act: Escape on the welcome dialog (it keeps the detected language)
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())

    // Assert
    expect(i18n.language).toBe("ar")
    expect(document.documentElement.dir).toBe("rtl")
    expect(document.documentElement.lang).toBe("ar")
    expect(localStorage.getItem(STORAGE_KEY)).toBe("ar")
    expect(localStorage.getItem(FIRST_VISIT_KEY)).toBe("true")
  })

  it.each([
    ["fr-FR", "fr"],
    ["ar-MA", "ar"],
    ["en-GB", "en"],
  ])("rewrites a stored regional tag (%s) to its language (%s) at boot", async (stored, expected) => {
    // Prepare: a value saved before the detection was normalised
    localStorage.setItem(STORAGE_KEY, stored)
    browserSays(["en-US"])

    // Act
    const i18n = await boot()

    // Assert
    expect(i18n.language).toBe(expected)
    expect(localStorage.getItem(STORAGE_KEY)).toBe(expected)
  })

  it("normalises a regional tag passed straight to changeLanguage too", async () => {
    // Prepare
    browserSays(["en-US"])
    const i18n = await boot()

    // Act
    await i18n.changeLanguage("fr-CA")

    // Assert
    expect(i18n.language).toBe("fr")
    expect(localStorage.getItem(STORAGE_KEY)).toBe("fr")
  })

  it("falls back to English for a browser language the app does not speak", async () => {
    // Prepare
    browserSays(["de-DE", "de"])

    // Act
    const i18n = await boot()

    // Assert
    expect(i18n.language).toBe("en")
  })
})

describe("locale downloads", () => {
  it("an English first visit downloads no French or Arabic locale, and the dialog still asks in all three", async () => {
    // Prepare
    browserSays(["en-US", "en"])
    const i18n = await boot()

    // Act
    await renderShell()

    // Assert: each prompt is in its own language…
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent(en.ui.chooseLanguage)
    expect(dialog).toHaveTextContent(fr.ui.chooseLanguage)
    expect(dialog).toHaveTextContent(ar.ui.chooseLanguage)
    // …without fetching the two other locales for three short lines
    expect(i18n.hasResourceBundle("en", "translation")).toBe(true)
    expect(i18n.hasResourceBundle("fr", "translation")).toBe(false)
    expect(i18n.hasResourceBundle("ar", "translation")).toBe(false)
  })

  it.each(["fr", "ar"] as const)("a %s session never downloads the English locale", async (lang) => {
    // Prepare: a returning visitor (no dialog)
    localStorage.setItem(FIRST_VISIT_KEY, "true")
    localStorage.setItem(STORAGE_KEY, lang)

    // Act
    const i18n = await boot()
    await renderShell()

    // Assert
    expect(i18n.language).toBe(lang)
    expect(i18n.hasResourceBundle(lang, "translation")).toBe(true)
    expect(i18n.hasResourceBundle("en", "translation")).toBe(false)
  })

  it("reloads the page once when a locale chunk is gone after a deploy, never in a loop", async () => {
    // Prepare
    browserSays(["en-US"])
    await boot()
    const { loadLocale } = await import("@/i18n")
    const reload = vi.fn()
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    // Act: the chunk named by the old build answers 404
    await expect(loadLocale("xx", reload)).rejects.toThrow()

    // Assert
    expect(reload).toHaveBeenCalledTimes(1)
    expect(warn).not.toHaveBeenCalled()

    // Act: the reloaded page fails on it again
    await expect(loadLocale("xx", reload)).rejects.toThrow()

    // Assert: no second reload in this tab, and the failure is said, not swallowed
    expect(reload).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it("re-arms the reload once a locale loads again", async () => {
    // Prepare: a failed load already reloaded this tab
    browserSays(["en-US"])
    await boot()
    const { loadLocale } = await import("@/i18n")
    const reload = vi.fn()
    await expect(loadLocale("xx", reload)).rejects.toThrow()

    // Act: the next load succeeds, then a later deploy removes a chunk again
    await expect(loadLocale("fr", reload)).resolves.toBeTruthy()
    await expect(loadLocale("xx", reload)).rejects.toThrow()

    // Assert
    expect(reload).toHaveBeenCalledTimes(2)
  })
})

describe("the app shell", () => {
  it.each(["/", "/about", "/game/undercover/123"])("loads no Google script on %s, even in a build with a client id", async (pathname) => {
    // Prepare
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    localStorage.setItem(FIRST_VISIT_KEY, "true")
    location.pathname = pathname
    browserSays(["en-US"])
    await boot()

    // Act
    await renderShell()

    // Assert
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
  })
})
