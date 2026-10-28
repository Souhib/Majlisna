import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { ScorePanel } from "./ScorePanel"

const defaultProps = {
  redRemaining: 8,
  blueRemaining: 7,
  currentTeam: "red" as const,
  currentTurn: null as { clue_word: string | null } | null,
  isMyTurn: false,
  isFinished: false,
  isSpymaster: false,
}

function renderScorePanel(overrides: Partial<typeof defaultProps> & Record<string, unknown> = {}) {
  return render(<ScorePanel {...defaultProps} {...overrides} />)
}

describe("ScorePanel", () => {
  it("renders the game name as the page heading", () => {
    renderScorePanel()
    expect(screen.getByRole("heading", { level: 1, name: "games.codenames.name" })).toBeInTheDocument()
  })

  it("shows both teams with their words left", () => {
    renderScorePanel({ redRemaining: 8, blueRemaining: 7 })
    expect(screen.getByText("8")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("game.codenames.teams.red")).toBeInTheDocument()
    expect(screen.getByText("game.codenames.teams.blue")).toBeInTheDocument()
  })

  it("asks the spymaster for a clue on their turn", () => {
    renderScorePanel({ isMyTurn: true, isSpymaster: true })
    expect(screen.getByText("game.codenames.status.yourClue")).toBeInTheDocument()
  })

  it("asks the operative to guess once the clue is given", () => {
    renderScorePanel({ isMyTurn: true, currentTurn: { clue_word: "faith" } })
    expect(screen.getByText("game.codenames.status.yourGuess")).toBeInTheDocument()
  })

  it("names whose turn it is when it is not yours", () => {
    renderScorePanel({ isMyTurn: false })
    expect(screen.getByText("game.codenames.status.theirClue")).toBeInTheDocument()
    renderScorePanel({ isMyTurn: false, currentTurn: { clue_word: "faith" } })
    expect(screen.getByText("game.codenames.status.guessing")).toBeInTheDocument()
  })

  it("announces the winner when the game is finished", () => {
    renderScorePanel({ isMyTurn: true, isFinished: true, winner: "blue" })
    expect(screen.getByText("game.codenames.status.won")).toBeInTheDocument()
    expect(screen.queryByText("game.codenames.status.yourClue")).not.toBeInTheDocument()
  })

  it("renders who you are and the clock when given", () => {
    renderScorePanel({ myInfo: <p>me</p>, clock: <span>clock</span> })
    expect(screen.getByText("me")).toBeInTheDocument()
    expect(screen.getByText("clock")).toBeInTheDocument()
  })
})
