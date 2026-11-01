/**
 * A Sadu band's tile (scripts/brand/sadu.py → src/assets/sadu/*.svg) as its woven cells,
 * so the card's madd band is the product's own, cell for cell and dye for dye, drawn
 * with `fillRect` (no image to decode, nothing fetched). The tiles are pixel grids of
 * `<rect x y width height fill>` in a `viewBox="0 0 W H"`.
 */

export interface BandRect {
  x: number
  y: number
  w: number
  h: number
  fill: string
}

export interface BandTile {
  w: number
  h: number
  rects: BandRect[]
}

const attr = (tag: string, name: string) => new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1]

export function parseBandTile(svg: string): BandTile {
  const box = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(svg)
  if (!box) throw new Error("band tile: no viewBox")
  const rects: BandRect[] = []
  for (const [tag] of svg.matchAll(/<rect\b[^>]*>/g)) {
    const fill = attr(tag, "fill")
    if (!fill) continue
    rects.push({ x: Number(attr(tag, "x") ?? 0), y: Number(attr(tag, "y") ?? 0), w: Number(attr(tag, "width")), h: Number(attr(tag, "height")), fill })
  }
  return { w: Number(box[1]), h: Number(box[2]), rects }
}
