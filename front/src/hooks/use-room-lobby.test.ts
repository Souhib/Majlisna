import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { createElement, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useGetShareLinkApiV1RoomsRoomIdShareLinkGet, useListRoomBansApiV1RoomsRoomIdBansGet } from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import type { LobbyMember } from "@/components/rooms/lobby"
import { LOBBY_RIDDLE_SCOPE, readRiddleRecord, writeRiddleRecord } from "@/components/rooms/samar-riddle"
import { useRoomLobby } from "./use-room-lobby"

/**
 * The lobby's client logic (TQ-12): the real generated hooks over the fake client, a
 * socket whose state the test sets, and fake timers where the clock matters.
 */
const router = vi.hoisted(() => ({ navigate: vi.fn() }))
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
const notices = vi.hoisted(() => ({ note: vi.fn() }))
const analytics = vi.hoisted(() => ({ track: vi.fn() }))
// The socket as the page sees it: `connected` is set by the test and re-renders the hook.
const socket = vi.hoisted(() => {
  let connected = false
  const listeners = new Set<() => void>()
  return {
    options: [] as { enabled?: boolean; onKicked?: (roomId: string) => void }[],
    get connected() {
      return connected
    },
    set(next: boolean) {
      connected = next
      listeners.forEach((listener) => listener())
    },
    reset() {
      connected = false
      this.options.length = 0
    },
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
})

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => router.navigate }))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/hooks/use-socket", async () => {
  const { useSyncExternalStore } = await import("react")
  return {
    useSocket: (options: { enabled?: boolean; onKicked?: (roomId: string) => void }) => {
      socket.options.push(options)
      const connected = useSyncExternalStore(
        (listener) => socket.subscribe(listener),
        () => socket.connected,
      )
      return { connected }
    },
  }
})
vi.mock("@/lib/analytics", () => ({ trackEvent: analytics.track }))
vi.mock("@/lib/room-notice", () => ({ noteRoomNotice: notices.note }))
vi.mock("sonner", () => ({ toast: toasts }))

const STATE = "GET /api/v1/rooms/room-1/state"
const BANS = "GET /api/v1/rooms/room-1/bans"
const SHARE = "GET /api/v1/rooms/room-1/share-link"
const KICK = "PATCH /api/v1/rooms/room-1/kick"
const LEAVE = "PATCH /api/v1/rooms/leave"

const player = (user_id: string, username: string) => ({ user_id, username, is_spectator: false, is_disconnected: false, away_seconds_left: null })

const roomState = (over: Record<string, unknown> = {}) => ({
  id: "room-1",
  public_id: "QX7PA",
  owner_id: "u1",
  password: "4821",
  active_game_id: null,
  game_type: "undercover",
  settings: { game_type: "undercover" },
  players: [player("u1", "Yusuf"), player("u2", "Maryam"), player("u3", "Ali")],
  ...over,
})

const RIDDLE = {
  id: "w1",
  category: "prophets" as const,
  hint: "A great patriarch",
  answer: { word_display: "Ibrahim", word_ar: "إبراهيم", word_ar_vocalized: null },
}

const maryam: LobbyMember = { id: "u2", username: "Maryam", isHost: false, isSpectator: false, isAway: false, awaySecondsLeft: null }

/** The lobby, plus the two reads a kick makes stale (the host's bans panel, a share link). */
function useLobbyAndItsReads() {
  const lobby = useRoomLobby("room-1")
  const bans = useListRoomBansApiV1RoomsRoomIdBansGet({ room_id: "room-1" })
  const share = useGetShareLinkApiV1RoomsRoomIdShareLinkGet({ room_id: "room-1" })
  return { lobby, bans, share }
}

function renderLobby() {
  // the hook's own query options (retry, refetchInterval) are under test: no test defaults
  const queryClient = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children)
  const view = renderHook(() => useRoomLobby("room-1"), { wrapper })
  return { queryClient, ...view }
}

function renderLobbyAndReads() {
  const queryClient = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children)
  const view = renderHook(() => useLobbyAndItsReads(), { wrapper })
  return { queryClient, ...view }
}

