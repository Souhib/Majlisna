import { describe, expect, it, vi, beforeEach } from "vitest"
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
  retrieveRoomIdForGame: vi.fn(() => "room-123"),
}))

vi.mock("@/api/client", () => ({
  getApiErrorMessage: vi.fn((err: unknown, fallback: string) => fallback),
}))

const mockSocketReturn = { connected: true }
// What the page asked the socket for (the kick handler in particular).
let lastSocketOptions: { onKicked?: (roomId: string) => void } | null = null
vi.mock("@/hooks/use-socket", () => ({
  useSocket: (options: { onKicked?: (roomId: string) => void }) => {
    lastSocketOptions = options
    return mockSocketReturn
  },
}))

// Mock the generated API hooks
const mockServerState = {
  my_role: "civilian",
  my_word: "Quran",
  my_word_hint: null,
  is_alive: true,
  players: [
    { user_id: "user-1", username: "TestUser", is_alive: true },
    { user_id: "user-2", username: "Player2", is_alive: true },
  ],
  eliminated_players: [],
  turn_number: 1,
  has_voted: false,
  room_id: "room-123",
  is_host: true,
  votes: {},
  winner: null,
  turn_phase: "describing",
  description_order: [{ user_id: "user-1", username: "TestUser" }],
  current_describer_index: 0,
  descriptions: {},
  vote_history: [],
  timer_config: { description_seconds: 60, voting_seconds: 30 },
  timer_started_at: null,
  newly_unlocked_achievements: [],
  word_explanations: null,
}

// Shared, so the prayer-pause tests can see what was (not) sent.
const mockVote = vi.fn()
const mockDescribe = vi.fn()
const mockTimerExpired = vi.fn()

let mockQueryData: typeof mockServerState | undefined = undefined
let mockIsLoading = true
let mockQueryError: Error | null = null

vi.mock("@/api/generated", () => ({
  useGetUndercoverStateApiV1UndercoverGamesGameIdStateGet: () => ({
    data: mockQueryData,
    isLoading: mockIsLoading,
    error: mockQueryError,
  }),
  useSubmitVoteApiV1UndercoverGamesGameIdVotePost: () => ({ mutateAsync: mockVote }),
  useSubmitDescriptionApiV1UndercoverGamesGameIdDescribePost: () => ({ mutateAsync: mockDescribe }),
  useRecordHintViewedApiV1UndercoverGamesGameIdHintViewedPost: () => ({ mutateAsync: vi.fn() }),
  useTimerExpiredApiV1UndercoverGamesGameIdTimerExpiredPost: () => ({ mutateAsync: mockTimerExpired }),
  useStartNextRoundApiV1UndercoverGamesGameIdNextRoundPost: () => ({ mutateAsync: vi.fn() }),
  useMrWhiteGuessApiV1UndercoverGamesGameIdMrWhiteGuessPost: () => ({ mutateAsync: vi.fn() }),
  useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: vi.fn() }),
  getUndercoverStateApiV1UndercoverGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/undercover/games/:game_id/state", params: { game_id } },
  ],
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [
    { url: "/api/v1/rooms/:room_id/state", params: { room_id } },
  ],
  getCodenamesBoardApiV1CodenamesGamesGameIdBoardGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/codenames/games/:game_id/board", params: { game_id } },
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
const { useUndercoverGame } = await import("./use-undercover-game")
const { takeRoomNotice } = await import("@/lib/room-notice")

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

