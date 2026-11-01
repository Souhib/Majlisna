import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { CluePanel } from "./CluePanel"

const defaultProps = {
  clueWord: "desert",
  clueNumber: 3,
  isSubmitting: false,
  onClueWordChange: vi.fn(),
  onClueNumberChange: vi.fn(),
  onSubmit: vi.fn(),
}

function renderCluePanel(overrides: Partial<typeof defaultProps> = {}) {
  return render(<CluePanel {...defaultProps} {...overrides} />)
}

const giveButton = () => screen.getByRole("button", { name: /game\.codenames\.composer\.give/ })

describe("CluePanel", () => {
  it("names the form after the action", () => {
    renderCluePanel()
    expect(screen.getByRole("form", { name: "game.codenames.giveClue" })).toBeInTheDocument()
  })

  it("renders the clue input with its value and placeholder (the E2E hook)", () => {
    renderCluePanel({ clueWord: "mosque" })
    const input = screen.getByPlaceholderText("game.codenames.cluePlaceholder")
    expect(input).toHaveValue("mosque")
    expect(input).toHaveAccessibleName("game.codenames.composer.label")
  })

  it("offers 1–4 and no limit, with the current count pressed", () => {
    renderCluePanel({ clueNumber: 3 })
    for (const n of ["1", "2", "3", "4"]) expect(screen.getByRole("button", { name: n })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "game.codenames.composer.unlimited" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "3" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "1" })).toHaveAttribute("aria-pressed", "false")
  })

  it("sends 0 for no limit", () => {
    const onClueNumberChange = vi.fn()
    renderCluePanel({ onClueNumberChange })
    fireEvent.click(screen.getByRole("button", { name: "game.codenames.composer.unlimited" }))
    expect(onClueNumberChange).toHaveBeenCalledWith(0)
    fireEvent.click(screen.getByRole("button", { name: "2" }))
    expect(onClueNumberChange).toHaveBeenCalledWith(2)
  })

  it("calls onClueWordChange on text input change", () => {
    const onClueWordChange = vi.fn()
    renderCluePanel({ onClueWordChange })
    const input = screen.getByPlaceholderText("game.codenames.cluePlaceholder")
    fireEvent.change(input, { target: { value: "prayer" } })
    expect(onClueWordChange).toHaveBeenCalledWith("prayer")
  })

  it("submits with the button and with Enter", () => {
    const onSubmit = vi.fn()
    renderCluePanel({ onSubmit })
    fireEvent.click(giveButton())
    expect(onSubmit).toHaveBeenCalledOnce()
    fireEvent.submit(screen.getByRole("form"))
    expect(onSubmit).toHaveBeenCalledTimes(2)
  })

  it("does not submit an empty clue, and the button says so by being disabled", () => {
    const onSubmit = vi.fn()
    renderCluePanel({ clueWord: "  ", onSubmit })
    expect(giveButton()).toBeDisabled()
    fireEvent.submit(screen.getByRole("form"))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("refuses a clue of several words before sending, inline, as the server would (BR-14)", () => {
    // Prepare: the board holds "Sunnah"; "the Sunnah" would carry it
    const onSubmit = vi.fn()
    renderCluePanel({ clueWord: "the Sunnah", onSubmit })

    // Act
    fireEvent.click(giveButton())

    // Assert: the field says why (the server's ClueMustBeOneWordError copy), nothing is sent
    expect(onSubmit).not.toHaveBeenCalled()
    const input = screen.getByPlaceholderText("game.codenames.cluePlaceholder")
    expect(screen.getByRole("alert")).toHaveTextContent("errors.api.clueMustBeOneWord")
    expect(input).toHaveAttribute("aria-invalid", "true")
    expect(input).toHaveAccessibleDescription("errors.api.clueMustBeOneWord")
  })

  it("refuses any whitespace inside the clue, a tab or a no-break space too", () => {
    const onSubmit = vi.fn()
    for (const clue of ["ilm\tnur", "ilm\u00a0nur"]) {
      const { unmount } = renderCluePanel({ clueWord: clue, onSubmit })
      fireEvent.submit(screen.getByRole("form"))
      expect(screen.getByRole("alert")).toBeInTheDocument()
      unmount()
    }
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("sends one word with spaces around it (they are trimmed), and clears the message once the clue is edited", () => {
    // Prepare: a refused clue first
    const onSubmit = vi.fn()
    const { rerender } = renderCluePanel({ clueWord: "two words", onSubmit })
    fireEvent.submit(screen.getByRole("form"))
    expect(screen.getByRole("alert")).toBeInTheDocument()

    // Act: the spymaster edits it down to one word
    fireEvent.change(screen.getByPlaceholderText("game.codenames.cluePlaceholder"), { target: { value: " ilm " } })
    rerender(<CluePanel {...defaultProps} clueWord=" ilm " onSubmit={onSubmit} />)

    // Assert
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    fireEvent.submit(screen.getByRole("form"))
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it("is busy while sending and ignores another submit", () => {
    const onSubmit = vi.fn()
    renderCluePanel({ isSubmitting: true, onSubmit })
    expect(giveButton()).toHaveAttribute("aria-busy", "true")
    fireEvent.submit(screen.getByRole("form"))
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
