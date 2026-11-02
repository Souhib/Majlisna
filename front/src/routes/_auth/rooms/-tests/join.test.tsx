import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { type ComponentType, type ReactNode, StrictMode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { answer, httpError, requests, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

/**
 * The share link (/rooms/join?code=…&pin=…), on the real generated hooks over a fake
 * client. The folder starts with "-" so the router's file scan leaves it alone.
 */
const router = vi.hoisted(() => ({ search: { code: "", pin: "" }, navigate: vi.fn() }))

// t names its parameters, so a test sees what was asked for in which words
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
      return params.length ? `${key}(${params.join(",")})` : key
    },
    i18n: { language: "en" },
  }),
}))
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useSearch: () => router.search }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useNavigate: () => router.navigate,
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))

const { Route } = await import("@/routes/_auth/rooms/join")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

const JOIN = "PATCH /api/v1/rooms/join"
const ACTIVE = "GET /api/v1/rooms/active"
const LEAVE = "PATCH /api/v1/rooms/leave"

/** Open the share link: the address the player followed, and what the router read from it. */
function followLink(code: string, pin: string) {
  window.history.replaceState(null, "", `/rooms/join?code=${code}&pin=${pin}`)
  router.search = { code, pin }
}

// the last render, so a test can render again after the router moved
let lastRender!: ReturnType<typeof render>

async function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    lastRender = render(
      <QueryClientProvider client={queryClient}>
        <Page />
      </QueryClientProvider>,
    )
  })
  return queryClient
}

beforeEach(() => {
  resetFakeApi()
  router.navigate.mockReset()
  followLink("BBBBB", "4321")
})

afterEach(() => {
  window.history.replaceState(null, "", "/")
})

