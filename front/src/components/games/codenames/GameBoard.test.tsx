import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { GameBoard } from "./GameBoard"
import type { CodenamesCard } from "./model"

function makeBoard(): CodenamesCard[] {
  return Array.from({ length: 25 }, (_, i) => ({
    word: `WORD${i}`,
    card_type: "neutral" as const,
    revealed: false,
  }))
}

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    board: makeBoard(),
    isSpymaster: false,
    canGuess: true,
    isFinished: false,
    onGuessCard: vi.fn(),
    ...overrides,
  }
}

const players = [
  { user_id: "user-1", username: "Maryam", team: "red", role: "operative" },
  { user_id: "user-2", username: "Idris", team: "red", role: "operative" },
  { user_id: "user-3", username: "Bilal", team: "red", role: "operative" },
]

describe("GameBoard", () => {
  it("renders 25 cards inside the board hook", () => {
    render(<GameBoard {...defaultProps()} />)
    const board = screen.getByTestId("codenames-board")
    expect(board.querySelectorAll('[data-testid="codenames-card"]')).toHaveLength(25)
    expect(screen.getAllByRole("button")).toHaveLength(25)
  })

  it("keeps one left-to-right order in every language", () => {
    render(<GameBoard {...defaultProps()} />)
    expect(screen.getByTestId("codenames-board")).toHaveAttribute("dir", "ltr")
  })

  it("draws the initials of whoever points at each card", () => {
    const cardVotes = { "user-1": 3, "user-2": 3, "user-3": 7 }
    render(<GameBoard {...defaultProps({ cardVotes, players })} />)
    const cards = screen.getAllByTestId("codenames-card")
    expect(cards[3]).toHaveTextContent("MA")
    expect(cards[3]).toHaveTextContent("ID")
    expect(cards[7]).toHaveTextContent("BI")
    expect(cards[0]).not.toHaveAttribute("data-pointed")
  })

  it("identifies your own choice from currentUserId", () => {
    const cardVotes = { "user-1": 5, "user-2": 10 }
    render(<GameBoard {...defaultProps({ cardVotes, players, currentUserId: "user-1" })} />)
    const cards = screen.getAllByTestId("codenames-card")
    expect(cards[5]).toHaveAttribute("data-mine", "true")
    expect(cards[10]).not.toHaveAttribute("data-mine")
    expect(cards[10]).toHaveAttribute("data-pointed", "true")
  })

  it("shows no pointing when cardVotes is undefined", () => {
    const { container } = render(<GameBoard {...defaultProps({ cardVotes: undefined })} />)
    expect(container.querySelectorAll(".cn-ptr")).toHaveLength(0)
  })

  it("forwards canGuess and isSpymaster to cards", () => {
    const board = makeBoard()
    board[0] = { word: "SPY_WORD", card_type: "red", revealed: false }

    render(<GameBoard {...defaultProps({ board, canGuess: false, isSpymaster: true })} />)

    const cards = screen.getAllByTestId("codenames-card")
    for (const card of cards) expect(card).toBeDisabled()
    expect(cards[0]).toHaveAttribute("data-face", "key")
    expect(cards[0]).toHaveAttribute("data-team", "madder")
  })

  it("at the end, turned cards are wool and the rest read as the key", () => {
    const board = makeBoard().map((c) => ({ ...c, revealed: true }))
    render(<GameBoard {...defaultProps({ board, isFinished: true, playedWords: ["WORD0"] })} />)
    const cards = screen.getAllByTestId("codenames-card")
    expect(cards[0]).toHaveAttribute("data-face", "wool")
    expect(cards[1]).toHaveAttribute("data-face", "key")
  })
})
