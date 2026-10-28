import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { BoardLegend } from "./BoardLegend"
import { ClueBanner } from "./ClueBanner"
import { CodenamesMyInfo } from "./CodenamesMyInfo"
import { GameOverTransition } from "./GameOverTransition"

describe("ClueBanner", () => {
  it("says who is choosing while there is no clue", () => {
    render(<ClueBanner turn={{ clue_word: null, clue_number: 0, guesses_made: 0 }} spymasterName="Yusuf" />)
    expect(screen.getByText("game.codenames.choosingClue")).toBeInTheDocument()
  })

  it("shows the clue, its count and where the guesses stand", () => {
    render(<ClueBanner turn={{ clue_word: "knowledge", clue_number: 2, guesses_made: 1 }} spymasterName="Yusuf" />)
    expect(screen.getByText("knowledge")).toHaveAttribute("data-script", "lat")
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("game.codenames.clueFrom")).toBeInTheDocument()
    expect(screen.getByText("game.codenames.guessesMade")).toBeInTheDocument()
    expect(screen.getByText("game.codenames.leftPlusBonus")).toBeInTheDocument()
  })

  it("says only the bonus is left once the count is used", () => {
    render(<ClueBanner turn={{ clue_word: "knowledge", clue_number: 2, guesses_made: 2 }} />)
    expect(screen.getByText("game.codenames.bonusLeft")).toBeInTheDocument()
  })

  it("shows ∞ for a clue with no limit, named for assistive tech", () => {
    render(<ClueBanner turn={{ clue_word: "mercy", clue_number: 0, guesses_made: 0 }} />)
    expect(screen.getByText("∞")).toHaveAttribute("aria-hidden", "true")
    expect(screen.getByText("game.codenames.composer.unlimited")).toHaveClass("sr-only")
    expect(screen.getByText("game.codenames.noLimitLeft")).toBeInTheDocument()
  })

  it("sets an Arabic clue in the hand", () => {
    render(<ClueBanner turn={{ clue_word: "صبر", clue_number: 1, guesses_made: 0 }} />)
    expect(screen.getByText("صبر")).toHaveAttribute("data-script", "ar")
  })

  it("counts teammates who have chosen when there are several", () => {
    render(<ClueBanner turn={{ clue_word: "x", clue_number: 1, guesses_made: 0 }} pointing={{ current: 1, total: 2 }} />)
    expect(screen.getByText("game.codenames.pointingProgress")).toBeInTheDocument()
  })
})

describe("CodenamesMyInfo", () => {
  it("names a spymaster", () => {
    render(<CodenamesMyInfo myTeam="red" myRole="spymaster" />)
    expect(screen.getByText("game.codenames.youAreSpymaster")).toBeInTheDocument()
  })

  it("names an operative", () => {
    render(<CodenamesMyInfo myTeam="blue" myRole="operative" />)
    expect(screen.getByText("game.codenames.youAreOperative")).toBeInTheDocument()
  })

  it("names a spectator", () => {
    render(<CodenamesMyInfo myTeam="spectator" myRole="spectator" />)
    expect(screen.getByText("game.codenames.youWatch")).toBeInTheDocument()
  })
})

describe("GameOverTransition", () => {
  it("renders nothing when hidden", () => {
    const { container } = render(<GameOverTransition show={false} winner="red" />)
    expect(container.innerHTML).toBe("")
  })

  it('shows "Game Over" as an h2 and the winner', () => {
    render(<GameOverTransition show winner="blue" />)
    expect(screen.getByRole("heading", { level: 2, name: "game.gameOver" })).toBeInTheDocument()
    expect(screen.getByText("game.codenames.over.title")).toBeInTheDocument()
  })
})

describe("BoardLegend", () => {
  it("names every cloth and the pointing outline", () => {
    render(<BoardLegend />)
    for (const k of ["madder", "indigo", "bystander", "assassin", "pointing"]) {
      expect(screen.getByText(`game.codenames.legend.${k}`)).toBeInTheDocument()
    }
  })
})
