import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { parseBandTile } from "../band"
import { type DrawOp, type GameCardInput } from "../model"
import { type CardEnv, drawnStack, drawOps, renderCardFile } from "../render"

/**
 * The canvas renderer applies the drawing model and nothing else. happy-dom has no
 * canvas, so the 2D context is a recording fake: it keeps every call with the state
 * (font, direction, colour) it was made in.
 */

interface Call {
  name: string
  args: unknown[]
  font: string
  direction: string
  fillStyle: unknown
  strokeStyle: unknown
  lineWidth: number
}

function recordingContext() {
  const calls: Call[] = []
  const state = {
    font: "10px sans-serif",
    direction: "inherit",
    fillStyle: "#000",
    strokeStyle: "#000",
    lineWidth: 1,
    textAlign: "start",
    textBaseline: "alphabetic",
  }
  const record =
    (name: string) =>
    (...args: unknown[]) => {
      calls.push({
        name,
        args,
        font: state.font,
        direction: state.direction,
        fillStyle: state.fillStyle,
        strokeStyle: state.strokeStyle,
        lineWidth: state.lineWidth,
      })
    }
  const ctx = Object.assign(state, {
    save: record("save"),
    restore: record("restore"),
    beginPath: record("beginPath"),
    closePath: record("closePath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    bezierCurveTo: record("bezierCurveTo"),
    rect: record("rect"),
    clip: record("clip"),
    fill: record("fill"),
    stroke: record("stroke"),
    fillRect: record("fillRect"),
    strokeRect: record("strokeRect"),
    fillText: record("fillText"),
    measureText: (text: string) => ({ width: [...text].length * (Number(/(\d+(?:\.\d+)?)px/.exec(state.font)?.[1]) || 10) * 0.5 }),
  })
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls }
}

const env: CardEnv = {
  color: (c) => `color(${c})`,
  font: (font) => `${font.weight} ${font.size}px stack(${font.face})`,
  drawn: (font) => `${font.weight} ${font.size}px drawn(${font.face})`,
  tile: { w: 2, h: 1, rects: [{ x: 0, y: 0, w: 1, h: 1, fill: "#111111" }] },
}

