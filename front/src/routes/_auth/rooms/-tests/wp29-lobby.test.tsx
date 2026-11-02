import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { queryKeys } from "@/api/queryKeys"
import { answer, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

/**
 * The lobby's two removals (owner decision, 2 November 2026; WP-29 before it): the host
 * confirms either. A kick (Remove) only takes the seat: nobody is listed as banned and the
 * PIN stays. A ban lists the player with a way back, and the PIN on screen and in the
 * share link is the new one. The activity line says which. The real page and generated
 * hooks over the fake client, the socket down.
 */
const router = vi.hoisted(() => ({ navigate: vi.fn() }))
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
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: false }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: toasts }))

const { Route } = await import("@/routes/_auth/rooms/$roomId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

const STATE = "GET /api/v1/rooms/room-1/state"
const BANS = "GET /api/v1/rooms/room-1/bans"
const KICK = "PATCH /api/v1/rooms/room-1/kick"
const BAN = "POST /api/v1/rooms/room-1/bans"
const LIFT = "DELETE /api/v1/rooms/room-1/bans/u2"

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

async function renderPage() {
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

const pinTiles = () => screen.getByRole("group", { name: "room.pinLabel" })

beforeEach(() => {
  resetFakeApi()
  router.navigate.mockReset()
  Object.values(toasts).forEach((fn) => fn.mockReset())
})

describe("the lobby's PIN after a ban", () => {
  it("shows the new PIN from room_state and copies it in the share link", async () => {
    // Prepare
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
    answer(STATE, () => roomState())
    answer(BANS, () => [])
    const queryClient = await renderPage()
    await waitFor(() => expect(pinTiles()).toHaveTextContent("4 8 2 1"))

    // Act: the push that follows a ban carries the rotated PIN
    answer(STATE, () => roomState({ password: "9034", players: [player("u1", "Yusuf"), player("u3", "Ali")] }))
    act(() => {
      queryClient.setQueryData(queryKeys.room.state("room-1"), roomState({ password: "9034", players: [player("u1", "Yusuf"), player("u3", "Ali")] }))
    })
    await waitFor(() => expect(pinTiles()).toHaveTextContent("9 0 3 4"))
    fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.share" }))

    // Assert: the tiles and the link hold the new PIN, never the old one
    await waitFor(() => expect(writeText).toHaveBeenCalledOnce())
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/rooms/join?code=QX7PA&pin=9034`)
    expect(pinTiles()).not.toHaveTextContent("4 8 2 1")
  })
})

/** Maryam's row in the roster (the E2E shape), for its two buttons. */
function maryamRow(): HTMLElement {
  const name = screen.getAllByText("Maryam").find((el) => el.closest("div.flex.items-center.justify-between"))
  return name!.closest("div.flex.items-center.justify-between") as HTMLElement
}

const activityLine = () => screen.getByTestId("lobby-activity")

describe("the host removes or bans a player", () => {
  it("Remove asks first, kicks once, lists no ban, keeps the PIN, and the line says removed", async () => {
    // Prepare
    answer(STATE, () => roomState())
    answer(BANS, () => [])
    answer(KICK, () => {
      answer(STATE, () => roomState({ players: [player("u1", "Yusuf"), player("u3", "Ali")] }))
      return { message: "Player kicked" }
    })
    await renderPage()
    await waitFor(() => expect(requestsTo(BANS)).toHaveLength(1))
    const remove = within(maryamRow()).getByRole("button", { name: "room.lobbyPage.kick" })

    // Act: Remove, then confirm
    fireEvent.click(remove)
    const confirm = await screen.findByRole("alertdialog")
    expect(within(confirm).getByText("room.lobbyPage.kickConfirmBody")).toBeInTheDocument()
    expect(requestsTo(KICK)).toHaveLength(0)
    fireEvent.click(within(confirm).getByRole("button", { name: "room.lobbyPage.kickConfirmAction" }))

    // Assert: one kick and no ban; nobody listed; the PIN is the same; the line says removed
    await waitFor(() => expect(screen.queryAllByText("Maryam")).toHaveLength(0))
    expect(requestsTo(KICK).map((r) => r.data)).toEqual([{ user_id: "u2" }])
    expect(requestsTo(BAN)).toHaveLength(0)
    expect(screen.queryByRole("heading", { name: /room\.lobbyPage\.bans\.title/ })).toBeNull()
    expect(pinTiles()).toHaveTextContent("4 8 2 1")
    expect(activityLine()).toHaveTextContent("room.lobbyPage.activityRemoved")
    expect(toasts.error).not.toHaveBeenCalled()
  })

  it("Ban asks first, bans once, then lists the player with a way back, which lifts the ban", async () => {
    // Prepare
    let bans: { user_id: string; username: string; banned_at: string }[] = []
    answer(STATE, () => roomState())
    answer(BANS, () => bans)
    answer(BAN, () => {
      bans = [{ user_id: "u2", username: "Maryam", banned_at: "2026-10-31T18:00:00Z" }]
      answer(STATE, () => roomState({ password: "9034", players: [player("u1", "Yusuf"), player("u3", "Ali")] }))
      return bans[0]
    })
    answer(LIFT, () => {
      bans = []
      return { status: "lifted" }
    })
    await renderPage()
    await waitFor(() => expect(requestsTo(BANS)).toHaveLength(1))
    // nobody banned yet: no panel
    expect(screen.queryByRole("heading", { name: /room\.lobbyPage\.bans\.title/ })).toBeNull()
    const ban = within(maryamRow()).getByRole("button", { name: "room.lobbyPage.ban" })

    // Act: Ban, then confirm
    fireEvent.click(ban)
    const confirm = await screen.findByRole("alertdialog")
    expect(within(confirm).getByText("room.lobbyPage.banConfirmBody")).toBeInTheDocument()
    expect(requestsTo(BAN)).toHaveLength(0)
    fireEvent.click(within(confirm).getByRole("button", { name: "room.lobbyPage.banConfirmAction" }))

    // Assert: one ban (no kick); the banned player is listed, the PIN is the new one, the line says banned
    await waitFor(() => expect(screen.getByRole("heading", { name: /room\.lobbyPage\.bans\.title/ })).toHaveTextContent("(1)"))
    expect(requestsTo(BAN).map((r) => r.data)).toEqual([{ user_id: "u2" }])
    expect(requestsTo(KICK)).toHaveLength(0)
    await waitFor(() => expect(pinTiles()).toHaveTextContent("9 0 3 4"))
    expect(activityLine()).toHaveTextContent("room.lobbyPage.activityBanned")

    // Act: let Maryam come back
    fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.bans.liftBan" }))

    // Assert
    await waitFor(() => expect(screen.getByText("room.lobbyPage.bans.empty")).toBeInTheDocument())
    expect(requestsTo(LIFT)).toHaveLength(1)
    expect(toasts.error).not.toHaveBeenCalled()
  })

  it("gives a guest no list of banned players, nor any Remove or Ban, and asks for none", async () => {
    // Prepare
    answer(STATE, () => roomState({ owner_id: "u2" }))
    answer(BANS, () => [{ user_id: "u9", username: "Bilal", banned_at: "2026-10-31T18:00:00Z" }])

    // Act
    await renderPage()
    await screen.findByRole("heading", { level: 1 })

    // Assert
    expect(requestsTo(BANS)).toHaveLength(0)
    expect(screen.queryByText("Bilal")).toBeNull()
    expect(screen.queryAllByRole("button", { name: "room.lobbyPage.kick" })).toHaveLength(0)
    expect(screen.queryAllByRole("button", { name: "room.lobbyPage.ban" })).toHaveLength(0)
  })
})
