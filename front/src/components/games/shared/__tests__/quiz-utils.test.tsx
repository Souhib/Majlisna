import { render, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { isGameGoneError } from "../game-errors"
import { competitionRanks, Figure, isArabicScript, listFormat, scriptAttrs, useHeldForPhase } from "../quiz-utils"

describe("quiz-utils", () => {
  it("detects Arabic script", () => {
    expect(isArabicScript("زكريا")).toBe(true)
    expect(isArabicScript("Zakariyya")).toBe(false)
    expect(isArabicScript(null)).toBe(false)
  })

  it("gives Arabic content its own lang and direction, anything else dir=auto", () => {
    expect(scriptAttrs("بغداد")).toEqual({ lang: "ar", dir: "rtl" })
    expect(scriptAttrs("Baghdad")).toEqual({ dir: "auto" })
  })

  it("keeps a signed figure left to right, in its own isolate", () => {
    const { container } = render(<Figure>+3</Figure>)
    const bdi = container.querySelector("bdi")
    expect(bdi).toHaveAttribute("dir", "ltr")
    expect(bdi?.className).toContain("num")
  })

  it("ranks ties together (1, 1, 3)", () => {
    expect(competitionRanks([20, 20, 15, 10, 10])).toEqual([1, 1, 3, 4, 4])
    expect(competitionRanks([])).toEqual([])
  })

  it("lists names in the reader's language", () => {
    expect(listFormat(["Maryam", "Idris"], "en")).toBe("Maryam and Idris")
    expect(listFormat(["Maryam", "Idris"], "fr")).toBe("Maryam et Idris")
    expect(listFormat(["Maryam"], "en")).toBe("Maryam")
  })

  it("draws a lagging phase from the state it belongs to", () => {
    const results = { round_phase: "results", answer: "Taif" }
    const next = { round_phase: "playing", answer: null }
    const { result, rerender } = renderHook(({ state, phase }) => useHeldForPhase(state, phase), {
      initialProps: { state: results as { round_phase: string; answer: string | null }, phase: "results" },
    })
    expect(result.current).toBe(results)
    // the server moved on, the screen has not yet: keep drawing the results
    rerender({ state: next, phase: "results" })
    expect(result.current).toBe(results)
    // the screen caught up
    rerender({ state: next, phase: "playing" })
    expect(result.current).toBe(next)
  })

  it("tells a game that is gone from any other failure", () => {
    expect(isGameGoneError({ response: { status: 404, data: {} } })).toBe(true)
    expect(isGameGoneError({ response: { status: 403, data: { message: "You were removed from this game." } } })).toBe(true)
    expect(isGameGoneError({ response: { status: 500, data: { message: "Internal error" } } })).toBe(false)
    expect(isGameGoneError(new Error("offline"))).toBe(false)
    expect(isGameGoneError(null)).toBe(false)
  })
})