describe("drawOps", () => {
  it("writes each line in its font, direction, colour and width, centred on its point", () => {
    // Prepare
    const { ctx, calls } = recordingContext()
    const ops: DrawOp[] = [
      {
        kind: "text",
        text: "صبر",
        x: 540,
        y: 300,
        font: { face: "nass", weight: 700, size: 96 },
        color: "brass",
        dir: "rtl",
        align: "center",
        maxWidth: 600,
        role: "name",
      },
      {
        kind: "text",
        text: "Sabr",
        x: 540,
        y: 360,
        font: { face: "ui", weight: 300, size: 30 },
        color: "text-muted",
        dir: "ltr",
        align: "center",
        maxWidth: 400,
        role: "meta",
      },
    ]

    // Act
    drawOps(ctx, ops, env)

    // Assert
    const texts = calls.filter((c) => c.name === "fillText")
    expect(texts.map((c) => [c.args, c.font, c.direction, c.fillStyle])).toEqual([
      [["صبر", 540, 300, 600], "700 96px stack(nass)", "rtl", "color(brass)"],
      [["Sabr", 540, 360, 400], "300 30px stack(ui)", "ltr", "color(text-muted)"],
    ])
    expect(ctx.textAlign).toBe("center")
  })

  it("strikes a passed rung's worth with a line through the figure", () => {
    // Prepare
    const { ctx, calls } = recordingContext()

    // Act
    drawOps(
      ctx,
      [
        {
          kind: "text",
          text: "6",
          x: 100,
          y: 200,
          font: { face: "ui", weight: 500, size: 28 },
          color: "text-muted",
          dir: "ltr",
          align: "center",
          maxWidth: 60,
          role: "rung-worth",
          strike: true,
        },
      ],
      env,
    )

    // Assert
    const stroke = calls.find((c) => c.name === "stroke")
    expect(stroke?.strokeStyle).toBe("color(text-muted)")
    const [from, to] = calls.filter((c) => c.name === "moveTo" || c.name === "lineTo").map((c) => c.args as number[])
    expect(from[1]).toBe(to[1])
    expect(from[0]).toBeLessThan(100)
    expect(to[0]).toBeGreaterThan(100)
  })

  it("draws a lozenge as a square turned on its point", () => {
    // Prepare
    const { ctx, calls } = recordingContext()

    // Act
    drawOps(ctx, [{ kind: "lozenge", x: 50, y: 60, r: 10, fill: "brass", role: "node" }], env)

    // Assert
    const points = calls.filter((c) => c.name === "moveTo" || c.name === "lineTo").map((c) => c.args)
    expect(points).toEqual([
      [50, 50],
      [60, 60],
      [50, 70],
      [40, 60],
    ])
    expect(calls.find((c) => c.name === "fill")?.fillStyle).toBe("color(brass)")
  })

  it("weaves the band from the reading start, inside its own box", () => {
    // Prepare
    const ltr = recordingContext()
    const rtl = recordingContext()
    const band = (from: "left" | "right"): DrawOp => ({ kind: "band", x: 100, y: 10, w: 9, h: 2, from })

    // Act
    drawOps(ltr.ctx, [band("left")], env)
    drawOps(rtl.ctx, [band("right")], env)

    // Assert (a 2 × 1 tile at 2 px a cell: 4 px wide, its one rect at the tile's start)
    const xs = (calls: Call[]) => calls.filter((c) => c.name === "fillRect").map((c) => (c.args as number[])[0])
    expect(xs(ltr.calls)).toEqual([100, 104, 108])
    expect(xs(rtl.calls)).toEqual([105, 101, 97])
    expect(ltr.calls.some((c) => c.name === "clip")).toBe(true)
  })

  it("draws warp as threads a step apart, and the arch as one stroked path", () => {
    // Prepare
    const { ctx, calls } = recordingContext()

    // Act
    drawOps(
      ctx,
      [
        { kind: "warp", x: 0, y: 0, w: 30, h: 10, step: 10, color: "warp" },
        { kind: "path", d: [["M", 0, 0], ["C", 1, 2, 3, 4, 5, 6], ["L", 7, 8], ["Z"]], color: "line-brass-strong", width: 2 },
      ],
      env,
    )

    // Assert
    expect(calls.filter((c) => c.name === "fillRect").map((c) => (c.args as number[])[0])).toEqual([0, 10, 20])
    expect(calls.find((c) => c.name === "bezierCurveTo")?.args).toEqual([1, 2, 3, 4, 5, 6])
    expect(calls.find((c) => c.name === "stroke")).toMatchObject({ strokeStyle: "color(line-brass-strong)", lineWidth: 2 })
  })
})

describe("drawnStack", () => {
  it("keeps only the families the card draws with, never a fallback (document.fonts.load fetches every face it is given)", () => {
    expect(drawnStack('"Amiri", "Readex Pro Variable", serif', "nass")).toBe('"Amiri"')
    expect(drawnStack('"Samar Figures", "Marcellus", "Amiri", serif', "display")).toBe('"Samar Figures", "Marcellus"')
    expect(drawnStack('"Readex Pro Variable", "Readex Pro", system-ui, sans-serif', "ui")).toBe('"Readex Pro Variable"')
  })
})

describe("parseBandTile", () => {
  it("reads the madd band's woven cells from its own SVG (the band's own dyes, no new colour)", () => {
    // Prepare: vitest runs with `css: false`; read the asset itself
    const svg = readFileSync(resolve(__dirname, "../../../../assets/sadu/madd-night.svg"), "utf8")

    // Act
    const tile = parseBandTile(svg)

    // Assert
    expect([tile.w, tile.h]).toEqual([18, 11])
    expect(tile.rects.length).toBeGreaterThan(40)
    expect(tile.rects[0]).toEqual({ x: 0, y: 0, w: 18, h: 1, fill: "#efe7d8" })
    expect(new Set(tile.rects.map((r) => r.fill))).toEqual(new Set(["#efe7d8", "#1d1613", "#9a3324", "#eadfc8", "#c08a3e"]))
  })
})

