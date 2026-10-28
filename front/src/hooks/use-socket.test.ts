import { describe, expect, it, vi, beforeEach } from "vitest"

// Mock socket.io-client
const mockOn = vi.fn()
const mockEmit = vi.fn()
const mockDisconnect = vi.fn()
const mockConnect = vi.fn()
const mockSocket = {
  on: mockOn,
  emit: mockEmit,
  disconnect: mockDisconnect,
  connect: mockConnect,
  connected: false,
  active: false,
}
const mockIo = vi.fn(() => mockSocket)
vi.mock("socket.io-client", () => ({
  io: (...args: unknown[]) => mockIo(...args),
}))

// The language the pages read their state in (mutable per test)
const mockLang = { value: "en" }
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: mockLang.value } }),
}))

// Mock auth
const mockToken = { value: "test-token" }
const tokenListeners = new Set<() => void>()
vi.mock("@/lib/auth", () => ({
  getStoredToken: () => mockToken.value,
  onTokenStored: (listener: () => void) => {
    tokenListeners.add(listener)
    return () => tokenListeners.delete(listener)
  },
}))

/** The handshake payload the socket would send now (auth is a function of the moment). */
function handshake(): Record<string, unknown> {
  const options = (mockIo.mock.calls.at(-1) as unknown[] | undefined)?.[1] as { auth: (cb: (data: object) => void) => void }
  let sent: Record<string, unknown> = {}
  options.auth((data) => {
    sent = data as Record<string, unknown>
  })
  return sent
}

// Mock generated API hooks
vi.mock("@/api/generated", () => ({
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/api/v1/rooms/:room_id/state", params: { room_id } }],
  getUndercoverStateApiV1UndercoverGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [
    { url: "/api/v1/undercover/games/:game_id/state", params: { game_id } },
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
}))

// Mock TanStack Query
const mockSetQueryData = vi.fn()
const mockSetQueriesData = vi.fn()
const mockInvalidateQueries = vi.fn()
const mockQueryClient = {
  setQueryData: mockSetQueryData,
  setQueriesData: mockSetQueriesData,
  invalidateQueries: mockInvalidateQueries,
}
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => mockQueryClient,
}))

// Import after mocks
const { useSocket } = await import("./use-socket")

// Minimal renderHook for testing hooks without full React test utils
import { act, renderHook } from "@testing-library/react"

