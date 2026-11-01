import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createElement } from "react"

// Mock dependencies before imports

const mockNavigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}))

const mockUser = { id: "user-1", username: "TestUser" }
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: mockUser }),
}))

vi.mock("sonner", () => ({
  toast: { info: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock("@/lib/analytics", () => ({
  trackEvent: vi.fn(),
}))

vi.mock("@/lib/room-session", () => ({
  retrieveRoomIdForGame: vi.fn(() => "room-456"),
}))

vi.mock("@/api/client", () => ({
  getApiErrorMessage: vi.fn((err: unknown, fallback: string) => fallback),
}))

const mockSocketReturn = { connected: true }
vi.mock("@/hooks/use-socket", () => ({
  useSocket: () => mockSocketReturn,
}))

// Mock server state for codenames
const mockBoard = [
  { word: "Quran", card_type: "red", revealed: false, hint: null },
  { word: "Mosque", card_type: "blue", revealed: false, hint: null },
  { word: "Prayer", card_type: "neutral", revealed: false, hint: null },
  { word: "Hajj", card_type: "assassin", revealed: false, hint: null },
]

const mockServerState = {
  game_id: "game-1",
  room_id: "room-456",
  team: "red" as const,
  role: "spymaster" as const,
  is_host: true,
  board: mockBoard,
  current_team: "red" as const,
  red_remaining: 3,
  blue_remaining: 3,
  status: "in_progress",
  current_turn: {
    team: "red" as const,
    clue_word: null,
    clue_number: 0,
    guesses_made: 0,
    max_guesses: null,
  },
  winner: null,
  players: [
    { user_id: "user-1", username: "TestUser", team: "red", role: "spymaster" },
    { user_id: "user-2", username: "Player2", team: "blue", role: "operative" },
  ],
  clue_history: [],
  timer_config: { clue_seconds: 60, guess_seconds: 60 },
  timer_started_at: null,
  newly_unlocked_achievements: [],
}

// Shared, so the prayer-pause tests can see what was (not) sent.
const mockGuess = vi.fn()
const mockClue = vi.fn()
const mockEndTurn = vi.fn()
const mockTimerExpired = vi.fn()

let mockQueryData: typeof mockServerState | undefined = undefined
let mockIsLoading = true
let mockQueryError: Error | null = null

vi.mock("@/api/generated", () => ({
  useGetCodenamesBoardApiV1CodenamesGamesGameIdBoardGet: () => ({
    data: mockQueryData,
    isLoading: mockIsLoading,
    error: mockQueryError,
  }),
  useGiveClueApiV1CodenamesGamesGameIdCluePost: () => ({ mutateAsync: mockClue }),
  useGuessCardApiV1CodenamesGamesGameIdGuessPost: () => ({ mutateAsync: mockGuess }),
  useEndTurnApiV1CodenamesGamesGameIdEndTurnPost: () => ({ mutateAsync: mockEndTurn }),
  useRecordHintViewedApiV1CodenamesGamesGameIdHintViewedPost: () => ({ mutateAsync: vi.fn() }),
  useTimerExpiredApiV1CodenamesGamesGameIdTimerExpiredPost: () => ({ mutateAsync: mockTimerExpired }),
  useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: vi.fn() }),
  getCodenamesBoardApiV1CodenamesGamesGameIdBoardGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/codenames/games/:game_id/board", params: { game_id } },
  ],
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/api/v1/rooms/:room_id/state", params: { room_id } }],
  getUndercoverStateApiV1UndercoverGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/undercover/games/:game_id/state", params: { game_id } },
  ],
  getWordquizStateApiV1WordquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/wordquiz/games/:game_id/state", params: { game_id } },
  ],
  getMcqquizStateApiV1McqquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/mcqquiz/games/:game_id/state", params: { game_id } },
  ],
  getFriendsApiV1FriendsGetQueryKey: () => [{ url: "/api/v1/friends" }],
  getPendingRequestsApiV1FriendsPendingGetQueryKey: () => [{ url: "/api/v1/friends/pending" }],
  getFriendshipStatusApiV1FriendsStatusUserIdGetQueryKey: ({ user_id }: { user_id: string }) => [
    { url: "/api/v1/friends/status/:user_id", params: { user_id } },
  ],
}))

