import { afterEach, describe, expect, it, vi } from "vitest"

/**
 * "Samar Figures" (Readex digits in front of Marcellus) must draw at the weight of the
 * letters around them, not at whatever weight the title asks for.
 */
describe("display figures face", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it("registers the digits pinned to one fixed weight, Marcellus's", async () => {
    // Prepare: a FontFace stand-in that records its descriptors
    const registered: { family: string; descriptors: FontFaceDescriptors }[] = []
    class FakeFontFace {
      constructor(family: string, _source: string, descriptors: FontFaceDescriptors) {
        registered.push({ family, descriptors })
      }
    }
    vi.stubGlobal("FontFace", FakeFontFace)
    const add = vi.fn()
    Object.defineProperty(document, "fonts", { value: { add }, configurable: true })

    // Act
    const { DISPLAY_FIGURES_WEIGHT } = await import("./fonts")

    // Assert: a single value (a range would follow the title's 400 or 700), digits only
    const figures = registered.filter((r) => r.family === "Samar Figures")
    expect(figures).toHaveLength(1)
    expect(figures[0].descriptors.weight).toBe(String(DISPLAY_FIGURES_WEIGHT))
    expect(figures[0].descriptors.weight).not.toContain(" ")
    expect(figures[0].descriptors.unicodeRange).toBe("U+0030-0039")
    expect(add).toHaveBeenCalledTimes(1)
    // lighter than a 400 Readex digit, which read as bold beside Marcellus
    expect(DISPLAY_FIGURES_WEIGHT).toBeLessThan(400)
  })
})
