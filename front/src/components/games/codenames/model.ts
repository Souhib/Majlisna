/**
 * Codenames, read the Samar way: pure helpers shared by the board, the header, the
 * clue banner and the colophon. No React here, so every rule is unit-tested.
 *
 * The teams are Red and Blue, as the server names them; on screen they are dyed wool:
 * red is madder (the tooth ▲, the ḍurūs selvedge), blue is indigo (the eye ◆, the
 * ʿayn selvedge). A team is never shown by colour alone.
 */
import type { Team } from "@/components/brand"

export type TeamId = "red" | "blue"
export type CardType = "red" | "blue" | "neutral" | "assassin"

export interface CodenamesCard {
  word: string
  word_ar?: string | null
  word_ar_vocalized?: string | null
  card_type: CardType | null
  revealed: boolean
  hint?: string | null
}

export interface CodenamesTurn {
  team: TeamId
  clue_word: string | null
  clue_number: number
  guesses_made: number
  max_guesses: number | null
  card_votes?: Record<string, number>
}

export interface CodenamesPlayer {
  user_id: string
  username: string
  team: string
  role: string
}

export interface ClueGuess {
  word: string
  word_ar?: string | null
  word_ar_vocalized?: string | null
  card_type: string
  correct: boolean
}

export interface ClueHistoryEntry {
  team: TeamId
  clue_word: string
  clue_number: number
  guesses: ClueGuess[]
}

/** Server team id → its wool. */
export function teamWool(team: TeamId): "madder" | "indigo" {
  return team === "red" ? "madder" : "indigo"
}

/** The other team. */
export function otherTeam(team: TeamId): TeamId {
  return team === "red" ? "blue" : "red"
}

/** A card's type → the TeamGlyph it carries (null while it is still hidden). */
export function cardGlyph(cardType: string | null | undefined): Team | null {
  switch (cardType) {
    case "red":
      return "madder"
    case "blue":
      return "indigo"
    case "neutral":
      return "bystander"
    case "assassin":
      return "assassin"
    default:
      return null
  }
}

/** The Arabic form to show: the vocalised one when the server has it. */
export function arabicForm(card: { word_ar?: string | null; word_ar_vocalized?: string | null }): string | null {
  return card.word_ar_vocalized?.trim() || card.word_ar?.trim() || null
}

/** True when the text is written (at least partly) in Arabic script. */
export function isArabicScript(text: string): boolean {
  return /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/.test(text)
}

/**
 * The longest run of characters a line cannot break inside: the card scales its Latin
 * word to fit this many characters on its width ("Alhamdulillah" → 13,
 * "Umar ibn Abdul Aziz" → 5).
 */
export function longestSegment(text: string): number {
  // harakat and other combining marks take no width of their own
  const letters = text.replace(/\p{M}/gu, "")
  return Math.max(1, ...letters.split(/[\s-]+/u).map((part) => Array.from(part).length))
}

const VOWELS = /[aeiouAEIOUāīūĀĪŪ]/u
const DIGRAPHS = new Set(["sh", "kh", "th", "dh", "gh", "ch", "ph", "zh"])

/** Advance widths of Readex Pro 600 in em (measured in the browser); 0.62 for the rest. */
const READEX_600_EM: Record<string, number> = {
  a: 0.56, b: 0.65, c: 0.54, d: 0.65, e: 0.59, f: 0.39, g: 0.66, h: 0.62, i: 0.31, j: 0.3, k: 0.61, l: 0.29, m: 0.95,
  n: 0.62, o: 0.63, p: 0.65, q: 0.65, r: 0.44, s: 0.49, t: 0.39, u: 0.63, v: 0.6, w: 0.82, x: 0.59, y: 0.61, z: 0.53,
  A: 0.7, B: 0.69, C: 0.69, D: 0.76, E: 0.63, F: 0.61, G: 0.78, H: 0.77, I: 0.53, J: 0.66, K: 0.74, L: 0.61, M: 0.87,
  N: 0.8, O: 0.8, P: 0.65, Q: 0.8, R: 0.7, S: 0.63, T: 0.63, U: 0.76, V: 0.72, W: 1, X: 0.7, Y: 0.68, Z: 0.68,
  "'": 0.24, "’": 0.26, "-": 0.43, " ": 0.25,
}

/** The width of a Latin text in Readex Pro 600, in em. */
export function latinEm(text: string): number {
  let w = 0
  for (const ch of text) w += READEX_600_EM[ch] ?? 0.62
  return Math.round(w * 100) / 100
}

/** Pieces of a word a line may end after: an existing hyphen stays on the left piece. */
function lineEm(part: string): number {
  return Math.max(...part.split(/(?<=-)/u).map(latinEm))
}

