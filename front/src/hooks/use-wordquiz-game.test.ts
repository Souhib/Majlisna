import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook } from "@testing-library/react"
import { createElement, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Kalimat's client logic (WP-26, TQ-12): the hint ladder's clock, the per-rung fetch, the
 * moves and the way out of a gone game, on fake timers. The page had all of it inline,
 * at 0 % line coverage.
 */
const FETCH_MS = vi.hoisted(() => 50)
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
  realQuery: false,
}))

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => mocks.navigate }))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1", username: "Yusuf" } }) }))
vi.mock("sonner", () => ({ toast: mocks.toast }))
vi.mock("@/lib/analytics", () => ({ trackEvent: mocks.trackEvent }))
vi.mock("@/lib/room-session", () => ({ retrieveRoomIdForGame: vi.fn(() => "r1") }))
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: true }) }))
// the server's envelope is translated through its key: the mock answers the key itself
vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: { response?: { data?: { error_key?: string } } } | null, fallback: string) => err?.response?.data?.error_key ?? fallback,
}))
// The state read: a fixed answer, or (`realQuery`) a real query over the same key, so an
// invalidation refetches and `useIsFetching` sees it, as on the page.
vi.mock("@/api/generated", async () => {
  const { useQuery } = await import("@tanstack/react-query")
  return {
    useGetWordquizStateApiV1WordquizGamesGameIdStateGet: (_path: unknown, _params: unknown, options: { query: { enabled?: boolean } }) => {
      const query = useQuery({
        queryKey: [{ url: "/wordquiz/state", params: { game_id: "g1" } }],
        // a read takes a moment, as over the network (so `useIsFetching` is seen to turn)
        queryFn: () => new Promise((resolve) => setTimeout(() => resolve(mocks.data ?? null), FETCH_MS)),
        enabled: mocks.realQuery && options.query.enabled !== false,
      })
      return mocks.realQuery ? query : { data: mocks.data, isLoading: false, error: mocks.error }
    },
    useSubmitAnswerApiV1WordquizGamesGameIdAnswerPost: () => ({ mutateAsync: mocks.answer, isPending: false }),
    useTimerExpiredApiV1WordquizGamesGameIdTimerExpiredPost: () => ({ mutateAsync: mocks.timerExpired, isPending: false }),
    useNextRoundApiV1WordquizGamesGameIdNextRoundPost: () => ({ mutateAsync: mocks.nextRound, isPending: false }),
    useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: mocks.leave, isPending: false }),
    getWordquizStateApiV1WordquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [{ url: "/wordquiz/state", params: { game_id } }],
    getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/rooms/state", params: { room_id } }],
  }
})

const { hintClockAt, isAnswerAttemptsExhaustedError, kalimatWorth, msUntilHintClockChanges, useWordQuizGame, GAME_GONE_REDIRECT_MS, HINT_FOLLOW_UP_MS } =
  await import("./use-wordquiz-game")
const { resetServerClock } = await import("@/lib/server-clock")

