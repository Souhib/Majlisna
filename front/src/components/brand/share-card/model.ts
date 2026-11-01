/**
 * The colophon card's drawing model (DESIGN.md §6, spec 11): a finished game, or the
 * word of the day once it is over, as a list of draw operations on a 1080 × 1350 card.
 * Pure: the text is measured by a function the caller passes (the canvas, or a fake in
 * tests), so every position here is tested without a canvas; `render.ts` applies it.
 *
 * The card is the evening's colophon under the night's light (the samar), whatever the
 * light on screen: the tent-black ground, Qandil's arch as a double brass hairline with
 * its three nodes (ArchFrame's own geometry, without the photograph), the game's Arabic
 * name large in Amiri brass, the Latin name in Marcellus, the colophon's meta line in
 * Readex, a brass rule, then the body:
 *
 * - a game: its words (public once it is over), a grid filled from the reading start,
 *   each word in Amiri with its form in the interface language under it;
 * - the word of the day: NEVER the word, its hints or a guess, only the ladder as a
 *   woven strip (the rung it was found at in brass, the rungs passed struck, the rest
 *   bare warp), how it went ("found at hint 3 · 4 points" or "given up"), the streaks.
 *
 * One madd band closes the arch, as on every colophon; the address sits under it.
 * Colours are the night's tokens only (`CARD_COLORS`), resolved when drawing.
 */

export const CARD_W = 1080
export const CARD_H = 1350

/** A grid of at most 25 cells (a Codenames board); a longer game says how many more. */
export const MAX_CARD_WORDS = 25

export type CardDir = "ltr" | "rtl"

/** The night's colours, as CSS the renderer resolves under `data-theme="dark"`. */
export const CARD_COLORS = {
  bg: "var(--bg)",
  text: "var(--text)",
  "text-muted": "var(--text-muted)",
  brass: "var(--brass)",
  "on-brass": "var(--on-brass)",
  line: "var(--line)",
  "line-brass": "var(--line-brass)",
  "line-brass-strong": "var(--line-brass-strong)",
  warp: "var(--warp)",
  /** the arch's inner hairline (styles/brand.css `.arch-head .in`) */
  "brass-70": "color-mix(in oklch, var(--brass) 70%, transparent)",
  /** the ladder's rung in play (styles/pages/quiz.css) */
  "brass-tint": "color-mix(in oklch, var(--brass) 9%, transparent)",
} as const

export type CardColor = keyof typeof CARD_COLORS

/** The type roles (DESIGN.md §3): nass = Amiri, display = Marcellus, ui = Readex. */
export type CardFace = "nass" | "display" | "ui"

export interface CardFont {
  face: CardFace
  weight: number
  size: number
}

/** The width of a run of text in a font, in card pixels. */
export type Measure = (text: string, font: CardFont, dir: CardDir) => number

export type TextRole = "name" | "latin" | "meta" | "word" | "word-form" | "more" | "rung-worth" | "result" | "streak" | "streak-label" | "footer"

export interface TextOp {
  kind: "text"
  text: string
  /** The centre of the line (every line of the card is centred). */
  x: number
  /** The baseline. */
  y: number
  font: CardFont
  color: CardColor
  dir: CardDir
  align: "center"
  /** The line never runs wider: the canvas squeezes it past this (`fillText`'s 4th argument). */
  maxWidth: number
  role: TextRole
  /** A line through the figure (a rung passed). */
  strike?: boolean
}

export type PathSeg = ["M", number, number] | ["L", number, number] | ["C", number, number, number, number, number, number] | ["Z"]

export interface PathOp {
  kind: "path"
  d: PathSeg[]
  color: CardColor
  width: number
}

export interface LozengeOp {
  kind: "lozenge"
  x: number
  y: number
  /** Half the diagonal: the square turned on its point reaches r from its centre. */
  r: number
  fill?: CardColor
  stroke?: CardColor
  width?: number
  role: "node" | "rule" | "rung"
}

export interface LineOp {
  kind: "line"
  x1: number
  y1: number
  x2: number
  y2: number
  color: CardColor
  width: number
}

export interface RectOp {
  kind: "rect"
  x: number
  y: number
  w: number
  h: number
  fill?: CardColor
  stroke?: CardColor
  width?: number
}

