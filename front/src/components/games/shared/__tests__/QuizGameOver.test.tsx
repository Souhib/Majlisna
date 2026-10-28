import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render as rtlRender, screen, fireEvent, waitFor, within } from "@testing-library/react"
import { type ReactElement, type ReactNode } from "react"
import { beforeEach, describe, it, expect, vi } from "vitest"
import { toast } from "sonner"
import { answer, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import { QuizGameOver } from "../QuizGameOver"

const route = vi.hoisted(() => ({ pathname: "/game/mcqquiz/m1" }))

const mockRematch = vi.hoisted(() => vi.fn())
vi.mock("@/api/generated", async () => ({
  ...(await (await import("@/components/notebook/__tests__/fake-api")).notebookGenerated()),
  useRematchApiV1RoomsRoomIdRematchPost: () => ({ mutateAsync: mockRematch, isPending: false }),
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@tanstack/react-router", () => ({
  useLocation: ({ select }: { select: (l: { pathname: string }) => unknown }) => select({ pathname: route.pathname }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

function render(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return rtlRender(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const leaderboard = [
  { user_id: "u1", username: "Alice", total_score: 10 },
  { user_id: "u2", username: "Bob", total_score: 20 },
  { user_id: "u3", username: "Charlie", total_score: 15 },
]

const defaultProps = {
  winner: "Bob",
  leaderboard,
  roomId: "r1",
  onBackToRoom: vi.fn(),
  onLeaveRoom: vi.fn(),
}

const rows = () => within(screen.getByTestId("quiz-final-scores")).getAllByRole("listitem")

describe("QuizGameOver (the colophon)", () => {
  it('keeps "Game Over" in the h2, with the winner sentence', () => {
    render(<QuizGameOver {...defaultProps} />)
    const title = screen.getByRole("heading", { level: 2 })
    expect(title).toHaveTextContent("game.gameOver")
    expect(title).toHaveTextContent("game.winner")
  })

  it('titles "Game Over" alone when there is no winner yet', () => {
    render(<QuizGameOver {...defaultProps} winner={null} />)
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/^game\.gameOver$/)
  })

  it("calls a tie a tie, whatever winner the server named", () => {
    render(<QuizGameOver {...defaultProps} leaderboard={[...leaderboard, { user_id: "u4", username: "Dina", total_score: 20 }]} />)
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("game.quiz.tie")
  })

  it("speaks to a solo player about their score", () => {
    render(<QuizGameOver {...defaultProps} leaderboard={[leaderboard[0]]} winner="Alice" />)
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("game.quiz.soloScore")
  })

  it("renders final scores heading with default i18n key", () => {
    render(<QuizGameOver {...defaultProps} />)
    expect(screen.getByText("game.finalScores")).toBeInTheDocument()
  })

  it("renders custom i18n keys when provided", () => {
    render(<QuizGameOver {...defaultProps} winnerI18nKey="game.wordQuiz.winner" finalScoresI18nKey="game.wordQuiz.finalScores" />)
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("game.wordQuiz.winner")
    expect(screen.getByText("game.wordQuiz.finalScores")).toBeInTheDocument()
    // the way back is the one label of every colophon
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toBeInTheDocument()
  })

  it("says how a win ended under the title: the lead over the runner-up", () => {
    render(<QuizGameOver {...defaultProps} />)
    // Bob 20, Charlie 15: five clear of Charlie
    expect(screen.getByText("game.quiz.winSummary")).toBeInTheDocument()
  })

  it("says a tie in points under the tie", () => {
    render(<QuizGameOver {...defaultProps} leaderboard={[...leaderboard, { user_id: "u4", username: "Dina", total_score: 20 }]} />)
    expect(screen.getByText("game.quiz.tieSummary")).toBeInTheDocument()
  })

  it('gives "Play again" to the host only, after the way back', () => {
    const { unmount } = render(<QuizGameOver {...defaultProps} isHost />)
    const order = screen.getAllByRole("button").map((b) => b.textContent)
    expect(order.indexOf("game.backToRoom")).toBeLessThan(order.indexOf("game.playAgain"))
    unmount()
    render(<QuizGameOver {...defaultProps} />)
    expect(screen.queryByRole("button", { name: "game.playAgain" })).not.toBeInTheDocument()
  })

  it("has no way back to a room it does not know", () => {
    render(<QuizGameOver {...defaultProps} roomId={null} isHost />)
    expect(screen.queryByRole("button", { name: "game.backToRoom" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "game.playAgain" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "room.lobbyPage.leave" })).toBeInTheDocument()
  })

  it("sorts the final scores, places first, with each score", () => {
    render(<QuizGameOver {...defaultProps} />)
    expect(rows().map((r) => r.textContent)).toEqual(["1Bob20", "2Charlie15", "3Alice10"])
  })

  it("marks your own row", () => {
    render(<QuizGameOver {...defaultProps} currentUserId="u3" />)
    expect(rows()[1]).toHaveAttribute("data-you", "true")
  })

  it("presses achievements as seals", () => {
    render(<QuizGameOver {...defaultProps} seals={[{ title: "Taste of Victory", caption: "Bob · Bronze" }]} />)
    expect(screen.getByText("Taste of Victory")).toBeInTheDocument()
    expect(screen.getByText("Bob · Bronze")).toBeInTheDocument()
  })

  it("sets extra actions before the way back", () => {
    render(<QuizGameOver {...defaultProps} extraActions={<button type="button">Keep the words</button>} />)
    const buttons = screen.getAllByRole("button").map((b) => b.textContent)
    expect(buttons.indexOf("Keep the words")).toBeLessThan(buttons.indexOf("game.backToRoom"))
  })

  it("calls onBackToRoom when back button is clicked", () => {
    const onBackToRoom = vi.fn()
    render(<QuizGameOver {...defaultProps} onBackToRoom={onBackToRoom} />)
    fireEvent.click(screen.getByText("game.backToRoom"))
    expect(onBackToRoom).toHaveBeenCalledOnce()
  })

  it("calls onLeaveRoom when leave button is clicked", () => {
    const onLeaveRoom = vi.fn()
    render(<QuizGameOver {...defaultProps} onLeaveRoom={onLeaveRoom} />)
    fireEvent.click(screen.getByText("room.lobbyPage.leave"))
    expect(onLeaveRoom).toHaveBeenCalledOnce()
  })

  it("renders with empty leaderboard", () => {
    render(<QuizGameOver {...defaultProps} leaderboard={[]} />)
    expect(screen.getByText("game.finalScores")).toBeInTheDocument()
  })
})

describe("QuizGameOver: the words of a Kalimat game (the Kunnash)", () => {
  const GET = "GET /api/v1/notebook/games/k1"
  const gameWords = () => ({
    game_id: "k1",
    game_type: "word_quiz",
    words: [
      { word: "Patience", word_display: "Patience", word_ar: "صبر", word_ar_vocalized: "صَبْر", hint: "Staying steady", kept: false, entry_id: null },
      { word: "Mercy", word_display: "Mercy", word_ar: "رحمة", word_ar_vocalized: null, hint: null, kept: true, entry_id: "e7" },
    ],
  })

  beforeEach(() => {
    resetFakeApi()
    route.pathname = "/game/wordquiz/k1"
    vi.mocked(toast.success).mockClear()
  })

  it("lists the game’s words after the scores: Amiri Arabic (vocalised first), the word, its meaning", async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    render(<QuizGameOver {...defaultProps} currentUserId="u1" />)

    // Assert
    const section = (await screen.findByRole("heading", { level: 3, name: "notebook.colophon.wordsTitle" })).closest("section") as HTMLElement
    expect(await within(section).findByText("صَبْر")).toHaveAttribute("lang", "ar")
    expect(within(section).getByText("Patience")).toBeInTheDocument()
    expect(within(section).getByText("Staying steady")).toBeInTheDocument()
    expect(within(section).getByText("رحمة")).toBeInTheDocument()
    const toggles = within(section).getAllByRole("button", { name: "notebook.colophon.keepWord" })
    expect(toggles.map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "true"])
    expect(requestsTo(GET)[0].params).toEqual({ lang: "en" })
  })

  it('makes "Keep the words" the brass action before "Back to Room", which steps down', async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    render(<QuizGameOver {...defaultProps} currentUserId="u1" />)

    // Assert
    const keep = await screen.findByRole("button", { name: "notebook.colophon.keep" })
    expect(keep).toHaveClass("bg-primary")
    expect(screen.getByRole("button", { name: "game.backToRoom" })).not.toHaveClass("bg-primary")
    const order = screen.getAllByRole("button").map((b) => b.textContent)
    expect(order.indexOf("notebook.colophon.keep")).toBeLessThan(order.indexOf("game.backToRoom"))
  })

  it("keeps the rest and links to the notebook", async () => {
    // Prepare
    answer(GET, gameWords)
    answer("POST /api/v1/notebook/games/k1/keep", () => ({
      added: 1,
      already_kept: 1,
      entries: [
        { id: "e6", word: "Patience", word_display: "Patience", game_type: "word_quiz", kept_at: "2026-10-28T20:00:00+00:00" },
        { id: "e7", word: "Mercy", word_display: "Mercy", game_type: "word_quiz", kept_at: "2026-10-27T20:00:00+00:00" },
      ],
    }))
    render(<QuizGameOver {...defaultProps} currentUserId="u1" />)

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "notebook.colophon.keep" }))

    // Assert
    expect(await screen.findByRole("link", { name: "notebook.colophon.kept" })).toHaveAttribute("href", "/notebook")
    expect(toast.success).not.toHaveBeenCalled() // the change is in place, never a toast
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toHaveClass("bg-primary")
  })

  it("shows bare warp while the words load, said to screen readers", async () => {
    // Prepare
    answer(GET, () => new Promise(() => {}))

    // Act
    render(<QuizGameOver {...defaultProps} currentUserId="u1" />)

    // Assert
    expect(await screen.findByRole("status")).toHaveTextContent("notebook.colophon.loadingWords")
  })

  it("has no words for the MCQ quiz, and asks nothing", async () => {
    // Prepare
    route.pathname = "/game/mcqquiz/k1"
    answer(GET, gameWords)

    // Act
    render(<QuizGameOver {...defaultProps} currentUserId="u1" />)

    // Assert
    await screen.findByRole("button", { name: "game.backToRoom" })
    expect(requestsTo(GET)).toHaveLength(0)
    expect(screen.queryByText("notebook.colophon.wordsTitle")).not.toBeInTheDocument()
  })

  it("offers a spectator (not on the leaderboard) nothing", async () => {
    // Prepare
    answer(GET, gameWords)

    // Act
    render(<QuizGameOver {...defaultProps} currentUserId="watcher" />)

    // Assert
    await screen.findByRole("button", { name: "game.backToRoom" })
    expect(requestsTo(GET)).toHaveLength(0)
    expect(screen.queryByRole("button", { name: "notebook.colophon.keep" })).not.toBeInTheDocument()
  })

  it("stays as before when the words cannot be read", async () => {
    // Act
    render(<QuizGameOver {...defaultProps} currentUserId="u1" />)

    // Assert
    await waitFor(() => expect(requestsTo(GET)).toHaveLength(1))
    await waitFor(() => expect(screen.queryByText("notebook.colophon.wordsTitle")).not.toBeInTheDocument())
    expect(screen.getByRole("button", { name: "game.backToRoom" })).toHaveClass("bg-primary")
  })
})