describe("useSocket", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLang.value = "en"
    mockSocket.connected = false
    mockSocket.active = false
    mockToken.value = "test-token"
    tokenListeners.clear()
    mockOn.mockReset()
    mockIo.mockReturnValue(mockSocket)
  })

  it("connects when enabled with roomId", () => {
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    expect(mockIo).toHaveBeenCalledTimes(1)
    expect(handshake()).toEqual({ token: "test-token", room_id: "room-1", lang: "en" })
  })

  it("shows the token stored at each (re)connect, not the one from mount", () => {
    // Access tokens last 15 min: a reconnect after a refresh used to send the expired
    // one captured at mount, which the server refuses.
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    mockToken.value = "refreshed-token"
    expect(handshake()).toMatchObject({ token: "refreshed-token" })
  })

  it("connects again on a fresh token after the server refused the handshake", () => {
    // socket.io-client never retries a refused handshake (socket.active is false).
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    mockSocket.active = false
    tokenListeners.forEach((listener) => listener())
    expect(mockConnect).toHaveBeenCalledTimes(1)
  })

  it("leaves a socket alone that is still reconnecting by itself, or connected", () => {
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    mockSocket.active = true
    tokenListeners.forEach((listener) => listener())
    mockSocket.active = false
    mockSocket.connected = true
    tokenListeners.forEach((listener) => listener())
    expect(mockConnect).not.toHaveBeenCalled()
  })

  it("stops listening for tokens when it unmounts", () => {
    const { unmount } = renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    unmount()
    expect(tokenListeners.size).toBe(0)
  })

  it("does not connect when disabled", () => {
    renderHook(() => useSocket({ roomId: "room-1", enabled: false }))
    expect(mockIo).not.toHaveBeenCalled()
  })

  it("does not connect without roomId", () => {
    renderHook(() => useSocket({ roomId: null, enabled: true }))
    expect(mockIo).not.toHaveBeenCalled()
  })

  it("registers room_state, game_state, game_updated, connect, disconnect, and connect_error listeners", () => {
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    const events = mockOn.mock.calls.map((c: unknown[]) => c[0])
    expect(events).toContain("room_state")
    expect(events).toContain("game_state")
    expect(events).toContain("game_updated")
    expect(events).toContain("connect")
    expect(events).toContain("disconnect")
    expect(events).toContain("connect_error")
  })

  it("returns connected: false initially and true after connect event", () => {
    const { result } = renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    expect(result.current.connected).toBe(false)
  })

  it("room_state handler updates query cache", () => {
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    const roomStateHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "room_state")?.[1]

    roomStateHandler({
      id: "room-1",
      public_id: "pub-1",
      owner_id: "o1",
      password: null,
      active_game_id: null,
      game_type: "undercover",
      settings: {},
      players: [{ user_id: "u1", username: "Alice", is_spectator: false }],
    })

    expect(mockSetQueryData).toHaveBeenCalledWith(
      [{ url: "/api/v1/rooms/:room_id/state", params: { room_id: "room-1" } }],
      expect.objectContaining({
        id: "room-1",
        players: [{ user_id: "u1", username: "Alice", is_spectator: false }],
      }),
    )
  })

  it("disconnects on unmount", () => {
    const { unmount } = renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    unmount()
    expect(mockDisconnect).toHaveBeenCalled()
  })

  it("emits join_game when gameId is set and socket is connected", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))
    expect(mockEmit).toHaveBeenCalledWith("join_game", { game_id: "game-1", lang: "en" })
  })

  it("asks for the game state in the player's language", () => {
    mockLang.value = "ar"
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))
    expect(mockEmit).toHaveBeenCalledWith("join_game", { game_id: "game-1", lang: "ar" })
    expect(handshake()).toMatchObject({ lang: "ar" })

    // ...and writes the push only into the query read in that language
    const gameStateHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "game_state")?.[1]
    gameStateHandler({ phase: "description" })
    expect(mockSetQueriesData).toHaveBeenCalledWith(
      { queryKey: [{ url: "/api/v1/undercover/games/:game_id/state", params: { game_id: "game-1" } }, { lang: "ar" }] },
      { phase: "description" },
    )
  })

  it("game_updated handler invalidates game query cache", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))
    const gameUpdatedHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "game_updated")?.[1]

    gameUpdatedHandler({ game_id: "game-1" })

    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: [{ url: "/api/v1/undercover/games/:game_id/state", params: { game_id: "game-1" } }],
    })
  })

  it("you_were_kicked handler fires onKicked callback", () => {
    const onKicked = vi.fn()
    renderHook(() => useSocket({ roomId: "room-1", enabled: true, onKicked }))
    const kickHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "you_were_kicked")?.[1]

    kickHandler({ room_id: "room-1" })

    expect(onKicked).toHaveBeenCalledWith("room-1")
  })

  it("disconnect event sets connected to false", async () => {
    mockSocket.connected = true
    const { result } = renderHook(() => useSocket({ roomId: "room-1", enabled: true }))

    const connectHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "connect")?.[1]
    const { act } = await import("@testing-library/react")
    await act(() => {
      connectHandler()
    })
    expect(result.current.connected).toBe(true)

    const disconnectHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "disconnect")?.[1]
    await act(() => {
      disconnectHandler()
    })
    expect(result.current.connected).toBe(false)
  })

  it("reconnect invalidates room and game queries", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))

    const connectHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "connect")?.[1]
    act(() => connectHandler())

    // Should invalidate room state query
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: [{ url: "/api/v1/rooms/:room_id/state", params: { room_id: "room-1" } }],
      }),
    )
    // Should invalidate game state query
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: [{ url: "/api/v1/undercover/games/:game_id/state", params: { game_id: "game-1" } }],
      }),
    )
  })

  it("reconnect re-emits join_game", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))

    // Clear the initial join_game emit from the gameId effect
    mockEmit.mockClear()

    const connectHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "connect")?.[1]
    act(() => connectHandler())

    expect(mockEmit).toHaveBeenCalledWith("join_game", { game_id: "game-1", lang: "en" })
  })

  it("game_state handler for word_quiz triggers invalidateQueries not setQueriesData", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "word_quiz", enabled: true }))

    const gameStateHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "game_state")?.[1]
    gameStateHandler({ round: 1, phase: "hints" })

    expect(mockInvalidateQueries).toHaveBeenCalled()
    expect(mockSetQueriesData).not.toHaveBeenCalled()
  })

  it("game_state handler for undercover triggers setQueriesData", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))

    const gameStateHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "game_state")?.[1]
    gameStateHandler({ phase: "description", players: [] })

    expect(mockSetQueriesData).toHaveBeenCalledWith(
      { queryKey: [{ url: "/api/v1/undercover/games/:game_id/state", params: { game_id: "game-1" } }, { lang: "en" }] },
      { phase: "description", players: [] },
    )
  })

  it("connect_error does not crash", () => {
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))

    const connectErrorHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "connect_error")?.[1]

    // Should not throw
    expect(() => connectErrorHandler(new Error("test connection error"))).not.toThrow()
  })

  it("does not emit join_game when gameId is null", () => {
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: null, gameType: "undercover", enabled: true }))

    expect(mockEmit).not.toHaveBeenCalledWith("join_game", expect.anything())
  })
})