/** Bare warp: 1.5 px threads `step` apart (the `warp-threads` utility, at the card's scale). */
export interface WarpOp {
  kind: "warp"
  x: number
  y: number
  w: number
  h: number
  step: number
  color: CardColor
}

/** The madd band, its tile repeated from the reading start inside its box. */
export interface BandOp {
  kind: "band"
  x: number
  y: number
  w: number
  h: number
  from: "left" | "right"
}

export interface FillOp {
  kind: "fill"
  color: CardColor
}

export type DrawOp = FillOp | PathOp | LozengeOp | LineOp | RectOp | WarpOp | BandOp | TextOp

/** A word on the card: its Arabic (vocalised when known) and its form in the interface language. */
export interface CardWord {
  arabic?: string
  display?: string
}

interface CardHead {
  /** The interface's direction: the reading start of the grid, the strip and the band. */
  dir: CardDir
  /** The large Arabic name (the games list's form, one kashida), always shown. */
  arabicName: string
  /** The name in the interface language; none in the Arabic interface. */
  latinName?: string
  /** The colophon's meta line, as parts ("Undercover", "Yusuf’s majlis", "3 rounds", "21:40"). */
  meta: string[]
  /** The address, under the arch. */
  footer: string
}

export interface GameCardInput extends CardHead {
  kind: "game"
  words: CardWord[]
  /** The last cell of a game with more words than fit ("and 6 more words"). */
  more?: string
}

export interface DailyCardInput extends CardHead {
  kind: "daily"
  /** The ladder: its length, the rungs opened, and the rung the word was found at (null: given up). */
  rungs: { total: number; revealed: number; found: number | null }
  /** "found at hint 3 · 4 points", or "given up". */
  result: string
  /** The two streaks, as on the reveal ("Your streak" 2, "Best streak" 5). */
  streak?: { label: string; value: number }[]
}

export type CardInput = GameCardInput | DailyCardInput

// --- the arch: ArchFrame's path (viewBox units, 520 wide) at the card's scale ---------

const ARCH_LEFT = 120
const ARCH_WIDTH = 840
const ARCH_APEX = 104
/** The inner hairline's foot (the outer one is 11 units further out, as in ArchFrame). */
const ARCH_BASE = 1188
const K = ARCH_WIDTH / 520
const ux = (u: number) => ARCH_LEFT + u * K
const uy = (v: number) => ARCH_APEX + v * K
const OUT = 11 * K
const SPRINGERS = uy(250)

const INNER_ARCH: PathSeg[] = [
  ["M", ux(0), ARCH_BASE],
  ["L", ux(0), uy(250)],
  ["C", ux(0), uy(130), ux(120), uy(55), ux(260), uy(0)],
  ["C", ux(400), uy(55), ux(520), uy(130), ux(520), uy(250)],
  ["L", ux(520), ARCH_BASE],
  ["Z"],
]

const OUTER_ARCH: PathSeg[] = [
  ["M", ux(-11), ARCH_BASE + OUT],
  ["L", ux(-11), uy(250)],
  ["C", ux(-11), uy(122), ux(114), uy(42), ux(260), uy(-12)],
  ["C", ux(406), uy(42), ux(531), uy(122), ux(531), uy(250)],
  ["L", ux(531), ARCH_BASE + OUT],
  ["Z"],
]

const MID = CARD_W / 2
/** How far under its baseline an Amiri word reaches (the tails of م ي ل ج ر), in ems. */
const AMIRI_DESCENT = 0.5
/** The text column inside the arch, below its head. */
const COLUMN = 760
const BAND_H = 22

// --- type --------------------------------------------------------------------------

const RTL_STRONG = /[֐-ࣿיִ-﷿ﹰ-﻿]/
const LTR_STRONG = /[A-Za-zÀ-ɏḀ-ỿ]/

/** A run's direction from its first strong letter (as `dir="auto"`), else the interface's. */
export function textDir(text: string, fallback: CardDir): CardDir {
  for (const ch of text) {
    if (RTL_STRONG.test(ch)) return "rtl"
    if (LTR_STRONG.test(ch)) return "ltr"
  }
  return fallback
}

