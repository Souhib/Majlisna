import { render, screen } from "@testing-library/react"
import { type ComponentType } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The Codenames PAGE reads a new clue out, for every role. ClueAnnouncer had its own
 * test and was mounted nowhere: the component test alone never caught it.
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
// the board's own pieces are tested on their own; here only the page's wiring matters
vi.mock("@/components/games/codenames/GameBoard", () => ({ GameBoard: () => <div data-testid="board" /> }))
vi.mock("@/components/games/codenames/ScorePanel", () => ({ ScorePanel: () => <div /> }))
vi.mock("@/components/games/codenames/CodenamesPlayerList", () => ({ CodenamesPlayerList: () => <div /> }))
vi.mock("@/components/games/codenames/ClueHistory", () => ({ ClueHistory: () => <div /> }))
vi.mock("@/components/games/codenames/ClueBanner", () => ({ ClueBanner: () => <div /> }))
vi.mock("@/components/games/codenames/BoardLegend", () => ({ BoardLegend: () => <div /> }))
vi.mock("@/components/games/codenames/GameOverTransition", () => ({ GameOverTransition: () => null }))
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))

const { Route } = await import("@/routes/_auth/game/codenames.$gameId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

function stateWith(myRole: string, turn: { clue_word: string | null; clue_number: number | null }) {
  return {
    user: { id: "u1" },
    gameState: {
      board: [],
      players: [],
      current_team: "red",
      current_turn: { team: "red", ...turn, guesses_made: 0, max_guesses: 3, card_votes: {} },
      status: "in_progress",
      winner: null,
      my_team: myRole === "spectator" ? null : "blue",
      my_role: myRole,
      red_remaining: 9,
      blue_remaining: 8,
    },
    serverState: { clue_history: [], timer_config: null, timer_started_at: null, paused: null, is_host: false },
    isLoading: false,
    socketConnected: true,
    cancelMessage: null,
    isPaused: false,
    showGameOverTransition: false,
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
  }
}

const announcer = () => document.querySelector('p[role="status"][aria-atomic="true"]')

describe("Codenames page: the clue is read out", () => {
  beforeEach(() => {
    game.state = stateWith("operative", { clue_word: null, clue_number: null })
  })

  it("keeps an empty polite status mounted while the spymaster chooses", () => {
    render(<Page />)
    expect(announcer()).not.toBeNull()
    expect(announcer()).toHaveTextContent("")
  })

  it.each(["operative", "spymaster", "spectator"])("reads a new clue out to a %s", (role) => {
    const { rerender } = render(<Page />)
    game.state = stateWith(role, { clue_word: "KNOWLEDGE", clue_number: 2 })
    rerender(<Page />)
    expect(announcer()).toHaveTextContent("game.codenames.clueAnnounce")
    expect(screen.getByTestId("board")).toBeInTheDocument()
  })
})
