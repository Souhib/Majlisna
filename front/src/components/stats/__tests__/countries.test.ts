import { describe, expect, it } from "vitest"
import { COUNTRY_CODES, countryName, countryOptions } from "@/components/profile/countries"

describe("countries", () => {
  it("holds exactly the alpha-3 codes the server accepts", () => {
    expect(COUNTRY_CODES).toHaveLength(249)
    expect(COUNTRY_CODES).toContain("MAR")
    expect(COUNTRY_CODES).toContain("PSE")
  })

  it("names a country in the page's language and passes an unknown code through", () => {
    expect(countryName("MAR", "en")).toBe("Morocco")
    expect(countryName("mar", "fr")).toBe("Maroc")
    expect(countryName("XYZ", "en")).toBe("XYZ")
    expect(countryName(null, "en")).toBeNull()
  })

  it("sorts the list by name in the reader's language", () => {
    const names = countryOptions("en").map((o) => o.name)
    expect(names).toHaveLength(249)
    expect([...names].sort((a, b) => a.localeCompare(b, "en"))).toEqual(names)
  })
})
