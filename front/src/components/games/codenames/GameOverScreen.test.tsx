import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { type ComponentProps, type ReactNode } from "react"
import { beforeEach, describe, it, expect, vi } from "vitest"
import { toast } from "sonner"
import { answer, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

const mockMutateAsync = vi.fn()

vi.mock("@/api/generated", async () => ({
  ...(await (await import("@/components/notebook/__tests__/fake-api")).notebookGenerated()),
  useRematchApiV1RoomsRoomIdRematchPost: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}))

vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)

vi.mock("@tanstack/react-router", () => ({
  useLocation: ({ select }: { select: (l: { pathname: string }) => unknown }) => select({ pathname: "/game/codenames/g2" }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

import { GameOverScreen } from "./GameOverScreen"

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

const board = [
  { word: "Salah", word_ar: "صلاة", card_type: "red" as const, revealed: true, hint: "The prayer" },
  { word: "Sabr", word_ar: "صبر", card_type: "blue" as const, revealed: true, hint: "Patience" },
  { word: "Sand", card_type: "neutral" as const, revealed: true, hint: null },
]

const history = [{ team: "red" as const, clue_word: "worship", clue_number: 1, guesses: [{ word: "Salah", card_type: "red", correct: true }] }]

const defaultProps: ComponentProps<typeof GameOverScreen> = {
  winner: "red",
  roomId: "room-123",
  onBackToRoom: vi.fn(),
  onLeaveRoom: vi.fn(),
}

function renderGameOver(overrides: Partial<ComponentProps<typeof GameOverScreen>> = {}) {
  return render(<GameOverScreen {...defaultProps} {...overrides} />, { wrapper: createWrapper() })
}

describe("GameOverScreen", () => {
  it('keeps exactly one "Game Over" heading for the E2E suite, as an h2', () => {
    renderGameOver()
    const headings = screen.getAllByRole("heading", { level: 2 })
    expect(headings.filter((h) => h.textContent === "game.gameOver")).toHaveLength(1)
  })

  it("titles the colophon with the winner", () => {
    renderGameOver({ winner: "blue" })
    expect(screen.getByRole("heading", { level: 3, name: "game.codenames.over.title" })).toBeInTheDocument()
  })

  it("says how the game was decided", () => {
    renderGameOver({ remaining: { red: 0, blue: 3 }, history })
    expect(screen.getByText("game.codenames.over.allFound")).toBeInTheDocument()
  })

  it("lists the words the table turned, with their meaning, and keeps the rest one tap away", () => {
    renderGameOver({ board, history, remaining: { red: 0, blue: 3 } })
    expect(screen.getByText("صلاة")).toBeInTheDocument()
    expect(screen.getByText("The prayer")).toBeInTheDocument()
    expect(screen.getByText("game.codenames.over.otherWords")).toBeInTheDocument()
    expect(screen.getByText("Patience")).toBeInTheDocument()
  })

  it("presses one seal per achievement, captioned with who earned it", () => {
    renderGameOver({
      players: [
        { user_id: "u1", username: "Maryam", team: "red", role: "operative" },
        { user_id: "u2", username: "Idris", team: "red", role: "spymaster" },
      ],
      currentUserId: "u2",
      achievements: [
        { user_id: "u1", achievements: [{ code: "first_win", name: "Taste of Victory", tier: 1 }] },
        { user_id: "u2", achievements: [{ code: "first_win", name: "Taste of Victory", tier: 1 }] },
      ],
    })
    expect(screen.getAllByText("achievements.items.first_win.name")).toHaveLength(1)
    // you first, then the others, in the reader's list format; then the tier
    expect(screen.getByText("game.quiz.you and Maryam · achievements.tiers.1")).toBeInTheDocument()
  })

  it('gives the host "Play again"; everyone gets "Back to the room"', () => {
    // a guest's "Play again" only drew a 403, and a guest had no way back to the lobby
    const { unmount } = renderGameOver({ roomId: "room-123", isHost: true })
    expect(screen.getByText("game.playAgain")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toBeInTheDocument()
    unmount()
    renderGameOver({ roomId: "room-123", isHost: false })
    expect(screen.queryByText("game.playAgain")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toBeInTheDocument()
  })

  it("hides play again button when roomId is null", () => {
    renderGameOver({ roomId: null })
    expect(screen.queryByText("game.playAgain")).not.toBeInTheDocument()
  })

  it("calls onLeaveRoom when leave button is clicked", () => {
    const onLeaveRoom = vi.fn()
    renderGameOver({ onLeaveRoom })
    fireEvent.click(screen.getByText("room.lobbyPage.leave"))
    expect(onLeaveRoom).toHaveBeenCalledOnce()
  })

  it("calls API and onBackToRoom when play again is clicked", async () => {
    mockMutateAsync.mockResolvedValueOnce({})

    const onBackToRoom = vi.fn()
    renderGameOver({ roomId: "room-456", onBackToRoom, isHost: true })

    fireEvent.click(screen.getByText("game.playAgain"))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({ room_id: "room-456" })
    })

    await waitFor(() => {
      expect(onBackToRoom).toHaveBeenCalledOnce()
    })
  })
})

describe("GameOverScreen: keeping the words (the Kunnash)", () => {
  const GET = "GET /api/v1/notebook/games/g2"
  const players = [
    { user_id: "u1", username: "Maryam", team: "red", role: "operative" },
    { user_id: "u2", username: "Idris", team: "blue", role: "spymaster" },
  ]
  const gameWords = () => ({
    game_id: "g2",
    game_type: "codenames",
    words: board.map((c) => ({
      word: c.word,
      word_display: c.word,
      word_ar: c.word_ar ?? null,
      word_ar_vocalized: null,
      hint: c.hint,
      kept: false,
      entry_id: null,
    })),
  })

  beforeEach(() => {
    resetFakeApi()
    vi.mocked(toast.success).mockClear()
  })

  it('puts a keep toggle on every word, turned or not, and "Keep the words" before the way back', async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    renderGameOver({ board, history, remaining: { red: 0, blue: 3 }, players, currentUserId: "u1", isHost: true })

    // Assert
    const toggles = await screen.findAllByRole("button", { name: "notebook.colophon.keepWord" })
    expect(toggles).toHaveLength(board.length)
    const order = screen.getAllByRole("button").map((b) => b.textContent)
    expect(order.indexOf("notebook.colophon.keep")).toBeLessThan(order.indexOf("game.backToRoom"))
    expect(order.indexOf("game.backToRoom")).toBeLessThan(order.indexOf("game.playAgain"))
    expect(screen.getByRole("button", { name: "notebook.colophon.keep" })).toHaveClass("bg-primary")
    expect(screen.getByRole("button", { name: "game.backToRoom" })).not.toHaveClass("bg-primary")
    expect(screen.getByRole("button", { name: "game.playAgain" })).not.toHaveClass("bg-primary")
  })

  it("keeps the whole board and says so", async () => {
    // Prepare
    answer(GET, gameWords)
    answer("POST /api/v1/notebook/games/g2/keep", () => ({
      added: 3,
      already_kept: 0,
      entries: board.map((c, i) => ({ id: `e${i}`, word: c.word, word_display: c.word, game_type: "codenames", kept_at: "2026-10-28T20:00:00+00:00" })),
    }))
    renderGameOver({ board, history, players, currentUserId: "u1" })

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "notebook.colophon.keep" }))

    // Assert
    expect(await screen.findByRole("link", { name: "notebook.colophon.kept" })).toHaveAttribute("href", "/notebook")
    expect(toast.success).not.toHaveBeenCalled() // the change is in place, never a toast
    expect(screen.getAllByRole("button", { name: "notebook.colophon.keepWord" }).every((b) => b.getAttribute("aria-pressed") === "true")).toBe(true)
  })

  it("offers a spectator (not among the players) nothing, and asks nothing", async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    renderGameOver({ board, history, players, currentUserId: "watcher" })

    // Assert
    await screen.findByRole("button", { name: "game.backToRoom" })
    expect(requestsTo(GET)).toHaveLength(0)
    expect(screen.queryByRole("button", { name: "notebook.colophon.keep" })).not.toBeInTheDocument()
  })

  it("without the words, the way back is the brass action", async () => {
    // Act
    renderGameOver({ board, history, players, currentUserId: "u1" })

    // Assert
    await waitFor(() => expect(requestsTo(GET)).toHaveLength(1))
    expect(screen.queryByRole("button", { name: "notebook.colophon.keepWord" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toHaveClass("bg-primary")
  })
})
