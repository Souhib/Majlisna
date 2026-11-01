import { act, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Undercover's page (WP-13, F2): after each phase swap focus goes to the new phase's
 * title, not to <body>, unless the player is typing (Mr. White's guess field). The game
 * hook and the phases' own pieces are mocked: the page's wiring is under test. The
 * folder starts with "-" so the router's file scan leaves it alone.
 */
const game = vi.hoisted(() => ({ state: null as unknown }))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => ({ gameId: "g1" }) }),
}))
vi.mock("@/hooks/use-undercover-game", () => ({ useUndercoverGame: () => game.state }))
vi.mock("@/components/games/shared/prayer-pause", () => ({
  AdhanSuggestion: () => null,
  PauseControl: () => null,
  PauseLayer: () => null,
  usePrayerPause: () => ({ canPause: false, canResume: false, pause: vi.fn(), resume: vi.fn(), refresh: vi.fn(), isPausing: false, isResuming: false }),
  useAdhanSuggestion: () => ({ prayer: null, answer: vi.fn() }),
}))
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))
// the route wraps the page in the app's ErrorBoundary, tested on its own
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/games/undercover/Lawh", () => ({ Lawh: () => <div data-testid="lawh" /> }))
vi.mock("@/components/games/undercover/DescriptionPhase", () => ({
  DescriptionPhase: () => (
    <section>
      <button type="button">Send</button>
      <h2>Describe your word</h2>
    </section>
  ),
}))
vi.mock("@/components/games/undercover/VotingPhase", () => ({
  VotingPhase: () => (
    <section>
      <button type="button">Vote for Maryam</button>
      <h2>Discuss and vote</h2>
    </section>
  ),
}))
vi.mock("@/components/games/undercover/MrWhiteGuessPanel", () => ({
  MrWhiteGuessPanel: () => (
    <section>
      <h2>Guess the word</h2>
      <input aria-label="guess" autoFocus />
    </section>
  ),
}))
vi.mock("@/components/games/undercover/GameOverScreen", async () => {
  const { Colophon } = await import("@/components/brand/Colophon")
  return { GameOverScreen: () => <Colophon arch={false} title="The civilians win." /> }
})

const { Route } = await import("@/routes/_auth/game/undercover.$gameId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

function stateIn(phase: string, over: Record<string, unknown> = {}) {
  return {
    gameState: {
      players: [
        { id: "u1", username: "Yusuf", is_alive: true },
        { id: "u2", username: "Maryam", is_alive: true },
      ],
      phase,
      round: 1,
      roundResolved: false,
      mrWhiteGuesser: null,
      my_role: "civilian",
      my_word: "Sabr",
      votedPlayers: [],
      isHost: false,
      descriptionOrder: [],
      currentDescriberIndex: 0,
      descriptions: {},
    },
    serverState: { vote_history: [], timer_config: null, timer_started_at: null, paused: null },
    isLoading: false,
    socketConnected: true,
    cancelMessage: null,
    isPaused: false,
    isAlive: true,
    isSpectator: false,
    isMyTurnToDescribe: false,
    isMrWhiteGuesser: false,
    mrWhiteGuessInput: "",
    isSubmittingMrWhiteGuess: false,
    isStartingNextRound: false,
    setMrWhiteGuessInput: vi.fn(),
    handleStartNextRound: vi.fn(),
    handleSubmitMrWhiteGuess: vi.fn(),
    hasVoted: false,
    selectedVote: null,
    isSubmittingVote: false,
    descriptionInput: "",
    descriptionError: "",
    isSubmittingDescription: false,
    showEliminationOverlay: false,
    eliminationData: null,
    roomIdRef: { current: "r1" },
    user: { id: "u1" },
    handleSelectPlayer: vi.fn(),
    handleConfirmVote: vi.fn(),
    handleSubmitDescription: vi.fn(),
    handleDismissRole: vi.fn(),
    handleHintViewed: vi.fn(),
    handleTimerExpired: vi.fn(),
    handleLeaveRoom: vi.fn(),
    handleBackToRoom: vi.fn(),
    handleDismissElimination: vi.fn(),
    handleDescriptionInputChange: vi.fn(),
    ...over,
  }
}

beforeEach(() => {
  sessionStorage.clear()
  game.state = stateIn("describing")
  ;(document.activeElement as HTMLElement | null)?.blur?.()
})

describe("Undercover page: focus after the phase changes (F2)", () => {
  it("from the description to the vote, focus goes to the vote's title", () => {
    // Prepare: the last describer sent their word with the keyboard
    const { rerender } = render(<Page />)
    screen.getByRole("button", { name: "Send" }).focus()

    // Act
    game.state = stateIn("playing")
    act(() => rerender(<Page />))

    // Assert
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: "Discuss and vote" }))
  })

  it("at the end, focus goes to the colophon's title, the h2 that says Game Over", () => {
    game.state = stateIn("playing")
    const { rerender } = render(<Page />)
    screen.getByRole("button", { name: "Vote for Maryam" }).focus()

    game.state = stateIn("game_over")
    act(() => rerender(<Page />))

    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: "The civilians win." }))
  })

  it("leaves Mr. White in his guess field", () => {
    game.state = stateIn("playing")
    const { rerender } = render(<Page />)

    game.state = stateIn("mr_white_guessing")
    act(() => rerender(<Page />))

    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "guess" }))
  })

  it("never moves focus when the page opens on a running game", () => {
    game.state = stateIn("describing", { isLoading: true, gameState: { ...stateIn("describing").gameState, my_role: undefined } })
    const { rerender } = render(<Page />)

    game.state = stateIn("describing")
    act(() => rerender(<Page />))

    expect(document.activeElement).toBe(document.body)
  })
})
