import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { DescriptionPhase } from "./DescriptionPhase"

describe("DescriptionPhase", () => {
  const defaultProps = {
    descriptionOrder: [
      { user_id: "u1", username: "Alice" },
      { user_id: "u2", username: "Bob" },
      { user_id: "u3", username: "Charlie" },
    ],
    currentDescriberIndex: 0,
    descriptions: {} as Record<string, string>,
    currentUserId: "u1",
    isMyTurnToDescribe: false,
    isAlive: true,
    descriptionInput: "",
    descriptionError: "",
    isSubmittingDescription: false,
    onDescriptionInputChange: vi.fn(),
    onSubmitDescription: vi.fn(),
  }

  it('lists everyone in speaking order, "You" for the current user', () => {
    render(<DescriptionPhase {...defaultProps} currentUserId="u2" />)
    const list = screen.getByRole("list", { name: "game.undercover.descriptionOrder" })
    expect(list).toHaveTextContent("Alice")
    expect(list).toHaveTextContent("game.undercover.you")
    expect(list).toHaveTextContent("Charlie")
  })

  it("heads the phase with whoever is describing", () => {
    render(<DescriptionPhase {...defaultProps} currentDescriberIndex={1} currentUserId="u3" />)
    expect(screen.getByRole("heading", { name: "game.undercover.describingTitle" })).toBeInTheDocument()
  })

  it("marks the current describer's row", () => {
    const { container } = render(<DescriptionPhase {...defaultProps} currentDescriberIndex={1} currentUserId="u3" />)
    const current = container.querySelector("[data-current]")
    expect(current).toHaveTextContent("Bob")
    expect(current).toHaveTextContent("game.undercover.describingNow")
  })

  it('says "your turn" (in brass) on your own row and in the heading', () => {
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} />)
    expect(screen.getByRole("heading", { name: "game.undercover.yourTurnToDescribe" })).toBeInTheDocument()
    expect(screen.getByText("game.undercover.yourTurn")).toHaveClass("text-brass")
  })

  it("shows Latin descriptions in quotes and Arabic ones in the hand", () => {
    render(<DescriptionPhase {...defaultProps} descriptions={{ u1: "patience", u2: "كظم" }} currentDescriberIndex={2} />)
    expect(screen.getByText("patience").closest(".uc-said")).toBeInTheDocument()
    const arabic = screen.getByText("كظم")
    expect(arabic).toHaveClass("uc-hand")
    expect(arabic).toHaveAttribute("lang", "ar")
  })

  it("gives the describer the #description-input composer", () => {
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} isAlive={true} />)
    const input = screen.getByRole("textbox", { name: "game.undercover.describeInOneWord" })
    expect(input).toHaveAttribute("id", "description-input")
  })

  it("hides the composer when it is not your turn", () => {
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={false} />)
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("hides the composer from an eliminated player", () => {
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} isAlive={false} />)
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("submits with the button and with Enter", () => {
    const onSubmitDescription = vi.fn()
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} descriptionInput="word" onSubmitDescription={onSubmitDescription} />)
    fireEvent.click(screen.getByRole("button", { name: "game.undercover.submitDescription" }))
    fireEvent.submit(screen.getByRole("textbox"))
    expect(onSubmitDescription).toHaveBeenCalledTimes(2)
  })

  it("reports the input change", () => {
    const onDescriptionInputChange = vi.fn()
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} onDescriptionInputChange={onDescriptionInputChange} />)
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hilm" } })
    expect(onDescriptionInputChange).toHaveBeenCalledWith("hilm")
  })

  it("shows the error as an alert tied to the field", () => {
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} descriptionError="Use one word" />)
    expect(screen.getByRole("alert")).toHaveTextContent("Use one word")
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true")
  })

  it("keeps the submit button disabled while the input is empty", () => {
    render(<DescriptionPhase {...defaultProps} isMyTurnToDescribe={true} descriptionInput="" />)
    expect(screen.getByRole("button", { name: "game.undercover.submitDescription" })).toBeDisabled()
  })

  it("is the whole table: the Mayor on their row, an emptied seat with its role at the end", () => {
    render(
      <DescriptionPhase
        {...defaultProps}
        players={[
          { id: "u1", username: "Alice", is_alive: true },
          { id: "u2", username: "Bob", is_alive: true, is_mayor: true },
          { id: "u3", username: "Charlie", is_alive: true },
          { id: "u4", username: "Dave", is_alive: false },
        ]}
        eliminated={[{ user_id: "u4", role: "civilian" }]}
      />,
    )
    const rows = screen.getByRole("list", { name: "game.undercover.descriptionOrder" }).querySelectorAll("li")
    expect(rows).toHaveLength(4)
    expect(rows[1]).toHaveTextContent("game.undercover.mayorLabel")
    expect(rows[3]).toHaveTextContent("Dave")
    expect(rows[3]).toHaveTextContent("game.eliminated · games.undercover.roles.civilian")
    expect(rows[3]).toHaveAttribute("data-out")
  })
})
