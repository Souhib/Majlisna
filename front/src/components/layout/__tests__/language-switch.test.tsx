import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { formatPrayerTime } from "@/components/prayer-times/PrayerTimesNav"
import { currentLanguage, LanguageSwitch } from "../language-switch"

// The language i18next holds, settable per test (the setup file's mock pins "en").
const i18nState = vi.hoisted(() => ({ language: "en", changeLanguage: vi.fn() }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: i18nState }),
}))

afterEach(() => {
  document.documentElement.dir = "ltr"
  document.documentElement.lang = "en"
  localStorage.removeItem("majlisna-language")
  i18nState.language = "en"
  i18nState.changeLanguage.mockClear()
})

describe("LanguageSwitch", () => {
  it("names each language in its own language and marks the current one", () => {
    // Prepare / Act
    render(<LanguageSwitch />)

    // Assert
    expect(screen.getByRole("group", { name: "nav.switchLanguage" })).toBeInTheDocument()
    const english = screen.getByRole("button", { name: "English" })
    const french = screen.getByRole("button", { name: "Français" })
    const arabic = screen.getByRole("button", { name: "العربية" })
    expect(english).toHaveAttribute("aria-pressed", "true")
    expect(french).toHaveAttribute("aria-pressed", "false")
    // the visible label is the short code; the full name is what assistive tech reads
    expect(arabic).toHaveTextContent("ع")
    expect(arabic).toHaveAttribute("lang", "ar")
  })

  it("switches in one tap: stores the choice and turns the page right to left for Arabic", () => {
    // Prepare
    render(<LanguageSwitch />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "العربية" }))

    // Assert
    expect(localStorage.getItem("majlisna-language")).toBe("ar")
    expect(document.documentElement.dir).toBe("rtl")
    expect(document.documentElement.lang).toBe("ar")
  })

  it("stores the bare code when the language was detected with a region (ar-SA), though ع already reads as current", () => {
    // Prepare: a visitor whose browser said ar-SA before the detection was normalised
    i18nState.language = "ar-SA"
    render(<LanguageSwitch />)
    const arabic = screen.getByRole("button", { name: "العربية" })
    expect(arabic).toHaveAttribute("aria-pressed", "true")

    // Act
    fireEvent.click(arabic)

    // Assert: the tap repairs the stored tag and the direction
    expect(i18nState.changeLanguage).toHaveBeenCalledWith("ar")
    expect(localStorage.getItem("majlisna-language")).toBe("ar")
    expect(document.documentElement.dir).toBe("rtl")
    expect(document.documentElement.lang).toBe("ar")
  })

  it("does nothing when the exact language is already the one chosen", () => {
    // Prepare
    i18nState.language = "fr"
    render(<LanguageSwitch />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Français" }))

    // Assert
    expect(i18nState.changeLanguage).not.toHaveBeenCalled()
  })

  it("spells the names out in the menu sheet", () => {
    // Prepare / Act
    render(<LanguageSwitch variant="full" />)

    // Assert
    expect(screen.getByRole("button", { name: "Français" })).toHaveTextContent("Français")
  })
})

describe("currentLanguage", () => {
  it("maps i18next codes onto the three interface languages", () => {
    expect(currentLanguage("ar-SA")).toBe("ar")
    expect(currentLanguage("fr-FR")).toBe("fr")
    expect(currentLanguage("en-US")).toBe("en")
    expect(currentLanguage("AR")).toBe("ar")
    expect(currentLanguage("fr_CA")).toBe("fr")
    // Mapudungun starts with "ar" but is not Arabic
    expect(currentLanguage("arn")).toBe("en")
    expect(currentLanguage(undefined)).toBe("en")
  })
})

describe("formatPrayerTime", () => {
  it("reads a 24-hour clock in Western digits, in the city's time zone", () => {
    // Prepare
    const maghrib = new Date("2026-10-28T15:42:00Z")

    // Act / Assert
    expect(formatPrayerTime(maghrib, "Asia/Riyadh")).toBe("18:42")
    expect(formatPrayerTime(maghrib, "UTC")).toBe("15:42")
  })

  it("falls back to the device's zone for an unknown stored zone", () => {
    expect(formatPrayerTime(new Date("2026-10-28T15:42:00Z"), "Not/AZone")).toMatch(/^\d{2}:\d{2}$/)
  })
})