describe("useUndercoverGame", () => {
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

    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.serverState).toBeUndefined()
  })

  it("returns game data when query succeeds", () => {
    mockIsLoading = false
    mockQueryData = { ...mockServerState }

    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.serverState).toBeDefined()
    expect(result.current.gameState.players).toHaveLength(2)
    expect(result.current.gameState.players[0].id).toBe("user-1")
    expect(result.current.gameState.players[0].username).toBe("TestUser")
    expect(result.current.gameState.round).toBe(1)
    expect(result.current.gameState.isHost).toBe(true)
  })

  it("passes through socket connected state", () => {
    mockIsLoading = false
    mockQueryData = { ...mockServerState }
    mockSocketReturn.connected = true

    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(result.current.socketConnected).toBe(true)

    mockSocketReturn.connected = false
    const { result: result2 } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(result2.current.socketConnected).toBe(false)
  })

  it("derives correct phase from game state", () => {
    mockIsLoading = false

    // describing phase
    mockQueryData = { ...mockServerState, turn_phase: "describing", winner: null, turn_number: 2 }
    const { result: r1 } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(r1.current.gameState.phase).toBe("describing")

    // game_over phase
    mockQueryData = { ...mockServerState, winner: "civilians" }
    const { result: r2 } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(r2.current.gameState.phase).toBe("game_over")

    // voting phase
    mockQueryData = { ...mockServerState, turn_phase: "voting", turn_number: 1, winner: null }
    const { result: r3 } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(r3.current.gameState.phase).toBe("playing")
  })

  it("returns safe defaults when serverState is undefined", () => {
    mockIsLoading = false
    mockQueryData = undefined

    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.gameState.players).toEqual([])
    expect(result.current.gameState.phase).toBe("role_reveal")
    expect(result.current.gameState.round).toBe(1)
    expect(result.current.gameState.votedPlayers).toEqual([])
    expect(result.current.gameState.isHost).toBe(false)
    expect(result.current.gameState.descriptionOrder).toEqual([])
    expect(result.current.gameState.descriptions).toEqual({})
  })
})

describe("useUndercoverGame: the verdict notice", () => {
  const resolvedRound = {
    round: 1,
    votes: [{ voter: "Player2", voter_id: "user-2", target: "Player3", target_id: "user-3" }],
    eliminated: { username: "Player3", role: "civilian", user_id: "user-3" },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsLoading = false
    mockQueryError = null
  })

  it("does not raise the notice when the round resolves on screen (the round-over screen tells it)", () => {
    mockQueryData = { ...mockServerState, turn_phase: "voting", turn_number: 1 }
    const { result, rerender } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    mockQueryData = { ...mockServerState, turn_phase: "voting", turn_number: 1, round_resolved: true, vote_history: [resolvedRound] } as typeof mockQueryData
    rerender()
    expect(result.current.gameState.phase).toBe("round_over")
    expect(result.current.showEliminationOverlay).toBe(false)
    // and not later either, when the next round starts
    mockQueryData = { ...mockServerState, turn_phase: "describing", turn_number: 2, vote_history: [resolvedRound] } as typeof mockQueryData
    rerender()
    expect(result.current.showEliminationOverlay).toBe(false)
  })

  it("raises the notice for a client that only saw the next round start", () => {
    mockQueryData = { ...mockServerState, turn_phase: "voting", turn_number: 1 }
    const { result, rerender } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    mockQueryData = { ...mockServerState, turn_phase: "describing", turn_number: 2, vote_history: [resolvedRound] } as typeof mockQueryData
    rerender()
    expect(result.current.showEliminationOverlay).toBe(true)
    expect(result.current.eliminationData).toMatchObject({ round: 1, username: "Player3", role: "civilian", user_id: "user-3" })
  })

  it("never announces achievements as toasts: they arrive as seals on the colophon", async () => {
    // Prepare: the server says the caller just earned a badge
    const { toast } = await import("sonner")
    mockQueryData = {
      ...mockServerState,
      newly_unlocked_achievements: [{ user_id: "user-1", achievements: [{ code: "first_win", name: "First win", icon: "", tier: 1 }] }],
    } as unknown as typeof mockServerState

    // Act
    renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    // Assert
    expect(toast.info).not.toHaveBeenCalled()
    expect(toast.error).not.toHaveBeenCalled()
    expect(toast.warning).not.toHaveBeenCalled()
  })
})

