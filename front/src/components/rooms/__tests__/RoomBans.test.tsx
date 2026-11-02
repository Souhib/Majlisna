import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { queryKeys } from "@/api/queryKeys"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import en from "@/i18n/locales/en.json"
import { RoomBans } from "../RoomBans"

/**
 * The host's list of banned players (a ban, not a kick: owner decision, 2 November 2026):
 * the real generated hooks over the fake client, and the real English strings.
 */
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("sonner", () => ({ toast: toasts }))
vi.unmock("react-i18next")

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

const BANS = "GET /api/v1/rooms/room-1/bans"
const lift = (userId: string) => `DELETE /api/v1/rooms/room-1/bans/${userId}`

const ban = (user_id: string, username: string) => ({ user_id, username, banned_at: "2026-10-31T18:00:00Z" })

function renderBans({ isHost = true } = {}) {
  const queryClient = new QueryClient()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RoomBans roomId="room-1" isHost={isHost} />
    </QueryClientProvider>,
  )
  return { queryClient, ...view }
}

const heading = () => screen.queryByRole("heading", { name: /Banned players/ })

beforeEach(() => {
  resetFakeApi()
  Object.values(toasts).forEach((fn) => fn.mockReset())
})

afterEach(() => {
  vi.useRealTimers()
})

describe("RoomBans", () => {
  it("lists the banned players by name, each with its way back", async () => {
    // Prepare
    answer(BANS, () => [ban("u2", "Maryam"), ban("u3", "Ali")])

    // Act
    renderBans()

    // Assert
    await waitFor(() => expect(heading()).toHaveTextContent("Banned players (2)"))
    expect(screen.getByText("Maryam")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Let Maryam come back" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Let Ali come back" })).toBeInTheDocument()
  })

  it("renders nothing for a guest, and asks nothing", async () => {
    // Prepare
    answer(BANS, () => [ban("u2", "Maryam")])

    // Act
    const { container } = renderBans({ isHost: false })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    // Assert
    expect(container).toBeEmptyDOMElement()
    expect(requestsTo(BANS)).toHaveLength(0)
  })

  it("stays out of the lobby while nobody is banned", async () => {
    // Prepare
    answer(BANS, () => [])

    // Act
    const { container } = renderBans()
    await waitFor(() => expect(requestsTo(BANS)).toHaveLength(1))
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    // Assert
    expect(container).toBeEmptyDOMElement()
  })

  it("lifts a ban with ONE request, a double tap included, and the row leaves the list", async () => {
    // Prepare
    let bans = [ban("u2", "Maryam"), ban("u3", "Ali")]
    answer(BANS, () => bans)
    let release!: () => void
    answer(
      lift("u2"),
      () =>
        new Promise((resolve) => {
          release = () => {
            bans = bans.filter((b) => b.user_id !== "u2")
            resolve({ status: "lifted" })
          }
        }),
    )
    renderBans()
    const letBack = await screen.findByRole("button", { name: "Let Maryam come back" })

    // Act
    fireEvent.click(letBack)
    fireEvent.click(letBack)
    await waitFor(() => expect(requestsTo(lift("u2"))).toHaveLength(1))
    await act(async () => release())

    // Assert: one DELETE, the list read again from the server, without Maryam
    await waitFor(() => expect(screen.queryByText("Maryam")).toBeNull())
    expect(requestsTo(lift("u2"))).toHaveLength(1)
    expect(requestsTo(BANS).length).toBeGreaterThanOrEqual(2)
    expect(heading()).toHaveTextContent("Banned players (1)")
    expect(screen.getByRole("button", { name: "Let Ali come back" })).toBeInTheDocument()
    expect(toasts.error).not.toHaveBeenCalled()
  })

  it("after the last one is lifted, says nobody is banned and keeps the host's place", async () => {
    // Prepare
    let bans = [ban("u2", "Maryam")]
    answer(BANS, () => bans)
    answer(lift("u2"), () => {
      bans = []
      return { status: "lifted" }
    })
    renderBans()
    const letBack = await screen.findByRole("button", { name: "Let Maryam come back" })
    letBack.focus()

    // Act
    fireEvent.click(letBack)

    // Assert: the panel stays under the host's hand, with the empty line and focus on its title
    await waitFor(() => expect(screen.getByText("No one is banned from this room.")).toBeInTheDocument())
    expect(heading()).toHaveTextContent("Banned players (0)")
    await waitFor(() => expect(document.activeElement).toBe(heading()))
  })

  it("says a lift that failed, and keeps the row", async () => {
    // Prepare
    answer(BANS, () => [ban("u2", "Maryam")])
    answer(lift("u2"), () => {
      throw httpError(500, {})
    })
    renderBans()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "Let Maryam come back" }))

    // Assert
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith("The ban was not lifted. Try again."))
    expect(screen.getByText("Maryam")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Let Maryam come back" })).not.toHaveAttribute("aria-busy")
  })

  it("takes a ban already lifted elsewhere (404) as lifted, with no error", async () => {
    // Prepare: the host's other tab lifted it first
    let bans = [ban("u2", "Maryam")]
    answer(BANS, () => bans)
    answer(lift("u2"), () => {
      throw httpError(404, { error: "RoomBanNotFoundError", error_key: "errors.api.roomBanNotFound" })
    })
    renderBans()
    const letBack = await screen.findByRole("button", { name: "Let Maryam come back" })
    bans = []

    // Act
    fireEvent.click(letBack)

    // Assert
    await waitFor(() => expect(screen.queryByText("Maryam")).toBeNull())
    expect(toasts.error).not.toHaveBeenCalled()
  })

  it("follows the list when it is invalidated (the host banned someone)", async () => {
    // Prepare
    let bans = [ban("u2", "Maryam")]
    answer(BANS, () => bans)
    const { queryClient } = renderBans()
    await screen.findByText("Maryam")
    bans = [ban("u2", "Maryam"), ban("u4", "Bilal")]

    // Act
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.room.bans("room-1") })
    })

    // Assert
    expect(await screen.findByText("Bilal")).toBeInTheDocument()
    expect(heading()).toHaveTextContent("Banned players (2)")
  })

  it("never says 'no one banned' when the list did not load (FR-7)", async () => {
    // Prepare
    vi.useFakeTimers()
    answer(BANS, () => {
      throw httpError(500, {})
    })
    renderBans()

    // Act: the read and its two retries fail
    for (let waited = 0; waited < 10_000 && !screen.queryByRole("button", { name: "Retry" }); waited += 250) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250)
      })
    }

    // Assert
    expect(requestsTo(BANS)).toHaveLength(3)
    expect(screen.getByText("This did not load. Check your connection, then try again.")).toBeInTheDocument()
    expect(screen.queryByText("No one is banned from this room.")).toBeNull()

    // ...and Retry asks again
    vi.useRealTimers()
    answer(BANS, () => [ban("u2", "Maryam")])
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("Maryam")).toBeInTheDocument()
  })

  it("does not ask again when the server refuses the list (a guest's 403)", async () => {
    // Prepare
    vi.useFakeTimers()
    answer(BANS, () => {
      throw httpError(403, { error_key: "errors.api.notRoomHost" })
    })

    // Act
    renderBans()
    for (let waited = 0; waited < 5_000; waited += 250) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250)
      })
    }

    // Assert
    expect(requestsTo(BANS)).toHaveLength(1)
  })
})
