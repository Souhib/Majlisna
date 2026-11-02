import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { StrictMode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

// t names its parameters, so a test sees what was asked for in which words
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
      return params.length ? `${key}(${params.join(",")})` : key
    },
    i18n: { language: "en" },
  }),
  Trans: ({ i18nKey, values }: { i18nKey: string; values?: Record<string, unknown> }) => `${i18nKey}(${JSON.stringify(values)})`,
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)

const { RoomInviteStrip } = await import("../RoomInviteStrip")

const invite = {
  id: "inv-1",
  room_id: "room-b",
  public_id: "LULIM",
  invited_by: "Yusuf",
  expires_at: "2026-11-02T12:30:00Z",
}
const ACCEPT = "POST /api/v1/rooms/invites/inv-1/accept"
const ACTIVE = "GET /api/v1/rooms/active"
const LEAVE = "PATCH /api/v1/rooms/leave"

async function renderStrip(handlers: { onJoined?: (roomId: string) => void; onDismiss?: () => void } = {}) {
  const onJoined = handlers.onJoined ?? vi.fn()
  const onDismiss = handlers.onDismiss ?? vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <RoomInviteStrip invite={invite} onJoined={onJoined} onDismiss={onDismiss} />
        </QueryClientProvider>
      </StrictMode>,
    )
  })
  return { onJoined, onDismiss }
}

beforeEach(() => {
  resetFakeApi()
})

describe("RoomInviteStrip (a friend's invite, never a toast)", () => {
  it("is a named strip with a polite status line naming the inviter, and takes no focus", async () => {
    const before = document.activeElement
    await renderStrip()
    expect(screen.getByRole("region", { name: "room.inviteLabel" })).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent('room.inviteReceived({"username":"Yusuf"})')
    expect(document.activeElement).toBe(before)
    expect(requestsTo(ACCEPT)).toHaveLength(0)
  })

  it("joins through the stored invite, with no code and no PIN, then opens the room", async () => {
    // The invite used to carry the PIN, which a kick rotates: an invite sent before a kick
    // opened a join that was refused (owner rule (c))
    // Prepare
    answer(ACCEPT, () => ({ id: "room-b" }))
    const { onJoined } = await renderStrip()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))

    // Assert
    await waitFor(() => expect(onJoined).toHaveBeenCalledWith("room-b"))
    expect(requestsTo(ACCEPT)).toHaveLength(1)
    expect(requestsTo(ACCEPT)[0].data).toBeUndefined()
    expect(requestsTo("PATCH /api/v1/rooms/join")).toHaveLength(0)
  })

  it("waits: Not now asks nothing of the server", async () => {
    const { onDismiss } = await renderStrip()
    fireEvent.click(screen.getByRole("button", { name: "room.inviteLater" }))
    expect(onDismiss).toHaveBeenCalledOnce()
    expect(requestsTo(ACCEPT)).toHaveLength(0)
  })

  it.each([
    ["a ban", 403, "errors.api.roomBanned"],
    ["an expired invite", 410, "errors.api.roomInviteExpired"],
    ["an invite no longer valid", 404, "errors.api.roomInviteNotFound"],
    ["a room that closed", 404, "errors.api.roomNotFound"],
  ])("says %s in the server's words, then only offers to close", async (_case, status, errorKey) => {
    // Prepare
    answer(ACCEPT, () => {
      throw httpError(status, { error_key: errorKey })
    })
    const { onJoined, onDismiss } = await renderStrip()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))

    // Assert
    expect(await screen.findByTestId("room-invite-error")).toHaveTextContent(errorKey)
    expect(screen.getByRole("alert")).toHaveTextContent(errorKey)
    expect(screen.queryByRole("button", { name: "room.joinInvite" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /leaveAndJoin/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common.close" }))
    expect(onDismiss).toHaveBeenCalledOnce()
    expect(onJoined).not.toHaveBeenCalled()
    expect(requestsTo(ACCEPT)).toHaveLength(1)
  })

  it("offers to leave the room the player sits in, then leaves it and accepts again", async () => {
    // Prepare
    let accepts = 0
    answer(ACCEPT, () => {
      accepts += 1
      if (accepts === 1) throw httpError(409, { error_key: "errors.api.userAlreadyInRoom" })
      return { id: "room-b" }
    })
    answer(ACTIVE, () => ({ room_id: "room-a", public_id: "AAAAA", is_connected: true }))
    answer(LEAVE, () => ({ id: "room-a" }))
    const { onJoined } = await renderStrip()
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))
    expect(await screen.findByTestId("room-invite-error")).toHaveTextContent("room.joinPage.alreadyInRoom")
    const offer = await screen.findByRole("button", { name: "room.joinPage.leaveAndJoin(room=AAAAA)" })
    await waitFor(() => expect(offer).not.toHaveAttribute("aria-busy"))

    // Act
    fireEvent.click(offer)

    // Assert: left room A, then the same invite seated them in room B
    await waitFor(() => expect(onJoined).toHaveBeenCalledWith("room-b"))
    expect(requestsTo(LEAVE).map((r) => r.data)).toEqual([{ room_id: "room-a" }])
    expect(requestsTo(ACCEPT)).toHaveLength(2)
  })

  it.each([
    ["too many tries", 429, "errors.api.rateLimitExceeded"],
    ["a server failure", 500, "errors.api.internalServer"],
  ])("says %s in the server's words but keeps Join: the invite still stands", async (_case, status, errorKey) => {
    // Every answer carries an error_key, a passing one too: only the refusals that hold
    // are final (review F3). Close would have hidden a live invite for good.
    // Prepare
    let accepts = 0
    answer(ACCEPT, () => {
      accepts += 1
      if (accepts === 1) throw httpError(status, { error_key: errorKey })
      return { id: "room-b" }
    })
    const { onJoined, onDismiss } = await renderStrip()
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))
    expect(await screen.findByTestId("room-invite-error")).toHaveTextContent(errorKey)
    expect(screen.getByRole("button", { name: "room.inviteLater" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "common.close" })).not.toBeInTheDocument()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))

    // Assert
    await waitFor(() => expect(onJoined).toHaveBeenCalledWith("room-b"))
    expect(requestsTo(ACCEPT)).toHaveLength(2)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it("keeps Join when the server could not be reached, to try again", async () => {
    // Prepare
    answer(ACCEPT, () => {
      throw new Error("Failed to fetch")
    })
    await renderStrip()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))

    // Assert
    expect(await screen.findByTestId("room-invite-error")).toHaveTextContent("room.joinPage.unreachable")
    expect(screen.getByRole("button", { name: "room.joinInvite" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "room.inviteLater" })).toBeInTheDocument()
  })
})
