import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import * as motion from "./motion"

/**
 * The motion grammar's script side (WP-18, F5): nothing animates through motion/react, so
 * only the tokens and the writing time remain (the variants were never imported anywhere).
 */
describe("lib/motion", () => {
  it("exports the tokens and the writing time, no motion/react variants", () => {
    expect(Object.keys(motion).sort()).toEqual(["REREAD", "bezier", "dur", "ease", "erase", "inkDuration", "stagger"])
    const source = readFileSync(resolve(process.cwd(), "src/lib/motion.ts"), "utf8")
    expect(source).not.toMatch(/from "motion\/react"/)
  })

  it("keeps the CSS tokens' values", () => {
    expect(motion.dur).toEqual({ tap: 0.09, state: 0.18, move: 0.32, authored: 0.64, ceremony: 1.1 })
    expect(motion.ease.ink).toEqual([0.45, 0.05, 0.2, 1])
    // --stagger (30 ms) and the seals' 240 ms cap, as numbers for the scripts that stagger
    expect(motion.stagger).toEqual({ step: 0.03, cap: 0.24 })
  })

  it("recedes an erased seat to the CSS tokens' levels: the name at the muted token's contrast, the lozenge at .45", () => {
    // ERASE (ANIM-2): the receded state is the CSS's (--erase-ink, --erase-mark); the script
    // animates from full ink to exactly those values, so they must agree
    const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8")
    expect(motion.erase).toEqual({ ink: 0.72, mark: 0.45 })
    expect(css).toMatch(/--erase-ink: 0\.72;/)
    expect(css).toMatch(/--erase-mark: 0\.45;/)
  })

  it("hands a curve to Web Animations as the CSS writes it", () => {
    expect(motion.bezier(motion.ease.ink)).toBe("cubic-bezier(0.45, 0.05, 0.2, 1)")
    expect(motion.bezier(motion.ease.settle)).toBe("cubic-bezier(0.22, 1, 0.36, 1)")
  })

  it("writes a word at 55 ms a grapheme, within its bounds", () => {
    expect(motion.inkDuration("صبر")).toBeCloseTo(0.365, 3)
    expect(motion.inkDuration("a")).toBe(0.36)
    expect(motion.inkDuration("x".repeat(40))).toBe(0.88)
  })
})
