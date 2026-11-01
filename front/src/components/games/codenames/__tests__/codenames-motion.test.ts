import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * The Codenames stylesheet's motion and layout contract (WP-18). vitest runs with
 * `css: false`, so these read the file; the measured guards (compositing, CLS at 390 px)
 * are the browser's job.
 */
const css = readFileSync(resolve(process.cwd(), "src/styles/pages/codenames.css"), "utf8")

/** One CSS rule's body, by its exact selector (the first occurrence after `from`). */
function rule(selector: string, from = 0) {
  const at = css.indexOf(`${selector} {`, from)
  if (at < 0) return null
  return css.slice(at + selector.length + 2, css.indexOf("}", at))
}

describe("Codenames weaves (F11)", () => {
  it("weaves by translating the band inside a clipped box, never by animating clip-path", () => {
    expect(css).not.toMatch(/clip-path/)
    const weave = css.slice(css.indexOf("@keyframes cn-weave {"), css.indexOf("@keyframes cn-weave-rtl {"))
    expect(weave).toMatch(/transform: translateX\(-100%\);/)
    const weaveRtl = css.slice(css.indexOf("@keyframes cn-weave-rtl {"))
    expect(weaveRtl.slice(0, weaveRtl.indexOf("}\n}"))).toMatch(/transform: translateX\(100%\);/)
  })

  it("clips a freshly turned card to its own box, so its selvedge slides in from the reading start", () => {
    expect(rule('.cn-card[data-fresh="true"]')).toMatch(/overflow: hidden;/)
    expect(rule('.cn-card[data-fresh="true"]::after')).toMatch(/animation: cn-weave var\(--dur-authored\) var\(--ease-ink\) both;/)
  })

  it("weaves the veil's band as a layer inside the band, which clips it", () => {
    expect(rule(".cn-veil .cn-veil-band")).toMatch(/overflow: hidden;/)
    expect(rule(".cn-veil .cn-veil-band::before")).toMatch(/animation: cn-weave var\(--dur-ceremony\) var\(--ease-ink\) both;/)
  })
})

describe("The clue banner (FP-18)", () => {
  it("reserves the clue's height on phones, so the board does not move when a clue arrives", () => {
    const phone = css.indexOf("@media (max-width: 639px)")
    expect(phone).toBeGreaterThan(-1)
    expect(rule(".cn-clue", phone)).toMatch(/min-height: /)
  })
})
