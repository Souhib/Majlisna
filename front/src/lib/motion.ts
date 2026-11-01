/**
 * The Samar motion grammar (scratchpad MOTION_DELIGHT.md §1), as numbers for script.
 *
 * One place, three gestures: things sit on the CIRCLE; knowledge is WRITTEN in the
 * reading direction, what is finished is ERASED, what is earned is SEALED.
 *
 * Frequency sets intensity:
 *   tap 90 ms (press, toggle) · state 180 ms (colour, label) · move 320 ms (arrive,
 *   reorder, sheet) · authored 640 ms (a written word, a revealed card) · ceremony
 *   1.1 s (at most once per game). Exits run 0.66 × the entry on the exit curve.
 * No bounce, no spring overshoot, no loop except the visible clock, no hover lift.
 *
 * The gestures themselves are CSS (index.css and styles/brand.css: `--dur-*`, `--ease-*`,
 * `.ink`, `.seal-press`, `loz-stamp`, the halqa's thread and seats, the thread clock), and
 * reduced motion is the CSS's job alone: its twins switch to short fades. Nothing in the
 * app animates through motion/react, so this file holds no variants (the old `write`,
 * `erase`, `seal`, `stamp`, `seatArrive`, `arrive`, `fade`, `t`, `exit()` and `stagger()`
 * were never used and were removed, WP-18), only what script needs: the same tokens as
 * numbers and the writing time of a word.
 */

/** Cubic-bezier tuples (the CSS `--ease-*` tokens). */
export const ease = {
  /** confident arrivals */
  out: [0.16, 1, 0.3, 1],
  /** exits */
  in: [0.55, 0, 1, 0.45],
  /** the qalam: press, glide, lift */
  ink: [0.45, 0.05, 0.2, 1],
  /** layout landing */
  settle: [0.22, 1, 0.36, 1],
  /** a seal or lozenge stamped */
  press: [0.3, 0.7, 0.2, 1],
} as const

/** Durations in seconds (the CSS `--dur-*` tokens). */
export const dur = { tap: 0.09, state: 0.18, move: 0.32, authored: 0.64, ceremony: 1.1 } as const

const graphemes = typeof Intl !== "undefined" && "Segmenter" in Intl ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null

/** Writing time in seconds: a word (55 ms per grapheme) or a line (15 ms per grapheme). */
export function inkDuration(text: string, kind: "word" | "line" = "word") {
  const n = graphemes ? [...graphemes.segment(text)].length : text.length
  return kind === "word" ? Math.min(0.88, Math.max(0.36, 0.2 + n * 0.055)) : Math.min(0.9, Math.max(0.42, 0.3 + n * 0.015))
}

/** Re-reading a secret already read: always quick, even the tenth glance. */
export const REREAD = 0.24
