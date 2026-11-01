import { describe, expect, it } from "vitest"
import {
  CARD_COLORS,
  CARD_H,
  CARD_W,
  type CardDir,
  type CardFont,
  type DailyCardInput,
  type DrawOp,
  type GameCardInput,
  layoutCard,
  type LozengeOp,
  type Measure,
  MAX_CARD_WORDS,
  type TextOp,
  textDir,
} from "../model"

/**
 * The colophon card's drawing model (spec 11): the game or the day as a list of draw
 * operations, pure and measured by an injected function. happy-dom has no canvas, so
 * the model is what is tested here; the canvas renderer only applies it.
 */

/** Half an em per grapheme: close enough to Readex and Amiri for layout tests. */
const measure: Measure = (text: string, font: CardFont) => [...text].length * font.size * 0.5

const texts = (ops: DrawOp[]) => ops.filter((op): op is TextOp => op.kind === "text")
const textOf = (ops: DrawOp[], text: string) => texts(ops).find((op) => op.text === text)
const lozenges = (ops: DrawOp[]) => ops.filter((op): op is LozengeOp => op.kind === "lozenge")

const game = (over: Partial<GameCardInput> = {}): GameCardInput => ({
  kind: "game",
  dir: "ltr",
  arabicName: "أندركفـــر",
  latinName: "Undercover",
  meta: ["Undercover", "Yusuf’s majlis", "3 rounds", "21:40"],
  footer: "majlisna.app",
  words: [
    { arabic: "صَبْر", display: "Sabr" },
    { arabic: "حِلْم", display: "Hilm" },
  ],
  ...over,
})

const daily = (over: Partial<DailyCardInput> = {}): DailyCardInput => ({
  kind: "daily",
  dir: "ltr",
  arabicName: "كلمة اليوم",
  latinName: "Word of the day",
  meta: ["#2", "Thursday 29 October 2026", "a place"],
  footer: "majlisna.app/today",
  rungs: { total: 6, revealed: 3, found: 3 },
  result: "found at hint 3 · 4 points",
  streak: [
    { label: "Your streak", value: 2 },
    { label: "Best streak", value: 5 },
  ],
  ...over,
})

