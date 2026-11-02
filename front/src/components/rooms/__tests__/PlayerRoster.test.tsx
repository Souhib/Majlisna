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
const banButtons = () => screen.getAllByRole("button", { name: /^Ban .+ from the room$/ })
const dialog = () => screen.queryByRole("alertdialog")

/** A row's action → its confirmation → the confirmation's own action. */
async function confirmWith(button: HTMLElement, action: "Remove" | "Ban") {
  fireEvent.click(button)
  const confirm = await screen.findByRole("alertdialog")
  fireEvent.click(within(confirm).getByRole("button", { name: action }))
  await waitFor(() => expect(dialog()).toBeNull())
}

function renderRoster(overrides: Partial<Parameters<typeof PlayerRoster>[0]> = {}) {
  const props = { players: table, myId: "h", canKick: true, onKick: vi.fn(), onBan: vi.fn(), ...overrides }
  return { ...render(<PlayerRoster {...props} />), props }
}

describe("PlayerRoster", () => {
  it("keeps the E2E row shape: the exact name in a span, then Remove and Ban, the row's two buttons", () => {
    renderRoster()
    const row = screen.getByText("Maryam").closest("div.flex.items-center.justify-between") as HTMLElement
    expect(row).not.toBeNull()
    const buttons = row.querySelectorAll("button")
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveAccessibleName("Remove Maryam from the room")
    expect(buttons[1]).toHaveAccessibleName("Ban Maryam from the room")
    expect(screen.getByRole("heading", { name: /Players/ })).toHaveTextContent("(4)")
  })

  it("asks before removing, and says the player may come back (a kick is no ban)", async () => {
    // Prepare
    const { props } = renderRoster()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Remove Idris from the room" }))

    // Assert: nothing is sent yet; the dialog names the player and leaves the door open
    const confirm = await screen.findByRole("alertdialog")
    expect(within(confirm).getByRole("heading", { name: "Remove Idris?" })).toBeInTheDocument()
    expect(confirm).toHaveAccessibleDescription(/Idris leaves the room, and can come back with its code and PIN, or through an invite/)
    expect(confirm).not.toHaveTextContent(/cannot come back/)
    expect(props.onKick).not.toHaveBeenCalled()
    expect(props.onBan).not.toHaveBeenCalled()
  })

  it("asks before banning, and says it holds until lifted and the PIN will change", async () => {
    // Prepare
    const { props } = renderRoster()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Ban Idris from the room" }))

    // Assert
    const confirm = await screen.findByRole("alertdialog")
    expect(within(confirm).getByRole("heading", { name: "Ban Idris?" })).toBeInTheDocument()
    expect(confirm).toHaveAccessibleDescription(/Idris leaves the room and cannot come back, not even through an invite, until you lift the ban/)
    expect(confirm).toHaveTextContent(/The PIN changes too/)
    expect(props.onKick).not.toHaveBeenCalled()
    expect(props.onBan).not.toHaveBeenCalled()
  })

  it.each(["Remove", "Ban"] as const)("keeps the player when the host cancels the %s", async (action) => {
    // Prepare
    const { props } = renderRoster()
    fireEvent.click(screen.getByRole("button", { name: `${action} Maryam from the room` }))
    const confirm = await screen.findByRole("alertdialog")

    // Act
    fireEvent.click(within(confirm).getByRole("button", { name: "Cancel" }))

    // Assert
    await waitFor(() => expect(dialog()).toBeNull())
    expect(props.onKick).not.toHaveBeenCalled()
    expect(props.onBan).not.toHaveBeenCalled()
  })

  it("removes the player named in the dialog, once, and never bans them", async () => {
    // Prepare
    const { props } = renderRoster()

    // Act
    await confirmWith(screen.getByRole("button", { name: "Remove Hafsa from the room" }), "Remove")

    // Assert
    expect(props.onKick).toHaveBeenCalledOnce()
    expect(props.onKick).toHaveBeenCalledWith(table[3])
    expect(props.onBan).not.toHaveBeenCalled()
  })

  it("bans the player named in the dialog, once, and does not also kick them", async () => {
    // Prepare
    const { props } = renderRoster()

    // Act
    await confirmWith(screen.getByRole("button", { name: "Ban Hafsa from the room" }), "Ban")

    // Assert
    expect(props.onBan).toHaveBeenCalledOnce()
    expect(props.onBan).toHaveBeenCalledWith(table[3])
    expect(props.onKick).not.toHaveBeenCalled()
  })

  it("never offers to remove or ban yourself, and nothing to a guest", () => {
    // Prepare / Act
    const { rerender, props } = renderRoster()

    // Assert
    expect(screen.queryByRole("button", { name: "Remove Yusuf from the room" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Ban Yusuf from the room" })).toBeNull()
    rerender(<PlayerRoster {...props} myId="a" canKick={false} />)
    expect(screen.queryAllByRole("button", { name: /^(Remove|Ban) / })).toHaveLength(0)
  })

  it("after a removal, puts focus on the next row's Remove instead of dropping it on <body>", async () => {
    // Prepare
    const { rerender, props } = renderRoster()
    const idris = removeButtons()[1]
    idris.focus()

    // Act
    await confirmWith(idris, "Remove")
    expect(props.onKick).toHaveBeenCalledWith(table[2])
    // the row (and its focused button) goes away with the next state
    idris.blur()
    rerender(<PlayerRoster {...props} players={table.filter((p) => p.id !== "b")} />)

    // Assert
    expect(document.activeElement).toBe(removeButtons()[1]) // Hafsa's, now second
  })

  it("after a ban, puts focus on the next row's Ban", async () => {
    // Prepare
    const { rerender, props } = renderRoster()
    const idris = banButtons()[1]
    idris.focus()

    // Act
    await confirmWith(idris, "Ban")
    idris.blur()
    rerender(<PlayerRoster {...props} players={table.filter((p) => p.id !== "b")} />)

    // Assert
    expect(document.activeElement).toBe(banButtons()[1]) // Hafsa's, now second
  })

  it("falls back to the previous row, then to the heading when nobody is left to remove", async () => {
    // Prepare
    const { rerender, props } = renderRoster({ players: [table[0], table[1]] })
    const maryam = removeButtons()[0]

    // Act
    await confirmWith(maryam, "Remove")
    maryam.blur()
    rerender(<PlayerRoster {...props} players={[table[0]]} />)

    // Assert
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: /Players/ }))
  })

  it("never takes focus from where the host has moved it meanwhile", async () => {
    // Prepare
    const onKick = vi.fn()
    const onBan = vi.fn()
    const { rerender } = render(
      <>
        <PlayerRoster players={table} myId="h" canKick onKick={onKick} onBan={onBan} />
        <button type="button">elsewhere</button>
      </>,
    )
    await confirmWith(removeButtons()[0], "Remove")
    const elsewhere = screen.getByRole("button", { name: "elsewhere" })
    elsewhere.focus()

    // Act
    rerender(
      <>
        <PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick onKick={onKick} onBan={onBan} />
        <button type="button">elsewhere</button>
      </>,
    )

    // Assert
    expect(document.activeElement).toBe(elsewhere)
  })

  it("waits for the removal to settle: the other rows' buttons are disabled while it runs", async () => {
    // Prepare
    const { rerender, props } = renderRoster({ removingId: null })
    const maryam = removeButtons()[0]
    await confirmWith(maryam, "Remove")
    maryam.blur()

    // Act: the room state (socket push) can land before the request resolves
    rerender(<PlayerRoster {...props} players={table.filter((p) => p.id !== "a")} removingId="a" />)

    // Assert
    expect(removeButtons().every((button) => button.hasAttribute("disabled"))).toBe(true)
    expect(banButtons().every((button) => button.hasAttribute("disabled"))).toBe(true)
    expect(document.activeElement).toBe(document.body)
    rerender(<PlayerRoster {...props} players={table.filter((p) => p.id !== "a")} removingId={null} />)
    expect(document.activeElement).toBe(removeButtons()[0]) // Idris's, now first
  })

  it("a cancelled dialog arms nothing: a later departure of that player moves no focus", async () => {
    // Prepare
    const onKick = vi.fn()
    const onBan = vi.fn()
    const { rerender } = render(
      <>
        <PlayerRoster players={table} myId="h" canKick onKick={onKick} onBan={onBan} />
        <button type="button">elsewhere</button>
      </>,
    )
    fireEvent.click(banButtons()[0])
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(dialog()).toBeNull())
    ;(document.activeElement as HTMLElement | null)?.blur()

    // Act: Maryam leaves by herself
    rerender(
      <>
        <PlayerRoster players={table.filter((p) => p.id !== "a")} myId="h" canKick onKick={onKick} onBan={onBan} />
        <button type="button">elsewhere</button>
      </>,
    )

    // Assert: focus is not pulled into the list
    expect(document.activeElement).toBe(document.body)
  })
})