const advance = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })

beforeEach(() => {
  resetFakeApi()
  socket.reset()
  router.navigate.mockReset()
  notices.note.mockReset()
  analytics.track.mockReset()
  Object.values(toasts).forEach((fn) => fn.mockReset())
  sessionStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("useRoomLobby: reading the room", () => {
  it("polls every 2 s while the socket is down, and stops once it is up", async () => {
    // Prepare
    vi.useFakeTimers()
    answer(STATE, () => roomState())
    const { result } = renderLobby()
    await advance(0)
    expect(result.current.room?.publicId).toBe("QX7PA")
    expect(requestsTo(STATE)).toHaveLength(1)

    // Act: two polls, then the socket connects
    await advance(4_000)
    const polled = requestsTo(STATE).length
    act(() => socket.set(true))
    await advance(10_000)

    // Assert: polled while down; the connect (a first one) re-reads nothing and stops the polls
    expect(polled).toBe(3)
    expect(result.current.socketConnected).toBe(true)
    expect(requestsTo(STATE)).toHaveLength(polled)
  })

  it("stops on a 404 with nothing on screen: no retry, no poll, no socket (FR-5)", async () => {
    // Prepare
    vi.useFakeTimers()
    answer(STATE, () => {
      throw httpError(404, { error: "UserNotInRoomError", error_key: "errors.api.userNotInRoom" })
    })

    // Act
    const { result } = renderLobby()
    await advance(10_000)

    // Assert
    expect(requestsTo(STATE)).toHaveLength(1)
    expect(result.current.room).toBeUndefined()
    expect(result.current.notSeated).toBe(true)
    expect(result.current.refusal).toMatchObject({ response: { status: 404 } })
    expect(socket.options.at(-1)?.enabled).toBe(false)
  })

  it("tries a 5xx with nothing on screen twice more, then stops asking", async () => {
    // Prepare
    vi.useFakeTimers()
    answer(STATE, () => {
      throw httpError(503, {})
    })

    // Act
    const { result } = renderLobby()
    await advance(30_000)

    // Assert
    expect(requestsTo(STATE)).toHaveLength(3)
    expect(result.current.refusal).toMatchObject({ response: { status: 503 } })
    expect(result.current.notSeated).toBe(false)
    expect(socket.options.at(-1)?.enabled).toBe(true)
  })

  it("keeps the roster on screen when a poll fails, says it is stale, and keeps polling", async () => {
    // Prepare
    vi.useFakeTimers()
    answer(STATE, () => roomState())
    const { result } = renderLobby()
    await advance(0)
    answer(STATE, () => {
      throw httpError(500, {})
    })

    // Act: a poll and its two retries fail
    await advance(10_000)

    // Assert
    expect(result.current.isError).toBe(true)
    expect(result.current.room?.members.map((m) => m.username)).toEqual(["Yusuf", "Maryam", "Ali"])
    expect(result.current.refusal).toBeNull()
    const asked = requestsTo(STATE).length
    await advance(4_000)
    expect(requestsTo(STATE).length).toBeGreaterThan(asked)
  })

  it("ignores a malformed push and keeps the last good room", async () => {
    // Prepare
    answer(STATE, () => roomState())
    const { result, queryClient } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    act(() => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), { id: "room-1" })
    })

    // Assert: no room (the skeleton), never a crash on a missing field
    await waitFor(() => expect(result.current.room).toBeUndefined())
    expect(result.current.refusal).toBeNull()
  })
})