describe("the colophon card, drawn as operations", () => {
  it("lays a 1080 × 1350 card on the night ground, inside the arch's double hairline and its three nodes", () => {
    // Act
    const ops = layoutCard(game(), measure)

    // Assert
    expect([CARD_W, CARD_H]).toEqual([1080, 1350])
    expect(ops[0]).toEqual({ kind: "fill", color: "bg" })
    const arch = ops.filter((op) => op.kind === "path")
    expect(arch).toHaveLength(2)
    expect(arch.map((op) => op.kind === "path" && op.color)).toEqual(["brass-70", "line-brass-strong"])
    const nodes = lozenges(ops).filter((op) => op.fill === "brass" && op.role === "node")
    expect(nodes).toHaveLength(3)
    // the apex and both springers, symmetric about the card's middle
    const xs = nodes.map((n) => Math.round(n.x)).sort((a, b) => a - b)
    expect(xs[1]).toBe(CARD_W / 2)
    expect(xs[0] + xs[2]).toBe(CARD_W)
  })

  it("sets the game's Arabic name large in Amiri brass, the Latin name in Marcellus, the meta line in Readex", () => {
    // Act
    const ops = layoutCard(game(), measure)

    // Assert
    const name = textOf(ops, "أندركفـــر")
    expect(name).toMatchObject({ font: { face: "nass", weight: 700 }, color: "brass", dir: "rtl", align: "center", x: CARD_W / 2 })
    expect(name?.font.size).toBeGreaterThanOrEqual(96)
    const latin = textOf(ops, "Undercover")
    expect(latin).toMatchObject({ font: { face: "display", weight: 400 }, color: "text" })
    expect(latin!.y).toBeGreaterThan(name!.y)
    const meta = textOf(ops, "Undercover · Yusuf’s majlis · 3 rounds · 21:40")
    expect(meta).toMatchObject({ font: { face: "ui" }, color: "text-muted", dir: "ltr" })
    expect(meta!.y).toBeGreaterThan(latin!.y)
  })

  it("reads the Arabic alone when there is no Latin name (the Arabic interface), the meta line right to left", () => {
    // Act
    const ops = layoutCard(game({ dir: "rtl", latinName: undefined, meta: ["أندركفر", "مجلس يوسف", "3 جولات", "21:40"] }), measure)

    // Assert
    expect(textOf(ops, "Undercover")).toBeUndefined()
    expect(textOf(ops, "أندركفر · مجلس يوسف · 3 جولات · 21:40")).toMatchObject({ dir: "rtl" })
  })

  it("wraps a meta line too long for the arch at its separators, on two lines at most", () => {
    // Prepare
    const meta = ["Codenames", "le majlis de Abdurrahman-al-Andalusi", "12 indices", "1:02:05"]

    // Act
    const ops = layoutCard(game({ meta }), measure)

    // Assert
    const lines = texts(ops).filter((op) => op.font.face === "ui" && op.color === "text-muted" && op.role === "meta")
    expect(lines.length).toBe(2)
    expect(lines.map((l) => l.text).join(" · ")).toBe(meta.join(" · "))
    expect(lines[1].y).toBeGreaterThan(lines[0].y)
  })

  it("fits every line inside its width, and never lets one run past the arch", () => {
    // Act
    const ops = [
      ...layoutCard(game({ words: Array.from({ length: 25 }, (_, i) => ({ arabic: `كلمة${i}`, display: `Word ${i}` })) }), measure),
      ...layoutCard(daily(), measure),
    ]

    // Assert
    for (const op of texts(ops)) {
      expect(op.maxWidth, op.text).toBeGreaterThan(0)
      expect(measure(op.text, op.font, op.dir), op.text).toBeLessThanOrEqual(op.maxWidth + 0.5)
      expect(op.x - op.maxWidth / 2, op.text).toBeGreaterThanOrEqual(120)
      expect(op.x + op.maxWidth / 2, op.text).toBeLessThanOrEqual(960)
    }
  })

  it("shrinks a word that does not fit its cell, down to a floor, and squeezes it past that", () => {
    // Prepare
    const long = "بسم الملك الذي في السماوات والأرض جميعًا"

    // Act
    const ops = layoutCard(game({ words: [{ arabic: long }, { arabic: "حلم" }] }), measure)

    // Assert
    const word = textOf(ops, long)!
    const short = textOf(ops, "حلم")!
    expect(word.font.size).toBeLessThan(short.font.size)
    expect(word.maxWidth).toBeLessThan(CARD_W / 2)
  })

  it("only ever uses the night's tokens", () => {
    // Act
    const ops = [
      ...layoutCard(game(), measure),
      ...layoutCard(daily(), measure),
      ...layoutCard(daily({ rungs: { total: 6, revealed: 6, found: null } }), measure),
    ]

    // Assert
    const used = new Set(
      ops.flatMap((op) => ("color" in op ? [op.color] : []).concat("fill" in op && op.fill ? [op.fill] : [], "stroke" in op && op.stroke ? [op.stroke] : [])),
    )
    for (const color of used) expect(Object.keys(CARD_COLORS), color).toContain(color)
    for (const expr of Object.values(CARD_COLORS)) expect(expr).toMatch(/^(var\(--[a-z-]+\)|color-mix\(in oklch, var\(--[a-z-]+\) \d+%, transparent\))$/)
  })

  it("closes the arch with one madd band, woven from the reading start", () => {
    // Act
    const ltr = layoutCard(game(), measure).filter((op) => op.kind === "band")
    const rtl = layoutCard(game({ dir: "rtl" }), measure).filter((op) => op.kind === "band")

    // Assert
    expect(ltr).toEqual([expect.objectContaining({ kind: "band", from: "left" })])
    expect(rtl).toEqual([expect.objectContaining({ kind: "band", from: "right" })])
  })

  it("says where it comes from under the arch", () => {
    const ops = layoutCard(game(), measure)
    expect(textOf(ops, "majlisna.app")!.y).toBeGreaterThan(1214)
  })
})

