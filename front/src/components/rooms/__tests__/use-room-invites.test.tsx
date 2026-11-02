import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { answer, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)

const { useRoomInvites } = await import("../use-room-invites")

const LIST = "GET /api/v1/rooms/invites"

function invite(id: string, expiresAt: string, invitedBy = "Yusuf") {
  return { id, room_id: `room-${id}`, public_id: "LULIM", invited_by: invitedBy, expires_at: expiresAt }
}

function renderInvites(viewer: string | null = "u1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  return renderHook(() => useRoomInvites(viewer), { wrapper })
}

beforeEach(() => {
  resetFakeApi()
})

describe("useRoomInvites (the invite the app shell shows)", () => {
  it("shows the newest stored invite when the page opens: one sent while it was closed", async () => {
    // Prepare
    answer(LIST, () => [invite("b", "2026-11-02T12:40:00Z"), invite("a", "2026-11-02T12:30:00Z")])

    // Act
    const { result } = renderInvites()

    // Assert
    await waitFor(() => expect(result.current.invite?.id).toBe("b"))
  })

  it("asks nothing before the player is known", () => {
    renderInvites(null)
    expect(requestsTo(LIST)).toHaveLength(0)
  })

  it("shows a pushed invite over the stored ones, and the next stored one once it is answered", async () => {
    // Prepare
    answer(LIST, () => [invite("a", "2026-11-02T12:30:00Z")])
    const { result } = renderInvites()
    await waitFor(() => expect(result.current.invite?.id).toBe("a"))

    // Act: a push, then Not now on it
    act(() => result.current.receive(invite("c", "2026-11-02T12:50:00Z", "Maryam")))
    expect(result.current.invite?.invited_by).toBe("Maryam")
    act(() => result.current.answer(invite("c", "2026-11-02T12:50:00Z")))

    // Assert
    expect(result.current.invite?.id).toBe("a")
  })

  it("hides the stored copy of an invite just answered, and shows it again when it is re-sent", async () => {
    // A re-invite keeps the invite's id and moves its expiry later
    // Prepare: the page opened with invite a; then a re-invite of a was pushed and answered
    answer(LIST, () => [invite("a", "2026-11-02T12:30:00Z")])
    const { result } = renderInvites()
    await waitFor(() => expect(result.current.invite?.id).toBe("a"))
    act(() => result.current.receive(invite("a", "2026-11-02T12:45:00Z")))
    act(() => result.current.answer(invite("a", "2026-11-02T12:45:00Z")))
    expect(result.current.invite).toBeNull()

    // Act: re-sent once more
    act(() => result.current.receive(invite("a", "2026-11-02T13:00:00.123456Z")))

    // Assert
    expect(result.current.invite?.expires_at).toBe("2026-11-02T13:00:00.123456Z")
  })

  it("reads the stored invites again on refresh (pushes missed while the socket was away)", async () => {
    // Prepare
    answer(LIST, () => [])
    const { result } = renderInvites()
    await waitFor(() => expect(requestsTo(LIST)).toHaveLength(1))
    answer(LIST, () => [invite("d", "2026-11-02T12:30:00Z")])

    // Act
    act(() => result.current.refresh())

    // Assert
    await waitFor(() => expect(result.current.invite?.id).toBe("d"))
    expect(requestsTo(LIST)).toHaveLength(2)
  })
})