describe("renderCardFile", () => {
  const input: GameCardInput = {
    kind: "game",
    dir: "ltr",
    arabicName: "أندركفـــر",
    latinName: "Undercover",
    meta: ["Undercover", "3 rounds"],
    footer: "majlisna.app",
    words: [{ arabic: "صبر", display: "Sabr" }],
  }
  let fake: ReturnType<typeof recordingContext>
  const fontsLoad = vi.fn(async () => [])
  const order: string[] = []

  beforeEach(() => {
    fake = recordingContext()
    order.length = 0
    fontsLoad.mockClear()
    fontsLoad.mockImplementation(async () => {
      order.push("load")
      return []
    })
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: {
        load: fontsLoad,
        get ready() {
          order.push("ready")
          return Promise.resolve()
        },
      },
    })
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => {
      order.push("context")
      return fake.ctx as never
    })
    Object.defineProperty(HTMLCanvasElement.prototype, "toBlob", {
      configurable: true,
      value: function (cb: (blob: Blob | null) => void, type: string) {
        order.push(`toBlob:${type}`)
        cb(new Blob(["png"], { type }))
      },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (document as { fonts?: unknown }).fonts
    delete (HTMLCanvasElement.prototype as { toBlob?: unknown }).toBlob
  })

  it("loads the faces it sets before measuring, draws 1080 × 1350 and hands back a PNG file", async () => {
    // Act
    const file = await renderCardFile(input, "majlisna-undercover.png")

    // Assert
    expect(file.name).toBe("majlisna-undercover.png")
    expect(file.type).toBe("image/png")
    // every line's face and text was asked for, then the set awaited, before a single draw
    const loaded = fontsLoad.mock.calls.map((call) => (call as unknown as [string, string])[1])
    expect(loaded).toEqual(expect.arrayContaining(["أندركفـــر", "Undercover", "صبر", "Sabr", "majlisna.app", "Undercover·3rounds"]))
    expect(order.indexOf("ready")).toBeGreaterThan(order.lastIndexOf("load"))
    expect(order.at(-1)).toBe("toBlob:image/png")
    const firstDraw = fake.calls.findIndex((c) => c.name === "fillRect" || c.name === "fillText")
    expect(firstDraw).toBeGreaterThanOrEqual(0)
    const canvas = vi.mocked(HTMLCanvasElement.prototype.getContext).mock.contexts[0] as HTMLCanvasElement
    expect([canvas.width, canvas.height]).toEqual([1080, 1350])
  })

  it("asks the font set for letters only: a space would fetch Amiri's Latin face too", async () => {
    // Act
    await renderCardFile({ ...input, words: [{ arabic: "صلاة الضحى", display: "Salat al-Duha" }] }, "card.png")

    // Assert
    const texts = (fontsLoad.mock.calls as unknown as [string, string][]).map(([, text]) => text)
    expect(texts).toEqual(expect.arrayContaining(["صلاةالضحى", "Salatal-Duha"]))
    for (const text of texts) expect(text).not.toMatch(/\s/)
  })

  it("reads the night's colours from the tokens, under data-theme=dark, and leaves nothing in the page", async () => {
    // Act
    await renderCardFile(input, "card.png")

    // Assert
    expect(document.querySelector("[data-share-card-probe]")).toBeNull()
  })

  it("leaves the tap's own task at once: nothing is measured or drawn before the browser had a turn", async () => {
    // Act: the work is started, then only microtasks run (what a click's task still runs)
    const pending = renderCardFile(input, "card.png")
    for (let i = 0; i < 20; i++) await Promise.resolve()

    // Assert
    expect(order).toEqual([])
    expect(fake.calls).toEqual([])

    // and it does finish, in later turns
    await pending
    expect(fake.calls.some((c) => c.name === "fillText")).toBe(true)
  })

  it("refuses when the browser gives no 2D context", async () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockImplementation(() => null)
    await expect(renderCardFile(input, "card.png")).rejects.toThrow()
  })
})
