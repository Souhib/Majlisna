import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { bandFor, ScoreBands } from "./ScoreBands"

describe("bandFor", () => {
  // mirrors the server: 1 + round(2 × time left), Python rounding half to even
  it("pays 3 in the first quarter, 2 in the middle half, 1 in the last quarter", () => {
    expect(bandFor(0)).toBe(3)
    expect(bandFor(0.25)).toBe(3)
    expect(bandFor(0.26)).toBe(2)
    expect(bandFor(0.74)).toBe(2)
    expect(bandFor(0.75)).toBe(1)
    expect(bandFor(1)).toBe(1)
  })
})

const hit = (c: HTMLElement) => Array.from(c.querySelectorAll(".score-bands > span")).map((s) => s.getAttribute("data-hit") === "true")

describe("ScoreBands", () => {
  it("lights the band you are in while the clock runs", () => {
    const { container } = render(<ScoreBands elapsedRatio={0.5} />)
    expect(hit(container)).toEqual([false, true, false])
    expect(container.querySelector(".lock-mark")).toBeNull()
  })

  it("once locked in, marks the moment on a thread and says when", () => {
    const { container } = render(<ScoreBands lockedRatio={0.4} lockedRemaining={9} />)
    expect(hit(container)).toEqual([false, true, false])
    expect(container.querySelector(".lock-mark")).not.toBeNull()
    expect(container.querySelector(".score-bands")?.getAttribute("style")).toContain("--at: 0.4")
    expect(container.querySelector(".score-bands")).toHaveTextContent("0:09")
  })

  it("takes the server’s band over its own clock when both are known", () => {
    const { container } = render(<ScoreBands lockedRatio={0.26} lockedRemaining={11} band={3} />)
    expect(hit(container)).toEqual([true, false, false])
  })

  it("marks no band after a wrong answer, but still says when you locked in", () => {
    const { container } = render(<ScoreBands lockedRatio={0.4} lockedRemaining={9} missed />)
    expect(hit(container)).toEqual([false, false, false])
    expect(container.querySelector(".score-bands")).toHaveTextContent("0:09")
  })

  it("states the rule in words for screen readers", () => {
    render(<ScoreBands />)
    expect(screen.getByText("game.quiz.mcq.bandsRule")).toBeInTheDocument()
  })
})
