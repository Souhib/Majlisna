import maddNight from "@/assets/sadu/madd-night.svg?raw"
import { type BandTile, parseBandTile } from "./band"
import { CARD_COLORS, CARD_H, CARD_W, type CardColor, type CardFace, type CardFont, type CardInput, type DrawOp, layoutCard, type Measure } from "./model"

/**
 * The colophon card on a canvas: a thin renderer over the drawing model (`model.ts`).
 * It reads the night's colours from the tokens (under `data-theme="dark"`, whatever the
 * light on screen) and the type stacks from `--f-*`, loads the faces the card sets
 * (self-hosted, already on the page: `document.fonts.load`, then `document.fonts.ready`),
 * measures, draws, and hands back a 1080 × 1350 PNG. Called on demand only, when the
 * player presses Share; nothing leaves the device.
 */

export interface CardEnv {
  color: (color: CardColor) => string
  /** The role's whole stack, as the canvas sets it. */
  font: (font: CardFont) => string
  /** The role's drawn families only, for `document.fonts.load` (see `DRAWN_FAMILIES`). */
  drawn: (font: CardFont) => string
  tile: BandTile
}

const FACE_VAR: Record<CardFace, string> = { nass: "--f-nass", display: "--f-display", ui: "--f-ui" }
const FACE_FALLBACK: Record<CardFace, string> = { nass: "serif", display: "serif", ui: "sans-serif" }

/**
 * How many families at the head of each `--f-*` stack the card draws with: Amiri for
 * nass, Samar Figures + Marcellus for display (its Amiri is for Arabic letters in a
 * title, which the card never sets in display), Readex for ui. `document.fonts.load`
 * fetches EVERY face of the list that covers the text, fallbacks included: given the
 * whole display stack it downloaded Amiri's Latin file for "Word of the day".
 */
const DRAWN_FAMILIES: Record<CardFace, number> = { nass: 1, display: 2, ui: 1 }

/** The head of a `--f-*` stack the card draws a role with: `"Amiri"`, `"Samar Figures", "Marcellus"`. */
export function drawnStack(stack: string, face: CardFace): string {
  return stack
    .split(",")
    .slice(0, DRAWN_FAMILIES[face])
    .map((family) => family.trim())
    .join(", ")
}

let maddTile: BandTile | null = null

/** The night's colours and the type stacks, read from the tokens; the probe leaves the page at once. */
export function nightEnv(): CardEnv {
  const host = document.createElement("div")
  host.dataset.theme = "dark"
  host.dataset.shareCardProbe = ""
  host.setAttribute("aria-hidden", "true")
  host.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none;contain:strict"
  const names = Object.keys(CARD_COLORS) as CardColor[]
  const probes = names.map((name) => {
    const probe = document.createElement("span")
    probe.style.color = CARD_COLORS[name]
    host.append(probe)
    return probe
  })
  document.body.append(host)
  try {
    // one style pass for the lot: every probe is in place before the first read
    const colors = new Map(names.map((name, i) => [name, getComputedStyle(probes[i]).color]))
    const style = getComputedStyle(host)
    const stacks = Object.fromEntries(
      (Object.keys(FACE_VAR) as CardFace[]).map((face) => [face, style.getPropertyValue(FACE_VAR[face]).trim() || FACE_FALLBACK[face]]),
    ) as Record<CardFace, string>
    maddTile ??= parseBandTile(maddNight)
    return {
      color: (color) => colors.get(color) || "transparent",
      font: (font) => `${font.weight} ${font.size}px ${stacks[font.face]}`,
      drawn: (font) => `${font.weight} ${font.size}px ${drawnStack(stacks[font.face], font.face)}`,
      tile: maddTile,
    }
  } finally {
    host.remove()
  }
}

/** Loads every face the card sets, for exactly the characters it sets in it, then waits for the set. */
async function loadFaces(ops: DrawOp[], env: CardEnv): Promise<void> {
  const fonts = typeof document !== "undefined" ? document.fonts : undefined
  if (!fonts) return
  const wanted = new Map<string, [string, string]>()
  for (const op of ops) {
    if (op.kind !== "text") continue
    // letters only: a space is also in Amiri's Latin face (fonts.css), which would be fetched for it
    const text = op.text.replace(/\s+/g, "")
    if (!text) continue
    const font = env.drawn({ ...op.font, size: 16 })
    wanted.set(`${font}\u0000${text}`, [font, text])
  }
  // a face that fails to load leaves its fallback: the card is still drawn
  await Promise.all([...wanted.values()].map(([font, text]) => fonts.load(font, text).catch(() => [])))
  await fonts.ready
}

function lozenge(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x, y - r)
  ctx.lineTo(x + r, y)
  ctx.lineTo(x, y + r)
  ctx.lineTo(x - r, y)
  ctx.closePath()
}

function strokeLine(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, color: string, width: number) {
  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.stroke()
}

