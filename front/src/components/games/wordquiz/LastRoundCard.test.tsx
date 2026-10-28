import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { LastRoundCard, lastRoundFrom, recallLastRound, rememberLastRound } from "./LastRoundCard"

describe("LastRoundCard", () => {
  it("names the last word, who found it first, at which hint, for how much", () => {
    render(<LastRoundCard last={{ round: 2, answer: "Zakariyya", finder: { username: "Maryam", hint: 2, points: 5 } }} />)
    expect(screen.getByText("Zakariyya")).toBeInTheDocument()
    expect(screen.getByText(/game.quiz.kalimat.firstToFind/)).toBeInTheDocument()
    expect(screen.getByText("+5")).toBeInTheDocument()
    expect(screen.getByText(/game.quiz.kalimat.atHint/)).toBeInTheDocument()
  })

  it("sets an Arabic answer in the hand, right to left", () => {
    render(<LastRoundCard last={{ round: 2, answer: "زكريّا", finder: { username: "Maryam", hint: 2, points: 5 } }} />)
    const word = screen.getByText("زكريّا")
    expect(word).toHaveAttribute("dir", "rtl")
    expect(word.className).toContain("type-hand")
  })

  it("says when nobody found it, with no points", () => {
    render(<LastRoundCard last={{ round: 2, answer: "Hira" }} />)
    expect(screen.getByText(/game.quiz.kalimat.nobodyFound/)).toBeInTheDocument()
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument()
  })

  it("says what the finder wrote, in their hand, right at which hint (sketch D)", () => {
    render(<LastRoundCard last={{ round: 4, answer: "Zakariyya", finder: { username: "Maryam", hint: 5, points: 2, wrote: "زكريّا" } }} />)
    expect(screen.getByText(/game.quiz.kalimat.wrote/)).toBeInTheDocument()
    expect(screen.getByText("زكريّا")).toHaveClass("type-hand")
    expect(screen.queryByText("Zakariyya")).not.toBeInTheDocument()
    expect(screen.getByText(/game.quiz.kalimat.rightAtHint/)).toBeInTheDocument()
    expect(screen.getByText("+2")).toBeInTheDocument()
  })
})

describe("lastRoundFrom", () => {
  it("takes the first finder and what they typed from the results phase", () => {
    const last = lastRoundFrom({
      current_round: 3,
      correct_answer: "Zakariyya",
      round_results: [
        { username: "Maryam", answered_at_hint: 5, points: 2, typed_answer: "زكريا" },
        { username: "Idris", answered_at_hint: null, points: 0, typed_answer: "Yahya" },
      ],
    })
    expect(last).toEqual({ round: 3, answer: "Zakariyya", finder: { username: "Maryam", hint: 5, points: 2, wrote: "زكريا" } })
  })

  it("has no finder when nobody found it, and nothing without an answer", () => {
    const results = [{ username: "Idris", answered_at_hint: null, points: 0, typed_answer: "Yahya" }]
    expect(lastRoundFrom({ current_round: 2, correct_answer: "Hira", round_results: results })).toEqual({ round: 2, answer: "Hira", finder: undefined })
    expect(lastRoundFrom({ current_round: 2, correct_answer: null, round_results: results })).toBeNull()
  })
})

describe("remembering the last round across a reload", () => {
  it("keeps it per game in the tab, and ignores anything malformed", () => {
    const last = { round: 2, answer: "Hira", finder: { username: "Maryam", hint: 3, points: 4, wrote: "حراء" } }
    rememberLastRound("g1", last)
    expect(recallLastRound("g1")).toEqual(last)
    expect(recallLastRound("g2")).toBeNull()
    sessionStorage.setItem("majlisna-kalimat-last-round:g3", "{not json")
    expect(recallLastRound("g3")).toBeNull()
  })
})
