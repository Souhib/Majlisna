import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Colophon } from "../Colophon"
import { Seal } from "../Seal"

/**
 * The colophon's seals (WP-18, F6): they used to press inside the 180 ms phase crossfade, all
 * in the same millisecond. Each is pressed after the crossfade, one stagger step apart.
 */

// vitest runs with `css: false`, so a `?raw` import of a stylesheet is empty: read the file.
const indexCss = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8")

function marks(container: HTMLElement) {
  return [...container.querySelectorAll<HTMLElement>(".brass-seal")]
}

describe("Seal in a set", () => {
  it("carries its place in the set for the stagger", () => {
    const { container } = render(<Seal index={2} title="Unanimous Decision" />)

    const [mark] = marks(container)
    expect(mark).toHaveClass("seal-press")
    expect(mark).toHaveAttribute("data-seal-index", "2")
    expect(mark.style.getPropertyValue("--i")).toBe("2")
  })

  it("alone, is pressed at once (no place, no delay)", () => {
    const { container } = render(<Seal size={26} />)

    const [mark] = marks(container)
    expect(mark).not.toHaveAttribute("data-seal-index")
    expect(mark.style.getPropertyValue("--i")).toBe("")
  })

  it("the colophon numbers its seals in reading order", () => {
    const { container } = render(
      <Colophon
        arch={false}
        title="Game Over"
        seals={[
          { title: "Taste of Victory", caption: "Maryam" },
          { title: "Unanimous Decision", caption: "the whole table" },
          { title: "Last Survivor", caption: "Idris" },
        ]}
      />,
    )

    expect(marks(container).map((m) => m.getAttribute("data-seal-index"))).toEqual(["0", "1", "2"])
  })
})

describe("Seal press, the CSS", () => {
  it("waits for the phase crossfade, then steps by --stagger, capped at 240 ms, reduced motion too", () => {
    const at = indexCss.indexOf(".seal-press[data-seal-index] {")
    expect(at).toBeGreaterThan(-1)
    const body = indexCss.slice(at, indexCss.indexOf("}", at))
    expect(body).toMatch(/animation-delay: calc\(var\(--dur-state\) \+ min\(var\(--i, 0\) \* var\(--stagger\), 240ms\)\);/)
  })
})
