import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook } from "@testing-library/react"
import { createElement, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The Quiz's client logic (WP-26, TQ-12): your pick, its lock-in (one answer per
 * question), the moves and the way out of a gone game, on fake timers. The page had all
 * of it inline, at 0 % line coverage.
 */
const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  trackEvent: vi.fn(),
  toast: { info: vi.fn(), error: vi.fn(), warning: vi.fn() },
  answer: vi.fn(),
  timerExpired: vi.fn(),
  nextRound: vi.fn(),
  leave: vi.fn(),
  data: undefined as Record<string, unknown> | undefined,
  error: null as unknown,
}))

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => mocks.navigate }))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1", username: "Yusuf" } }) }))
vi.mock("sonner", () => ({ toast: mocks.toast }))
vi.mock("@/lib/analytics", () => ({ trackEvent: mocks.trackEvent }))
vi.mock("@/lib/room-session", () => ({ retrieveRoomIdForGame: vi.fn(() => "r1") }))
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: true }) }))
vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: { response?: { data?: { error_key?: string } } } | null, fallback: string) => err?.response?.data?.error_key ?? fallback,
}))
vi.mock("@/api/generated", () => ({
  useGetMcqquizStateApiV1McqquizGamesGameIdStateGet: () => ({ data: mocks.data, isLoading: false, error: mocks.error }),
  useSubmitAnswerApiV1McqquizGamesGameIdAnswerPost: () => ({ mutateAsync: mocks.answer, isPending: false }),
  useTimerExpiredApiV1McqquizGamesGameIdTimerExpiredPost: () => ({ mutateAsync: mocks.timerExpired, isPending: false }),
  useNextRoundApiV1McqquizGamesGameIdNextRoundPost: () => ({ mutateAsync: mocks.nextRound, isPending: false }),
  useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: mocks.leave, isPending: false }),
  getMcqquizStateApiV1McqquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [{ url: "/mcqquiz/state", params: { game_id } }],
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/rooms/state", params: { room_id } }],
}))

const { useMcqQuizGame, BAND_TICK_MS, GAME_GONE_REDIRECT_MS } = await import("./use-mcqquiz-game")

const NOW = Date.parse("2026-10-31T12:00:00Z")
const GAME_KEY = [{ url: "/mcqquiz/state", params: { game_id: "g1" } }]
const PAUSED_KEY = { response: { status: 409, data: { error_key: "errors.api.gamePaused" } } }

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
    round_started_at: new Date(NOW - 4_000).toISOString(),
    players: [],
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

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(queryClient, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children)
  const hook = renderHook(() => useMcqQuizGame("g1"), { wrapper })
  return { ...hook, invalidate }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
  mocks.data = mcqState()
  mocks.error = null
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("useMcqQuizGame: one lock-in per question", () => {
  it("sends one answer for two taps that land together", async () => {
    // Prepare: the answer takes a moment
    let accept: (value: unknown) => void = () => {}
    mocks.answer.mockImplementation(() => new Promise((resolve) => (accept = resolve)))
    const { result } = setup()
    act(() => result.current.handleSelectChoice(0))

    // Act
    await act(async () => {
      void result.current.handleConfirmChoice()
      void result.current.handleConfirmChoice()
      accept({ correct: true, points_earned: 3 })
    })

    // Assert
    expect(mocks.answer).toHaveBeenCalledTimes(1)
    expect(mocks.answer).toHaveBeenCalledWith({ game_id: "g1", data: { choice_index: 0 } })
  })

  it("is locked in once the server says yes, before the state that says so (a second submit sends nothing)", async () => {
    // Prepare
    mocks.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    const { result, invalidate } = setup()
    act(() => result.current.handleSelectChoice(0))
    await act(() => result.current.handleConfirmChoice())

    // Act: the refetch has not answered (my_answered still false); another tap
    await act(() => result.current.handleConfirmChoice())

    // Assert
    expect(result.current.hasLockedIn).toBe(true)
    expect(mocks.answer).toHaveBeenCalledTimes(1)
    expect(mocks.toast.error).not.toHaveBeenCalled()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: GAME_KEY })
  })

  it("keeps the pick that was sent once locked in", async () => {
    // Prepare
    mocks.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    const { result } = setup()
    act(() => result.current.handleSelectChoice(2))
    await act(() => result.current.handleConfirmChoice())

    // Act
    act(() => result.current.handleSelectChoice(1))

    // Assert
    expect(result.current.selectedChoice).toBe(2)
  })

  it("notes when you locked in, from the round's start", async () => {
    // Prepare: 4 s into the question
    mocks.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    const { result } = setup()
    act(() => result.current.handleSelectChoice(0))

    // Act
    await act(() => result.current.handleConfirmChoice())

    // Assert
    expect(result.current.lockIn).toEqual({ round: 1, elapsed: 4 })
  })

  it("stops the band's clock once locked in", async () => {
    // Prepare
    mocks.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    const { result } = setup()
    act(() => vi.advanceTimersByTime(BAND_TICK_MS))
    expect(result.current.now).toBe(NOW + BAND_TICK_MS)
    act(() => result.current.handleSelectChoice(0))
    await act(() => result.current.handleConfirmChoice())
    const lockedAt = result.current.now

    // Act
    act(() => vi.advanceTimersByTime(BAND_TICK_MS * 6))

    // Assert
    expect(result.current.now).toBe(lockedAt)
  })

  it("opens the next question: no pick, no mark, a new lock-in allowed", async () => {
    // Prepare: question 1 locked in
    mocks.answer.mockResolvedValue({ correct: true, points_earned: 3 })
    const { result, rerender } = setup()
    act(() => result.current.handleSelectChoice(0))
    await act(() => result.current.handleConfirmChoice())

    // Act
    mocks.data = mcqState({ current_round: 2, round_started_at: new Date(NOW).toISOString() })
    rerender()

    // Assert
    expect(result.current.hasLockedIn).toBe(false)
    expect(result.current.selectedChoice).toBeNull()
    expect(result.current.lockIn).toBeNull()
    act(() => result.current.handleSelectChoice(3))
    await act(() => result.current.handleConfirmChoice())
    expect(mocks.answer).toHaveBeenCalledTimes(2)
  })

  it("lets a refused lock-in be tried again, the pick cleared", async () => {
    // Prepare
    mocks.answer.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValue({ correct: true, points_earned: 2 })
    const { result } = setup()
    act(() => result.current.handleSelectChoice(1))

    // Act
    await act(() => result.current.handleConfirmChoice())

    // Assert
    expect(mocks.toast.error).toHaveBeenCalledWith("game.errors.answerFailed")
    expect(result.current.selectedChoice).toBeNull()
    expect(result.current.hasLockedIn).toBe(false)
    act(() => result.current.handleSelectChoice(1))
    await act(() => result.current.handleConfirmChoice())
    expect(mocks.answer).toHaveBeenCalledTimes(2)
  })

  it("keeps the pick through a pause that refused it, and fetches the veil", async () => {
    // Prepare
    mocks.answer.mockRejectedValue(PAUSED_KEY)
    const { result, invalidate } = setup()
    act(() => result.current.handleSelectChoice(1))

    // Act
    await act(() => result.current.handleConfirmChoice())

    // Assert
    expect(result.current.selectedChoice).toBe(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: GAME_KEY })
  })

  it("lets a spectator neither pick nor lock in", async () => {
    // Prepare
    mocks.data = mcqState({ is_spectator: true })
    const { result } = setup()

    // Act
    act(() => result.current.handleSelectChoice(0))
    await act(() => result.current.handleConfirmChoice())

    // Assert
    expect(result.current.selectedChoice).toBeNull()
    expect(mocks.answer).not.toHaveBeenCalled()
  })
})