/** Applies the operations in order. Exported for the recording-context test. */
export function drawOps(ctx: CanvasRenderingContext2D, ops: DrawOp[], env: CardEnv): void {
  ctx.textAlign = "center"
  ctx.textBaseline = "alphabetic"
  for (const op of ops) {
    switch (op.kind) {
      case "fill":
        ctx.fillStyle = env.color(op.color)
        ctx.fillRect(0, 0, CARD_W, CARD_H)
        break
      case "path":
        ctx.beginPath()
        for (const seg of op.d) {
          if (seg[0] === "M") ctx.moveTo(seg[1], seg[2])
          else if (seg[0] === "L") ctx.lineTo(seg[1], seg[2])
          else if (seg[0] === "C") ctx.bezierCurveTo(seg[1], seg[2], seg[3], seg[4], seg[5], seg[6])
          else ctx.closePath()
        }
        ctx.strokeStyle = env.color(op.color)
        ctx.lineWidth = op.width
        ctx.stroke()
        break
      case "lozenge":
        lozenge(ctx, op.x, op.y, op.r)
        if (op.fill) {
          ctx.fillStyle = env.color(op.fill)
          ctx.fill()
        }
        if (op.stroke) {
          ctx.strokeStyle = env.color(op.stroke)
          ctx.lineWidth = op.width ?? 1.5
          ctx.stroke()
        }
        break
      case "line":
        strokeLine(ctx, op.x1, op.y1, op.x2, op.y2, env.color(op.color), op.width)
        break
      case "rect":
        if (op.fill) {
          ctx.fillStyle = env.color(op.fill)
          ctx.fillRect(op.x, op.y, op.w, op.h)
        }
        if (op.stroke) {
          const w = op.width ?? 1.5
          ctx.strokeStyle = env.color(op.stroke)
          ctx.lineWidth = w
          ctx.strokeRect(op.x + w / 2, op.y + w / 2, op.w - w, op.h - w)
        }
        break
      case "warp":
        ctx.fillStyle = env.color(op.color)
        for (let x = op.x; x < op.x + op.w; x += op.step) ctx.fillRect(x, op.y, 1.5, op.h)
        break
      case "band": {
        const cell = op.h / env.tile.h
        const tileW = env.tile.w * cell
        ctx.save()
        ctx.beginPath()
        ctx.rect(op.x, op.y, op.w, op.h)
        ctx.clip()
        for (let k = 0; k * tileW < op.w; k++) {
          const ox = op.from === "right" ? op.x + op.w - (k + 1) * tileW : op.x + k * tileW
          for (const r of env.tile.rects) {
            ctx.fillStyle = r.fill
            ctx.fillRect(ox + r.x * cell, op.y + r.y * cell, r.w * cell, r.h * cell)
          }
        }
        ctx.restore()
        break
      }
      case "text": {
        const color = env.color(op.color)
        ctx.font = env.font(op.font)
        ctx.direction = op.dir
        ctx.fillStyle = color
        ctx.fillText(op.text, op.x, op.y, op.maxWidth)
        if (op.strike) {
          const half = (Math.min(ctx.measureText(op.text).width, op.maxWidth) + op.font.size * 0.4) / 2
          const y = op.y - op.font.size * 0.34
          strokeLine(ctx, op.x - half, y, op.x + half, y, color, Math.max(1.5, op.font.size * 0.07))
        }
        break
      }
    }
  }
}

/**
 * Gives the browser a turn (a frame, an input) between two pieces of the card's work.
 * Every await of `renderCardFile` would otherwise resolve at once (the faces are
 * already loaded), and the whole card ran inside the tap's task: 29 ms at 4x CPU.
 */
function yieldToBrowser(): Promise<void> {
  const scheduler = (globalThis as { scheduler?: { yield?: () => Promise<void> } }).scheduler
  if (typeof scheduler?.yield === "function") return scheduler.yield()
  return new Promise((resolve) => setTimeout(resolve, 0))
}

/** The card as a PNG file, drawn now (the player's tap), with the faces of the page. */
export async function renderCardFile(input: CardInput, fileName: string): Promise<File> {
  // the tap's own task ends first: the button's busy state paints, input stays live
  await yieldToBrowser()
  const canvas = document.createElement("canvas")
  canvas.width = CARD_W
  canvas.height = CARD_H
  const ctx = canvas.getContext("2d")
  if (!ctx) throw new Error("share card: the browser gave no 2D context")
  const env = nightEnv()
  // the faces first: a layout that measures nothing names every line and its face
  await loadFaces(
    layoutCard(input, () => 0),
    env,
  )
  await yieldToBrowser()
  const measure: Measure = (text, font, dir) => {
    ctx.font = env.font(font)
    ctx.direction = dir
    return ctx.measureText(text).width
  }
  drawOps(ctx, layoutCard(input, measure), env)
  // Chrome encodes the PNG in idle slices (canvas_async_blob_creator: IdleEncodeRows)
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"))
  if (!blob) throw new Error("share card: the canvas gave no PNG")
  return new File([blob], fileName, { type: "image/png" })
}
