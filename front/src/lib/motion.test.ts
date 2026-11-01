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
    expect(Object.keys(motion).sort()).toEqual(["REREAD", "dur", "ease", "inkDuration"])
    const source = readFileSync(resolve(process.cwd(), "src/lib/motion.ts"), "utf8")
    expect(source).not.toMatch(/from "motion\/react"/)
  })

  it("keeps the CSS tokens' values", () => {
    expect(motion.dur).toEqual({ tap: 0.09, state: 0.18, move: 0.32, authored: 0.64, ceremony: 1.1 })
    expect(motion.ease.ink).toEqual([0.45, 0.05, 0.2, 1])
  })

  it("writes a word at 55 ms a grapheme, within its bounds", () => {
    expect(motion.inkDuration("صبر")).toBeCloseTo(0.365, 3)
    expect(motion.inkDuration("a")).toBe(0.36)
    expect(motion.inkDuration("x".repeat(40))).toBe(0.88)
  })
})
