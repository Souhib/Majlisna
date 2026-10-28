/**
 * The Samar motion grammar (scratchpad MOTION_DELIGHT.md §1), for motion/react.
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
 * Reduced motion: <MotionConfig reducedMotion="user"> (routes/__root.tsx) drops
 * transforms and layout animation and keeps opacity and colour, which is exactly the
 * grammar's reduced form ("less travel, not less information"). The CSS twins of these
 * tokens live in index.css (--dur-*, --ease-*, .ink, .seal-press).
 */
import type { Transition, Variants } from "motion/react"

/** Cubic-bezier tuples. `as const` keeps them readonly tuples, which motion accepts. */
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

/** Durations in seconds. */
export const dur = { tap: 0.09, state: 0.18, move: 0.32, authored: 0.64, ceremony: 1.1 } as const

/** Ready-made transitions. */
export const t = {
  tap: { duration: dur.tap, ease: ease.out },
  state: { duration: dur.state, ease: ease.out },
  move: { duration: dur.move, ease: ease.settle },
  authored: { duration: dur.authored, ease: ease.ink },
  ceremony: { duration: dur.ceremony, ease: ease.out },
} satisfies Record<string, Transition>

/** An exit transition: 0.66 × the entry, on the exit curve. */
export const exit = (d: number = dur.state): Transition => ({ duration: d * 0.66, ease: ease.in })

/** Delay for item `i` of a list: 30 ms steps, capped at 240 ms in total. */
export const stagger = (i: number, step = 0.03, cap = 0.24) => Math.min(i * step, cap)

const graphemes =
  typeof Intl !== "undefined" && "Segmenter" in Intl ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null

/** Writing time in seconds: a word (55 ms per grapheme) or a line (15 ms per grapheme). */
export function inkDuration(text: string, kind: "word" | "line" = "word") {
  const n = graphemes ? [...graphemes.segment(text)].length : text.length
  return kind === "word"
    ? Math.min(0.88, Math.max(0.36, 0.2 + n * 0.055))
    : Math.min(0.9, Math.max(0.42, 0.3 + n * 0.015))
}

/** Re-reading a secret already read: always quick, even the tenth glance. */
export const REREAD = 0.24

/* ---------------------------------------------------------------------------
   Variants. Every one starts from a VISIBLE default where it matters (truth
   first, gesture second): use them with `initial="hidden" animate="shown"`.
   --------------------------------------------------------------------------- */

/**
 * WRITE: text inked in the reading direction with a mask sweep. Pass the direction
 * as `custom` ("ltr" | "rtl"). For pure CSS use the `ink` utility instead.
 */
export const write: Variants = {
  hidden: (dir: "ltr" | "rtl" = "ltr") => ({
    WebkitMaskImage: `linear-gradient(${dir === "rtl" ? "to left" : "to right"}, #000 -15%, transparent 0%)`,
    maskImage: `linear-gradient(${dir === "rtl" ? "to left" : "to right"}, #000 -15%, transparent 0%)`,
  }),
  shown: (dir: "ltr" | "rtl" = "ltr") => ({
    WebkitMaskImage: `linear-gradient(${dir === "rtl" ? "to left" : "to right"}, #000 100%, transparent 115%)`,
    maskImage: `linear-gradient(${dir === "rtl" ? "to left" : "to right"}, #000 100%, transparent 115%)`,
    transition: t.authored,
  }),
}

/** ERASE: what is finished recedes to secondary ink, never vanishes. Never over a sacred name. */
export const erase: Variants = {
  shown: { opacity: 1 },
  erased: { opacity: 0.45, transition: t.authored },
}

/** SEAL: pressed once (330 ms: 1.5 → 0.94 → 1), then still. */
export const seal: Variants = {
  hidden: { scale: 1.5, opacity: 0 },
  shown: { scale: [1.5, 0.94, 1], opacity: [0, 1, 1], transition: { duration: 0.33, ease: ease.press, times: [0, 0.6, 1] } },
}

/** A clock lozenge stamped for each of the last five seconds (220 ms: 1.6 → 0.92 → 1). */
export const stamp: Variants = {
  hidden: { scale: 1.6, opacity: 0 },
  shown: { scale: [1.6, 0.92, 1], opacity: [0, 1, 1], transition: { duration: 0.22, ease: ease.press, times: [0, 0.6, 1] } },
}

/** CIRCLE: a seat arriving on the halqa (ink filling in, 460 ms). */
export const seatArrive: Variants = {
  hidden: { scale: 0.25, opacity: 0 },
  shown: { scale: 1, opacity: 1, transition: { duration: 0.46, ease: ease.out } },
  gone: { scale: 0.25, opacity: 0, transition: { duration: 0.2, ease: ease.in } },
}

/** A plain arrival for panels and sheets: opacity plus a short rise, no overshoot. */
export const arrive: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: t.move },
  gone: { opacity: 0, y: 4, transition: exit(dur.move) },
}

/** Opacity only: what reduced motion keeps, and what most state changes need. */
export const fade: Variants = {
  hidden: { opacity: 0 },
  shown: { opacity: 1, transition: t.state },
  gone: { opacity: 0, transition: exit() },
}