/** The largest size from `size` down to `min` at which the text fits `maxWidth`. */
function fitSize(text: string, font: CardFont, min: number, maxWidth: number, dir: CardDir, measure: Measure): number {
  let size = font.size
  while (size > min && measure(text, { ...font, size }, dir) > maxWidth) size = Math.max(min, Math.floor(size * 0.94))
  return size
}

function line(
  text: string,
  x: number,
  y: number,
  font: CardFont,
  color: CardColor,
  dir: CardDir,
  maxWidth: number,
  role: TextRole,
  measure: Measure,
  min = font.size,
): TextOp {
  const size = fitSize(text, font, min, maxWidth, dir, measure)
  return { kind: "text", text, x, y, font: { ...font, size }, color, dir, align: "center", maxWidth, role }
}

/** The meta parts on one line, or two split at a separator, at the largest size that fits. */
function metaLines(parts: string[], dir: CardDir, measure: Measure): { lines: string[]; size: number } {
  const SEP = " · "
  for (let size = 32; size >= 24; size -= 2) {
    const font: CardFont = { face: "ui", weight: 300, size }
    const lines: string[] = []
    for (const part of parts) {
      const last = lines.at(-1)
      if (last != null && measure(last + SEP + part, font, dir) <= COLUMN) lines[lines.length - 1] = last + SEP + part
      else lines.push(part)
    }
    if (lines.length <= 2 && lines.every((l) => measure(l, font, dir) <= COLUMN)) return { lines, size }
  }
  // past the floor: two lines, halved at a separator, squeezed by maxWidth if need be
  const half = Math.ceil(parts.length / 2)
  return { lines: parts.length > 1 ? [parts.slice(0, half).join(SEP), parts.slice(half).join(SEP)] : parts, size: 24 }
}

// --- the frame -----------------------------------------------------------------------

/** Where the head starts (the Arabic name's baseline) when a body follows it. */
const NAME_BASELINE = 372

function frame(input: CardInput, measure: Measure, nameBaseline = NAME_BASELINE): { ops: DrawOp[]; bodyTop: number; ruleY: number } {
  const ops: DrawOp[] = [
    { kind: "fill", color: "bg" },
    { kind: "path", d: INNER_ARCH, color: "brass-70", width: 2 },
    { kind: "path", d: OUTER_ARCH, color: "line-brass-strong", width: 2 },
    { kind: "lozenge", x: ux(-11), y: SPRINGERS, r: 11, fill: "brass", role: "node" },
    { kind: "lozenge", x: ux(531), y: SPRINGERS, r: 11, fill: "brass", role: "node" },
    { kind: "lozenge", x: MID, y: uy(-12), r: 11, fill: "brass", role: "node" },
  ]

  // the head: the Arabic name where the arch is wide enough for it, then the Latin.
  // Amiri's tails (م ي ل ج) fall about half an em under the baseline: the next line
  // starts below them (AMIRI_DESCENT), never between them.
  let y = nameBaseline
  ops.push(line(input.arabicName, MID, y, { face: "nass", weight: 700, size: 132 }, "brass", "rtl", 600, "name", measure, 72))
  if (input.latinName) {
    y += Math.round(132 * AMIRI_DESCENT) + 62
    ops.push(line(input.latinName, MID, y, { face: "display", weight: 400, size: 54 }, "text", textDir(input.latinName, input.dir), 680, "latin", measure, 34))
  }

  const meta = metaLines(input.meta, input.dir, measure)
  y += input.latinName ? 66 : Math.round(132 * AMIRI_DESCENT) + 46
  for (const text of meta.lines) {
    ops.push({
      kind: "text",
      text,
      x: MID,
      y,
      font: { face: "ui", weight: 300, size: meta.size },
      color: "text-muted",
      dir: input.dir,
      align: "center",
      maxWidth: COLUMN,
      role: "meta",
    })
    y += Math.round(meta.size * 1.45)
  }

  // the brass rule: a hairline broken by its lozenge (the `rule-brass` utility)
  const ruleY = y + 6
  ops.push(
    { kind: "line", x1: MID - 210, y1: ruleY, x2: MID - 22, y2: ruleY, color: "line-brass", width: 2 },
    { kind: "line", x1: MID + 22, y1: ruleY, x2: MID + 210, y2: ruleY, color: "line-brass", width: 2 },
    { kind: "lozenge", x: MID, y: ruleY, r: 8, fill: "brass", role: "rule" },
  )

  // the foot: one madd band closing the arch, the address under it
  ops.push(
    { kind: "band", x: ux(0), y: ARCH_BASE - BAND_H, w: ARCH_WIDTH, h: BAND_H, from: input.dir === "rtl" ? "right" : "left" },
    line(input.footer, MID, 1290, { face: "ui", weight: 400, size: 30 }, "text-muted", "ltr", 600, "footer", measure, 22),
  )
  return { ops, bodyTop: ruleY + 44, ruleY }
}

