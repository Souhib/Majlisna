import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { toast } from "sonner"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

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
  useLocation: ({ select }: { select: (l: { pathname: string }) => unknown }) => select({ pathname: "/game/undercover/g1" }),
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

const players = [
  { id: "u1", username: "Maryam" },
  { id: "u2", username: "Bilal" },
  { id: "u3", username: "Idris" },
]

const history = [
  {
    round: 1,
    votes: [{ voter: "Maryam", voter_id: "u1", target: "Bilal", target_id: "u2" }],
    eliminated: { username: "Bilal", role: "undercover", user_id: "u2" },
  },
]

const words = {
  civilian_word: "Sabr",
  civilian_word_ar: "صبر",
  civilian_word_ar_vocalized: "صَبْر",
  civilian_word_hint: "Patience",
  undercover_word: "Hilm",
  undercover_word_ar: "حلم",
  undercover_word_ar_vocalized: null,
  undercover_word_hint: "Forbearance",
}

describe("GameOverScreen (the colophon)", () => {
  const defaultProps = {
    winner: "civilians",
    roomId: "room-123" as string | null,
    isHost: true,
    myRole: "civilian",
    players,
    voteHistory: history,
    rounds: 1,
    wordExplanations: words,
    onBackToRoom: vi.fn(),
    onLeaveRoom: vi.fn(),
  }

  it('keeps "Game Over" first in the h2 (E2E) and says who was found', () => {
    render(<GameOverScreen {...defaultProps} />, { wrapper: createWrapper() })
    const title = screen.getByRole("heading", { level: 2 })
    expect(title).toHaveTextContent("game.gameOver")
    expect(title).toHaveTextContent("game.undercover.colophon.found")
  })

  it("says who won and what you held", () => {
    render(<GameOverScreen {...defaultProps} />, { wrapper: createWrapper() })
    expect(screen.getByText("game.undercover.colophon.civiliansWin game.undercover.colophon.youCivilian")).toBeInTheDocument()
  })

  it("when the impostors win, the other word held out", () => {
    render(<GameOverScreen {...defaultProps} winner="undercovers" myRole="undercover" />, { wrapper: createWrapper() })
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("game.undercover.colophon.otherWordHeld")
  })

  it('without a known winner the title is plain "Game Over"', () => {
    render(<GameOverScreen {...defaultProps} winner={undefined} />, { wrapper: createWrapper() })
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/^game\.gameOver$/)
  })

  it("lists both words: Arabic (vocalized first), the transliteration, the meaning", () => {
    render(<GameOverScreen {...defaultProps} />, { wrapper: createWrapper() })
    expect(screen.getByText("صَبْر")).toBeInTheDocument()
    expect(screen.getByText("Sabr")).toBeInTheDocument()
    expect(screen.getByText("Patience")).toBeInTheDocument()
    expect(screen.getByText("حلم")).toBeInTheDocument()
    expect(screen.getByText("Forbearance")).toBeInTheDocument()
  })

  it("seals the achievements earned this game, with who earned them", () => {
    render(
      <GameOverScreen
        {...defaultProps}
        achievements={[
          { user_id: "u1", achievements: [{ code: "first_win", name: "Taste of Victory", icon: "", tier: 1 }] },
          { user_id: "u3", achievements: [{ code: "first_win", name: "Taste of Victory", icon: "", tier: 1 }] },
        ]}
      />,
      { wrapper: createWrapper() },
    )
    expect(screen.getByText("achievements.items.first_win.name")).toBeInTheDocument()
    expect(screen.getByText("Maryam and Idris")).toBeInTheDocument()
  })

  it('the host gets "Play Again"; everyone gets "Back to Room"', () => {
    const { unmount } = render(<GameOverScreen {...defaultProps} isHost />, { wrapper: createWrapper() })
    expect(screen.getByRole("button", { name: "game.playAgain" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toBeInTheDocument()
    unmount()
    render(<GameOverScreen {...defaultProps} isHost={false} />, { wrapper: createWrapper() })
    // only the host can call a rematch (the server answers 403 to anyone else)
    expect(screen.queryByRole("button", { name: "game.playAgain" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toBeInTheDocument()
  })

  it("hides the room actions without a room", () => {
    render(<GameOverScreen {...defaultProps} roomId={null} />, { wrapper: createWrapper() })
    expect(screen.queryByRole("button", { name: "game.playAgain" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "game.backToRoom" })).not.toBeInTheDocument()
  })

  it("leaves the room", () => {
    const onLeaveRoom = vi.fn()
    render(<GameOverScreen {...defaultProps} onLeaveRoom={onLeaveRoom} />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.leave" }))
    expect(onLeaveRoom).toHaveBeenCalledOnce()
  })

  it('"Back to Room" goes back to the room', () => {
    const onBackToRoom = vi.fn()
    render(<GameOverScreen {...defaultProps} onBackToRoom={onBackToRoom} />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByRole("button", { name: "game.backToRoom" }))
    expect(onBackToRoom).toHaveBeenCalledOnce()
  })

  it('"Play Again" calls the rematch, then goes back to the room', async () => {
    const onBackToRoom = vi.fn()
    mockMutateAsync.mockResolvedValueOnce({})
    render(<GameOverScreen {...defaultProps} onBackToRoom={onBackToRoom} />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByRole("button", { name: "game.playAgain" }))
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledWith({ room_id: "room-123" }))
    await waitFor(() => expect(onBackToRoom).toHaveBeenCalledOnce())
  })

  it("keeps a slot for more actions at the head of the row", () => {
    render(<GameOverScreen {...defaultProps} extraActions={<button type="button">Keep the words</button>} />, { wrapper: createWrapper() })
    expect(screen.getByRole("button", { name: "Keep the words" })).toBeInTheDocument()
  })
})

describe("GameOverScreen: keeping the words (the Kunnash)", () => {
  const props = {
    winner: "civilians",
    roomId: "room-123" as string | null,
    isHost: true,
    myRole: "civilian",
    players,
    voteHistory: history,
    rounds: 1,
    wordExplanations: words,
    onBackToRoom: vi.fn(),
    onLeaveRoom: vi.fn(),
  }
  const GET = "GET /api/v1/notebook/games/g1"
  const KEEP_ALL = "POST /api/v1/notebook/games/g1/keep"

  const gameWords = () => ({
    game_id: "g1",
    game_type: "undercover",
    words: [
      { word: "Sabr", word_display: "Sabr", word_ar: "صبر", word_ar_vocalized: "صَبْر", hint: "Patience", kept: false, entry_id: null },
      { word: "Hilm", word_display: "Hilm", word_ar: "حلم", word_ar_vocalized: null, hint: "Forbearance", kept: false, entry_id: null },
    ],
  })
  const entry = (id: string, word: string) => ({
    id,
    word,
    word_display: word,
    game_type: "undercover",
    source_game_id: "g1",
    kept_at: "2026-10-28T20:00:00+00:00",
  })

  const renderIt = (over: Partial<typeof props> = {}) => render(<GameOverScreen {...props} {...over} />, { wrapper: createWrapper() })

  beforeEach(() => {
    resetFakeApi()
    vi.mocked(toast.success).mockClear()
    vi.mocked(toast.error).mockClear()
  })

  it('offers "Keep the words" as the brass action, then the way back, then the host\'s "Play again"', async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    renderIt()

    // Assert
    const keep = await screen.findByRole("button", { name: "notebook.colophon.keep" })
    const order = screen.getAllByRole("button").map((b) => b.textContent)
    // one order in the four colophons (ColophonActions)
    expect(order.indexOf("notebook.colophon.keep")).toBeLessThan(order.indexOf("game.backToRoom"))
    expect(order.indexOf("game.backToRoom")).toBeLessThan(order.indexOf("game.playAgain"))
    expect(order.indexOf("game.playAgain")).toBeLessThan(order.indexOf("room.lobbyPage.leave"))
    expect(keep).toHaveClass("bg-primary")
    expect(screen.getByRole("button", { name: "game.backToRoom" })).not.toHaveClass("bg-primary")
    expect(screen.getByRole("button", { name: "game.playAgain" })).not.toHaveClass("bg-primary")
    expect(requestsTo(GET)[0].params).toEqual({ lang: "en" })
  })

  it("keeps them all, says how many, then links to the notebook with focus on the link", async () => {
    // Prepare
    answer(GET, gameWords)
    answer(KEEP_ALL, () => ({ added: 2, already_kept: 0, entries: [entry("e1", "Sabr"), entry("e2", "Hilm")] }))
    renderIt()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "notebook.colophon.keep" }))

    // Assert
    const link = await screen.findByRole("link", { name: "notebook.colophon.kept" })
    expect(link).toHaveAttribute("href", "/notebook")
    await waitFor(() => expect(link).toHaveFocus())
    expect(toast.success).not.toHaveBeenCalled() // the change is in place, never a toast
    expect(requestsTo(KEEP_ALL)[0].params).toEqual({ lang: "en" })
    // nothing left to keep: the way back is the primary ("Play again" stays secondary)
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toHaveClass("bg-primary")
    const toggles = screen.getAllByRole("button", { name: "notebook.colophon.keepWord" })
    expect(toggles.map((b) => b.getAttribute("aria-pressed"))).toEqual(["true", "true"])
  })

  it("keeps one word with its toggle, then takes it out again by its entry id", async () => {
    // Prepare
    answer(GET, gameWords)
    answer("POST /api/v1/notebook/entries", () => ({ added: 1, already_kept: 0, entries: [entry("e9", "Sabr")] }))
    answer("DELETE /api/v1/notebook/entries/e9", () => undefined)
    renderIt()
    await screen.findAllByRole("button", { name: "notebook.colophon.keepWord" })
    const sabrRow = screen.getByText("Sabr").closest("li") as HTMLElement
    const sabr = within(sabrRow).getByRole("button", { name: "notebook.colophon.keepWord" })
    expect(sabr).toHaveAttribute("aria-pressed", "false")

    // Act: keep
    fireEvent.click(sabr)

    // Assert
    await waitFor(() => expect(sabr).not.toHaveAttribute("aria-busy"))
    expect(sabr).toHaveAttribute("aria-pressed", "true")
    expect(requestsTo("POST /api/v1/notebook/entries")[0].data).toEqual({ game_id: "g1", word: "Sabr" })

    // Act: take it out
    fireEvent.click(sabr)

    // Assert
    await waitFor(() => expect(sabr).toHaveAttribute("aria-pressed", "false"))
    expect(requestsTo("DELETE /api/v1/notebook/entries/e9")).toHaveLength(1)
  })

  it("takes a word out on the 204", async () => {
    // Prepare
    answer(GET, () => ({ ...gameWords(), words: gameWords().words.map((w) => ({ ...w, kept: true, entry_id: `id-${w.word}` })) }))
    answer("DELETE /api/v1/notebook/entries/id-Sabr", () => undefined)
    renderIt()
    await screen.findByRole("link", { name: "notebook.colophon.kept" })
    const sabr = within(screen.getByText("Sabr").closest("li") as HTMLElement).getByRole("button", { name: "notebook.colophon.keepWord" })

    // Act
    fireEvent.click(sabr)

    // Assert: un-kept, no error, and "Keep the words" is offered again
    await waitFor(() => expect(sabr).not.toHaveAttribute("aria-busy"))
    expect(sabr).toHaveAttribute("aria-pressed", "false")
    expect(toast.error).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "notebook.colophon.keep" })).toBeInTheDocument()
  })

  it("says a refusal (429) in the player’s language and leaves the words to keep", async () => {
    // Prepare
    answer(GET, gameWords)
    answer(KEEP_ALL, () => {
      throw httpError(429, { error_key: "errors.api.rateLimitExceeded" })
    })
    renderIt()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "notebook.colophon.keep" }))

    // Assert
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("errors.api.rateLimitExceeded"))
    expect(toast.success).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "notebook.colophon.keep" })).not.toHaveAttribute("aria-busy")
  })

  it("puts a word back as it was when the server refuses one keep", async () => {
    // Prepare
    answer(GET, gameWords)
    answer("POST /api/v1/notebook/entries", () => {
      throw httpError(403, { error_key: "errors.api.notAGameParticipant" })
    })
    renderIt()
    const sabr = (await screen.findAllByRole("button", { name: "notebook.colophon.keepWord" }))[0]

    // Act
    fireEvent.click(sabr)

    // Assert
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("errors.api.notAGameParticipant"))
    expect(sabr).toHaveAttribute("aria-pressed", "false")
  })

  it("offers a spectator nothing, and asks the server nothing", async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    renderIt({ myRole: "spectator" })

    // Assert
    await screen.findByRole("button", { name: "game.backToRoom" })
    expect(requestsTo(GET)).toHaveLength(0)
    expect(screen.queryByRole("button", { name: "notebook.colophon.keep" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "notebook.colophon.keepWord" })).not.toBeInTheDocument()
  })

  it("stays as before when the words cannot be read (403)", async () => {
    // Prepare
    answer(GET, () => {
      throw httpError(403, { error_key: "errors.api.notAGameParticipant" })
    })

    // Act
    renderIt()

    // Assert
    await waitFor(() => expect(requestsTo(GET)).toHaveLength(1))
    expect(screen.queryByRole("button", { name: "notebook.colophon.keep" })).not.toBeInTheDocument()
    // nothing left to keep: the way back is the primary ("Play again" stays secondary)
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toHaveClass("bg-primary")
    expect(toast.error).not.toHaveBeenCalled()
  })
})