describe("useRoomLobby: the host removes a player (owner rule c)", () => {
  it("a kick that went through re-reads the room state, the share link and the bans list", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer(BANS, () => [])
    answer(SHARE, () => ({ public_id: "QX7PA", password: "4821" }))
    answer(KICK, () => ({ status: "kicked" }))
    const { result } = renderLobbyAndReads()
    await waitFor(() => expect(result.current.share.data).toBeDefined())
    await waitFor(() => expect(result.current.bans.data).toBeDefined())
    const before = { state: requestsTo(STATE).length, bans: requestsTo(BANS).length, share: requestsTo(SHARE).length }
    answer(BANS, () => [{ user_id: "u2", username: "Maryam", banned_at: "2026-10-31T18:00:00Z" }])
    answer(SHARE, () => ({ public_id: "QX7PA", password: "9034" }))

    // Act
    await act(async () => {
      await result.current.lobby.kickPlayer(maryam)
    })

    // Assert: the kick was sent once, and every read holding the old PIN or the old list is re-read
    expect(requestsTo(KICK).map((r) => r.data)).toEqual([{ user_id: "u2" }])
    await waitFor(() => expect(result.current.bans.data).toHaveLength(1))
    await waitFor(() => expect(result.current.share.data?.password).toBe("9034"))
    expect(requestsTo(STATE).length).toBeGreaterThan(before.state)
    expect(requestsTo(BANS)).toHaveLength(before.bans + 1)
    expect(requestsTo(SHARE)).toHaveLength(before.share + 1)
    expect(result.current.lobby.kickingId).toBeNull()
    expect(toasts.error).not.toHaveBeenCalled()
  })

  it("marks the player being removed until the kick has settled", async () => {
    // Prepare
    answer(STATE, () => roomState())
    let release!: () => void
    answer(KICK, () => new Promise((resolve) => (release = () => resolve({ status: "kicked" }))))
    const { result } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    let kicked!: Promise<void>
    act(() => {
      kicked = result.current.kickPlayer(maryam)
    })

    // Assert
    expect(result.current.kickingId).toBe("u2")
    await waitFor(() => expect(requestsTo(KICK)).toHaveLength(1))
    expect(result.current.kickingId).toBe("u2")
    await act(async () => {
      release()
      await kicked
    })
    expect(result.current.kickingId).toBeNull()
  })

  it("a kick that failed says so and re-reads nothing", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer(BANS, () => [])
    answer(SHARE, () => ({ public_id: "QX7PA", password: "4821" }))
    answer(KICK, () => {
      throw httpError(403, { error_key: "errors.api.notRoomHost" })
    })
    const { result } = renderLobbyAndReads()
    await waitFor(() => expect(result.current.share.data).toBeDefined())
    await waitFor(() => expect(result.current.bans.data).toBeDefined())
    const before = { bans: requestsTo(BANS).length, share: requestsTo(SHARE).length }

    // Act
    await act(async () => {
      await result.current.lobby.kickPlayer(maryam)
    })

    // Assert
    expect(toasts.error).toHaveBeenCalledWith("errors.api.notRoomHost")
    expect(requestsTo(BANS)).toHaveLength(before.bans)
    expect(requestsTo(SHARE)).toHaveLength(before.share)
    expect(result.current.lobby.kickingId).toBeNull()
  })

  it("a new PIN in the room state re-reads the share link and the bans list (a kick from the host's other device)", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer(BANS, () => [])
    answer(SHARE, () => ({ public_id: "QX7PA", password: "4821" }))
    const { result, queryClient } = renderLobbyAndReads()
    await waitFor(() => expect(result.current.share.data).toBeDefined())
    await waitFor(() => expect(result.current.bans.data).toBeDefined())
    const before = { bans: requestsTo(BANS).length, share: requestsTo(SHARE).length }

    // Act: a push with the same PIN, then one with a new PIN
    act(() => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ players: [player("u1", "Yusuf"), player("u3", "Ali")] }))
    })
    await waitFor(() => expect(result.current.lobby.members).toHaveLength(2))
    expect(requestsTo(BANS)).toHaveLength(before.bans)
    expect(requestsTo(SHARE)).toHaveLength(before.share)
    act(() => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ password: "9034", players: [player("u1", "Yusuf"), player("u3", "Ali")] }))
    })

    // Assert
    await waitFor(() => expect(result.current.lobby.room?.password).toBe("9034"))
    await waitFor(() => expect(requestsTo(BANS)).toHaveLength(before.bans + 1))
    await waitFor(() => expect(requestsTo(SHARE)).toHaveLength(before.share + 1))
  })
})