// Import after mocks
const { useCodenamesGame } = await import("./use-codenames-game")
const { toast } = await import("sonner")

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children)
}

describe("useCodenamesGame", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQueryData = undefined
    mockIsLoading = true
    mockQueryError = null
    mockSocketReturn.connected = true
  })

  it("returns loading state when query is loading", () => {
    mockIsLoading = true
    mockQueryData = undefined

    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.serverState).toBeUndefined()
    expect(result.current.gameState).toBeNull()
  })

  it("returns game data when query succeeds", () => {
    mockIsLoading = false
    mockQueryData = { ...mockServerState }

    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.serverState).toBeDefined()
    expect(result.current.gameState).not.toBeNull()
    expect(result.current.gameState!.board).toHaveLength(4)
    expect(result.current.gameState!.my_team).toBe("red")
    expect(result.current.gameState!.my_role).toBe("spymaster")
    expect(result.current.gameState!.current_team).toBe("red")
    expect(result.current.gameState!.red_remaining).toBe(3)
    expect(result.current.gameState!.blue_remaining).toBe(3)
    expect(result.current.gameState!.players).toHaveLength(2)
  })

  it("passes through socket connected state", () => {
    mockIsLoading = false
    mockQueryData = { ...mockServerState }
    mockSocketReturn.connected = true

    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(result.current.socketConnected).toBe(true)

    mockSocketReturn.connected = false
    const { result: result2 } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(result2.current.socketConnected).toBe(false)
  })

  it("derives correct status from game state", () => {
    mockIsLoading = false

    // in_progress
    mockQueryData = { ...mockServerState, status: "in_progress", winner: null }
    const { result: r1 } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(r1.current.gameState!.status).toBe("in_progress")
    expect(r1.current.gameState!.winner).toBeNull()

    // finished with winner
    mockQueryData = { ...mockServerState, status: "finished", winner: "red" }
    const { result: r2 } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(r2.current.gameState!.status).toBe("finished")
    expect(r2.current.gameState!.winner).toBe("red")
  })

  it("returns null gameState when serverState is undefined", () => {
    mockIsLoading = false
    mockQueryData = undefined

    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.gameState).toBeNull()
    expect(result.current.clueWord).toBe("")
    expect(result.current.clueNumber).toBe(1)
    expect(result.current.isSubmittingClue).toBe(false)
    expect(result.current.cancelMessage).toBeNull()
    expect(result.current.showGameOverTransition).toBe(false)
  })

  it("says a game that is gone is gone, whatever the language of its message (404)", () => {
    mockIsLoading = false
    mockQueryError = Object.assign(new Error("Request failed with status code 404"), {
      response: { status: 404, data: { error_key: "errors.api.gameNotFound", message: "Game not found." } },
    })
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(result.current.cancelMessage).toBe("errors.api.gameNotFound")
  })

  it("does not treat a server error as a game that is gone", () => {
    mockIsLoading = false
    mockQueryError = Object.assign(new Error("Request failed with status code 500"), {
      response: { status: 500, data: { message: "Internal error" } },
    })
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(result.current.cancelMessage).toBeNull()
  })

  it("does not toast achievements: the colophon seals them", () => {
    mockIsLoading = false
    mockQueryData = {
      ...mockServerState,
      status: "finished",
      winner: "red",
      newly_unlocked_achievements: [{ user_id: "user-1", achievements: [{ code: "first_win", name: "Taste of Victory", icon: "", tier: 1 }] }],
    } as typeof mockServerState

    renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(toast.info).not.toHaveBeenCalled()
    expect(toast.error).not.toHaveBeenCalled()
    expect(toast.warning).not.toHaveBeenCalled()
  })
})

