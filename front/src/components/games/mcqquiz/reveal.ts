/**
 * The note at the end of each choice of The Quiz (sketch C, D): "you" once you have
 * locked in; at the reveal, how many locked in each choice, from the server's
 * `choice_tallies` ("1 player", "0"), with yours said as "you" / "you and 2 others", and
 * your points on the right one ("+2 · you"). Pure, so the page only words it.
 */
export type ChoiceNote =
  /** Your choice: `others` more chose it; `points` when it was the right one. */
  | { kind: "you"; others: number; points?: number }
  /** Someone else's choice (or nobody's): how many locked it in. */
  | { kind: "picked"; count: number }
  | null

interface ChoiceNotesInput {
  /** How many choices the question has. */
  count: number
  /** The answer is out (the results phase). */
  revealed: boolean
  /** The server's tallies, one per choice (null while the question is open). */
  tallies: number[] | null | undefined
  /** Your choice: the server's once revealed, your own pick while open; null for none. */
  myIndex: number | null
  /** You have locked in (while open, "you" goes on your pick only then). */
  myAnswered: boolean
  correctIndex: number | null | undefined
  /** Your points this round, when you had it right. */
  myPoints?: number | null
}

export function choiceNotes({ count, revealed, tallies, myIndex, myAnswered, correctIndex, myPoints }: ChoiceNotesInput): ChoiceNote[] {
  return Array.from({ length: count }, (_, index): ChoiceNote => {
    const mine = index === myIndex
    if (!revealed) return myAnswered && mine ? { kind: "you", others: 0 } : null
    // a state without tallies (from before they were sent) can still say which was yours
    if (!tallies) return mine ? { kind: "you", others: 0 } : null
    const picked = tallies[index] ?? 0
    if (!mine) return { kind: "picked", count: picked }
    const others = Math.max(0, picked - 1)
    return index === correctIndex && myPoints != null && myPoints > 0 ? { kind: "you", others, points: myPoints } : { kind: "you", others }
  })
}
