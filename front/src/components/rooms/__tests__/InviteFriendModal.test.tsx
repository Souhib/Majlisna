import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import en from "@/i18n/locales/en.json"

/**
 * Inviting a friend from the lobby (owner decision, 2 November 2026): a friend the host
 * BANNED from the room cannot be invited (403 `inviteeBanned`), and the inviter is told so
 * on that friend's row, in place of the Invite button. A kicked friend is invited as anyone.
 * The real English strings, the real generated hooks over the fake client.
 */
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.unmock("react-i18next")
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("sonner", () => ({ toast: toasts }))
vi.mock("@tanstack/react-router", () => ({ Link: ({ children }: { children: unknown }) => children }))

const { InviteFriendModal } = await import("../InviteFriendModal")

const FRIENDS = "GET /api/v1/friends"
const INVITE = "POST /api/v1/rooms/room-1/invite"

const friend = (user_id: string, username: string) => ({ friendship_id: `f-${user_id}`, user_id, username })

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

beforeEach(() => {
  resetFakeApi()
  Object.values(toasts).forEach((fn) => fn.mockReset())
})

function renderModal() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <InviteFriendModal roomId="room-1" open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  )
}

/** The friend's row in the dialog's list (the name as shown; the avatar repeats it for screen readers). */
const rowOf = (name: string) => screen.getByText(name, { selector: "bdi" }).closest("li") as HTMLElement

describe("InviteFriendModal", () => {
  it("says on the row that a banned friend is banned from this room, and keeps Invite for the others", async () => {
    // Prepare
    answer(FRIENDS, () => [friend("u2", "Maryam"), friend("u3", "Ali")])
    answer(INVITE, (request) => {
      if ((request.data as { friend_user_id: string }).friend_user_id === "u2") {
        throw httpError(403, { error_key: "errors.api.inviteeBanned" })
      }
      return { room_id: "room-1", invited_user_id: "u3", message: "Invite sent", invite: {} }
    })
    renderModal()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "Invite Maryam" }))

    // Assert: the row says why, no Invite there any more, and no toast on top of it
    await waitFor(() => expect(within(rowOf("Maryam")).getByRole("status")).toHaveTextContent("Banned from this room"))
    expect(within(rowOf("Maryam")).queryByRole("button")).toBeNull()
    expect(toasts.error).not.toHaveBeenCalled()
    expect(within(rowOf("Ali")).getByRole("button", { name: "Invite Ali" })).toBeEnabled()
    expect(requestsTo(INVITE).map((r) => r.data)).toEqual([{ friend_user_id: "u2" }])
  })

  it("invites any other friend as before: Invited on the row, and the toast", async () => {
    // Prepare
    answer(FRIENDS, () => [friend("u3", "Ali")])
    answer(INVITE, () => ({ room_id: "room-1", invited_user_id: "u3", message: "Invite sent", invite: {} }))
    renderModal()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "Invite Ali" }))

    // Assert
    await waitFor(() => expect(within(rowOf("Ali")).getByRole("status")).toHaveTextContent("Invited"))
    expect(toasts.success).toHaveBeenCalledWith("Invite sent!")
  })

  it("says any other refusal in a toast, and keeps Invite to try again", async () => {
    // Prepare
    answer(FRIENDS, () => [friend("u3", "Ali")])
    answer(INVITE, () => {
      throw httpError(400, { error_key: "errors.api.inviterNotInRoom" })
    })
    renderModal()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "Invite Ali" }))

    // Assert
    await waitFor(() => expect(toasts.error).toHaveBeenCalledOnce())
    expect(within(rowOf("Ali")).getByRole("button", { name: "Invite Ali" })).toBeEnabled()
  })
})
