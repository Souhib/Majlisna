import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import { beforeAll, describe, expect, it, vi } from "vitest"
import en from "@/i18n/locales/en.json"
import type { LobbyMember } from "../lobby"
import { PlayerRoster } from "../PlayerRoster"

// The real English strings (the setup file mocks react-i18next to print keys): the host
// reads what the confirmation says, and a missing key fails.
vi.unmock("react-i18next")

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

const member = (id: string, username: string, isHost = false): LobbyMember => ({
  id,
  username,
  isHost,
  isSpectator: false,
  isAway: false,
  awaySecondsLeft: null,
})

const table = [member("h", "Yusuf", true), member("a", "Maryam"), member("b", "Idris"), member("c", "Hafsa")]
const removeButtons = () => screen.getAllByRole("button", { name: /^Remove .+ from the room$/ })
const dialog = () => screen.queryByRole("alertdialog")

/** Remove → the confirmation → its "Remove": what a host does to take a seat away. */
async function removeAndConfirm(button: HTMLElement) {
  fireEvent.click(button)
  const confirm = await screen.findByRole("alertdialog")
  fireEvent.click(within(confirm).getByRole("button", { name: "Remove" }))
  await waitFor(() => expect(dialog()).toBeNull())
}

describe("PlayerRoster", () => {
  it("keeps the E2E row shape: the exact name in a span, Remove as the row's last button", () => {
    render(<PlayerRoster players={table} myId="h" canKick onKick={vi.fn()} />)
    const row = screen.getByText("Maryam").closest("div.flex.items-center.justify-between") as HTMLElement
    expect(row).not.toBeNull()
    expect(row.querySelectorAll("button")).toHaveLength(1)
    expect(row.querySelector("button")).toHaveAccessibleName("Remove Maryam from the room")
    expect(screen.getByRole("heading", { name: /Players/ })).toHaveTextContent("(4)")
  })

  it("asks before removing, and says the player cannot come back to this room (owner rule c)", async () => {
    // A kick is a ban for the room's lifetime now: one tap used to remove the player at once
    // Prepare
    const onKick = vi.fn()
    render(<PlayerRoster players={table} myId="h" canKick onKick={onKick} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Remove Idris from the room" }))

    // Assert: nothing is sent yet; the dialog names the player and says it is for good
    const confirm = await screen.findByRole("alertdialog")
    expect(within(confirm).getByRole("heading", { name: "Remove Idris?" })).toBeInTheDocument()
    expect(confirm).toHaveAccessibleDescription(/Idris leaves the room and cannot come back to it/)
    expect(confirm).toHaveTextContent("You can lift this later, in the list of removed players.")
    expect(onKick).not.toHaveBeenCalled()
  })

  it("keeps the player when the host cancels", async () => {
    // Prepare
    const onKick = vi.fn()
    render(<PlayerRoster players={table} myId="h" canKick onKick={onKick} />)
    fireEvent.click(screen.getByRole("button", { name: "Remove Maryam from the room" }))
    const confirm = await screen.findByRole("alertdialog")

    // Act
    fireEvent.click(within(confirm).getByRole("button", { name: "Cancel" }))

    // Assert
    await waitFor(() => expect(dialog()).toBeNull())
    expect(onKick).not.toHaveBeenCalled()
  })

  it("removes the player named in the dialog, once", async () => {
    // Prepare
    const onKick = vi.fn()
    render(<PlayerRoster players={table} myId="h" canKick onKick={onKick} />)

    // Act
    await removeAndConfirm(screen.getByRole("button", { name: "Remove Hafsa from the room" }))

    // Assert
    expect(onKick).toHaveBeenCalledOnce()
    expect(onKick).toHaveBeenCalledWith(table[3])
  })

  it("never offers to remove yourself, and nothing to remove for a guest", () => {
    // Prepare / Act
    const { rerender } = render(<PlayerRoster players={table} myId="h" canKick onKick={vi.fn()} />)

    // Assert
    expect(screen.queryByRole("button", { name: "Remove Yusuf from the room" })).toBeNull()
    rerender(<PlayerRoster players={table} myId="a" canKick={false} onKick={vi.fn()} />)
    expect(screen.queryAllByRole("button", { name: /^Remove / })).toHaveLength(0)
  })

  it("after a removal, puts focus on the next row's Remove instead of dropping it on <body>", async () => {
    // Prepare
    const onKick = vi.fn()
    const { rerender } = render(<PlayerRoster players={table} myId="h" canKick onKick={onKick} />)
    const idris = removeButtons()[1]
    idris.focus()

    // Act
    await removeAndConfirm(idris)
    expect(onKick).toHaveBeenCalledWith(table[2])
    // the row (and its focused button) goes away with the next state
    idris.blur()
    rerender(<PlayerRoster players={table.filter((p) => p.id !== "b")} myId="h" canKick onKick={onKick} />)

    // Assert
    expect(document.activeElement).toBe(removeButtons()[1]) // Hafsa's, now second
  })

  it("falls back to the previous row, then to the heading when nobody is left to remove", async () => {
    // Prepare
    const { rerender } = render(<PlayerRoster players={[table[0], table[1]]} myId="h" canKick onKick={vi.fn()} />)
    const maryam = removeButtons()[0]

    // Act
    await removeAndConfirm(maryam)
    maryam.blur()
    rerender(<PlayerRoster players={[table[0]]} myId="h" canKick onKick={vi.fn()} />)

    // Assert
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: /Players/ }))
  })

  it("never takes focus from where the host has moved it meanwhile", async () => {
    // Prepare
    const { rerender } = render(
      <>
        <PlayerRoster players={table} myId="h" canKick onKick={vi.fn()} />
        <button type="button">elsewhere</button>
      </>,
    )
    await removeAndConfirm(removeButtons()[0])
    const elsewhere = screen.getByRole("button", { name: "elsewhere" })
    elsewhere.focus()

    // Act
    rerender(
      <>
        <PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick onKick={vi.fn()} />
        <button type="button">elsewhere</button>
      </>,
    )

    // Assert
    expect(document.activeElement).toBe(elsewhere)
  })

  it("waits for the removal to settle: the other Remove buttons are disabled while it runs", async () => {
    // Prepare
    const { rerender } = render(<PlayerRoster players={table} myId="h" canKick kickingId={null} onKick={vi.fn()} />)
    const maryam = removeButtons()[0]
    await removeAndConfirm(maryam)
    maryam.blur()

    // Act: the room state (socket push) can land before the request resolves
    rerender(<PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick kickingId="a" onKick={vi.fn()} />)

    // Assert
    expect(document.activeElement).toBe(document.body)
    rerender(<PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick kickingId={null} onKick={vi.fn()} />)
    expect(document.activeElement).toBe(removeButtons()[0]) // Idris's, now first
  })

  it("a cancelled dialog arms nothing: a later departure of that player moves no focus", async () => {
    // Prepare
    const { rerender } = render(
      <>
        <PlayerRoster players={table} myId="h" canKick onKick={vi.fn()} />
        <button type="button">elsewhere</button>
      </>,
    )
    fireEvent.click(removeButtons()[0])
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(dialog()).toBeNull())
    ;(document.activeElement as HTMLElement | null)?.blur()

    // Act: Maryam leaves by herself
    rerender(
      <>
        <PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick onKick={vi.fn()} />
        <button type="button">elsewhere</button>
      </>,
    )

    // Assert: focus is not pulled into the list
    expect(document.activeElement).toBe(document.body)
  })
})
