import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { formatPrayerTime } from "@/components/prayer-times/PrayerTimesNav"
import { currentLanguage, LanguageSwitch } from "../language-switch"

afterEach(() => {
  document.documentElement.dir = "ltr"
  document.documentElement.lang = "en"
  localStorage.removeItem("majlisna-language")
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