const NOW = Date.parse("2026-10-31T12:00:00Z")
const GAME_KEY = [{ url: "/wordquiz/state", params: { game_id: "g1" } }]
const RULES = { intervalSeconds: 10, maxHints: 6, turnSeconds: 60 }

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
    hints: ["A prophet", "Swallowed by a whale", "Nineveh"],
    max_hints: 6,
    turn_duration_seconds: 60,
    hint_interval_seconds: 10,
    round_started_at: new Date(NOW - 2_000).toISOString(),
    players: [],
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
    timer_config: null,
    paused: null,
    ...over,
  }
}

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(queryClient, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children)
  const hook = renderHook(() => useWordQuizGame("g1"), { wrapper })
  return { ...hook, invalidate }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
  resetServerClock()
  sessionStorage.clear()
  mocks.data = kalimatState()
  mocks.error = null
  mocks.realQuery = false
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("hintClockAt and msUntilHintClockChanges (the server's ladder rule)", () => {
  it.each([
    [0, { revealed: 1, nextIn: 10 }],
    [9_999, { revealed: 1, nextIn: 1 }],
    [10_000, { revealed: 2, nextIn: 10 }],
    [49_999, { revealed: 5, nextIn: 1 }],
    [50_000, { revealed: 6, nextIn: null }],
    [500_000, { revealed: 6, nextIn: null }],
  ])("%i ms into the round: %o", (elapsed, expected) => {
    expect(hintClockAt(elapsed, RULES)).toEqual(expected)
  })

  it("announces no rung that would arrive after the round ends", () => {
    expect(hintClockAt(20_000, { ...RULES, turnSeconds: 30 })).toEqual({ revealed: 3, nextIn: null })
  })

  it("stands at the first rung before the start (a clock a beat behind the server's)", () => {
    expect(hintClockAt(-400, RULES)).toEqual({ revealed: 1, nextIn: 10 })
    expect(msUntilHintClockChanges(-400, RULES)).toBe(1_400)
  })

  it("releases the whole ladder when the interval is 0, as the server does", () => {
    expect(hintClockAt(0, { ...RULES, intervalSeconds: 0 })).toEqual({ revealed: 6, nextIn: null })
    expect(msUntilHintClockChanges(0, { ...RULES, intervalSeconds: 0 })).toBeNull()
  })

  it.each([
    [7_500, 500],
    [8_000, 1_000],
    [9_700, 300],
    [10_000, 1_000],
    [45_200, 800],
  ])("from %i ms the clock changes in %i ms", (elapsed, wait) => {
    expect(msUntilHintClockChanges(elapsed, RULES)).toBe(wait)
  })

  it("waits for the next rung itself when no countdown is shown, and for nothing past the last", () => {
    expect(msUntilHintClockChanges(25_000, { ...RULES, turnSeconds: 30 })).toBe(5_000)
    expect(msUntilHintClockChanges(50_000, RULES)).toBeNull()
  })
})

describe("kalimatWorth (owner rule (e): a miss costs a rung)", () => {
  it.each([
    [1, 0, 6],
    [1, 2, 4],
    [3, 1, 3],
    [6, 0, 1],
    [6, 3, 1],
    [0, 0, 6],
  ])("rung %i with %i rungs lost is worth %i", (rung, lost, worth) => {
    expect(kalimatWorth(6, rung, lost)).toBe(worth)
  })
})

describe("isAnswerAttemptsExhaustedError", () => {
  it("knows the 409 that says the round's tries are used, and nothing else", () => {
    expect(isAnswerAttemptsExhaustedError({ response: { status: 409, data: { error_key: "errors.api.answerAttemptsExhausted" } } })).toBe(true)
    expect(isAnswerAttemptsExhaustedError({ response: { status: 409, data: { error: "AnswerAttemptsExhaustedError" } } })).toBe(true)
    expect(isAnswerAttemptsExhaustedError({ response: { status: 409, data: { error_key: "errors.api.gamePaused" } } })).toBe(false)
    expect(isAnswerAttemptsExhaustedError({ response: { status: 400, data: { error_key: "errors.api.answerAttemptsExhausted" } } })).toBe(false)
    expect(isAnswerAttemptsExhaustedError(new TypeError("Failed to fetch"))).toBe(false)
  })
})

