import { render } from "@testing-library/react"
import { existsSync, statSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { ArchFrame } from "../ArchFrame"

/**
 * The Jabreen photograph behind every colophon (FP-15): a 3x phone (390 px, 1170 device
 * px) used to take the 1600w file (207 kB); a 1200w file covers it at about a third.
 */
describe("ArchFrame: the photograph", () => {
  it("offers 800, 1200 and 1600 widths, so a 3x phone stops at 1200", () => {
    // Prepare / Act
    const { container } = render(
      <ArchFrame>
        <p>colophon</p>
      </ArchFrame>,
    )

    // Assert
    const img = container.querySelector(".arch-photo img") as HTMLImageElement
    const widths = (img.getAttribute("srcset") ?? "").split(",").map((c) => c.trim().split(/\s+/))
    expect(widths.map(([, w]) => w)).toEqual(["800w", "1200w", "1600w"])
    expect(widths[1][0]).toMatch(/jabreen-niches\.duo\.1200(-[\w-]+)?\.webp$/)
    expect(img.getAttribute("sizes")).toBe("(max-width: 760px) 100vw, 560px")
  })

  it("ships the 1200w file well under the 1600w one", () => {
    // Prepare
    const dir = resolve(process.cwd(), "src/assets/brand")
    const file = resolve(dir, "jabreen-niches.duo.1200.webp")

    // Act / Assert
    expect(existsSync(file)).toBe(true)
    expect(statSync(file).size).toBeLessThan(100 * 1024)
    expect(statSync(file).size).toBeLessThan(statSync(resolve(dir, "jabreen-niches.duo.1600.webp")).size / 2)
  })
})
