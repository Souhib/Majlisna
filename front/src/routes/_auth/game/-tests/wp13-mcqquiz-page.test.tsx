import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The Quiz's page (WP-13): what a player does with the keyboard, a double tap, a refusal
 * and the end of the clock. The page's own wiring is under test, on mocked API hooks; the
 * pieces it is built from have their own tests. The folder starts with "-" so the
 * router's file scan leaves it alone.
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
// the route wraps the page in the app's ErrorBoundary, tested on its own
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))
// the samar riddle under the results reads its own endpoint: tested on its own (mcqquiz-riddle.test.tsx)
vi.mock("@/components/rooms/SamarRiddle", () => ({ SamarRiddle: () => null }))
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
    round_started_at: "2026-10-31T12:00:00+00:00",
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

const revealed = (over: Record<string, unknown> = {}) =>
  mcqState({
    round_phase: "results",
    my_answered: true,
    correct_answer_index: 0,
    explanation: "Yunus was swallowed by the whale.",
    round_results: [{ user_id: "u1", username: "Yusuf", chose_correct: true, points: 3, choice_index: 0 }],
    choice_tallies: [1, 0, 0, 0],
    my_choice_index: 0,
    ...over,
  })

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>,
  )
  const rerender = () =>
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <Page />
      </QueryClientProvider>,
    )
  return { ...view, rerender }
}

const lockIn = () => screen.getByRole("button", { name: "game.quiz.mcq.lockIn" })

beforeEach(() => {
  vi.clearAllMocks()
  api.state = mcqState()
  clock.onExpired = null
  ;(document.activeElement as HTMLElement | null)?.blur?.()
})

describe("The Quiz page: moves (FR-4, FR-8)", () => {
  it("locks in once for a double tap that lands before the button turns busy", async () => {
    // Prepare: the answer takes a moment
    api.answer.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve({ correct: true }), 20)))
    renderPage()
    fireEvent.click(screen.getByRole("radio", { name: /Yunus/ }))

    // Act: two taps in one go
    await act(async () => {
      fireEvent.click(lockIn())
      fireEvent.click(lockIn())
      await new Promise((resolve) => setTimeout(resolve, 40))
    })

    // Assert
    expect(api.answer).toHaveBeenCalledTimes(1)
  })

  it("says a refused answer in the player's language, never an English literal", async () => {
    api.answer.mockRejectedValue(new TypeError("Failed to fetch"))
    renderPage()
    fireEvent.click(screen.getByRole("radio", { name: /Musa/ }))

    await act(async () => {
      fireEvent.click(lockIn())
    })

    expect(toasts.error).toHaveBeenCalledWith("game.errors.answerFailed")
  })

  it("says a next round that did not start in the player's language", async () => {
    api.state = revealed({ is_host: true })
    api.nextRound.mockRejectedValue(new TypeError("Failed to fetch"))
    renderPage()

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "game.mcqQuiz.nextRound" }))
    })

    expect(toasts.error).toHaveBeenCalledWith("game.errors.nextRoundFailed")
  })

  it("asks for the next round once for a double tap", async () => {
    api.state = revealed({ is_host: true })
    api.nextRound.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve({}), 20)))
    renderPage()
    const next = screen.getByRole("button", { name: "game.mcqQuiz.nextRound" })

    await act(async () => {
      fireEvent.click(next)
      fireEvent.click(next)
      await new Promise((resolve) => setTimeout(resolve, 40))
    })

    expect(api.nextRound).toHaveBeenCalledTimes(1)
  })
})

describe("The Quiz page: focus after the phase changes (F2)", () => {
  it("after the reveal, focus is on the results heading, not <body>", () => {
    // Prepare: a keyboard player pressed Lock in; the button is gone with the open question
    const { rerender } = renderPage()
    lockIn().focus()

    // Act: the reveal arrives
    api.state = revealed()
    act(() => rerender())

    // Assert
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 3, name: "game.mcqQuiz.explanation" }))
  })

  it("after Next question, focus is on the new question", () => {
    api.state = revealed()
    const { rerender } = renderPage()
    // a guest pressed "I'm ready"; the host moved on
    screen.getByRole("button", { name: "game.readyUp" }).focus()

    api.state = mcqState({ current_round: 2, question: "Who built the Kaaba with his son?" })
    act(() => rerender())

    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: "Who built the Kaaba with his son?" }))
  })

  it("after locking in among others, focus is on the locked-in note", () => {
    const { rerender } = renderPage()
    fireEvent.click(screen.getByRole("radio", { name: /Yunus/ }))
    lockIn().focus()

    api.state = mcqState({ my_answered: true })
    act(() => rerender())

    const note = screen.getByText("game.quiz.mcq.lockedIn").closest("p")
    expect(note).not.toBeNull()
    expect(document.activeElement).toBe(note)
  })

  it("never moves focus when the page opens", () => {
    renderPage()
    expect(document.activeElement).toBe(document.body)
  })
})

describe("The Quiz page: the end of the clock (BDP-03)", () => {
  it("a guest does not report the clock at once: the host's report comes first", async () => {
    renderPage()
    expect(clock.onExpired).toBeTypeOf("function")

    await act(async () => {
      clock.onExpired?.()
    })

    expect(api.timerExpired).not.toHaveBeenCalled()
  })

  it("the host reports at once", async () => {
    api.state = mcqState({ is_host: true })
    api.timerExpired.mockResolvedValue({ game_id: "g1", action: "results" })
    renderPage()

    await act(async () => {
      clock.onExpired?.()
    })

    expect(api.timerExpired).toHaveBeenCalledTimes(1)
  })
})

describe("The Quiz page: one authored moment at the reveal (review RM-2)", () => {
  it("weaves the scores once the tally threads are drawn, never at the same time", () => {
    // Prepare: a recording fake of Web Animations (happy-dom has none)
    const delays: number[] = []
    Object.defineProperty(HTMLElement.prototype, "animate", {
      configurable: true,
      writable: true,
      value: vi.fn((_keyframes: Keyframe[], options: KeyframeAnimationOptions) => {
        delays.push(Number(options.delay ?? 0))
        return { cancel: vi.fn(), playState: "running" }
      }),
    })
    const { container, rerender } = renderPage()

    // Act: the reveal arrives on screen, Yusuf earned 3
    api.state = revealed({
      players: [
        { user_id: "u1", username: "Yusuf", total_score: 3, current_round_answered: true, current_round_points: 3 },
        { user_id: "u2", username: "Maryam", total_score: 0, current_round_answered: false, current_round_points: 0 },
      ],
    })
    act(() => rerender())

    // Assert: the tallies weave (CSS) and every part of the scoreboard's weave waits for their 730 ms
    expect(container.querySelector("ul.quiz-choices")).toHaveAttribute("data-weave", "true")
    expect(delays.length).toBeGreaterThan(0)
    for (const delay of delays) expect(delay).toBeGreaterThanOrEqual(730)
    delete (HTMLElement.prototype as { animate?: unknown }).animate
  })
})
