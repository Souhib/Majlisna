import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { UndercoverLeaveButton } from "./UndercoverLeaveButton"

const open = () => fireEvent.click(screen.getByRole("button", { name: "room.lobbyPage.leave" }))

describe("UndercoverLeaveButton", () => {
  it("asks first, and says the seat empties for a seated player", () => {
    const onLeave = vi.fn()
    render(<UndercoverLeaveButton onLeave={onLeave} />)
    open()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    expect(screen.getByText("game.undercover.leaveConfirmBody")).toBeInTheDocument()
    expect(onLeave).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByRole("button", { name: "room.lobbyPage.leave" }).at(-1)!)
    expect(onLeave).toHaveBeenCalledOnce()
  })

  it("tells an eliminated player their seat is already empty", () => {
    render(<UndercoverLeaveButton onLeave={vi.fn()} isEliminated />)
    open()
    expect(screen.getByText("game.undercover.leaveConfirmBodyOut")).toBeInTheDocument()
  })

  it("tells a spectator they only stop watching", () => {
    render(<UndercoverLeaveButton onLeave={vi.fn()} isSpectator isEliminated />)
    open()
    expect(screen.getByText("game.undercover.leaveConfirmBodySpectator")).toBeInTheDocument()
  })
})