describe("/rooms/join", () => {
  it("joins with the link's code and PIN, then opens the lobby", async () => {
    // Prepare
    answer(JOIN, () => ({ id: "room-b" }))

    // Act
    await renderPage()

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms/$roomId", params: { roomId: "room-b" }, replace: true }))
    expect(requestsTo(JOIN).map((r) => r.data)).toEqual([{ public_room_id: "BBBBB", password: "4321" }])
  })

  it("drops the code and PIN from the address before the join answers", async () => {
    // SEC F06: analytics and the browser history kept every room's PIN
    // Prepare
    let answerJoin!: (room: unknown) => void
    answer(JOIN, () => new Promise((resolve) => (answerJoin = resolve)))

    // Act
    await renderPage()

    // Assert: the join is in flight, with the link's values, and the address is clean
    expect(requestsTo(JOIN).map((r) => r.data)).toEqual([{ public_room_id: "BBBBB", password: "4321" }])
    expect(window.location.search).toBe("")
    expect(window.location.href).not.toContain("4321")
    expect(window.location.pathname).toBe("/rooms/join")
    await act(async () => answerJoin({ id: "room-b" }))
  })

  it("offers to leave the room the player sits in, then leaves it and joins this one", async () => {
    // FR-2: the server answers 409 to a player seated in another room
    // Prepare
    let joins = 0
    answer(JOIN, () => {
      joins += 1
      if (joins === 1) throw httpError(409, { error_key: "errors.api.userAlreadyInRoom" })
      return { id: "room-b" }
    })
    answer(ACTIVE, () => ({ room_id: "room-a", public_id: "AAAAA", is_connected: true }))
    answer(LEAVE, () => ({ id: "room-a" }))
    await renderPage()
    expect(await screen.findByTestId("join-error")).toHaveTextContent("room.joinPage.alreadyInRoom")
    const offer = await screen.findByRole("button", { name: "room.joinPage.leaveAndJoin(room=AAAAA)" })

    // Act
    fireEvent.click(offer)

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms/$roomId", params: { roomId: "room-b" }, replace: true }))
    const calls = requests.map((r) => `${r.method} ${r.url}`).filter((r) => r !== ACTIVE)
    expect(calls).toEqual([JOIN, LEAVE, JOIN])
    expect(requestsTo(LEAVE).map((r) => r.data)).toEqual([{ room_id: "room-a" }])
    expect(requestsTo(JOIN).map((r) => r.data)).toEqual([
      { public_room_id: "BBBBB", password: "4321" },
      { public_room_id: "BBBBB", password: "4321" },
    ])
    // the room to leave is read again when the button is pressed (once to name the
    // offer, once on the press), not taken from what the offer showed
    const sequence = requests.map((r) => `${r.method} ${r.url}`)
    const beforeLeave = sequence.slice(sequence.indexOf(JOIN) + 1, sequence.indexOf(LEAVE))
    expect(beforeLeave).toEqual([ACTIVE, ACTIVE])
  })

  it("says why when leaving the other room fails, and does not join", async () => {
    // Prepare
    answer(JOIN, () => {
      throw httpError(409, { error_key: "errors.api.userAlreadyInRoom" })
    })
    answer(ACTIVE, () => ({ room_id: "room-a", public_id: "AAAAA", is_connected: true }))
    answer(LEAVE, () => {
      throw new Error("Failed to fetch")
    })
    await renderPage()
    const offer = await screen.findByRole("button", { name: "room.joinPage.leaveAndJoin(room=AAAAA)" })

    // Act
    fireEvent.click(offer)

    // Assert
    await waitFor(() => expect(screen.getByTestId("join-error")).toHaveTextContent("room.indexPage.leaveFailed"))
    expect(requestsTo(JOIN)).toHaveLength(1)
    expect(router.navigate).not.toHaveBeenCalled()
  })

  it("says a ban in the server's words, with no offer to leave and no second try", async () => {
    // The host banned this player; leaving another room changes nothing
    // Prepare
    answer(JOIN, () => {
      throw httpError(403, { error_key: "errors.api.roomBanned" })
    })

    // Act
    await renderPage()

    // Assert
    expect(await screen.findByTestId("join-error")).toHaveTextContent("errors.api.roomBanned")
    expect(screen.queryByRole("button", { name: /leaveAndJoin/ })).not.toBeInTheDocument()
    expect(requestsTo(JOIN)).toHaveLength(1)
    expect(requestsTo(LEAVE)).toHaveLength(0)
    expect(requestsTo(ACTIVE)).toHaveLength(0)
    // review F2: nothing the player could try — a ban holds whatever the code and PIN
    expect(screen.queryByText("room.joinPage.errorRepair")).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "room.joinPage.typeCode" })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "common.goHome" })).toBeInTheDocument()
  })

  it("says the PIN may have changed when the link's PIN is refused (review F1: a ban rotates it)", async () => {
    // Prepare — a link made before the host banned someone carries the old PIN
    answer(JOIN, () => {
      throw httpError(403, { error_key: "errors.api.wrongRoomPassword" })
    })

    // Act
    await renderPage()

    // Assert
    expect(await screen.findByTestId("join-error")).toHaveTextContent("errors.api.wrongRoomPassword")
    expect(screen.getByText("room.joinPage.pinChangedRepair")).toBeInTheDocument()
    expect(screen.queryByText("room.joinPage.errorRepair")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "room.joinPage.typeCode" })).toBeInTheDocument()
  })

  it("lets the offer to leave and join be pressed under StrictMode (review F8)", async () => {
    // Prepare — StrictMode's mount, unmount, mount detached the mutation observer of the
    // join sent at mount, and the offer stayed "Working" for ever under `bun dev`
    let joins = 0
    answer(JOIN, () => {
      joins += 1
      if (joins === 1) throw httpError(409, { error_key: "errors.api.userAlreadyInRoom" })
      return { id: "room-b" }
    })
    answer(ACTIVE, () => ({ room_id: "room-a", public_id: "AAAAA", is_connected: true }))
    answer(LEAVE, () => ({ id: "room-a" }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    await act(async () => {
      render(
        <StrictMode>
          <QueryClientProvider client={queryClient}>
            <Page />
          </QueryClientProvider>
        </StrictMode>,
      )
    })
    const offer = await screen.findByRole("button", { name: "room.joinPage.leaveAndJoin(room=AAAAA)" })
    await waitFor(() => expect(offer).not.toHaveAttribute("aria-busy", "true"))

    // Act
    fireEvent.click(offer)

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms/$roomId", params: { roomId: "room-b" }, replace: true }))
    expect(requestsTo(LEAVE)).toHaveLength(1)
  })

  it("tries a second link opened while the page is open (a friend's invite)", async () => {
    // Prepare: the first link was refused, the page stays
    answer(JOIN, () => {
      throw httpError(404, { error_key: "errors.api.roomNotFound" })
    })
    const queryClient = await renderPage()
    await screen.findByTestId("join-error")
    answer(JOIN, () => ({ id: "room-c" }))

    // Act: the invite's link, through the router
    followLink("CCCCC", "9999")
    await act(async () => {
      lastRender.rerender(
        <QueryClientProvider client={queryClient}>
          <Page />
        </QueryClientProvider>,
      )
    })

    // Assert
    await waitFor(() => expect(router.navigate).toHaveBeenCalledWith({ to: "/rooms/$roomId", params: { roomId: "room-c" }, replace: true }))
    expect(requestsTo(JOIN).map((r) => r.data)).toEqual([
      { public_room_id: "BBBBB", password: "4321" },
      { public_room_id: "CCCCC", password: "9999" },
    ])
    expect(window.location.search).toBe("")
  })

  it("names an incomplete link without asking the server", async () => {
    // Prepare
    followLink("BBBBB", "")

    // Act
    await renderPage()

    // Assert
    expect(screen.getByText("room.joinPage.missingTitle")).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })
})