describe("useCodenamesGame: the prayer pause", () => {
  const pause = {
    by_user_id: "user-1",
    by_username: "TestUser",
    since: "2026-10-28T15:00:00+00:00",
    reason: "salah" as const,
    remaining_seconds: 30,
    paused_for_seconds: 0,
    anyone_can_resume_at: "2026-10-28T15:45:00+00:00",
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsLoading = false
    mockQueryError = null
  })

  it("says the game is paused", () => {
    mockQueryData = { ...mockServerState, paused: pause } as typeof mockQueryData
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    expect(result.current.isPaused).toBe(true)
  })

  it("sends no guess, no end of turn and no timer report while paused", async () => {
    // Prepare
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T14:59:00+00:00", paused: pause } as typeof mockQueryData
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    // Act
    await act(() => result.current.handleGuessCard(0))
    await act(() => result.current.handleEndTurn())
    await act(() => result.current.handleTimerExpired())

    // Assert
    expect(mockGuess).not.toHaveBeenCalled()
    expect(mockEndTurn).not.toHaveBeenCalled()
    expect(mockTimerExpired).not.toHaveBeenCalled()
  })

  it("stops reporting a timer window the server answered 'paused' for", async () => {
    mockTimerExpired.mockResolvedValue({ game_id: "game-1", action: "paused" })
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T14:59:00+00:00" } as typeof mockQueryData
    const { result, rerender } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    await act(() => result.current.handleTimerExpired())
    await act(() => result.current.handleTimerExpired())
    expect(mockTimerExpired).toHaveBeenCalledTimes(1)

    // resumed: the server moved the turn's start forward
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T15:20:00+00:00" } as typeof mockQueryData
    rerender()
    await act(() => result.current.handleTimerExpired())
    expect(mockTimerExpired).toHaveBeenCalledTimes(2)
  })

  it("tells a guess refused because the game was paused under it", async () => {
    const refusal = Object.assign(new Error("paused"), {
      response: { status: 409, data: { error_key: "errors.api.gamePaused" } },
    })
    mockGuess.mockRejectedValue(refusal)
    mockQueryData = { ...mockServerState } as typeof mockQueryData
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    await act(() => result.current.handleGuessCard(1))

    expect(mockGuess).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledTimes(1)
  })
})

