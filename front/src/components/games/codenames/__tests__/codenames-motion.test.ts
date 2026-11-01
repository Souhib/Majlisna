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

describe("The clue written in (ANIM-3)", () => {
  /** The clue section's declarations, comments left out. */
  const clueRules = () => css.slice(css.indexOf("/* --- the clue on the table"), css.indexOf("/* --- the board")).replace(/\/\*[\s\S]*?\*\//g, "")

  it("clips the banner's inline axis, so the travelling pen never makes the page scroll", () => {
    expect(rule(".cn-clue")).toMatch(/overflow-x: clip;/)
    expect(rule(".cn-clue")).not.toMatch(/overflow(-y)?: (hidden|clip)/)
  })

  it("gives the pen a STATIC soft edge at its reading end, longer than the word by exactly the room its ink pads", () => {
    const pen = rule(".cn-clue-pen") ?? ""
    expect(pen).toMatch(/display: block;/)
    expect(pen).toMatch(/mask-image: linear-gradient\(var\(--pen-to\), #000 calc\(100% - var\(--pen-edge\)\), transparent\);/)
    expect(pen).toMatch(/margin-block: calc\(-1 \* var\(--pen-head\)\);/)
    expect(pen).toMatch(/margin-inline: calc\(-1 \* var\(--pen-room\)\) calc\(-1 \* \(var\(--pen-room\) \+ var\(--pen-edge\)\)\);/)
    expect(rule('.cn-clue-pen[data-dir="rtl"]')).toMatch(/--pen-to: to left;/)
    const ink = rule(".cn-clue-ink") ?? ""
    expect(ink).toMatch(/display: block;/)
    expect(ink).toMatch(/padding-block: var\(--pen-head\);/)
    expect(ink).toMatch(/padding-inline: var\(--pen-room\) calc\(var\(--pen-room\) \+ var\(--pen-edge\)\);/)
  })

  it("leaves the timing to the script: no CSS animation, transition or mask sweep on the clue", () => {
    expect(clueRules()).not.toMatch(/animation|transition|--ink-pos|will-change/)
  })

  it("draws the count's lozenges in a ::before, so the stamp's transform never meets the rotation", () => {
    expect(rule(".cn-clue-loz > i")).not.toMatch(/rotate|scale/)
    expect(rule(".cn-clue-loz > i::before")).toMatch(/rotate: 45deg;/)
    expect(rule(".cn-clue-loz > i::before")).toMatch(/background: var\(--brass\);/)
  })

  it("draws the lozenges only on a banner wide enough for them, so they never wrap the guess column", () => {
    // measured at 390 px: with 2–4 lozenges an 11–13 letter clue pushed "2 left, plus a bonus"
    // to another line and the banner grew 17.5–52.5 px; from a 530 px banner nothing grew
    expect(rule(".cn-clue")).toMatch(/container-type: inline-size;/)
    const narrow = css.indexOf("@container (max-width: 479px)")
    expect(narrow).toBeGreaterThan(-1)
    expect(rule(".cn-clue-loz", narrow)).toMatch(/display: none;/)
  })

  it("keeps an identity transform on every box the script moves, so an animation's end lays nothing out", () => {
    const moved = rule(".cn-clue-pen,\n  .cn-clue-ink,\n  .cn-clue-n,\n  .cn-clue-loz > i")
    expect(moved).toMatch(/transform: translateX\(0\);/)
  })

  it("reserves the clue's height at every width, from the same type sizes the clue is set in", () => {
    const reserve = /min-height: calc\(2px \+ 2 \* (10|12)px \+ max\(13px \* 1\.25 \+ 0\.25rem \+ clamp\(20px, 2vw, 30px\) \* 1\.35, 3 \* 12\.5px \* 1\.4\)\);/
    expect(rule(".cn-clue", css.indexOf("@media (max-width: 639px)"))).toMatch(reserve)
    expect(rule(".cn-clue", css.indexOf("@media (min-width: 640px)", css.indexOf("/* --- the clue on the table")))).toMatch(reserve)
    // the sizes it is computed from (mt-1 is 0.25rem: 4.4 px in Arabic, where the rem is 110 %)
    expect(rule(".cn-clue-word")).toMatch(/font-size: clamp\(20px, 2vw, 30px\);/)
    expect(rule('.cn-clue-word[data-script="ar"]')).toMatch(/line-height: 1\.35;/)
    expect(rule(".cn-clue-rest")).toMatch(/font: 400 12\.5px \/ 1\.4 var\(--f-ui\);/)
  })
})
