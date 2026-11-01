import { describe, expect, it } from "vitest"
import { dur, stagger } from "@/lib/motion"
import { choiceNotes, QUIZ_ROUND_MAX, tallyShares, tallyWeaveMs } from "./reveal"

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

describe("tallyShares (the reveal's tally threads)", () => {
  it("gives each choice its share of the players who are playing", () => {
    // Prepare: four players; one chose A, two chose C, one did not answer
    const shares = tallyShares([1, 0, 2, 0], 4)

    // Assert: measured against the players, not the answers
    expect(shares).toEqual([0.25, 0, 0.5, 0])
  })

  it("never draws a thread past its full length (a leaver's answer may still be counted)", () => {
    // Prepare: three locked in, then one left: two players remain
    const shares = tallyShares([2, 1, 0, 0], 2)

    // Assert: the larger of the two counts is the whole
    expect(shares).toEqual([2 / 3, 1 / 3, 0, 0])
    expect(Math.max(...(shares ?? []))).toBeLessThanOrEqual(1)
  })

  it("draws nothing without the server's tallies (the question still open, an older state)", () => {
    expect(tallyShares(null, 4)).toBeNull()
    expect(tallyShares(undefined, 4)).toBeNull()
  })

  it("draws empty threads for a table where nobody answered", () => {
    expect(tallyShares([0, 0, 0, 0], 0)).toEqual([0, 0, 0, 0])
  })

  it("knows the most one question pays: 1 point and 2 for speed", () => {
    expect(QUIZ_ROUND_MAX).toBe(3)
  })
})

describe("tallyWeaveMs (how long the reveal's authored moment lasts)", () => {
  it("is the last thread's end: 640 ms, --stagger after the one before", () => {
    expect(tallyWeaveMs(4)).toBe(Math.round((dur.authored + 3 * stagger.step) * 1000))
    expect(tallyWeaveMs(4)).toBe(730)
    expect(tallyWeaveMs(1)).toBe(640)
  })

  it("is nothing without a choice", () => {
    expect(tallyWeaveMs(0)).toBe(0)
  })
})
