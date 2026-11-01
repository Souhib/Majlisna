import { dur, stagger } from "@/lib/motion"

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

/**
 * The most one question of The Quiz pays: 1 point, and up to 2 more for speed (the
 * server's rule, ScoreBands' +3). Times the rounds, it is what the scoreboard's threads are
 * measured against, so a thread only ever grows.
 */
export const QUIZ_ROUND_MAX = 3

/**
 * Each choice's share of the table at the reveal (0–1), for its tally thread: how many
 * locked it in over how many play. Measured against the players, not the answers, so a
 * choice two of eight picked is a quarter thread even when only two answered; the larger
 * of the two counts is the whole, so no thread runs past its length (a leaver's answer may
 * still be counted). Null without the server's tallies: the question is still open, or the
 * state is from before they were sent.
 */
export function tallyShares(tallies: number[] | null | undefined, players: number): number[] | null {
  if (!tallies) return null
  const whole = Math.max(
    players,
    tallies.reduce((sum, count) => sum + Math.max(0, count), 0),
  )
  return tallies.map((count) => (whole > 0 ? Math.max(0, count) / whole : 0))
}

/**
 * How long the reveal's tally threads take, in ms: the last one's end (640 ms, `--stagger`
 * after the one before; quiz.css `quiz-tally`). The reveal's one authored moment: The Quiz's
 * scoreboard waits for it before it weaves (`PlayerScoreboard` `weaveAfter`), so the two
 * weaves never run at once (DESIGN.md §7, one authored moment per screen).
 */
export function tallyWeaveMs(choices: number): number {
  if (choices <= 0) return 0
  return Math.round((dur.authored + (choices - 1) * stagger.step) * 1000)
}
