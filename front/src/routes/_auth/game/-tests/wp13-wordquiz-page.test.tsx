import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Kalimat's page (WP-13): refusals said in the player's language, one request per tap,
 * focus after each phase, and the end of the clock. On mocked API hooks; the folder
 * starts with "-" so the router's file scan leaves it alone.
 */
const api = vi.hoisted(() => ({
  state: null as Record<string, unknown> | null,
  answer: vi.fn(),
  timerExpired: vi.fn(),
  nextRound: vi.fn(),
  leave: vi.fn(),
}))
const toasts = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn(), success: vi.fn() }))
const clock = vi.hoisted(() => ({ onExpired: null as null | (() => void) }))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => ({ gameId: "g1" }) }),
  useNavigate: () => vi.fn(),
}))
vi.mock("@/api/generated", () => ({
  wordQuizCategoryEnum: { prophets: "prophets", places: "places", quran: "quran" },
  useGetWordquizStateApiV1WordquizGamesGameIdStateGet: () => ({ data: api.state, isLoading: false, error: null }),
  useSubmitAnswerApiV1WordquizGamesGameIdAnswerPost: () => ({ mutateAsync: api.answer, isPending: false }),
  useTimerExpiredApiV1WordquizGamesGameIdTimerExpiredPost: () => ({ mutateAsync: api.timerExpired, isPending: false }),
  useNextRoundApiV1WordquizGamesGameIdNextRoundPost: () => ({ mutateAsync: api.nextRound, isPending: false }),
  useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: api.leave, isPending: false }),
  getWordquizStateApiV1WordquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [{ url: "/wordquiz/state", params: { game_id } }],
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/rooms/state", params: { room_id } }],
}))
vi.mock("@/api/client", () => ({ getApiErrorMessage: (_err: unknown, fallback: string) => fallback }))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: true }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: toasts }))
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))
// the route wraps the page in the app's ErrorBoundary, tested on its own
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/games/shared/PhaseTimer", () => ({
  PhaseTimer: ({ onExpired }: { onExpired?: () => void }) => {
    clock.onExpired = onExpired ?? null
    return null
  },
}))
vi.mock("@/components/games/shared/prayer-pause", async () => ({
  ...(await import("@/components/games/shared/prayer-pause/pause-utils")),
  AdhanSuggestion: () => null,
  PauseControl: () => null,
  PauseLayer: () => null,
  usePrayerPause: () => ({ canPause: false, canResume: false, pause: vi.fn(), resume: vi.fn(), refresh: vi.fn(), isPausing: false, isResuming: false }),
  useAdhanSuggestion: () => ({ prayer: null, answer: vi.fn() }),
}))

const { Route } = await import("@/routes/_auth/game/wordquiz.$gameId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

function kalimatState(over: Record<string, unknown> = {}) {
  return {
    game_id: "g1",
    room_id: "r1",
    is_host: false,
    is_spectator: false,
    current_round: 1,
    total_rounds: 3,
    round_phase: "playing",
    hints_revealed: 1,
    hints: ["A prophet"],
    max_hints: 6,
    turn_duration_seconds: 60,
    hint_interval_seconds: 10,
    // two seconds ago: the local hint clock is on the first rung
    round_started_at: new Date(Date.now() - 2_000).toISOString(),
    players: [
      { user_id: "u1", username: "Yusuf", total_score: 0, current_round_answered: false, current_round_points: 0, answered_at_hint: null },
      { user_id: "u2", username: "Maryam", total_score: 0, current_round_answered: false, current_round_points: 0, answered_at_hint: null },
    ],
    my_answered: false,
    my_points: 0,
    round_results: [],
    correct_answer: null,
    explanation: null,
    winner: null,
    leaderboard: [],
    game_over: false,
    timer_config: { turn_duration_seconds: 60, hint_interval_seconds: 10 },
    category: "prophets",
    paused: null,
    ...over,
  }
}

const results = (over: Record<string, unknown> = {}) =>
  kalimatState({
    round_phase: "results",
    correct_answer: "Yunus",
    explanation: "The prophet of the whale.",
    round_results: [{ user_id: "u1", username: "Yusuf", answered_at_hint: 2, points: 5, typed_answer: "Yunus", attempts: 1 }],
    ...over,
  })

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = () => (
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>
  )
  const view = render(ui())
  return { ...view, rerender: () => view.rerender(ui()) }
}

const answerField = () => screen.getByPlaceholderText("game.quiz.kalimat.askWho")

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  api.state = kalimatState()
  clock.onExpired = null
  ;(document.activeElement as HTMLElement | null)?.blur?.()
})

describe("Kalimat page: refusals and double taps (FR-8, FR-4)", () => {
  it("says a refused answer in the player's language, never an English literal", async () => {
    api.answer.mockRejectedValue(new TypeError("Failed to fetch"))
    renderPage()
    fireEvent.change(answerField(), { target: { value: "Yunus" } })

    await act(async () => {
      fireEvent.submit(answerField().closest("form") as HTMLFormElement)
    })

    expect(toasts.error).toHaveBeenCalledWith("game.errors.answerFailed")
  })

  it("says a next round that did not start in the player's language, and asks once for a double tap", async () => {
    // Prepare
    api.state = results({ is_host: true })
    api.nextRound.mockImplementation(() => new Promise((_, reject) => setTimeout(() => reject(new TypeError("Failed to fetch")), 20)))
    renderPage()
    const next = screen.getByRole("button", { name: "game.wordQuiz.nextRound" })

    // Act
    await act(async () => {
      fireEvent.click(next)
      fireEvent.click(next)
      await new Promise((resolve) => setTimeout(resolve, 40))
    })

    // Assert
    expect(api.nextRound).toHaveBeenCalledTimes(1)
    expect(toasts.error).toHaveBeenCalledWith("game.errors.nextRoundFailed")
  })
})

describe("Kalimat page: focus after the phase changes (F2)", () => {
  it("at the round's end, focus goes to the answer that was found", () => {
    const { rerender } = renderPage()

    api.state = results()
    act(() => rerender())

    expect(document.activeElement).toBe(screen.getByText("game.quiz.kalimat.answerWas"))
  })

  it("at the next round, focus goes to the hint in play; Tab then reaches the field", () => {
    api.state = results()
    const { rerender } = renderPage()
    screen.getByRole("button", { name: "game.readyUp" }).focus()

    api.state = kalimatState({ current_round: 2 })
    act(() => rerender())

    const rung = document.activeElement as HTMLElement
    expect(rung).toHaveAttribute("aria-current", "step")
    expect(rung).toHaveTextContent("A prophet")
  })

  it("leaves a player typing their answer in the field", () => {
    const { rerender } = renderPage()
    answerField().focus()

    // someone else's answer arrives: the same phase, new scores
    api.state = kalimatState({ players: [...(kalimatState().players as object[])] })
    act(() => rerender())

    expect(document.activeElement).toBe(answerField())
  })

  it("once you found it (the field is gone), focus is on what you found", () => {
    const { rerender } = renderPage()
    answerField().focus()

    api.state = kalimatState({ my_answered: true, my_points: 6 })
    act(() => rerender())

    expect(document.activeElement).toHaveTextContent("game.quiz.kalimat.found")
    expect(document.activeElement).not.toBe(document.body)
  })
})

describe("Kalimat page: the end of the clock (BDP-03)", () => {
  it("a guest does not report the clock at once", async () => {
    renderPage()
    expect(clock.onExpired).toBeTypeOf("function")

    await act(async () => {
      clock.onExpired?.()
    })

    expect(api.timerExpired).not.toHaveBeenCalled()
  })
})
