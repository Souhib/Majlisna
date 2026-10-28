/**
 * Charts draw on a canvas, which cannot read CSS custom properties. These helpers read
 * the Samar tokens from <html> at render time (so a chart follows the light) and turn
 * whatever colour syntax the token uses (OKLCH here) into an rgb() string that both the
 * canvas and Chart.js's own colour parser understand.
 */

let probe: CanvasRenderingContext2D | null | undefined

function probeContext(): CanvasRenderingContext2D | null {
  if (probe !== undefined) return probe
  try {
    const canvas = document.createElement("canvas")
    canvas.width = canvas.height = 1
    probe = canvas.getContext("2d", { willReadFrequently: true })
  } catch {
    probe = null
  }
  return probe
}

/** Any CSS colour → `rgb(r g b / a)`; returns the input unchanged when it cannot be resolved. */
export function toRgb(color: string, alpha = 1): string {
  const ctx = probeContext()
  if (!ctx || !color) return color
  ctx.clearRect(0, 0, 1, 1)
  ctx.fillStyle = "#000"
  ctx.fillStyle = color
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  const out = (a / 255) * alpha
  return `rgb(${r} ${g} ${b} / ${Math.round(out * 1000) / 1000})`
}

/** The value of a Samar token (`--brass`, `--text-muted`…) as an rgb() string. */
export function tokenColor(name: string, alpha = 1, root: Element = document.documentElement): string {
  const raw = getComputedStyle(root).getPropertyValue(name).trim()
  return toRgb(raw, alpha)
}