describe("useUndercoverGame: the prayer pause", () => {
  const pause = {
    by_user_id: "user-1",
    by_username: "TestUser",
    since: "2026-10-28T15:00:00+00:00",
    reason: "salah" as const,
    remaining_seconds: 42,
    paused_for_seconds: 60,
    anyone_can_resume_at: "2026-10-28T15:45:00+00:00",
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsLoading = false
    mockQueryError = null
  })

  it("says the game is paused", () => {
    mockQueryData = { ...mockServerState, paused: pause } as typeof mockQueryData
    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(result.current.isPaused).toBe(true)
  })

  it("never reports an expired timer while the game is paused", async () => {
    // Prepare
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T14:59:00+00:00", paused: pause } as typeof mockQueryData
    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    // Act
    await act(() => result.current.handleTimerExpired())

    // Assert
    expect(mockTimerExpired).not.toHaveBeenCalled()
  })

  it("stops reporting a timer the server answered 'paused' or 'round_already_resolved' for, until a new window", async () => {
    // Prepare: the clock ran out a beat before the pause reached this client
    mockTimerExpired.mockResolvedValue({ game_id: "game-1", action: "paused" })
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T14:59:00+00:00" } as typeof mockQueryData
    const { result, rerender } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    // Act: the PhaseTimer's 15 s valve fires again for the same window
    await act(() => result.current.handleTimerExpired())
    await act(() => result.current.handleTimerExpired())

    // Assert: one request for the window
    expect(mockTimerExpired).toHaveBeenCalledTimes(1)

    // The resume moved the start forward: a new window may be reported again
    mockTimerExpired.mockResolvedValue({ game_id: "game-1", action: "round_already_resolved" })
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T15:10:00+00:00" } as typeof mockQueryData
    rerender()
    await act(() => result.current.handleTimerExpired())
    await act(() => result.current.handleTimerExpired())
    expect(mockTimerExpired).toHaveBeenCalledTimes(2)
  })

  it("keeps reporting after an answer that is not a stop", async () => {
    mockTimerExpired.mockResolvedValue({ game_id: "game-1", action: "timer_not_expired" })
    mockQueryData = { ...mockServerState, timer_started_at: "2026-10-28T14:59:00+00:00" } as typeof mockQueryData
    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    await act(() => result.current.handleTimerExpired())
    await act(() => result.current.handleTimerExpired())

    expect(mockTimerExpired).toHaveBeenCalledTimes(2)
  })

  it("sends no move while the game is paused", async () => {
    // Prepare: my turn to describe, a word typed, the game paused
    mockQueryData = { ...mockServerState, paused: pause } as typeof mockQueryData
    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    act(() => result.current.handleDescriptionInputChange("patience"))

    // Act
    await act(() => result.current.handleSubmitDescription())

    // Assert
    expect(mockDescribe).not.toHaveBeenCalled()
  })

  it("shows the translated refusal when a move lands just after the pause", async () => {
    // Prepare: the pause has not reached this client yet
    const { toast } = await import("sonner")
    const refusal = Object.assign(new Error("paused"), {
      response: { status: 409, data: { error_key: "errors.api.gamePaused", message: "The game is paused for the prayer." } },
    })
    mockDescribe.mockRejectedValue(refusal)
    mockQueryData = { ...mockServerState } as typeof mockQueryData
    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    act(() => result.current.handleDescriptionInputChange("patience"))

    // Act
    await act(() => result.current.handleSubmitDescription())

    // Assert: the server's error is told (getApiErrorMessage is mocked to the fallback here)
    expect(mockDescribe).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledTimes(1)
  })
})

describe("useUndercoverGame: leaving a game you can no longer play", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQueryData = { ...mockServerState }
    mockIsLoading = false
    mockQueryError = null
    lastSocketOptions = null
    takeRoomNotice()
  })

  it("sends a player the host removed to /rooms, with the notice for that page, once", () => {
    renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })
    expect(lastSocketOptions?.onKicked).toBeTypeOf("function")

    act(() => {
      lastSocketOptions?.onKicked?.("room-123")
      lastSocketOptions?.onKicked?.("room-123")
    })

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/rooms" })
    expect(takeRoomNotice()).toBe("kicked")
  })

  it("tells a removed player the game is gone by the status, whatever the language of the text", () => {
    mockQueryData = undefined
    mockQueryError = Object.assign(new Error("Request failed"), {
      response: { status: 403, data: { message: "Player user-1 was removed from game game-1 due to inactivity" } },
    })

    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.cancelMessage).toBeTruthy()
  })

  it("does not treat any other error as the game being gone", () => {
    mockQueryData = undefined
    mockQueryError = Object.assign(new Error("Request failed"), { response: { status: 500, data: { message: "boom" } } })

    const { result } = renderHook(() => useUndercoverGame("game-1"), { wrapper: createWrapper() })

    expect(result.current.cancelMessage).toBeNull()
  })
})