describe("useCodenamesGame: the end of the game (the veil)", () => {
  const realMatchMedia = window.matchMedia

  function reducedMotion(on: boolean) {
    window.matchMedia = ((query: string) => ({
      matches: on && query.includes("prefers-reduced-motion: reduce"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockIsLoading = false
    mockQueryError = null
    reducedMotion(false)
  })

  afterEach(() => {
    vi.useRealTimers()
    window.matchMedia = realMatchMedia
  })

  /** Ends the game on screen, then follows the veil in 10 ms steps: when it came, how long it stayed. */
  function endTheGame() {
    mockQueryData = { ...mockServerState, status: "in_progress", winner: null }
    const hook = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    mockQueryData = { ...mockServerState, status: "finished", winner: "red" } as typeof mockQueryData
    act(() => hook.rerender())
    let shownAt: number | null = null
    let liftedAt: number | null = null
    const colophonHeldWhileVeiled: boolean[] = []
    for (let t = 0; t <= 4000 && liftedAt === null; t += 10) {
      const veiled = hook.result.current.showGameOverTransition
      if (veiled) colophonHeldWhileVeiled.push(hook.result.current.colophonHeld)
      if (veiled && shownAt === null) shownAt = t
      if (!veiled && shownAt !== null) liftedAt = t
      act(() => vi.advanceTimersByTime(10))
    }
    return { hook, shownAt, liftedAt, colophonHeldWhileVeiled }
  }

  it("lets the decisive card's selvedge be seen, then holds the veil for the ceremony, not 3 s", () => {
    // Act
    const { hook, shownAt, liftedAt, colophonHeldWhileVeiled } = endTheGame()

    // Assert: the veil comes after the card's 640 ms weave and is gone within 1.3 s
    expect(shownAt).not.toBeNull()
    expect(shownAt!).toBeGreaterThanOrEqual(600)
    expect(liftedAt).not.toBeNull()
    expect(liftedAt! - shownAt!).toBeLessThanOrEqual(1300)
    // the colophon waits for the veil (its "Game Over" never sits beside the veil's)
    expect(colophonHeldWhileVeiled.every(Boolean)).toBe(true)
    expect(hook.result.current.colophonHeld).toBe(false)
  })

  it("holds the colophon back while the decisive card is still being woven", () => {
    mockQueryData = { ...mockServerState, status: "in_progress", winner: null }
    const { result, rerender } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    mockQueryData = { ...mockServerState, status: "finished", winner: "red" } as typeof mockQueryData

    act(() => rerender())

    expect(result.current.showGameOverTransition).toBe(false)
    expect(result.current.colophonHeld).toBe(true)
  })

  it("under reduced motion, shows the veil at once and holds it 600 ms at most", () => {
    // Prepare
    reducedMotion(true)

    // Act
    const { shownAt, liftedAt } = endTheGame()

    // Assert
    expect(shownAt).toBe(0)
    expect(liftedAt).not.toBeNull()
    expect(liftedAt! - shownAt!).toBeLessThanOrEqual(600)
  })

  it("draws no veil for a game that was already over when the page opened", () => {
    mockQueryData = { ...mockServerState, status: "finished", winner: "red" } as typeof mockQueryData
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    act(() => vi.advanceTimersByTime(100))

    expect(result.current.showGameOverTransition).toBe(false)
    expect(result.current.colophonHeld).toBe(false)
  })
})

describe("useCodenamesGame: reporting the end of the clock (BDP-03)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockIsLoading = false
    mockQueryError = null
    mockTimerExpired.mockResolvedValue({ game_id: "game-1", action: "auto_end_turn" })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("lets the host report at once", async () => {
    mockQueryData = { ...mockServerState, is_host: true, timer_started_at: "2026-10-28T14:59:00+00:00" } as typeof mockQueryData
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    await act(() => result.current.handleTimerExpired())

    expect(mockTimerExpired).toHaveBeenCalledTimes(1)
  })

  it("a non-host does not POST timer-expired within 1 s, nor at all when a game_updated arrives", async () => {
    // Prepare: a guest's clock ran out
    mockQueryData = { ...mockServerState, is_host: false, timer_started_at: "2026-10-28T14:59:00+00:00" } as typeof mockQueryData
    const { result, rerender } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    await act(() => result.current.handleTimerExpired())
    await act(() => vi.advanceTimersByTimeAsync(900))
    expect(mockTimerExpired).not.toHaveBeenCalled()

    // Act: the host's report landed, the turn passed (game_updated → the new board)
    mockQueryData = { ...mockServerState, is_host: false, current_team: "blue", timer_started_at: "2026-10-28T15:00:01+00:00" } as typeof mockQueryData
    rerender()
    await act(() => vi.advanceTimersByTimeAsync(3000))

    // Assert
    expect(mockTimerExpired).not.toHaveBeenCalled()
  })

  it("a non-host reports after its wait when nothing came", async () => {
    mockQueryData = { ...mockServerState, is_host: false, timer_started_at: "2026-10-28T14:59:00+00:00" } as typeof mockQueryData
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    await act(() => result.current.handleTimerExpired())
    await act(() => vi.advanceTimersByTimeAsync(2001))

    expect(mockTimerExpired).toHaveBeenCalledTimes(1)
  })
})

describe("useCodenamesGame: moves", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsLoading = false
    mockQueryError = null
    mockQueryData = { ...mockServerState } as typeof mockQueryData
  })

  it("says a refused move in the player's language, never an English literal", async () => {
    // Prepare
    mockEndTurn.mockRejectedValue(new TypeError("Failed to fetch"))
    mockGuess.mockRejectedValue(new TypeError("Failed to fetch"))
    mockClue.mockRejectedValue(new TypeError("Failed to fetch"))
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })
    act(() => result.current.setClueWord("Ilm"))

    // Act
    await act(() => result.current.handleEndTurn())
    await act(() => result.current.handleGuessCard(0))
    await act(() => result.current.handleGiveClue())

    // Assert
    expect(vi.mocked(toast.error).mock.calls.map((c) => c[0])).toEqual(["game.errors.moveFailed", "game.errors.moveFailed", "game.errors.moveFailed"])
  })

  it("sends one guess and one end of turn for a double tap", async () => {
    // Prepare: the requests take a moment
    mockGuess.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve({ all_voted: true }), 20)))
    mockEndTurn.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve({}), 20)))
    const { result } = renderHook(() => useCodenamesGame("game-1"), { wrapper: createWrapper() })

    // Act: two taps in the same tick, before any re-render
    await act(async () => {
      await Promise.all([result.current.handleGuessCard(1), result.current.handleGuessCard(1)])
      await Promise.all([result.current.handleEndTurn(), result.current.handleEndTurn()])
    })

    // Assert
    expect(mockGuess).toHaveBeenCalledTimes(1)
    expect(mockEndTurn).toHaveBeenCalledTimes(1)
  })
})
