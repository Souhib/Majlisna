import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import en from "@/i18n/locales/en.json"
import { animationsOf, calls, recordAnimations, stopRecordingAnimations, stubReducedMotion } from "@/components/games/undercover/__tests__/record-animations"
import type { LobbyMember } from "../lobby"
import { PlayerRoster } from "../PlayerRoster"

/**
 * ERASE in the lobby (ANIM-2, spec 7): the roster's emptied seat is an AWAY seat (the player
 * lost the connection; the server keeps the seat for the grace, "away · 9:58"). It recedes on
 * screen instead of jumping; a player who comes back is restored. A player who leaves the room
 * is no longer in the room state: their row goes, it is never kept as a ghost.
 */
vi.unmock("react-i18next")

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

const INK_CURVE = "cubic-bezier(0.45, 0.05, 0.2, 1)"
const OUT_CURVE = "cubic-bezier(0.16, 1, 0.3, 1)"

const member = (id: string, username: string, over: Partial<LobbyMember> = {}): LobbyMember => ({
  id,
  username,
  isHost: false,
  isSpectator: false,
  isAway: false,
  awaySecondsLeft: null,
  ...over,
})

const table = [member("h", "Yusuf", { isHost: true }), member("a", "Maryam"), member("b", "Idris")]
const idrisAway = table.map((m) => (m.id === "b" ? { ...m, isAway: true, awaySecondsLeft: 598 } : m))
const seatOf = (container: HTMLElement, id: string) => container.querySelector(`[data-seat="${id}"]`)

beforeEach(() => {
  recordAnimations()
  stubReducedMotion(false)
})

afterEach(() => {
  stopRecordingAnimations()
})

describe("PlayerRoster: an away seat recedes", () => {
  it("erases the seat whose player drops: name and lozenge on the ink curve, the countdown faded in", () => {
    // Prepare
    const { container, rerender } = render(<PlayerRoster players={table} myId="h" canKick={false} onKick={vi.fn()} />)

    // Act
    rerender(<PlayerRoster players={idrisAway} myId="h" canKick={false} onKick={vi.fn()} awayLeft={new Map([["b", 598]])} />)

    // Assert
    const idris = seatOf(container, "b")
    expect(idris).toHaveAttribute("data-away")
    expect(animationsOf(idris, "ink")[0].keyframes).toEqual([{ opacity: 1 }, { opacity: 0.72 }])
    expect(animationsOf(idris, "ink")[0].options).toMatchObject({ duration: 640, easing: INK_CURVE })
    expect(animationsOf(idris, "mark")[0].keyframes).toEqual([{ opacity: 1 }, { opacity: 0.45 }])
    const [note] = animationsOf(idris, "note")
    expect(note.keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(note.el).toHaveTextContent("away · 9:58")
    expect(calls).toHaveLength(3)
  })

  it("restores a player who comes back, in the state time", () => {
    // Prepare
    const { container, rerender } = render(<PlayerRoster players={idrisAway} myId="h" canKick={false} onKick={vi.fn()} />)
    expect(calls).toHaveLength(0)

    // Act
    rerender(<PlayerRoster players={table} myId="h" canKick={false} onKick={vi.fn()} />)

    // Assert
    const idris = seatOf(container, "b")
    expect(idris).not.toHaveAttribute("data-away")
    expect(animationsOf(idris, "ink")[0].keyframes).toEqual([{ opacity: 0.72 }, { opacity: 1 }])
    expect(animationsOf(idris, "mark")[0].keyframes).toEqual([{ opacity: 0.45 }, { opacity: 1 }])
    for (const part of calls) expect(part.options).toMatchObject({ duration: 180, easing: OUT_CURVE })
  })

  it("keeps the E2E row shape: the exact name in its own span, the row a flex justify-between", () => {
    // Prepare / Act
    render(<PlayerRoster players={idrisAway} myId="h" canKick onKick={vi.fn()} />)

    // Assert
    const name = screen.getByText("Idris")
    expect(name.tagName).toBe("SPAN")
    expect(name).toHaveAttribute("data-erase", "ink")
    const row = name.closest("div.flex.items-center.justify-between") as HTMLElement
    expect(row.querySelectorAll("button")).toHaveLength(1)
    expect(row.querySelector("button")).toHaveAccessibleName("Remove Idris from the room")
  })

  it("moves nothing on load, nor for the host's own state, nor when a player leaves the room", () => {
    // Prepare
    const { rerender } = render(<PlayerRoster players={idrisAway} myId="h" canKick={false} onKick={vi.fn()} />)
    // the host's seat says "host", never "away", even when their connection drops
    const hostAway = idrisAway.map((m) => (m.id === "h" ? { ...m, isAway: true } : m))

    // Act
    rerender(<PlayerRoster players={hostAway} myId="a" canKick={false} onKick={vi.fn()} />)
    rerender(<PlayerRoster players={hostAway.filter((m) => m.id !== "a")} myId="b" canKick={false} onKick={vi.fn()} />)

    // Assert
    expect(calls).toHaveLength(0)
    expect(screen.queryByText("Maryam")).toBeNull()
  })

  it("under reduced motion, is a 180 ms opacity change", () => {
    // Prepare
    stubReducedMotion(true)
    const { container, rerender } = render(<PlayerRoster players={table} myId="h" canKick={false} onKick={vi.fn()} />)

    // Act
    rerender(<PlayerRoster players={idrisAway} myId="h" canKick={false} onKick={vi.fn()} />)

    // Assert
    const parts = animationsOf(seatOf(container, "b"))
    expect(parts).toHaveLength(3)
    for (const part of parts) expect(part.options).toMatchObject({ duration: 180, easing: "linear" })
  })
})

describe("rooms.css: the receded seat", () => {
  const css = readFileSync(resolve(process.cwd(), "src/styles/pages/rooms.css"), "utf8")

  it("recedes an away seat's name and lozenge by opacity alone, the countdown in the muted token", () => {
    expect(css).toMatch(/\.lobby-roster > li\[data-away\] \[data-erase="ink"\] \{\s*opacity: var\(--erase-ink\);\s*\}/)
    expect(css).toMatch(/\.lobby-roster > li\[data-away\] \[data-erase="mark"\] \{\s*opacity: var\(--erase-mark\);\s*\}/)
    expect(css).not.toMatch(/transition|animation/)
  })
})
