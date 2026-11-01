import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Kalimat's page (WP-26): the hint ladder runs on a timer set for the next change (no
 * half-second polling of the clock), a rung arrives at `round_started_at + N × interval`,
 * the field says the tries left (owner rule (e)) and the worth line counts the rungs the
 * misses cost. On mocked API hooks, like the WP-13 page test next to it.
 */
const api = vi.hoisted(() => ({
  state: null as Record<string, unknown> | null,
  answer: vi.fn(),
  timerExpired: vi.fn(),
  nextRound: vi.fn(),
  leave: vi.fn(),
}))
const toasts = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn(), success: vi.fn() }))
const clock = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) => (opts?.count != null ? `${key}:${opts.count}` : key),
    i18n: { language: "en" },
  }),
  Trans: ({ i18nKey, count }: { i18nKey: string; count?: number }) => `${i18nKey}:${count}`,
}))
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
// the server's envelope is translated through its key: the mock answers the key itself
vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: { response?: { data?: { error_key?: string } } } | null, fallback: string) => err?.response?.data?.error_key ?? fallback,
}))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: true }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: toasts }))
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))
// the thread clock is PhaseTimer's (WP-18): mocked, so any interval left is the page's own
vi.mock("@/components/games/shared/PhaseTimer", () => ({
  PhaseTimer: (props: Record<string, unknown>) => {
    clock.props = props
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

const NOW = Date.parse("2026-10-31T12:00:00Z")

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
    round_started_at: new Date(NOW - 2_000).toISOString(),
    players: [
      { user_id: "u1", username: "Yusuf", total_score: 0, current_round_answered: false, current_round_points: 0, answered_at_hint: null },
      { user_id: "u2", username: "Maryam", total_score: 0, current_round_answered: false, current_round_points: 0, answered_at_hint: null },
    ],
    my_answered: false,
    my_points: 0,
    my_attempts_left: 5,
    my_rungs_lost: 0,
    max_attempts: 5,
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = () => (
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>
  )
  const view = render(ui())
  return { ...view, queryClient, rerender: () => view.rerender(ui()) }
}

const answerField = () => screen.getByPlaceholderText("game.quiz.kalimat.askWho")
const rungInPlay = () => document.querySelector(".hint-ladder [aria-current='step']")

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  api.state = kalimatState()
  clock.props = null
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("Kalimat page: the hint clock (WP-26, F1)", () => {
  it("runs no half-second interval of its own while a round plays", () => {
    // Prepare
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
    const intervals = vi.spyOn(globalThis, "setInterval")

    // Act: a round in play, then twelve seconds of it
    renderPage()
    act(() => vi.advanceTimersByTime(12_000))

    // Assert
    expect(intervals.mock.calls.filter(([, delay]) => delay === 500)).toEqual([])
  })

  it("puts the next hint in play at round_started_at + N × interval, not up to half a second later", () => {
    // Prepare: 9.7 s into the round, both rungs already held
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
    api.state = kalimatState({ round_started_at: new Date(NOW - 9_700).toISOString(), hints: ["A prophet", "Swallowed by a whale"] })
    renderPage()
    expect(rungInPlay()).toHaveTextContent("A prophet")

    // Act: the round reaches 10 s
    act(() => vi.advanceTimersByTime(300))

    // Assert
    expect(rungInPlay()).toHaveTextContent("Swallowed by a whale")
  })

  it("counts down to the next hint second by second", () => {
    // Prepare: 7.5 s into the round, the next hint at 10 s
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
    api.state = kalimatState({ round_started_at: new Date(NOW - 7_500).toISOString() })
    renderPage()
    const tag = () => document.querySelector(".hint-rung[data-rung='2'] .rung-tag")
    expect(tag()).toHaveTextContent("0:03")

    // Act / Assert: 8 s → 2 left, 9 s → 1 left
    act(() => vi.advanceTimersByTime(500))
    expect(tag()).toHaveTextContent("0:02")
    act(() => vi.advanceTimersByTime(1_000))
    expect(tag()).toHaveTextContent("0:01")
  })

  it("hands the round's start and length to the thread clock", () => {
    // Prepare / Act
    renderPage()

    // Assert: PhaseTimer turns these into ThreadClock's startedAt and durationMs
    expect(clock.props).toMatchObject({ timerStartedAt: kalimatState().round_started_at, durationSeconds: 60 })
  })
})

describe("Kalimat page: five tries a round (owner rule (e), BR-10)", () => {
  it("passes the tries left to the answer field", () => {
    // Prepare
    api.state = kalimatState({ my_attempts_left: 3 })

    // Act
    renderPage()

    // Assert
    expect(screen.getByText("game.wordQuiz.triesLeft:3")).toBeInTheDocument()
  })

  it("closes the field once no try is left", () => {
    // Prepare
    api.state = kalimatState({ my_attempts_left: 0 })

    // Act
    renderPage()

    // Assert
    expect(answerField()).toBeDisabled()
  })

  it("says a refused try (409) in the field, in the player's language, and fetches the state", async () => {
    // Prepare
    api.answer.mockRejectedValue({
      response: { status: 409, data: { error_key: "errors.api.answerAttemptsExhausted", error_params: { max: 5 } } },
    })
    const { queryClient } = renderPage()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    fireEvent.change(answerField(), { target: { value: "Yunus" } })

    // Act
    await act(async () => {
      fireEvent.submit(answerField().closest("form") as HTMLFormElement)
    })

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("errors.api.answerAttemptsExhausted")
    expect(toasts.error).not.toHaveBeenCalled()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [{ url: "/wordquiz/state", params: { game_id: "g1" } }] })
  })

  it("prices the word with the rungs the misses cost", () => {
    // Prepare: hint 1 on screen, two misses
    api.state = kalimatState({ my_rungs_lost: 2, my_attempts_left: 3 })

    // Act
    renderPage()

    // Assert: 6 - (1 + 2) + 1
    expect(screen.getByText("game.quiz.kalimat.worthNow:4")).toBeInTheDocument()
  })

  it("prices nothing once the player is out of tries (review F5)", () => {
    // Prepare: five misses, the field closed — "worth 1 point now" offered nothing to earn
    api.state = kalimatState({ my_rungs_lost: 5, my_attempts_left: 0 })

    // Act
    renderPage()

    // Assert
    expect(screen.queryByText(/game\.quiz\.kalimat\.worthNow/)).not.toBeInTheDocument()
    expect(answerField()).toBeDisabled()
  })

  it("prices nothing once the player has found the word", () => {
    // Prepare
    api.state = kalimatState({ my_answered: true, my_points: 5, my_attempts_left: null })

    // Act
    renderPage()

    // Assert
    expect(screen.queryByText(/game\.quiz\.kalimat\.worthNow/)).not.toBeInTheDocument()
  })
})
