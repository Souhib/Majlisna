import { act, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Codenames' page (WP-13): the colophon waits for the veil (F3), focus then goes to its
 * title (F2), and End Turn is busy while it is sent (FR-4). The game hook is mocked; the
 * page's wiring is under test. The folder starts with "-" so the router's file scan
 * leaves it alone.
 */
const game = vi.hoisted(() => ({ state: null as unknown }))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => ({ gameId: "g1" }) }),
}))
vi.mock("@/hooks/use-codenames-game", () => ({ useCodenamesGame: () => game.state }))
vi.mock("@/components/games/shared/prayer-pause", () => ({
  AdhanSuggestion: () => null,
  PauseControl: () => null,
  PauseLayer: () => null,
  usePrayerPause: () => ({ canPause: false, canResume: false, pause: vi.fn(), resume: vi.fn(), refresh: vi.fn(), isPausing: false, isResuming: false }),
  useAdhanSuggestion: () => ({ prayer: null, answer: vi.fn() }),
}))
vi.mock("@/components/games/codenames/GameBoard", () => ({ GameBoard: () => <button type="button">Card</button> }))
vi.mock("@/components/games/codenames/ScorePanel", () => ({ ScorePanel: () => <div /> }))
vi.mock("@/components/games/codenames/CodenamesPlayerList", () => ({ CodenamesPlayerList: () => <div /> }))
vi.mock("@/components/games/codenames/ClueHistory", () => ({ ClueHistory: () => <div /> }))
vi.mock("@/components/games/codenames/ClueBanner", () => ({ ClueBanner: () => <div /> }))
vi.mock("@/components/games/codenames/BoardLegend", () => ({ BoardLegend: () => <div /> }))
vi.mock("@/components/games/codenames/GameOverTransition", () => ({
  GameOverTransition: ({ show }: { show: boolean }) => (show ? <div data-testid="veil" /> : null),
}))
vi.mock("@/components/games/codenames/GameOverScreen", async () => {
  const { Colophon } = await import("@/components/brand/Colophon")
  return {
    GameOverScreen: () => (
      <>
        <h2 className="sr-only">Game Over</h2>
        <Colophon arch={false} titleAs="h3" title="The Red team wins." />
      </>
    ),
  }
})
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))
// the route wraps the page in the app's ErrorBoundary, tested on its own
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))

const { Route } = await import("@/routes/_auth/game/codenames.$gameId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

function stateWith(over: { status?: string; winner?: string | null; showGameOverTransition?: boolean; colophonHeld?: boolean; isEndingTurn?: boolean } = {}) {
  const { status = "in_progress", winner = null, ...rest } = over
  return {
    user: { id: "u1" },
    gameState: {
      board: [],
      players: [{ user_id: "u1", username: "Yusuf", team: "red", role: "operative" }],
      current_team: "red",
      current_turn: { team: "red", clue_word: "Ilm", clue_number: 2, guesses_made: 0, max_guesses: 3, card_votes: {} },
      status,
      winner,
      my_team: "red",
      my_role: "operative",
      red_remaining: 0,
      blue_remaining: 4,
    },
    serverState: { clue_history: [], timer_config: null, timer_started_at: null, paused: null, is_host: false },
    isLoading: false,
    socketConnected: true,
    cancelMessage: null,
    isPaused: false,
    showGameOverTransition: false,
    colophonHeld: false,
    isEndingTurn: false,
    roomIdRef: { current: "r1" },
    clueWord: "",
    setClueWord: vi.fn(),
    clueNumber: 1,
    setClueNumber: vi.fn(),
    isSubmittingClue: false,
    handleGiveClue: vi.fn(),
    handleGuessCard: vi.fn(),
    handleEndTurn: vi.fn(),
    handleLeaveRoom: vi.fn(),
    handleBackToRoom: vi.fn(),
    handleHintViewed: vi.fn(),
    handleTimerExpired: vi.fn(),
    navigate: vi.fn(),
    ...rest,
  }
}

beforeEach(() => {
  game.state = stateWith()
  ;(document.activeElement as HTMLElement | null)?.blur?.()
})

describe("Codenames page: the end of the game (F3, F2)", () => {
  it("keeps the colophon back while the last card is woven and while the veil is up", () => {
    // the decisive card weaving: no veil yet, and no colophon either
    game.state = stateWith({ status: "finished", winner: "red", colophonHeld: true })
    const { rerender } = render(<Page />)
    expect(screen.queryByText("The Red team wins.")).not.toBeInTheDocument()

    // the veil
    game.state = stateWith({ status: "finished", winner: "red", colophonHeld: true, showGameOverTransition: true })
    rerender(<Page />)
    expect(screen.getByTestId("veil")).toBeInTheDocument()
    expect(screen.queryByText("The Red team wins.")).not.toBeInTheDocument()
  })

  it("when the veil lifts, focus goes to the colophon's title", () => {
    // Prepare: the operative pointed at the decisive card with the keyboard
    const { rerender } = render(<Page />)
    screen.getByRole("button", { name: "Card" }).focus()
    game.state = stateWith({ status: "finished", winner: "red", colophonHeld: true, showGameOverTransition: true })
    act(() => rerender(<Page />))

    // Act: the veil lifts
    game.state = stateWith({ status: "finished", winner: "red" })
    act(() => rerender(<Page />))

    // Assert
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 3, name: "The Red team wins." }))
  })

  it("takes no focus on a page opened on a finished game", () => {
    game.state = { ...stateWith(), gameState: null, isLoading: true }
    const { rerender } = render(<Page />)

    game.state = stateWith({ status: "finished", winner: "red" })
    act(() => rerender(<Page />))

    expect(screen.getByText("The Red team wins.")).toBeInTheDocument()
    expect(document.activeElement).toBe(document.body)
  })
})

describe("Codenames page: End Turn (FR-4)", () => {
  it("is busy while the end of the turn is sent", () => {
    game.state = stateWith({ isEndingTurn: true })
    render(<Page />)
    expect(screen.getByRole("button", { name: /game\.codenames\.endTurn/ })).toHaveAttribute("aria-busy", "true")
  })
})