describe("useRoomLobby: leaving, and being removed", () => {
  it("leaves for /rooms, once, with the notice, when the room state no longer seats the player", async () => {
    // Prepare
    answer(STATE, () => roomState())
    const { result, queryClient } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act: the state that no longer has us (polling: no you_were_kicked reaches us), then the socket event too
    act(() => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ players: [player("u2", "Maryam"), player("u3", "Ali")], owner_id: "u2" }))
    })
    await waitFor(() => expect(router.navigate).toHaveBeenCalled())
    act(() => socket.options.at(-1)?.onKicked?.("room-1"))

    // Assert
    expect(router.navigate).toHaveBeenCalledOnce()
    expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms" })
    expect(notices.note).toHaveBeenCalledWith("kicked")
  })

  it("leaving is not being removed: the leave is sent, said, and no removal notice follows", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer(LEAVE, () => ({ status: "left" }))
    const { result, queryClient } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    await act(async () => {
      await result.current.leaveRoom()
    })
    act(() => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ players: [player("u2", "Maryam")], owner_id: "u2" }))
    })
    await waitFor(() => expect(result.current.members.map((m) => m.id)).toEqual(["u2"]))

    // Assert
    expect(requestsTo(LEAVE).map((r) => r.data)).toEqual([{ room_id: "room-1" }])
    expect(toasts.info).toHaveBeenCalledWith("toast.youLeftRoom")
    expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms" })
    expect(notices.note).not.toHaveBeenCalled()
  })

  it("still leaves when the leave request fails (the grace sweep frees the seat)", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer(LEAVE, () => {
      throw httpError(500, {})
    })
    const { result } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    await act(async () => {
      await result.current.leaveRoom()
    })

    // Assert
    expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms" })
  })
})

