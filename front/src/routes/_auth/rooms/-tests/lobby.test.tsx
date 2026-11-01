import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { queryKeys } from "@/api/queryKeys"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

/**
 * The room lobby (/rooms/$roomId) on the real generated hooks over a fake client, with
 * the socket down (the page then polls). The folder starts with "-" so the router's
 * file scan leaves it alone.
 */
const router = vi.hoisted(() => ({ navigate: vi.fn() }))
// whether the page wanted its socket, render after render
const socket = vi.hoisted(() => ({ enabled: [] as boolean[] }))
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en", dir: () => "ltr" } }),
  Trans: ({ i18nKey }: { i18nKey: string }) => i18nKey,
}))
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => ({ roomId: "room-1" }) }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useNavigate: () => router.navigate,
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/hooks/use-socket", () => ({
  useSocket: ({ enabled }: { enabled?: boolean }) => {
    socket.enabled.push(enabled !== false)
    return { connected: false }
  },
}))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: toasts }))

const { Route } = await import("@/routes/_auth/rooms/$roomId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

const STATE = "GET /api/v1/rooms/room-1/state"
const JOIN = "PATCH /api/v1/rooms/join"

const notInRoom = () => httpError(404, { error: "UserNotInRoomError", error_key: "errors.api.userNotInRoom" })

const roomState = (over: Record<string, unknown> = {}) => ({
  id: "room-1",
  public_id: "QX7PA",
  owner_id: "u1",
  password: "4821",
  active_game_id: null,
  game_type: "undercover",
  settings: { game_type: "undercover" },
  players: [
    { user_id: "u1", username: "Yusuf", is_spectator: false, is_disconnected: false, away_seconds_left: null },
    { user_id: "u2", username: "Maryam", is_spectator: false, is_disconnected: false, away_seconds_left: null },
    { user_id: "u3", username: "Ali", is_spectator: false, is_disconnected: false, away_seconds_left: null },
  ],
  ...over,
})

async function renderPage() {
  // the page's own query options (retry, refetchInterval) are what is under test: no
  // test defaults on top of them
  const queryClient = new QueryClient()
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <Page />
      </QueryClientProvider>,
    )
  })
  return queryClient
}

const errorPanel = () => screen.queryByText("room.lobbyPage.errorTitle")
const skeleton = () => screen.queryByText("room.lobbyPage.loading")

beforeEach(() => {
  resetFakeApi()
  router.navigate.mockReset()
  socket.enabled.length = 0
  Object.values(toasts).forEach((fn) => fn.mockReset())
})

afterEach(() => {
  vi.useRealTimers()
})

