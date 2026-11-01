import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The Quiz's page (WP-26): a lock-in is one answer per question, even in the beat between
 * the server accepting it and the state that says so (the refetch). On mocked API hooks,
 * like the WP-13 page test next to it.
 */
const api = vi.hoisted(() => ({
  state: null as Record<string, unknown> | null,
  answer: vi.fn(),
  timerExpired: vi.fn(),
  nextRound: vi.fn(),
  leave: vi.fn(),
}))
const toasts = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn(), success: vi.fn() }))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => ({ gameId: "g1" }) }),
  useNavigate: () => vi.fn(),
}))
vi.mock("@/api/generated", () => ({
  useGetMcqquizStateApiV1McqquizGamesGameIdStateGet: () => ({ data: api.state, isLoading: false, error: null }),
  useSubmitAnswerApiV1McqquizGamesGameIdAnswerPost: () => ({ mutateAsync: api.answer, isPending: false }),
  useTimerExpiredApiV1McqquizGamesGameIdTimerExpiredPost: () => ({ mutateAsync: api.timerExpired, isPending: false }),
  useNextRoundApiV1McqquizGamesGameIdNextRoundPost: () => ({ mutateAsync: api.nextRound, isPending: false }),
  useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: api.leave, isPending: false }),
  getMcqquizStateApiV1McqquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [{ url: "/mcqquiz/state", params: { game_id } }],
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/rooms/state", params: { room_id } }],
}))
vi.mock("@/api/client", () => ({ getApiErrorMessage: (_err: unknown, fallback: string) => fallback }))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: true }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: toasts }))
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/games/shared/PhaseTimer", () => ({ PhaseTimer: () => null }))
vi.mock("@/components/games/shared/prayer-pause", async () => ({
  ...(await import("@/components/games/shared/prayer-pause/pause-utils")),
  AdhanSuggestion: () => null,
  PauseControl: () => null,
  PauseLayer: () => null,
  usePrayerPause: () => ({ canPause: false, canResume: false, pause: vi.fn(), resume: vi.fn(), refresh: vi.fn(), isPausing: false, isResuming: false }),
  useAdhanSuggestion: () => ({ prayer: null, answer: vi.fn() }),
}))

const { Route } = await import("@/routes/_auth/game/mcqquiz.$gameId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

function mcqState(over: Record<string, unknown> = {}) {
  return {
    game_id: "g1",
    room_id: "r1",
    is_host: false,
    is_spectator: false,
    current_round: 1,
    total_rounds: 3,
    round_phase: "playing",
    question: "Which prophet was swallowed by a whale?",
    choices: ["Yunus", "Musa", "Isa", "Nuh"],
    turn_duration_seconds: 30,
    round_started_at: new Date(Date.now() - 4_000).toISOString(),
    players: [
      { user_id: "u1", username: "Yusuf", total_score: 0, current_round_answered: false, current_round_points: 0 },
      { user_id: "u2", username: "Maryam", total_score: 0, current_round_answered: false, current_round_points: 0 },
    ],
    my_answered: false,
    my_points: 0,
    round_results: [],
    correct_answer_index: null,
    explanation: null,
    winner: null,
    leaderboard: [],
    game_over: false,
    paused: null,
    ...over,
  }
}

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

const lockIn = () => screen.getByRole("button", { name: "game.quiz.mcq.lockIn" })

beforeEach(() => {
  vi.clearAllMocks()
  api.state = mcqState()
})

describe("The Quiz page: one lock-in per question (WP-26)", () => {
  it("sends no second answer in the beat between the server's yes and the state that says so", async () => {
    // Prepare: the first lock-in is accepted; the refetch has not answered yet
    api.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    renderPage()
    fireEvent.click(screen.getByRole("radio", { name: /Yunus/ }))
    await act(async () => {
      fireEvent.click(lockIn())
    })

    // Act: a second tap, the state still saying "not answered"
    await act(async () => {
      fireEvent.click(lockIn())
    })

    // Assert
    expect(api.answer).toHaveBeenCalledTimes(1)
    expect(lockIn()).toBeDisabled()
    expect(toasts.error).not.toHaveBeenCalled()
  })

  it("keeps the choices still once locked in", async () => {
    // Prepare
    api.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    renderPage()
    fireEvent.click(screen.getByRole("radio", { name: /Yunus/ }))
    await act(async () => {
      fireEvent.click(lockIn())
    })

    // Act: a tap on another choice before the refetch
    fireEvent.click(screen.getByRole("radio", { name: /Musa/ }))

    // Assert: the pick that was sent stays the pick on screen
    expect(screen.getByRole("radio", { name: /Yunus/ })).toHaveAttribute("aria-checked", "true")
    expect(screen.getByRole("radio", { name: /Musa/ })).toHaveAttribute("aria-checked", "false")
  })

  it("opens the next question for a new lock-in", async () => {
    // Prepare: round 1 locked in
    api.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    const { rerender } = renderPage()
    fireEvent.click(screen.getByRole("radio", { name: /Yunus/ }))
    await act(async () => {
      fireEvent.click(lockIn())
    })

    // Act: round 2 opens
    api.state = mcqState({ current_round: 2, question: "Who built the Kaaba with his son?" })
    act(() => rerender())
    fireEvent.click(screen.getByRole("radio", { name: /Musa/ }))
    await act(async () => {
      fireEvent.click(lockIn())
    })

    // Assert
    expect(api.answer).toHaveBeenCalledTimes(2)
    expect(api.answer).toHaveBeenLastCalledWith({ game_id: "g1", data: { choice_index: 1 } })
  })
})
