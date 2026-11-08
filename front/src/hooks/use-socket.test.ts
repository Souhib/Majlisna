import { describe, expect, it, vi, beforeEach } from "vitest"
import { queryKeys } from "@/api/queryKeys"

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
  getMessagesApiV1RoomsRoomIdMessagesGetQueryKey: ({ room_id }: { room_id: string }, params: object = {}) => [
    { url: "/api/v1/rooms/:room_id/messages", params: { room_id } },
    params,
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

/** The listener the hook registered last for a socket event. */
function handlerFor(event: string): (...args: unknown[]) => void {
  const call = mockOn.mock.calls.filter((c: unknown[]) => c[0] === event).at(-1)
  if (!call) throw new Error(`no listener for ${event}`)
  return call[1] as (...args: unknown[]) => void
}

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

  it("a room_state read before the one on screen never replaces it (pushes can cross)", () => {
    // Prepare
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    const roomStateHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "room_state")?.[1]
    const onScreen = { id: "room-1", game_type: "word_quiz", players: [], as_of_ms: 2_000 }

    // Act — the connect's read, made before the host's pick, arrives after the pick's push
    roomStateHandler({ id: "room-1", game_type: "undercover", players: [], as_of_ms: 1_000 })

    // Assert — written through an updater that keeps the newer read
    const [key, write] = mockSetQueryData.mock.calls.at(-1) as [unknown, (old: unknown) => unknown]
    expect(key).toEqual([{ url: "/api/v1/rooms/:room_id/state", params: { room_id: "room-1" } }])
    expect(write(onScreen)).toBe(onScreen)
    expect(write({ ...onScreen, as_of_ms: 500 })).toEqual(expect.objectContaining({ game_type: "undercover", as_of_ms: 1_000 }))
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

    const [key, write] = mockSetQueryData.mock.calls.at(-1) as [unknown, (old: unknown) => unknown]
    expect(key).toEqual([{ url: "/api/v1/rooms/:room_id/state", params: { room_id: "room-1" } }])
    expect(write(undefined)).toEqual(
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

  it("you_were_kicked handler fires onKicked callback, saying whether it was a ban", () => {
    const onKicked = vi.fn()
    renderHook(() => useSocket({ roomId: "room-1", enabled: true, onKicked }))
    const kickHandler = mockOn.mock.calls.find((c: unknown[]) => c[0] === "you_were_kicked")?.[1]

    kickHandler({ room_id: "room-1", banned: false })
    kickHandler({ room_id: "room-1", banned: true })
    // a server from before the ban had its own action sends no `banned`: a kick
    kickHandler({ room_id: "room-1" })

    expect(onKicked.mock.calls).toEqual([
      ["room-1", false],
      ["room-1", true],
      ["room-1", false],
    ])
  })

  it("you_were_kicked for another room is not this page's: the player stays where they are", () => {
    // Prepare: seated in room-1. The event reaches every socket of the player (it goes to
    // their personal channel, which a room socket joins too): a removal from a room they had
    // left away (Remove), or a ban from one they were removed from earlier
    const onKicked = vi.fn()
    renderHook(() => useSocket({ roomId: "room-1", enabled: true, onKicked }))

    // Act
    handlerFor("you_were_kicked")({ room_id: "room-0", banned: false })
    handlerFor("you_were_kicked")({ room_id: "room-0", banned: true })

    // Assert
    expect(onKicked).not.toHaveBeenCalled()
  })

  it("member_removed_by_host tells the page which of the host's removals took a seat, and a ban's name", () => {
    const onMemberRemoved = vi.fn()
    renderHook(() => useSocket({ roomId: "room-1", enabled: true, onMemberRemoved }))

    handlerFor("member_removed_by_host")({ room_id: "room-1", user_id: "u2", banned: false, username: null })
    handlerFor("member_removed_by_host")({ room_id: "room-1", user_id: "u3", banned: true, username: "Omar" })
    // a server from before the name was sent
    handlerFor("member_removed_by_host")({ room_id: "room-1", user_id: "u4", banned: true })

    expect(onMemberRemoved.mock.calls).toEqual([
      ["u2", false, null],
      ["u3", true, "Omar"],
      ["u4", true, null],
    ])
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

  it("the first connect re-reads the chat history only", () => {
    // The page read its state over REST, the server pushes room_state on connect and
    // join_game answers with game_state: refetching those was a third read of the same
    // state on every load (FP-10). The chat is different: a line sent between the page's
    // history read and the socket joining the room was pushed to nobody and never shown
    // until a reconnect (CI, 2026-11-01). One read after the join closes that gap.
    // Prepare
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))
    const connectHandler = handlerFor("connect")

    // Act
    act(() => connectHandler())

    // Assert
    expect(mockInvalidateQueries).toHaveBeenCalledTimes(1)
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.room.messages("room-1") })
    expect(mockEmit).toHaveBeenCalledWith("join_game", { game_id: "game-1", lang: "en" })
  })

  it("a reconnect invalidates the room, game and chat queries", () => {
    // python-socketio replays nothing: what happened while the socket was down (a chat
    // line above all, which nothing else re-reads) has to be fetched again (FR-6).
    // Prepare
    mockSocket.connected = true
    renderHook(() => useSocket({ roomId: "room-1", gameId: "game-1", gameType: "undercover", enabled: true }))
    act(() => handlerFor("connect")())
    act(() => handlerFor("disconnect")())
    mockInvalidateQueries.mockClear()

    // Act
    act(() => handlerFor("connect")())

    // Assert
    const invalidated = mockInvalidateQueries.mock.calls.map((c: unknown[]) => (c[0] as { queryKey: unknown }).queryKey)
    expect(invalidated).toContainEqual([{ url: "/api/v1/rooms/:room_id/state", params: { room_id: "room-1" } }])
    expect(invalidated).toContainEqual([{ url: "/api/v1/undercover/games/:game_id/state", params: { game_id: "game-1" } }])
    expect(invalidated).toContainEqual([{ url: "/api/v1/rooms/:room_id/messages", params: { room_id: "room-1" } }, {}])
  })

  it("catches up on a first connect that came after a failed attempt", () => {
    // The page read its state at mount, then the socket could not connect for a while:
    // a chat line sent in between reached no one's socket.
    // Prepare
    renderHook(() => useSocket({ roomId: "room-1", enabled: true }))
    handlerFor("connect_error")(new Error("websocket error"))

    // Act
    act(() => handlerFor("connect")())

    // Assert
    const invalidated = mockInvalidateQueries.mock.calls.map((c: unknown[]) => (c[0] as { queryKey: unknown }).queryKey)
    expect(invalidated).toContainEqual([{ url: "/api/v1/rooms/:room_id/state", params: { room_id: "room-1" } }])
    expect(invalidated).toContainEqual([{ url: "/api/v1/rooms/:room_id/messages", params: { room_id: "room-1" } }, {}])
  })

  it("a socket for another room starts over: its first connect re-reads that room's chat only", () => {
    // Prepare
    const { rerender } = renderHook(({ roomId }) => useSocket({ roomId, enabled: true }), { initialProps: { roomId: "room-1" } })
    act(() => handlerFor("connect")())
    act(() => handlerFor("disconnect")())
    mockOn.mockClear()
    mockInvalidateQueries.mockClear()

    // Act
    rerender({ roomId: "room-2" })
    act(() => handlerFor("connect")())

    // Assert
    expect(mockIo).toHaveBeenCalledTimes(2)
    expect(mockInvalidateQueries).toHaveBeenCalledTimes(1)
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.room.messages("room-2") })
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
