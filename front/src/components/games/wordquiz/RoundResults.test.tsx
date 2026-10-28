import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RoundResults } from "./RoundResults"

const roundResults = [
  { user_id: "u1", username: "Alice", answered_at_hint: 2, points: 5 },
  { user_id: "u2", username: "Bob", answered_at_hint: null, points: 0 },
  { user_id: "u3", username: "Charlie", answered_at_hint: 4, points: 3 },
]

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    correctAnswer: "Mosque",
    explanation: "A mosque is a place of worship for Muslims.",
    roundResults,
    isHost: false,
    onNextRound: vi.fn(),
    isAdvancing: false,
    ...overrides,
  }
}

describe("RoundResults", () => {
  it('reveals the answer under "The answer was"', () => {
    render(<RoundResults {...defaultProps()} />)
    expect(screen.getByText("game.quiz.kalimat.answerWas")).toBeInTheDocument()
    expect(screen.getByText("Mosque")).toBeInTheDocument()
  })

  it("sets an Arabic answer right to left", () => {
    render(<RoundResults {...defaultProps({ correctAnswer: "زكريا" })} />)
    expect(screen.getByText("زكريا")).toHaveAttribute("dir", "rtl")
    expect(screen.getByText("زكريا")).toHaveAttribute("lang", "ar")
  })

  it("shows the explanation verbatim when there is one", () => {
    render(<RoundResults {...defaultProps()} />)
    expect(screen.getByText("A mosque is a place of worship for Muslims.")).toBeInTheDocument()
  })

  it("does not display explanation when null", () => {
    render(<RoundResults {...defaultProps({ explanation: null })} />)
    expect(screen.queryByText("A mosque is a place of worship for Muslims.")).not.toBeInTheDocument()
  })

  it("lists the players by points, with the points of those who found it", () => {
    render(<RoundResults {...defaultProps()} />)
    const rows = screen.getAllByRole("listitem")
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining("Alice"), expect.stringContaining("Charlie"), expect.stringContaining("Bob")])
    expect(rows[0]).toHaveTextContent("+5")
    expect(rows[0]).toHaveTextContent("game.quiz.kalimat.atHint")
    expect(rows[2]).toHaveTextContent("game.wordQuiz.notAnswered")
  })

  it("marks your own row", () => {
    render(<RoundResults {...defaultProps({ currentUserId: "u3" })} />)
    const mine = screen.getAllByRole("listitem").find((r) => r.hasAttribute("data-you"))
    expect(mine).toHaveTextContent("Charlie")
  })

  it("gives the host the next-round button", () => {
    render(<RoundResults {...defaultProps({ isHost: true })} />)
    expect(screen.getByRole("button", { name: "game.wordQuiz.nextRound" })).toBeInTheDocument()
  })

  it("offers a non-host the ready button instead of next round", () => {
    const onNextRound = vi.fn()
    render(<RoundResults {...defaultProps({ isHost: false, onNextRound })} />)
    expect(screen.queryByText("game.wordQuiz.nextRound")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "game.readyUp" }))
    expect(onNextRound).toHaveBeenCalledOnce()
  })

  it("disables the ready button once the player is ready", () => {
    render(<RoundResults {...defaultProps({ isHost: false, isReady: true, readyCount: 2 })} />)
    expect(screen.getByRole("button", { name: "game.readyWaiting" })).toBeDisabled()
  })

  it('says "See results" on the last round', () => {
    render(<RoundResults {...defaultProps({ isHost: true, isLastRound: true })} />)
    expect(screen.getByRole("button", { name: "game.wordQuiz.seeResults" })).toBeInTheDocument()
  })

  it("calls onNextRound when next round button is clicked", () => {
    const onNextRound = vi.fn()
    render(<RoundResults {...defaultProps({ isHost: true, onNextRound })} />)
    fireEvent.click(screen.getByRole("button", { name: "game.wordQuiz.nextRound" }))
    expect(onNextRound).toHaveBeenCalledOnce()
  })

  it("shows the next-round button as busy while advancing", () => {
    render(<RoundResults {...defaultProps({ isHost: true, isAdvancing: true })} />)
    expect(screen.getByRole("button", { name: /game.wordQuiz.nextRound/ })).toHaveAttribute("aria-busy", "true")
  })

  it("says what each player wrote: the finder’s answer, a miss’s last try and how many tries", () => {
    // Prepare
    const results = [
      { user_id: "u1", username: "Maryam", answered_at_hint: 5, points: 2, typed_answer: "زكريا", attempts: 1 },
      { user_id: "u2", username: "Idris", answered_at_hint: null, points: 0, typed_answer: "Yahya", attempts: 3 },
      { user_id: "u3", username: "Bilal", answered_at_hint: null, points: 0, typed_answer: null, attempts: 0 },
    ]

    // Act
    render(<RoundResults {...defaultProps({ roundResults: results })} />)

    // Assert
    expect(screen.getByText("زكريا")).toHaveClass("type-hand")
    expect(screen.getByText("زكريا")).toHaveAttribute("lang", "ar")
    expect(screen.getByText("Yahya")).toBeInTheDocument()
    expect(screen.getByText("game.quiz.kalimat.lastTry")).toBeInTheDocument()
    expect(screen.getByText("game.quiz.kalimat.tries")).toBeInTheDocument()
    expect(screen.getByText("game.wordQuiz.notAnswered")).toBeInTheDocument()
  })
})
