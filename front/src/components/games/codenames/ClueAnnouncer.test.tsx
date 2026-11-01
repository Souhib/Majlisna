import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}))

const { ClueAnnouncer, clueJustLanded, clueKey } = await import("./CluePanel")

describe("ClueAnnouncer", () => {
  it("is an empty polite region while the spymaster is choosing, so the clue is read when it lands", () => {
    // Prepare / Act
    render(<ClueAnnouncer clueWord={null} clueNumber={null} teamName="Red" />)

    // Assert: the region is in the DOM before its text arrives
    const region = screen.getByRole("status")
    expect(region).toHaveTextContent("")
    expect(region).toHaveAttribute("aria-atomic", "true")
  })

  it("reads the clue word, its count and its team once it is given", () => {
    // Prepare
    const { rerender } = render(<ClueAnnouncer clueWord={null} clueNumber={null} teamName="Red" />)

    // Act
    rerender(<ClueAnnouncer clueWord="Knowledge" clueNumber={2} teamName="Red" />)

    // Assert
    expect(screen.getByRole("status")).toHaveTextContent('game.codenames.clueAnnounce {"team":"Red","word":"Knowledge","number":2}')
  })

  it("keeps the same text across re-renders of the same clue (nothing is read twice)", () => {
    // Prepare
    const { rerender } = render(<ClueAnnouncer clueWord="علم" clueNumber={0} teamName="Blue" />)
    const region = screen.getByRole("status")
    const first = region.textContent

    // Act
    rerender(<ClueAnnouncer clueWord="علم" clueNumber={0} teamName="Blue" />)

    // Assert: same node, same text; "no limit" is said in words, not as ∞
    expect(screen.getByRole("status")).toBe(region)
    expect(region.textContent).toBe(first)
    expect(region).toHaveTextContent('"number":"game.codenames.composer.unlimited"')
  })
})

describe("ClueAnnouncer: the clue that has just landed (for ClueBanner's writing)", () => {
  it("names a clue by its word and its count, and nothing while the spymaster is choosing", () => {
    expect(clueKey("Knowledge", 2)).toBe(clueKey(" Knowledge ", 2))
    expect(clueKey("Knowledge", 2)).not.toBe(clueKey("Knowledge", 3))
    expect(clueKey(null, null)).toBeNull()
    expect(clueKey("  ", 1)).toBeNull()
  })

  it("does not call the clue it was mounted with new (a page opened on it)", () => {
    render(<ClueAnnouncer clueWord="Knowledge" clueNumber={2} teamName="Red" />)
    expect(clueJustLanded(clueKey("Knowledge", 2))).toBe(false)
  })

  it("says a clue has landed during the commit that brings it, and only then", async () => {
    // Prepare
    const { rerender } = render(<ClueAnnouncer clueWord={null} clueNumber={null} teamName="Red" />)

    // Act
    rerender(<ClueAnnouncer clueWord="Knowledge" clueNumber={2} teamName="Red" />)

    // Assert: true for that commit, for that clue alone; forgotten right after
    expect(clueJustLanded(clueKey("Knowledge", 2))).toBe(true)
    expect(clueJustLanded(clueKey("Knowledge", 1))).toBe(false)
    expect(clueJustLanded(null)).toBe(false)
    await Promise.resolve()
    expect(clueJustLanded(clueKey("Knowledge", 2))).toBe(false)
  })

  it("speaks the new clue once, its text unchanged by a re-render of the same clue", () => {
    const { rerender } = render(<ClueAnnouncer clueWord={null} clueNumber={null} teamName="Red" />)
    rerender(<ClueAnnouncer clueWord="Knowledge" clueNumber={2} teamName="Red" />)
    const region = screen.getByRole("status")
    const spoken = region.textContent

    rerender(<ClueAnnouncer clueWord="Knowledge" clueNumber={2} teamName="Red" />)

    expect(screen.getByRole("status")).toBe(region)
    expect(region.textContent).toBe(spoken)
  })
})
