import { render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { DescriptionList } from "../DescriptionList"
import { UndercoverPlayerList } from "../UndercoverPlayerList"
import { animationsOf, calls, recordAnimations, stopRecordingAnimations, stubReducedMotion } from "./record-animations"

/**
 * ERASE, the grammar's third gesture (ANIM-2, spec 7): a seat that empties ON SCREEN recedes
 * instead of jumping. Its name goes to the muted token's level (opacity .72 of the ink) and its
 * lozenge to .45, over 640 ms on the ink curve; its "Eliminated · Civilian" fades in over
 * 180 ms. Opacity only. The receded state itself is the CSS's (data-out), so a page loaded with
 * the seat already empty shows it receded with nothing moving.
 */

const INK_CURVE = "cubic-bezier(0.45, 0.05, 0.2, 1)"
const OUT_CURVE = "cubic-bezier(0.16, 1, 0.3, 1)"

const seated = [
  { id: "u1", username: "Maryam", is_alive: true },
  { id: "u2", username: "Bilal", is_alive: true },
  { id: "u3", username: "Idris", is_alive: true },
]
const bilalLeft = seated.map((p) => (p.id === "u2" ? { ...p, is_alive: false } : p))
const bilalCivilian = [{ user_id: "u2", role: "civilian" }]

function seat(container: HTMLElement, id: string) {
  return container.querySelector(`[data-seat="${id}"]`)
}

beforeEach(() => {
  recordAnimations()
  stubReducedMotion(false)
})

afterEach(() => {
  stopRecordingAnimations()
})

describe("ERASE in the table list (UndercoverPlayerList)", () => {
  it("erases the seat that empties on screen: name and lozenge recede on the ink curve, the status fades in", () => {
    // Prepare
    const { container, rerender } = render(<UndercoverPlayerList players={seated} currentUserId="u1" />)
    expect(calls).toHaveLength(0)

    // Act
    rerender(<UndercoverPlayerList players={bilalLeft} eliminated={bilalCivilian} currentUserId="u1" />)

    // Assert
    const bilal = seat(container, "u2")
    const [ink] = animationsOf(bilal, "ink")
    expect(ink.keyframes).toEqual([{ opacity: 1 }, { opacity: 0.72 }])
    expect(ink.options).toMatchObject({ duration: 640, easing: INK_CURVE })
    const [mark] = animationsOf(bilal, "mark")
    expect(mark.keyframes).toEqual([{ opacity: 1 }, { opacity: 0.45 }])
    expect(mark.options).toMatchObject({ duration: 640, easing: INK_CURVE })
    const [note] = animationsOf(bilal, "note")
    expect(note.keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(note.options).toMatchObject({ duration: 180, easing: OUT_CURVE })
    // only the emptied seat moves, and only opacity
    expect(calls).toHaveLength(3)
    expect(calls.every((c) => c.keyframes.every((k) => Object.keys(k).every((p) => p === "opacity" || p === "offset")))).toBe(true)
    // truth first: the status and the receded state are there from the first frame
    expect(bilal).toHaveAttribute("data-out")
    expect(within(bilal as HTMLElement).getByText("game.eliminated · games.undercover.roles.civilian")).toBeInTheDocument()
  })

  it("moves nothing on a page load: a seat already empty is simply receded", () => {
    // Prepare / Act
    const { container } = render(<UndercoverPlayerList players={bilalLeft} eliminated={bilalCivilian} currentUserId="u1" />)

    // Assert
    expect(calls).toHaveLength(0)
    expect(seat(container, "u2")).toHaveAttribute("data-out")
    expect(screen.getByText("game.eliminated · games.undercover.roles.civilian")).toBeInTheDocument()
  })

  it("replays nothing when the same state comes again (a refetch, a socket push)", () => {
    // Prepare
    const { rerender } = render(<UndercoverPlayerList players={seated} currentUserId="u1" />)
    rerender(<UndercoverPlayerList players={bilalLeft} eliminated={bilalCivilian} currentUserId="u1" />)
    const played = calls.length

    // Act
    rerender(<UndercoverPlayerList players={bilalLeft.map((p) => ({ ...p }))} eliminated={[...bilalCivilian]} currentUserId="u1" />)

    // Assert
    expect(calls).toHaveLength(played)
  })

  it("under reduced motion, is a 180 ms opacity change", () => {
    // Prepare
    stubReducedMotion(true)
    const { container, rerender } = render(<UndercoverPlayerList players={seated} currentUserId="u1" />)

    // Act
    rerender(<UndercoverPlayerList players={bilalLeft} eliminated={bilalCivilian} currentUserId="u1" />)

    // Assert
    const parts = animationsOf(seat(container, "u2"))
    expect(parts).toHaveLength(3)
    for (const part of parts) expect(part.options).toMatchObject({ duration: 180, easing: "linear" })
  })

  it("keeps your own receded seat's suffix at the ink's level, not the muted one under an opacity (4.5:1)", () => {
    // Prepare / Act
    const { container } = render(<UndercoverPlayerList players={bilalLeft} eliminated={bilalCivilian} currentUserId="u2" />)

    // Assert: the name carries the opacity; a muted colour inside it would fall to ~3.3:1
    const ink = seat(container, "u2")?.querySelector('[data-erase="ink"]') as HTMLElement
    expect(ink).toHaveTextContent("Bilal · game.undercover.youLower")
    expect(ink.querySelector(".text-muted-foreground")).toBeNull()
  })

  it("does nothing where Web Animations are missing (the receded state is the CSS's)", () => {
    // Prepare
    stopRecordingAnimations()
    stubReducedMotion(false)
    const { container, rerender } = render(<UndercoverPlayerList players={seated} currentUserId="u1" />)

    // Act / Assert: no throw, the seat is receded
    rerender(<UndercoverPlayerList players={bilalLeft} eliminated={bilalCivilian} currentUserId="u1" />)
    expect(seat(container, "u2")).toHaveAttribute("data-out")
  })
})

describe("ERASE in the speaking order (DescriptionList)", () => {
  const order = [
    { user_id: "u1", username: "Maryam" },
    { user_id: "u2", username: "Bilal" },
    { user_id: "u3", username: "Idris" },
  ]
  const voting = (players: typeof seated, eliminated: { user_id: string; role: string }[] = []) => (
    <DescriptionList
      order={order}
      descriptions={{ u1: "Patience", u2: "صبر", u3: "Calm" }}
      currentIndex={3}
      currentUserId="u1"
      mode="voting"
      players={players}
      eliminated={eliminated}
      voted={[]}
      choice={{ selected: null, onSelect: vi.fn() }}
    />
  )

  it("a player who leaves mid-round recedes in their own place in the order, instead of jumping to the end", () => {
    // Prepare
    const { container, rerender } = render(voting(seated))
    expect(screen.getAllByRole("button", { name: "game.undercover.voteFor" })).toHaveLength(2)

    // Act
    rerender(voting(bilalLeft, bilalCivilian))

    // Assert: still the second row, receded, no longer a candidate, its role said
    const rows = container.querySelectorAll("ol.uc-descs > li")
    expect(rows[1]).toHaveAttribute("data-seat", "u2")
    expect(rows[1]).toHaveAttribute("data-out")
    expect(rows[1]).toHaveTextContent("Bilal")
    expect(rows[1]).toHaveTextContent("game.eliminated · games.undercover.roles.civilian")
    expect(rows[1].querySelector("button.uc-seat")).toBeNull()
    expect(container.querySelectorAll("button.uc-seat")).toHaveLength(1)
    // and the gesture runs on that seat only
    const bilal = seat(container, "u2")
    expect(animationsOf(bilal, "ink")[0].keyframes).toEqual([{ opacity: 1 }, { opacity: 0.72 }])
    expect(animationsOf(bilal, "mark")[0].keyframes).toEqual([{ opacity: 1 }, { opacity: 0.45 }])
    expect(animationsOf(bilal, "note")[0].keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(calls).toHaveLength(3)
  })

  it("leaves the seat the vote empties to the verdict: a complete vote erases nothing in its list", () => {
    // Prepare: everyone has voted, the last ballot resolves the round
    const all = ["u1", "u2", "u3"]
    const ballot = (players: typeof seated, eliminated: { user_id: string; role: string }[] = []) => (
      <DescriptionList
        order={order}
        descriptions={{}}
        currentIndex={3}
        currentUserId="u1"
        mode="voting"
        players={players}
        eliminated={eliminated}
        voted={all}
      />
    )
    const { container, rerender } = render(ballot(seated))

    // Act: the page draws this list one more frame with the resolved state, then the verdict
    rerender(ballot(bilalLeft, bilalCivilian))

    // Assert: receded as it should be, but nothing animated on a row that is leaving the screen
    expect(seat(container, "u2")).toHaveAttribute("data-out")
    expect(calls).toHaveLength(0)
  })

  it("still erases a player who leaves while the others are voting", () => {
    // Prepare
    const ballot = (players: typeof seated, voted: string[]) => (
      <DescriptionList order={order} descriptions={{}} currentIndex={3} currentUserId="u1" mode="voting" players={players} eliminated={[]} voted={voted} />
    )
    const { container, rerender } = render(ballot(seated, ["u1"]))

    // Act: Bilal leaves; Idris has not voted yet
    rerender(ballot(bilalLeft, ["u1"]))

    // Assert
    expect(animationsOf(seat(container, "u2"))).toHaveLength(3)
  })

  it("keeps the seats emptied in earlier rounds at the end, after the living", () => {
    // Prepare / Act: Dave was voted out last round, so this round's order does not name him
    const { container } = render(
      <DescriptionList
        order={order}
        descriptions={{}}
        currentIndex={0}
        mode="describing"
        players={[{ id: "u4", username: "Dave", is_alive: false }, ...seated]}
        eliminated={[{ user_id: "u4", role: "undercover" }]}
      />,
    )

    // Assert
    const rows = [...container.querySelectorAll("ol.uc-descs > li")].map((li) => li.getAttribute("data-seat"))
    expect(rows).toEqual(["u1", "u2", "u3", "u4"])
    expect(calls).toHaveLength(0)
  })

  it("names every candidate by its button, as the E2E helpers click them", () => {
    // Prepare / Act
    const { container } = render(voting(seated))

    // Assert
    const buttons = [...container.querySelectorAll("button.uc-seat")]
    expect(buttons.map((b) => b.textContent)).toEqual([expect.stringContaining("Bilal"), expect.stringContaining("Idris")])
    expect(calls).toHaveLength(0)
  })
})