describe("the lobby of a room the player is not seated in", () => {
  it("keeps its error on screen and stops asking (FR-5)", async () => {
    // A guest who opens the lobby's address instead of the share link, or whose seat the
    // grace sweep removed: the page blinked between the error and the skeleton every 2 s
    // and asked for a 404 forever.
    // Prepare
    vi.useFakeTimers()
    answer(STATE, () => {
      throw notInRoom()
    })

    const tick = () =>
      act(async () => {
        await vi.advanceTimersByTimeAsync(250)
      })

    // Act: open the page and wait for its error
    await renderPage()
    for (let waited = 0; waited < 10_000 && !errorPanel(); waited += 250) await tick()
    const asked = requestsTo(STATE).length

    // Assert: the error stays for 10 s, with no skeleton between and no new request
    expect(errorPanel()).toBeInTheDocument()
    for (let elapsed = 0; elapsed < 10_000; elapsed += 250) {
      await tick()
      expect(errorPanel()).toBeInTheDocument()
      expect(skeleton()).toBeNull()
    }
    expect(requestsTo(STATE)).toHaveLength(asked)
    // ...and a refusal is not asked again at all
    expect(asked).toBe(1)
  })

  it("offers to join this room with its code and PIN", async () => {
    // Prepare
    answer(STATE, () => {
      throw notInRoom()
    })
    await renderPage()
    await waitFor(() => expect(errorPanel()).toBeInTheDocument())
    answer(JOIN, () => ({ id: "room-1" }))
    answer(STATE, () => roomState({ owner_id: "u2" }))

    // Act
    fireEvent.change(screen.getByLabelText("room.codeLabel"), { target: { value: "qx7pa" } })
    fireEvent.change(screen.getByLabelText("room.pinLabel"), { target: { value: "4821" } })
    fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.joinThisRoom" }))

    // Assert: seated, the lobby opens in place
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("room.lobbyPage.title"))
    expect(requestsTo(JOIN).map((r) => r.data)).toEqual([{ public_room_id: "QX7PA", password: "4821" }])
    expect(errorPanel()).toBeNull()
  })

  it("keeps the error on screen while it is asked again (a refocus)", async () => {
    // TanStack puts a query with no data back to pending at each fetch: the page drew
    // the skeleton for the length of every refetch
    // Prepare
    answer(STATE, () => {
      throw notInRoom()
    })
    const queryClient = await renderPage()
    await waitFor(() => expect(errorPanel()).toBeInTheDocument())
    let answerAgain!: () => void
    answer(STATE, () => new Promise((_, reject) => (answerAgain = () => reject(notInRoom()))))

    // Act
    let refetched!: Promise<void>
    await act(async () => {
      refetched = queryClient.refetchQueries({ queryKey: queryKeys.room.state("room-1") })
      // let the query's "pending again" reach the page (TanStack notifies on a timeout)
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    // Assert: in flight, the error stays and no skeleton replaces it
    expect(requestsTo(STATE)).toHaveLength(2)
    expect(errorPanel()).toBeInTheDocument()
    expect(skeleton()).toBeNull()
    await act(async () => {
      answerAgain()
      await refetched
    })
    expect(errorPanel()).toBeInTheDocument()
  })

  it("keeps the socket closed until the player has a seat", async () => {
    // the server refuses the socket of a non-member, and never retries a refused one
    // Prepare
    answer(STATE, () => {
      throw notInRoom()
    })
    await renderPage()
    await waitFor(() => expect(errorPanel()).toBeInTheDocument())
    expect(socket.enabled.at(-1)).toBe(false)
    answer(JOIN, () => ({ id: "room-1" }))
    answer(STATE, () => roomState({ owner_id: "u2" }))

    // Act
    fireEvent.change(screen.getByLabelText("room.codeLabel"), { target: { value: "QX7PA" } })
    fireEvent.change(screen.getByLabelText("room.pinLabel"), { target: { value: "4821" } })
    fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.joinThisRoom" }))

    // Assert
    await waitFor(() => expect(errorPanel()).toBeNull())
    expect(socket.enabled.at(-1)).toBe(true)
  })

  it("opens the other room when the code typed is another room's", async () => {
    // Prepare
    answer(STATE, () => {
      throw notInRoom()
    })
    await renderPage()
    await waitFor(() => expect(errorPanel()).toBeInTheDocument())
    answer(JOIN, () => ({ id: "room-2" }))

    // Act
    fireEvent.change(screen.getByLabelText("room.codeLabel"), { target: { value: "ZZZZZ" } })
    fireEvent.change(screen.getByLabelText("room.pinLabel"), { target: { value: "1111" } })
    fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.joinThisRoom" }))

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms/$roomId", params: { roomId: "room-2" }, replace: true }))
  })

  it("does not offer to join a room that is gone", async () => {
    // Prepare
    answer(STATE, () => {
      throw httpError(404, { error: "RoomNotFoundError", error_key: "errors.api.roomNotFound" })
    })

    // Act
    await renderPage()

    // Assert
    await waitFor(() => expect(errorPanel()).toBeInTheDocument())
    expect(screen.queryByRole("button", { name: "room.lobbyPage.joinThisRoom" })).not.toBeInTheDocument()
    expect(screen.getByText("room.lobbyPage.backToRooms")).toBeInTheDocument()
  })
})

describe("the host starts the game", () => {
  it("goes to the game with no toast over its header (F10)", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer("POST /api/v1/undercover/games/room-1/start", () => ({ game_id: "g1", room_id: "room-1" }))
    await renderPage()
    const start = await screen.findByRole("button", { name: "room.lobbyPage.start" })

    // Act
    fireEvent.click(start)

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/game/undercover/$gameId", params: { gameId: "g1" } }))
    expect(toasts.success).not.toHaveBeenCalled()
  })

  it("still says it when the game did not start", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer("POST /api/v1/undercover/games/room-1/start", () => {
      throw httpError(400, { error_key: "errors.api.notEnoughPlayers" })
    })
    await renderPage()
    const start = await screen.findByRole("button", { name: "room.lobbyPage.start" })

    // Act
    fireEvent.click(start)

    // Assert
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith("errors.api.notEnoughPlayers"))
    expect(router.navigate).not.toHaveBeenCalled()
  })
})

describe("the lobby's side column", () => {
  it("gives the bans and the chat keys of their own (review F3: React refused the shared one)", async () => {
    // Prepare — React reports a duplicate key through console.error
    const errors = vi.spyOn(console, "error").mockImplementation(() => {})
    answer(STATE, () => roomState())

    // Act
    await renderPage()
    await screen.findByRole("button", { name: "room.lobbyPage.start" })

    // Assert
    const duplicateKey = errors.mock.calls.filter((call) => String(call[0]).includes("same key"))
    errors.mockRestore()
    expect(duplicateKey).toEqual([])
  })
})