describe("useRoomLobby: the game", () => {
  it("starts the room's game with ONE request, a double tap included, and follows it", async () => {
    // Prepare
    answer(STATE, () => roomState({ game_type: "word_quiz", settings: { game_type: "word_quiz" } }))
    let release!: () => void
    answer("POST /api/v1/wordquiz/games/room-1/start", () => new Promise((resolve) => (release = () => resolve({ game_id: "g1", room_id: "room-1" }))))
    const { result } = renderLobby()
    await waitFor(() => expect(result.current.gameType).toBe("word_quiz"))

    // Act
    act(() => {
      result.current.startGame(3)
      result.current.startGame(3)
    })
    await waitFor(() => expect(requestsTo("POST /api/v1/wordquiz/games/room-1/start")).toHaveLength(1))
    await act(async () => release())

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/game/wordquiz/$gameId", params: { gameId: "g1" } }))
    expect(router.navigate).toHaveBeenCalledOnce()
    expect(requestsTo("POST /api/v1/wordquiz/games/room-1/start")).toHaveLength(1)
    expect(analytics.track).toHaveBeenCalledWith("game-start", { game: "word_quiz", players: 3 })
    expect(sessionStorage.getItem("game-room:g1")).toBe("room-1")
    expect(toasts.success).not.toHaveBeenCalled()
  })

  it("lets the host try again after a start that failed", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer("POST /api/v1/undercover/games/room-1/start", () => {
      throw httpError(400, { error_key: "errors.api.notEnoughPlayers" })
    })
    const { result } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    act(() => result.current.startGame(3))
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith("errors.api.notEnoughPlayers"))
    await waitFor(() => expect(result.current.isStartingGame).toBe(false))
    act(() => result.current.startGame(3))

    // Assert
    await waitFor(() => expect(requestsTo("POST /api/v1/undercover/games/room-1/start")).toHaveLength(2))
    expect(router.navigate).not.toHaveBeenCalled()
  })

  it("sends every member to the game the room state names, once", async () => {
    // Prepare
    answer(STATE, () => roomState({ owner_id: "u2" }))
    const { result, queryClient } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act: the push, then the same state again
    const started = roomState({ owner_id: "u2", active_game_id: "g7", game_type: "codenames", settings: { game_type: "codenames" } })
    act(() => queryClient.setQueryData(queryKeys.room.state("room-1"), started))
    await waitFor(() => expect(router.navigate).toHaveBeenCalled())
    await act(async () => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), { ...started, players: [...started.players] })
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    // Assert
    expect(router.navigate).toHaveBeenCalledOnce()
    expect(router.navigate).toHaveBeenCalledWith({ to: "/game/codenames/$gameId", params: { gameId: "g7" } })
    expect(sessionStorage.getItem("game-room:g7")).toBe("room-1")
  })

  it("answers the lobby's riddle as a member follows the table into the game (read at the room's next wait)", async () => {
    // Prepare: a samar riddle on screen in this tab, its answer not read yet
    writeRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE, {
      current: { riddle: RIDDLE, lang: "en", waitKey: LOBBY_RIDDLE_SCOPE, shownAt: 1, revealed: false },
      last: null,
    })
    answer(STATE, () => roomState({ owner_id: "u2" }))
    const { result, queryClient } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    act(() => queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ owner_id: "u2", active_game_id: "g7" })))
    await waitFor(() => expect(router.navigate).toHaveBeenCalled())

    // Assert
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)).toEqual({ current: null, last: { riddle: RIDDLE, lang: "en" } })
  })

  it("answers the lobby's riddle when the host's own start goes through", async () => {
    // Prepare
    writeRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE, {
      current: { riddle: RIDDLE, lang: "en", waitKey: LOBBY_RIDDLE_SCOPE, shownAt: 1, revealed: false },
      last: null,
    })
    answer(STATE, () => roomState())
    answer("POST /api/v1/undercover/games/room-1/start", () => ({ game_id: "g1", room_id: "room-1" }))
    const { result } = renderLobby()
    await waitFor(() => expect(result.current.room).toBeDefined())

    // Act
    act(() => result.current.startGame(3))
    await waitFor(() => expect(router.navigate).toHaveBeenCalled())

    // Assert
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE).last?.riddle.id).toBe("w1")
  })

  it("shows the host's pick at once, and keeps it once the server has it", async () => {
    // Prepare
    answer(STATE, () => roomState())
    let release!: () => void
    answer("PATCH /api/v1/rooms/room-1/settings", () => new Promise((resolve) => (release = () => resolve({ status: "ok" }))))
    const { result } = renderLobby()
    await waitFor(() => expect(result.current.isHost).toBe(true))
    expect(result.current.gameType).toBe("undercover")

    // Act
    let picked!: Promise<void>
    act(() => {
      picked = result.current.pickGame("mcq_quiz")
    })
    expect(result.current.gameType).toBe("mcq_quiz")
    await waitFor(() => expect(requestsTo("PATCH /api/v1/rooms/room-1/settings")).toHaveLength(1))
    await act(async () => {
      release()
      await picked
    })

    // Assert: the server's copy now says it (the pick written into the cache)
    expect(result.current.gameType).toBe("mcq_quiz")
    expect(result.current.room?.gameType).toBe("mcq_quiz")
    expect(requestsTo("PATCH /api/v1/rooms/room-1/settings").map((r) => r.data)).toEqual([{ game_type: "mcq_quiz" }])
  })
})

describe("useRoomLobby: sharing the room", () => {
  it("copies the link with the PIN the room state carries now, and says so for 1.5 s", async () => {
    // Prepare
    vi.useFakeTimers()
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
    answer(STATE, () => roomState())
    const { result, queryClient } = renderLobby()
    await advance(50)
    expect(result.current.room?.password).toBe("4821")
    act(() => queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ password: "9034" })))
    await advance(50)

    // Act
    await act(async () => {
      await result.current.shareRoom()
    })

    // Assert
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/rooms/join?code=QX7PA&pin=9034`)
    expect(toasts.success).toHaveBeenCalledWith("room.lobbyPage.shareToast")
    expect(result.current.shareCopied).toBe(true)
    await advance(1_500)
    expect(result.current.shareCopied).toBe(false)
  })
})