describe("useWordQuizGame: the hint ladder's clock", () => {
  it("puts the next rung in play at round_started_at + N × interval, to the millisecond", () => {
    // Prepare: 9.7 s into the round
    mocks.data = kalimatState({ round_started_at: new Date(NOW - 9_700).toISOString() })
    const { result } = setup()
    expect(result.current.hintClock.revealed).toBe(1)

    // Act / Assert: still rung 1 a millisecond before 10 s, rung 2 at 10 s
    act(() => vi.advanceTimersByTime(299))
    expect(result.current.hintClock.revealed).toBe(1)
    act(() => vi.advanceTimersByTime(1))
    expect(result.current.hintClock).toEqual({ revealed: 2, nextIn: 10 })
  })

  it("counts down to the next rung second by second", () => {
    // Prepare: 7.5 s into the round
    mocks.data = kalimatState({ round_started_at: new Date(NOW - 7_500).toISOString() })
    const { result } = setup()
    expect(result.current.hintClock.nextIn).toBe(3)

    // Act / Assert
    act(() => vi.advanceTimersByTime(500))
    expect(result.current.hintClock.nextIn).toBe(2)
    act(() => vi.advanceTimersByTime(1_000))
    expect(result.current.hintClock.nextIn).toBe(1)
    act(() => vi.advanceTimersByTime(1_000))
    expect(result.current.hintClock).toEqual({ revealed: 2, nextIn: 10 })
  })

  it("never polls the clock: no interval runs while a round plays", () => {
    // Prepare
    const intervals = vi.spyOn(globalThis, "setInterval")

    // Act: a whole round
    setup()
    act(() => vi.advanceTimersByTime(60_000))

    // Assert
    expect(intervals).not.toHaveBeenCalled()
  })

  it("arms one timer for the next change, not one per half-second", () => {
    // Prepare: 2 s into the round, the next change at 3 s
    const timeouts = vi.spyOn(globalThis, "setTimeout")

    // Act
    setup()

    // Assert
    expect(timeouts.mock.calls.map(([, delay]) => delay)).toContain(1_000)
    expect(timeouts.mock.calls.filter(([, delay]) => delay === 500)).toEqual([])
  })

  it("stands still while the game is paused, at the server's frozen countdown", () => {
    // Prepare: paused with 35 s left of 60 → 25 s in: rung 3, the next in 5 s
    mocks.data = kalimatState({
      round_started_at: new Date(NOW - 600_000).toISOString(),
      paused: {
        by_user_id: "u2",
        by_username: "Maryam",
        since: new Date(NOW - 300_000).toISOString(),
        reason: "salah",
        remaining_seconds: 35,
        paused_for_seconds: 300,
        anyone_can_resume_at: new Date(NOW + 2_400_000).toISOString(),
      },
    })
    const { result } = setup()

    // Act: a minute of prayer
    act(() => vi.advanceTimersByTime(60_000))

    // Assert
    expect(result.current.hintClock).toEqual({ revealed: 3, nextIn: 5 })
  })

  it("shows the server's count between rounds", () => {
    // Prepare / Act
    mocks.data = kalimatState({ round_phase: "results", hints_revealed: 4, round_started_at: new Date(NOW - 35_000).toISOString() })
    const { result } = setup()

    // Assert
    expect(result.current.hintClock).toEqual({ revealed: 4, nextIn: null })
  })

  it("fetches a rung it does not hold once, with one follow-up, never a loop", async () => {
    // Prepare: 9.8 s in, only the first hint held; every refetch brings the same state
    mocks.realQuery = true
    mocks.data = kalimatState({ hints: ["A prophet"], round_started_at: new Date(NOW - 9_800).toISOString() })
    const { result, invalidate } = setup()
    await act(() => vi.advanceTimersByTimeAsync(2 * FETCH_MS))
    expect(result.current.state?.hints).toEqual(["A prophet"])
    expect(invalidate).not.toHaveBeenCalled()

    // Act: the clock crosses into rung 2 (at 10 s), which the refetch does not bring
    await act(() => vi.advanceTimersByTimeAsync(100))
    expect(invalidate).toHaveBeenCalledTimes(1)
    await act(() => vi.advanceTimersByTimeAsync(2 * FETCH_MS + HINT_FOLLOW_UP_MS))

    // Assert: the follow-up, then nothing more for that rung
    expect(invalidate).toHaveBeenCalledTimes(2)
    await act(() => vi.advanceTimersByTimeAsync(5_000))
    expect(invalidate).toHaveBeenCalledTimes(2)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: GAME_KEY })
  })
})