describe("useMcqQuizGame: the next round, the end and a gone game", () => {
  it("asks for the next round once for a double tap", async () => {
    // Prepare
    mocks.data = mcqState({ round_phase: "results", is_host: true })
    let release: () => void = () => {}
    mocks.nextRound.mockImplementation(() => new Promise<void>((resolve) => (release = resolve)))
    const { result } = setup()

    // Act
    await act(async () => {
      void result.current.handleNextRound()
      void result.current.handleNextRound()
      release()
    })

    // Assert
    expect(mocks.nextRound).toHaveBeenCalledTimes(1)
  })

  it("reports the clock at once for the host", async () => {
    // Prepare
    mocks.data = mcqState({ is_host: true })
    mocks.timerExpired.mockResolvedValue({ action: "results" })
    const { result, invalidate } = setup()

    // Act
    await act(() => result.current.handleTimerExpired())

    // Assert
    expect(mocks.timerExpired).toHaveBeenCalledWith({ game_id: "g1" })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: GAME_KEY })
  })

  it("counts the game's end once", () => {
    // Prepare
    mocks.data = mcqState({ round_phase: "game_over", game_over: true })
    const { rerender } = setup()

    // Act
    mocks.data = mcqState({ round_phase: "game_over", game_over: true, leaderboard: [] })
    rerender()

    // Assert
    expect(mocks.trackEvent).toHaveBeenCalledTimes(1)
    expect(mocks.trackEvent).toHaveBeenCalledWith("game-over", { game: "mcq_quiz" })
  })

  it("says a gone game is gone, then goes home once", () => {
    // Prepare
    mocks.data = undefined
    mocks.error = { response: { status: 404, data: { error_key: "errors.api.gameNotFound" } } }
    const { result, rerender } = setup()
    expect(result.current.cancelMessage).toBe("errors.api.gameNotFound")

    // Act
    mocks.error = { response: { status: 404, data: { error_key: "errors.api.gameNotFound" } } }
    rerender()
    act(() => vi.advanceTimersByTime(GAME_GONE_REDIRECT_MS * 3))

    // Assert
    expect(mocks.navigate).toHaveBeenCalledTimes(1)
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/" })
  })

  it("leaves the room once, then goes to /rooms", async () => {
    // Prepare
    mocks.leave.mockResolvedValue({})
    const { result } = setup()

    // Act
    await act(async () => {
      void result.current.handleLeaveRoom()
      await result.current.handleLeaveRoom()
    })

    // Assert
    expect(mocks.leave).toHaveBeenCalledTimes(1)
    expect(mocks.leave).toHaveBeenCalledWith({ data: { room_id: "r1" } })
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/rooms" })
  })
})
