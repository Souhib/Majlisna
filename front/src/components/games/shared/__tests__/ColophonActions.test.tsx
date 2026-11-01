import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { NotebookGameWord } from "@/api/generated"
import type { ColophonNotebook } from "@/components/notebook/use-colophon-notebook"

const renderCardFile = vi.hoisted(() => vi.fn())
vi.mock("@/components/brand/share-card/render", () => ({ renderCardFile }))

vi.mock("@/api/generated", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/generated")>()),
  useRematchApiV1RoomsRoomIdRematchPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const { ColophonActions } = await import("../ColophonActions")

/**
 * The way on from every colophon, now with "Share" (spec 11): the card of the evening,
 * for a player of the game only (a spectator gets no Share, as they get no Keep).
 */

const words: NotebookGameWord[] = [
  { word: "Sabr", word_display: "Sabr", word_ar: "صبر", word_ar_vocalized: "صَبْر", hint: "Patience", kept: false, entry_id: null },
  { word: "Hilm", word_display: "Hilm", word_ar: "حلم", word_ar_vocalized: null, hint: "Forbearance", kept: false, entry_id: null },
]

const notebook = (over: Partial<ColophonNotebook> = {}): ColophonNotebook => ({
  words,
  isLoading: false,
  available: true,
  allKept: false,
  keepAll: vi.fn(async () => {}),
  keepingAll: false,
  find: () => undefined,
  toggle: vi.fn(async () => {}),
  isBusy: () => false,
  ...over,
})

const share = { game: "codenames", host: "Yusuf", count: "9 clues", startedAt: "2026-10-28T20:00:00Z", endedAt: "2026-10-28T20:14:05Z" } as const

beforeEach(() => {
  renderCardFile.mockReset()
  renderCardFile.mockImplementation(async (_input: unknown, name: string) => new File(["png"], name, { type: "image/png" }))
})

afterEach(() => {
  for (const key of ["canShare", "share"]) delete (navigator as unknown as Record<string, unknown>)[key]
})

describe("ColophonActions", () => {
  it("offers Share after the way on and before Leave, as a quiet secondary", () => {
    // Act
    render(<ColophonActions notebook={notebook()} roomId="r1" isHost share={share} onBackToRoom={vi.fn()} onLeaveRoom={vi.fn()} />)

    // Assert
    const order = screen.getAllByRole("button").map((b) => b.textContent)
    expect(order).toEqual(["notebook.colophon.keep", "game.backToRoom", "game.playAgain", "game.colophon.share.action", "room.lobbyPage.leave"])
    expect(screen.getByRole("button", { name: "game.colophon.share.action" })).not.toHaveClass("bg-primary")
  })

  it("offers no Share to a spectator, as it offers no Keep", () => {
    // Act
    render(<ColophonActions notebook={notebook({ words: undefined, available: false })} roomId="r1" onBackToRoom={vi.fn()} onLeaveRoom={vi.fn()} />)

    // Assert
    expect(screen.queryByRole("button", { name: "game.colophon.share.action" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "notebook.colophon.keep" })).not.toBeInTheDocument()
  })

  it("draws the card from the game's words and its meta line when the player shares", async () => {
    // Prepare
    const shareSheet = vi.fn(async () => {})
    Object.defineProperty(navigator, "canShare", { value: () => true, configurable: true })
    Object.defineProperty(navigator, "share", { value: shareSheet, configurable: true })
    render(<ColophonActions notebook={notebook()} roomId="r1" share={share} onBackToRoom={vi.fn()} onLeaveRoom={vi.fn()} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(shareSheet).toHaveBeenCalledTimes(1))
    const [input, fileName] = renderCardFile.mock.calls[0]
    expect(fileName).toBe("majlisna-codenames.png")
    expect(input).toMatchObject({
      kind: "game",
      arabicName: "home.fihrist.codenames.arabic",
      latinName: "games.codenames.name",
      words: [
        { arabic: "صَبْر", display: "Sabr" },
        { arabic: "حلم", display: "Hilm" },
      ],
    })
    expect(input.meta).toEqual(["games.codenames.name", "game.colophon.majlis", "9 clues", "14:05"])
    expect(shareSheet).toHaveBeenCalledWith(expect.objectContaining({ title: "games.codenames.name", text: "game.colophon.share.line" }))
  })

  it("shares a game without words too (the Quiz): the name and the meta line", async () => {
    // Prepare
    Object.defineProperty(navigator, "canShare", { value: () => true, configurable: true })
    Object.defineProperty(navigator, "share", { value: vi.fn(async () => {}), configurable: true })
    render(<ColophonActions roomId="r1" share={{ game: "mcqquiz", count: "10 questions" }} onBackToRoom={vi.fn()} onLeaveRoom={vi.fn()} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(renderCardFile).toHaveBeenCalled())
    expect(renderCardFile.mock.calls[0][0]).toMatchObject({ arabicName: "home.fihrist.mcqQuiz.arabic", words: [] })
  })
})