/** Where the body ends: above the band, with the same air as the arch's sides. */
const BODY_BOTTOM = ARCH_BASE - BAND_H - 44

// --- a game: its words ---------------------------------------------------------------

function columnsFor(n: number): number {
  if (n <= 2) return Math.max(1, n)
  if (n <= 4) return 2
  if (n <= 9) return 3
  if (n <= 16) return 4
  return 5
}

/** Amiri's size for a word, by the grid's number of columns. */
const WORD_SIZE: Record<number, number> = { 1: 112, 2: 100, 3: 74, 4: 58, 5: 46 }

function gameBody(input: GameCardInput, top: number, measure: Measure): DrawOp[] {
  const words = input.words.slice(0, input.more ? MAX_CARD_WORDS - 1 : MAX_CARD_WORDS)
  const cells: (CardWord | { more: string })[] = input.more ? [...words, { more: input.more }] : words
  if (cells.length === 0) return []

  const cols = columnsFor(cells.length)
  const rows = Math.ceil(cells.length / cols)
  const width = COLUMN - 20
  const cellW = width / cols
  const cellH = Math.min((BODY_BOTTOM - top) / rows, 230)
  const blockTop = top + (BODY_BOTTOM - top - cellH * rows) / 2
  const hasForm = cells.some((c) => "arabic" in c && c.arabic && c.display)
  const base = Math.min(WORD_SIZE[cols], cellH * (hasForm ? 0.5 : 0.62))
  const formSize = Math.max(18, Math.round(base * 0.34))
  const ops: DrawOp[] = []

  cells.forEach((cell, i) => {
    const row = Math.floor(i / cols)
    const inRow = row === rows - 1 ? cells.length - row * cols : cols
    const col = i % cols
    // a short last row is centred; the grid reads from the interface's start
    const offset = ((cols - inRow) * cellW) / 2
    const fromStart = offset + col * cellW + cellW / 2
    const x = input.dir === "rtl" ? MID + width / 2 - fromStart : MID - width / 2 + fromStart
    const cy = blockTop + row * cellH + cellH / 2
    const fit = cellW - 22

    if ("more" in cell) {
      ops.push(line(cell.more, x, cy + 8, { face: "ui", weight: 400, size: Math.max(20, formSize + 2) }, "text-muted", input.dir, fit, "more", measure, 16))
      return
    }
    if (cell.arabic) {
      const form = cell.display
      // the word and its form as one group centred in the cell, the form clear of Amiri's tails
      const wordY = form ? cy - (base * AMIRI_DESCENT + formSize) / 2 + base * 0.3 : cy + base * 0.3
      ops.push(line(cell.arabic, x, wordY, { face: "nass", weight: 700, size: base }, "text", "rtl", fit, "word", measure, Math.min(base, 26)))
      if (form)
        ops.push(
          line(
            form,
            x,
            wordY + base * AMIRI_DESCENT + formSize,
            { face: "ui", weight: 300, size: formSize },
            "text-muted",
            textDir(form, input.dir),
            fit,
            "word-form",
            measure,
            14,
          ),
        )
      return
    }
    if (cell.display) {
      const size = Math.round(base * 0.62)
      ops.push(line(cell.display, x, cy + size * 0.32, { face: "ui", weight: 400, size }, "text", textDir(cell.display, input.dir), fit, "word", measure, 16))
    }
  })

  // hairlines between the rows, as the colophon's word rows have
  for (let r = 1; r < rows; r++) {
    const y = blockTop + r * cellH
    ops.push({ kind: "line", x1: MID - width / 2, y1: y, x2: MID + width / 2, y2: y, color: "line", width: 1.5 })
  }
  return ops
}

