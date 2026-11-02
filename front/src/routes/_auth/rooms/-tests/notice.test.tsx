import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { answer, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import { noteRoomNotice, takeRoomNotice } from "@/lib/room-notice"

/**
 * /rooms after the host took the player's seat (owner decision, 2 November 2026): a kick
 * says they may join again, a ban says they are banned, and a removal no event named (the
 * lobby's polling fallback) promises nothing. Said once, in place (not a toast).
 */
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useNavigate: () => vi.fn(),
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const { Route } = await import("@/routes/_auth/rooms/index")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

async function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <Page />
      </QueryClientProvider>,
    )
  })
}

beforeEach(() => {
  resetFakeApi()
  takeRoomNotice()
  answer("GET /api/v1/rooms/active", () => null)
})

describe("/rooms: the notice of a removal", () => {
  it.each([
    ["kicked", "room.youWereKicked"],
    ["banned", "room.youWereBanned"],
    // the lobby's polling fallback: the seat is gone, and no event said which removal it was
    ["removed", "room.youWereRemoved"],
  ] as const)("says the %s notice once, in place", async (notice, key) => {
    // Prepare
    noteRoomNotice(notice)

    // Act
    await renderPage()

    // Assert
    expect(screen.getByTestId("room-notice")).toHaveTextContent(key)
    expect(takeRoomNotice()).toBeNull()
  })

  it("says nothing when the player was not removed", async () => {
    // Act
    await renderPage()

    // Assert
    expect(screen.queryByTestId("room-notice")).toBeNull()
  })
})