describe("useWordQuizGame: an answer", () => {
  it("returns the server's verdict and fetches the state", async () => {
    // Prepare
    mocks.answer.mockResolvedValue({ correct: false, points_earned: 0, hint_number: 1 })
    const { result, invalidate } = setup()

    // Act
    let outcome: unknown
    await act(async () => {
      outcome = await result.current.handleSubmitAnswer("Zakariya")
    })

    // Assert
    expect(mocks.answer).toHaveBeenCalledWith({ game_id: "g1", data: { answer: "Zakariya" } })
    expect(outcome).toEqual({ correct: false, points_earned: 0, hint_number: 1 })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: GAME_KEY })
  })

  it("hands a refused try (409, tries used) back to the field in the player's language, without a toast", async () => {
    // Prepare
    mocks.answer.mockRejectedValue({ response: { status: 409, data: { error_key: "errors.api.answerAttemptsExhausted", error_params: { max: 5 } } } })
    const { result, invalidate } = setup()

    // Act
    let outcome: unknown
    await act(async () => {
      outcome = await result.current.handleSubmitAnswer("Yunus")
    })

    // Assert: the state that closes the field is fetched
    expect(outcome).toEqual({ refused: "errors.api.answerAttemptsExhausted" })
    expect(mocks.toast.error).not.toHaveBeenCalled()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: GAME_KEY })
  })

  it("says any other refusal as a toast, in the player's language", async () => {
    // Prepare
    mocks.answer.mockRejectedValue(new TypeError("Failed to fetch"))
    const { result } = setup()

    // Act
    let outcome: unknown
    await act(async () => {
      outcome = await result.current.handleSubmitAnswer("Yunus")
    })

    // Assert
    expect(outcome).toBeNull()
    expect(mocks.toast.error).toHaveBeenCalledWith("game.errors.answerFailed")
  })

  it("sends nothing while the game is paused", async () => {
    // Prepare
    mocks.data = kalimatState({
      paused: {
        by_user_id: "u2",
        by_username: "Maryam",
        since: new Date(NOW).toISOString(),
        reason: "salah",
        remaining_seconds: 50,
        paused_for_seconds: 0,
        anyone_can_resume_at: new Date(NOW).toISOString(),
      },
    })
    const { result } = setup()

    // Act
    let outcome: unknown
    await act(async () => {
      outcome = await result.current.handleSubmitAnswer("Yunus")
    })

    // Assert
    expect(outcome).toBeNull()
    expect(mocks.answer).not.toHaveBeenCalled()
  })
})

describe("useWordQuizGame: the next round, the end and a gone game", () => {
  it("asks for the next round once for a double tap", async () => {
    // Prepare
    mocks.data = kalimatState({ round_phase: "results", correct_answer: "Yunus" })
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

  it("keeps the round that just ended for the next one, and for a reload", () => {
    // Prepare / Act
    mocks.data = kalimatState({
      round_phase: "results",
      correct_answer: "Yunus",
      round_results: [{ user_id: "u2", username: "Maryam", answered_at_hint: 2, points: 5, typed_answer: "يونس", attempts: 1 }],
    })
    const { result } = setup()

    // Assert
    expect(result.current.lastRound).toEqual({ round: 1, answer: "Yunus", finder: { username: "Maryam", hint: 2, points: 5, wrote: "يونس" } })
    expect(sessionStorage.getItem("majlisna-kalimat-last-round:g1")).toContain("Yunus")
  })

  it("counts the game's end once", () => {
    // Prepare
    mocks.data = kalimatState({ round_phase: "game_over", game_over: true })
    const { rerender } = setup()

    // Act: more states of the finished game arrive
    mocks.data = kalimatState({ round_phase: "game_over", game_over: true, leaderboard: [] })
    rerender()
    rerender()

    // Assert
    expect(mocks.trackEvent).toHaveBeenCalledTimes(1)
    expect(mocks.trackEvent).toHaveBeenCalledWith("game-over", { game: "word_quiz" })
  })

  it("says a gone game is gone, then goes home once", () => {
    // Prepare
    mocks.data = undefined
    mocks.error = { response: { status: 404, data: { error_key: "errors.api.gameNotFound" } } }
    const { result, rerender } = setup()
    expect(result.current.cancelMessage).toBe("errors.api.gameNotFound")
    expect(mocks.navigate).not.toHaveBeenCalled()

    // Act: the error comes back from another read, then the notice's time runs out
    mocks.error = { response: { status: 404, data: { error_key: "errors.api.gameNotFound" } } }
    rerender()
    act(() => vi.advanceTimersByTime(GAME_GONE_REDIRECT_MS * 3))

    // Assert
    expect(mocks.navigate).toHaveBeenCalledTimes(1)
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/" })
  })
})
