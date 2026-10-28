import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { LobbyMember } from "../lobby"
import { PlayerRoster } from "../PlayerRoster"

const member = (id: string, username: string, isHost = false): LobbyMember => ({
  id,
  username,
  isHost,
  isSpectator: false,
  isAway: false,
  awaySecondsLeft: null,
})

const table = [member("h", "Yusuf", true), member("a", "Maryam"), member("b", "Idris"), member("c", "Hafsa")]
const removeButtons = () => screen.getAllByRole("button", { name: "room.lobbyPage.kick" })

describe("PlayerRoster", () => {
  it("keeps the E2E row shape: the exact name in a span, Remove as the row's last button", () => {
    render(<PlayerRoster players={table} myId="h" canKick onKick={vi.fn()} />)
    const row = screen.getByText("Maryam").closest("div.flex.items-center.justify-between") as HTMLElement
    expect(row).not.toBeNull()
    expect(row.querySelectorAll("button")).toHaveLength(1)
    expect(screen.getByRole("heading", { name: /room\.players/ })).toHaveTextContent("(4)")
  })

  it("after a removal, puts focus on the next row's Remove instead of dropping it on <body>", () => {
    const onKick = vi.fn()
    const { rerender } = render(<PlayerRoster players={table} myId="h" canKick onKick={onKick} />)
    const idris = removeButtons()[1]
    idris.focus()
    fireEvent.click(idris)
    expect(onKick).toHaveBeenCalledWith(table[2])

    // the row (and its focused button) goes away with the next state
    idris.blur()
    rerender(<PlayerRoster players={table.filter((p) => p.id !== "b")} myId="h" canKick onKick={onKick} />)

    expect(document.activeElement).toBe(removeButtons()[1]) // Hafsa's, now second
  })

  it("falls back to the previous row, then to the heading when nobody is left to remove", () => {
    const { rerender } = render(<PlayerRoster players={[table[0], table[1]]} myId="h" canKick onKick={vi.fn()} />)
    fireEvent.click(removeButtons()[0])
    rerender(<PlayerRoster players={[table[0]]} myId="h" canKick onKick={vi.fn()} />)
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: /room\.players/ }))
  })

  it("never takes focus from where the host has moved it meanwhile", () => {
    const { rerender } = render(
      <>
        <PlayerRoster players={table} myId="h" canKick onKick={vi.fn()} />
        <button type="button">elsewhere</button>
      </>,
    )
    fireEvent.click(removeButtons()[0])
    const elsewhere = screen.getByRole("button", { name: "elsewhere" })
    elsewhere.focus()
    rerender(
      <>
        <PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick onKick={vi.fn()} />
        <button type="button">elsewhere</button>
      </>,
    )
    expect(document.activeElement).toBe(elsewhere)
  })

  it("waits for the removal to settle: the other Remove buttons are disabled while it runs", () => {
    const { rerender } = render(<PlayerRoster players={table} myId="h" canKick kickingId={null} onKick={vi.fn()} />)
    fireEvent.click(removeButtons()[0])
    // the room state (socket push) can land before the request resolves
    rerender(<PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick kickingId="a" onKick={vi.fn()} />)
    expect(document.activeElement).toBe(document.body)
    rerender(<PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick kickingId={null} onKick={vi.fn()} />)
    expect(document.activeElement).toBe(removeButtons()[0]) // Idris's, now first
  })
})