describe("a game's words on the card", () => {
  const wordOps = (ops: DrawOp[]) => texts(ops).filter((op) => op.role === "word")

  it("sets each word in Amiri with its form in the interface language under it", () => {
    // Act
    const ops = layoutCard(game(), measure)

    // Assert
    expect(wordOps(ops).map((op) => op.text)).toEqual(["صَبْر", "حِلْم"])
    expect(textOf(ops, "صَبْر")).toMatchObject({ font: { face: "nass", weight: 700 }, color: "text", dir: "rtl" })
    const sabr = textOf(ops, "Sabr")!
    expect(sabr).toMatchObject({ font: { face: "ui" }, color: "text-muted", dir: "ltr", role: "word-form" })
    expect(sabr.y).toBeGreaterThan(textOf(ops, "صَبْر")!.y)
  })

  it("fills its grid from the reading start: the first word on the left in English, on the right in Arabic", () => {
    // Act
    const ltr = wordOps(layoutCard(game(), measure))
    const rtl = wordOps(layoutCard(game({ dir: "rtl" }), measure))

    // Assert
    expect(ltr[0].x).toBeLessThan(ltr[1].x)
    expect(rtl[0].x).toBeGreaterThan(rtl[1].x)
    expect(ltr[0].y).toBe(ltr[1].y)
  })

  it("sets a Codenames board as five rows of five", () => {
    // Prepare
    const words = Array.from({ length: 25 }, (_, i) => ({ arabic: `ك${i}` }))

    // Act
    const ops = wordOps(layoutCard(game({ words }), measure))

    // Assert
    expect(ops).toHaveLength(25)
    expect(new Set(ops.map((op) => Math.round(op.x))).size).toBe(5)
    expect(new Set(ops.map((op) => Math.round(op.y))).size).toBe(5)
  })

  it("centres the last row of a grid that does not fill it (seven Kalimat rounds: 3, 3, then 1)", () => {
    // Act
    const ops = wordOps(layoutCard(game({ words: Array.from({ length: 7 }, (_, i) => ({ arabic: `ك${i}` })) }), measure))

    // Assert
    expect(Math.round(ops[6].x)).toBe(CARD_W / 2)
    expect(ops[6].y).toBeGreaterThan(ops[3].y)
  })

  it("sets a word that has no Arabic form in Readex, in the Arabic's place", () => {
    // Act
    const ops = layoutCard(game({ words: [{ display: "Tasbih" }, { arabic: "حلم", display: "Hilm" }] }), measure)

    // Assert
    expect(textOf(ops, "Tasbih")).toMatchObject({ role: "word", font: { face: "ui" }, color: "text", dir: "ltr" })
  })

  it(`shows ${MAX_CARD_WORDS} cells at most, the last saying how many more there were`, () => {
    // Prepare
    const words = Array.from({ length: 30 }, (_, i) => ({ arabic: `ك${i}` }))

    // Act
    const ops = layoutCard(game({ words, more: "and 6 more words" }), measure)

    // Assert
    expect(wordOps(ops)).toHaveLength(MAX_CARD_WORDS - 1)
    expect(textOf(ops, "and 6 more words")).toMatchObject({ color: "text-muted" })
  })

  it("draws no word at all for a game without words (the Quiz), and sets its head in the middle of the arch instead", () => {
    // Act
    const ops = layoutCard(game({ arabicName: "مســـائل", words: [] }), measure)
    const withWords = layoutCard(game({ arabicName: "مســـائل" }), measure)

    // Assert
    expect(wordOps(ops)).toEqual([])
    const name = textOf(ops, "مســـائل")!
    expect(name.y).toBeGreaterThan(textOf(withWords, "مســـائل")!.y + 150)
    // the head stays inside the arch, above its band
    const rule = ops.find((op) => op.kind === "lozenge" && op.role === "rule")!
    expect(rule.kind === "lozenge" && rule.y).toBeLessThan(1188 - 22 - 44)
  })
})