// --- the word of the day: the ladder as a strip ---------------------------------------

const RUNG = 108

function dailyBody(input: DailyCardInput, top: number, measure: Measure): DrawOp[] {
  const { total, revealed, found } = input.rungs
  const stripW = RUNG * total
  const x0 = MID - stripW / 2
  // the strip, the result and the streaks as one block, centred in the body
  const blockH = RUNG + 82 + (input.streak?.length ? 128 + 46 : 0)
  const y0 = top + Math.max(18, (BODY_BOTTOM - top - blockH) / 2)
  const ops: DrawOp[] = []

  for (let i = 0; i < total; i++) {
    const number = i + 1
    const worth = total - i
    const slot = input.dir === "rtl" ? total - 1 - i : i
    const x = x0 + slot * RUNG
    const cx = x + RUNG / 2
    const cy = y0 + RUNG / 2
    const isFound = found === number
    const passed = !isFound && number <= revealed
    if (isFound) ops.push({ kind: "rect", x, y: y0, w: RUNG, h: RUNG, fill: "brass-tint" })
    else if (!passed) ops.push({ kind: "warp", x: x + 1, y: y0 + 1, w: RUNG - 2, h: RUNG - 2, step: 9, color: "warp" })
    ops.push(
      isFound
        ? { kind: "lozenge", x: cx, y: cy, r: 30, fill: "brass", role: "rung" }
        : { kind: "lozenge", x: cx, y: cy, r: 30, stroke: passed ? "line-brass" : "line", width: 2, role: "rung" },
    )
    const figure = line(
      String(worth),
      cx,
      cy + 10,
      { face: "ui", weight: isFound ? 600 : 500, size: 28 },
      isFound ? "on-brass" : "text-muted",
      "ltr",
      40,
      "rung-worth",
      measure,
    )
    ops.push(passed ? { ...figure, strike: true } : figure)
  }
  // the strip's selvedge and the hairlines between its rungs; the found rung's frame on top
  ops.push({ kind: "rect", x: x0, y: y0, w: stripW, h: RUNG, stroke: "line", width: 2 })
  for (let i = 1; i < total; i++) ops.push({ kind: "line", x1: x0 + i * RUNG, y1: y0, x2: x0 + i * RUNG, y2: y0 + RUNG, color: "line", width: 2 })
  if (found != null && found >= 1 && found <= total) {
    const slot = input.dir === "rtl" ? total - found : found - 1
    ops.push({ kind: "rect", x: x0 + slot * RUNG, y: y0, w: RUNG, h: RUNG, stroke: "line-brass-strong", width: 2 })
  }

  let y = y0 + RUNG + 82
  ops.push(line(input.result, MID, y, { face: "ui", weight: 400, size: 40 }, found != null ? "text" : "text-muted", input.dir, COLUMN, "result", measure, 26))

  if (input.streak?.length) {
    y += 128
    const n = input.streak.length
    input.streak.forEach((s, i) => {
      const slot = input.dir === "rtl" ? n - 1 - i : i
      const x = MID + (slot - (n - 1) / 2) * 300
      ops.push(line(String(s.value), x, y, { face: "ui", weight: 260, size: 84 }, "text", "ltr", 280, "streak", measure))
      ops.push(line(s.label, x, y + 46, { face: "ui", weight: 400, size: 26 }, "text-muted", input.dir, 280, "streak-label", measure, 18))
    })
  }
  return ops
}

/** The card as draw operations, in painting order. */
export function layoutCard(input: CardInput, measure: Measure): DrawOp[] {
  if (input.kind === "game" && input.words.length === 0 && !input.more) {
    // nothing under the rule (the Quiz has no words): the head is set in the middle of the
    // arch, from the top of the name (about an em over its baseline) to its rule
    const { ruleY } = frame(input, measure)
    const top = NAME_BASELINE - 132
    const middle = (uy(0) + BODY_BOTTOM) / 2
    return frame(input, measure, NAME_BASELINE + Math.max(0, middle - (top + ruleY) / 2)).ops
  }
  const { ops, bodyTop } = frame(input, measure)
  const body = input.kind === "daily" ? dailyBody(input, bodyTop, measure) : gameBody(input, bodyTop, measure)
  return [...ops, ...body]
}
