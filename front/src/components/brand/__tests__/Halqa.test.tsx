import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Halqa, type HalqaSeat } from "../Halqa"

/**
 * The halqa fills (WP-18, F4/I2): the brass thread is ONE circle in every state, so an
 * arrival, a departure and the closing of the ring are transitions of the same element
 * (React used to swap a <path> for a <circle> at quorum, so nothing could transition),
 * and a new seat's lozenge is pressed in once, on arrival.
 */

// vitest runs with `css: false`, so a `?raw` import of a stylesheet is empty: read the file.
const brandCss = readFileSync(resolve(process.cwd(), "src/styles/brand.css"), "utf8")

const YUSUF: HalqaSeat = { id: "a", name: "Yusuf", state: "host" }
const MARYAM: HalqaSeat = { id: "b", name: "Maryam", state: "in" }
const IDRIS: HalqaSeat = { id: "c", name: "Idris", state: "in" }
const BILAL: HalqaSeat = { id: "d", name: "Bilal", state: "in" }

function threadOf(container: HTMLElement) {
  const threads = container.querySelectorAll(".thread")
  expect(threads).toHaveLength(1)
  return threads[0] as SVGCircleElement
}

/** The seat group (the lozenge's own <g>) of the player named `name`. */
function seatOf(container: HTMLElement, name: string) {
  const text = [...container.querySelectorAll("text")].find((t) => t.textContent === name)
  if (!text) throw new Error(`no seat for ${name}`)
  return text.previousElementSibling as SVGGElement
}

/** One CSS rule's body, by its exact selector. */
function rule(css: string, selector: string) {
  const at = css.indexOf(`${selector} {`)
  if (at < 0) return null
  return css.slice(at + selector.length + 2, css.indexOf("}", at))
}