/**
 * A Latin card word, ready for its card. `em` is the width of its longest unbreakable
 * piece (the card sizes the word to fit it). Very long words (10+ letters) get ONE soft
 * hyphen at their most even natural break (a camel-case join, "Subhan|Allah", or two
 * consonants that are not a digraph, "Huday|biyyah"), and `em` is sized for that
 * two-line form. On a wide card the word still sits on one line (the hyphen only shows
 * when the line breaks there); on a phone it breaks at a syllable, never at an
 * arbitrary letter. The browser's own hyphenation cannot be relied on: it has no
 * dictionary for transliterations, and none at all on some systems.
 */
export function fitLatin(word: string): { text: string; em: number } {
  let em = 0.6
  const parts = word.split(" ").map((part) => {
    const letters = Array.from(part)
    const whole = lineEm(part)
    if (letters.length < 10) {
      em = Math.max(em, whole)
      return part
    }
    let best = -1
    let bestEm = whole
    for (let i = 3; i <= letters.length - 3; i++) {
      const a = letters[i - 1]
      const b = letters[i]
      const camel = /\p{Lu}/u.test(b) && /[\p{Ll}'’]/u.test(a)
      const consonants =
        /\p{L}/u.test(a) && /\p{L}/u.test(b) && !VOWELS.test(a) && !VOWELS.test(b) && !DIGRAPHS.has((a + b).toLowerCase())
      if (!camel && !consonants) continue
      const longer = Math.max(latinEm(`${letters.slice(0, i).join("")}-`), latinEm(letters.slice(i).join("")))
      if (longer < bestEm) {
        bestEm = longer
        best = i
      }
    }
    if (best < 0) {
      em = Math.max(em, whole)
      return part
    }
    em = Math.max(em, bestEm)
    return `${letters.slice(0, best).join("")}\u00AD${letters.slice(best).join("")}`
  })
  return { text: parts.join(" "), em: Math.round(em * 100) / 100 }
}

/**
 * The face a card shows.
 *   wool  turned over: dyed in its team's wool, woven selvedge, glyph
 *   key   still face down, but this viewer may know its team (the spymaster's key, or
 *         the end-of-game board for cards nobody turned): glyph + selvedge on the bare card
 *   bare  face down: bare card, bare warp at the edge
 */
export type CardFace = "wool" | "key" | "bare"

export function cardFace(
  card: Pick<CodenamesCard, "revealed" | "card_type">,
  opts: { isSpymaster: boolean; isFinished: boolean; played?: boolean },
): CardFace {
  // At the end the server marks every card revealed; the ones nobody turned read
  // as the key, so the table can see what was left on the board.
  if (card.revealed && !(opts.isFinished && opts.played === false)) return "wool"
  if ((opts.isSpymaster || opts.isFinished) && cardGlyph(card.card_type)) return "key"
  return "bare"
}

/** Words turned over during play, in the order they were turned. */
export function playedWords(history: ClueHistoryEntry[] | null | undefined): string[] {
  if (!history) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const entry of history) {
    for (const guess of entry.guesses) {
      if (!seen.has(guess.word)) {
        seen.add(guess.word)
        out.push(guess.word)
      }
    }
  }
  return out
}

/**
 * Where the current clue stands. A clue for N allows N + 1 guesses (the bonus); a clue
 * for 0 is "no limit" (the server allows the whole board).
 */
export interface GuessStatus {
  made: number
  /** Guesses left before the bonus (0 when only the bonus remains). */
  left: number
  /** The bonus guess is still available. */
  bonus: boolean
  unlimited: boolean
}

export function guessStatus(turn: Pick<CodenamesTurn, "clue_number" | "guesses_made">): GuessStatus {
  const made = Math.max(0, turn.guesses_made)
  if (turn.clue_number <= 0) return { made, left: 0, bonus: false, unlimited: true }
  const left = Math.max(0, turn.clue_number - made)
  return { made, left, bonus: made <= turn.clue_number, unlimited: false }
}

/** How a finished game was decided. */
export type EndReason = "all-found" | "assassin" | "forfeit"

export function endReason(
  winner: TeamId,
  remaining: { red: number; blue: number },
  history: ClueHistoryEntry[] | null | undefined,
): EndReason {
  if (remaining[winner] === 0) return "all-found"
  const loser = otherTeam(winner)
  const hitAssassin = (history ?? []).some(
    (entry) => entry.team === loser && entry.guesses.some((g) => g.card_type === "assassin"),
  )
  return hitAssassin ? "assassin" : "forfeit"
}

/** Who pointed at which card: card index → the players (user ids) pointing at it. */
export function votersByCard(cardVotes: Record<string, number> | null | undefined): Map<number, string[]> {
  const out = new Map<number, string[]>()
  if (!cardVotes) return out
  for (const [userId, index] of Object.entries(cardVotes)) {
    if (typeof index !== "number") continue
    const list = out.get(index)
    if (list) list.push(userId)
    else out.set(index, [userId])
  }
  return out
}

/** The spymaster of a team, if still at the table. */
export function spymasterOf(players: CodenamesPlayer[], team: TeamId): CodenamesPlayer | undefined {
  return players.find((p) => p.team === team && p.role === "spymaster")
}