describe("the word of the day's card", () => {
  const rungLozenges = (ops: DrawOp[]) => lozenges(ops).filter((op) => op.role === "rung")
  const worths = (ops: DrawOp[]) => texts(ops).filter((op) => op.role === "rung-worth")

  it("draws the six rungs as one woven strip, from the reading start, each with its worth (6 down to 1)", () => {
    // Act
    const ltr = layoutCard(daily(), measure)
    const rtl = layoutCard(daily({ dir: "rtl" }), measure)

    // Assert
    expect(rungLozenges(ltr)).toHaveLength(6)
    expect(worths(ltr).map((op) => op.text)).toEqual(["6", "5", "4", "3", "2", "1"])
    const xs = (ops: DrawOp[]) => worths(ops).map((op) => op.x)
    expect(xs(ltr)).toEqual([...xs(ltr)].sort((a, b) => a - b))
    expect(xs(rtl)).toEqual([...xs(rtl)].sort((a, b) => b - a))
  })

  it("sets the rung the word was found at in brass, strikes the rungs passed, leaves the rest as bare warp", () => {
    // Act
    const ops = layoutCard(daily(), measure)

    // Assert
    const rungs = rungLozenges(ops)
    expect(rungs.map((r) => r.fill ?? null)).toEqual([null, null, "brass", null, null, null])
    const figures = worths(ops)
    expect(figures[2]).toMatchObject({ color: "on-brass" })
    expect(figures.filter((f) => f.strike).map((f) => f.text)).toEqual(["6", "5"])
    // the found rung's cell is tinted, the unopened ones are warp
    expect(ops.filter((op) => op.kind === "rect" && op.fill === "brass-tint")).toHaveLength(1)
    expect(ops.filter((op) => op.kind === "warp")).toHaveLength(3)
    expect(textOf(ops, "found at hint 3 · 4 points")).toMatchObject({ color: "text" })
  })

  it("has no brass rung for a word given up: every rung opened reads as passed", () => {
    // Act
    const ops = layoutCard(daily({ rungs: { total: 6, revealed: 4, found: null }, result: "given up" }), measure)

    // Assert
    expect(rungLozenges(ops).some((r) => r.fill === "brass")).toBe(false)
    expect(
      worths(ops)
        .filter((f) => f.strike)
        .map((f) => f.text),
    ).toEqual(["6", "5", "4", "3"])
    expect(ops.filter((op) => op.kind === "warp")).toHaveLength(2)
    expect(textOf(ops, "given up")).toMatchObject({ color: "text-muted" })
  })

  it("sets the two streaks as Readex figures over their labels", () => {
    // Act
    const ops = layoutCard(daily(), measure)

    // Assert
    const streaks = texts(ops).filter((op) => op.role === "streak")
    expect(streaks.map((op) => op.text)).toEqual(["2", "5"])
    expect(streaks[0]).toMatchObject({ font: { face: "ui" }, color: "text" })
    expect(streaks[0].x).toBeLessThan(streaks[1].x)
    expect(textOf(ops, "Your streak")!.y).toBeGreaterThan(streaks[0].y)
    expect(layoutCard(daily({ streak: undefined }), measure).some((op) => op.kind === "text" && op.role === "streak")).toBe(false)
  })
})

describe("textDir", () => {
  it("reads a run's direction from its first strong letter, else the interface's", () => {
    const cases: [string, CardDir, CardDir][] = [
      ["صبر", "ltr", "rtl"],
      ["Sabr", "rtl", "ltr"],
      ["21:40", "rtl", "rtl"],
      ["« Ṣabr »", "rtl", "ltr"],
    ]
    for (const [text, ui, expected] of cases) expect(textDir(text, ui), text).toBe(expected)
  })
})