describe("Halqa, the thread", () => {
  it("is one circle with pathLength 1 whose arc runs from the ṣadr to the last seated player", () => {
    const { container } = render(<Halqa seats={[YUSUF, MARYAM]} capacity={8} quorum={3} dir="ltr" />)

    const thread = threadOf(container)
    expect(thread.tagName.toLowerCase()).toBe("circle")
    expect(thread.getAttribute("pathLength")).toBe("1")
    // two seated of eight: the arc spans one step of the ring
    expect(thread.style.getPropertyValue("--arc")).toBe(String(1 / 8))
    expect(thread).toHaveAttribute("data-closed", "false")
  })

  it("closes the ring at quorum on the SAME element, so the closing can be drawn", () => {
    // Prepare
    const { container, rerender } = render(<Halqa seats={[YUSUF, MARYAM]} capacity={8} quorum={3} dir="ltr" />)
    const before = threadOf(container)

    // Act: the third player sits down.
    rerender(<Halqa seats={[YUSUF, MARYAM, IDRIS]} capacity={8} quorum={3} dir="ltr" />)

    // Assert
    const after = threadOf(container)
    expect(after).toBe(before)
    expect(after).toHaveAttribute("data-closed", "true")
    expect(after.style.getPropertyValue("--arc")).toBe("1")
  })

  it("retracts on the exit curve when someone leaves, and arrives on the entry curve", () => {
    // Prepare
    const { container, rerender } = render(<Halqa seats={[YUSUF, MARYAM, IDRIS]} capacity={8} quorum={3} dir="ltr" />)
    expect(threadOf(container)).toHaveAttribute("data-leaving", "false")

    // Act: Idris leaves.
    rerender(<Halqa seats={[YUSUF, MARYAM]} capacity={8} quorum={3} dir="ltr" />)

    // Assert
    expect(threadOf(container)).toHaveAttribute("data-leaving", "true")
    expect(threadOf(container)).toHaveAttribute("data-closed", "false")

    // Act: Bilal sits down.
    rerender(<Halqa seats={[YUSUF, MARYAM, BILAL]} capacity={8} quorum={3} dir="ltr" />)

    // Assert
    expect(threadOf(container)).toHaveAttribute("data-leaving", "false")
  })

  it("starts at the ṣadr in both directions, mirrored (anticlockwise) in Arabic", () => {
    const { container: ltr } = render(<Halqa seats={[YUSUF, MARYAM]} capacity={8} quorum={3} dir="ltr" />)
    const { container: rtl } = render(<Halqa seats={[YUSUF, MARYAM]} capacity={8} quorum={3} dir="rtl" />)

    const ltrTransform = threadOf(ltr).getAttribute("transform") ?? ""
    const rtlTransform = threadOf(rtl).getAttribute("transform") ?? ""
    expect(ltrTransform).toMatch(/^rotate\(-90 /)
    expect(ltrTransform).not.toMatch(/scale/)
    expect(rtlTransform).toMatch(/scale\(-1 1\) rotate\(-90 /)
  })

  it("never closes without a quorum (the home's halqa)", () => {
    const { container } = render(<Halqa seats={[YUSUF, MARYAM, IDRIS]} capacity={8} dir="ltr" />)

    expect(threadOf(container)).toHaveAttribute("data-closed", "false")
    expect(threadOf(container).style.getPropertyValue("--arc")).toBe(String(2 / 8))
  })
})

describe("Halqa, a seat arriving", () => {
  it("presses in only the new seat, and nothing on the first drawing", () => {
    // Prepare: the ring as the page first draws it.
    const { container, rerender } = render(<Halqa seats={[YUSUF, MARYAM]} capacity={8} quorum={3} dir="ltr" />)
    expect(container.querySelectorAll('[data-fresh="true"]')).toHaveLength(0)

    // Act: Idris sits down.
    rerender(<Halqa seats={[YUSUF, MARYAM, IDRIS]} capacity={8} quorum={3} dir="ltr" />)

    // Assert: his lozenge (its own group, the label beside it) and nobody else's.
    expect(seatOf(container, "Idris")).toHaveAttribute("data-fresh", "true")
    expect(seatOf(container, "Idris").getAttribute("class")).toBe("seat")
    expect(seatOf(container, "Maryam")).not.toHaveAttribute("data-fresh")
    expect(seatOf(container, "Yusuf")).not.toHaveAttribute("data-fresh")

    // Act: a re-render that seats nobody (a seat's second line changed).
    rerender(<Halqa seats={[YUSUF, { ...MARYAM, sub: "ready" }, IDRIS]} capacity={8} quorum={3} dir="ltr" />)

    // Assert: Idris keeps his mark (the press is not cut short), still no one else.
    expect(seatOf(container, "Idris")).toHaveAttribute("data-fresh", "true")
    expect(container.querySelectorAll('g.seat[data-fresh="true"]')).toHaveLength(1)

    // Act: Bilal sits down.
    rerender(<Halqa seats={[YUSUF, MARYAM, IDRIS, BILAL]} capacity={8} quorum={3} dir="ltr" />)

    // Assert
    expect(seatOf(container, "Bilal")).toHaveAttribute("data-fresh", "true")
    expect(seatOf(container, "Idris")).not.toHaveAttribute("data-fresh")
  })
})

describe("Halqa, the CSS", () => {
  it("draws the arc with the dash offset and transitions it on the motion tokens", () => {
    const thread = rule(brandCss, ".halqa .thread")
    expect(thread).toMatch(/stroke-dasharray: 1 1;/)
    expect(thread).toMatch(/stroke-dashoffset: calc\(1 - var\(--arc, 0\)\);/)
    expect(thread).toMatch(/stroke-dashoffset var\(--dur-move\) var\(--ease-settle\)/)

    const closed = rule(brandCss, '.halqa .thread[data-closed="true"]')
    expect(closed).toMatch(/stroke-width: 2\.6;/)
    expect(closed).toMatch(/stroke-dashoffset var\(--dur-authored\) var\(--ease-ink\)/)

    const leaving = rule(brandCss, '.halqa .thread[data-leaving="true"]')
    expect(leaving).toMatch(/transition-duration: calc\(var\(--dur-move\) \* 0\.66\);/)
    expect(leaving).toMatch(/transition-timing-function: var\(--ease-in\);/)

    expect(rule(brandCss, '.halqa .seat[data-fresh="true"]')).toMatch(/animation: seat-in var\(--dur-move\) var\(--ease-out\) both;/)
  })
})
