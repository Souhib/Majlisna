import { describe, expect, it } from "vitest"
import { choiceNotes } from "./reveal"

const base = { count: 4, myAnswered: true, correctIndex: 2 }

describe("choiceNotes", () => {
  it("says only 'you' on your pick while the question is open, once you have locked in", () => {
    expect(choiceNotes({ ...base, revealed: false, tallies: null, myIndex: 1 })).toEqual([null, { kind: "you", others: 0 }, null, null])
    expect(choiceNotes({ ...base, revealed: false, tallies: null, myIndex: 1, myAnswered: false })).toEqual([null, null, null, null])
  })

  it("counts every choice at the reveal from the server's tallies (sketch C)", () => {
    // Prepare: you chose B (wrong) with one other; three chose C (right); nobody D
    const notes = choiceNotes({ ...base, revealed: true, tallies: [1, 2, 3, 0], myIndex: 1, myPoints: null })

    // Assert
    expect(notes).toEqual([
      { kind: "picked", count: 1 },
      { kind: "you", others: 1 },
      { kind: "picked", count: 3 },
      { kind: "picked", count: 0 },
    ])
  })

  it("puts your points on the right answer when it was yours (sketch D)", () => {
    const notes = choiceNotes({ ...base, revealed: true, tallies: [1, 0, 3, 1], myIndex: 2, myPoints: 3 })
    expect(notes[2]).toEqual({ kind: "you", others: 2, points: 3 })
  })

  it("keeps a spectator or a player who did not answer out of it", () => {
    const notes = choiceNotes({ ...base, revealed: true, tallies: [1, 0, 2, 0], myIndex: null })
    expect(notes.every((n) => n?.kind === "picked")).toBe(true)
  })

  it("falls back to 'you' alone for a state without tallies", () => {
    expect(choiceNotes({ ...base, revealed: true, tallies: null, myIndex: 0 })).toEqual([{ kind: "you", others: 0 }, null, null, null])
  })
})
