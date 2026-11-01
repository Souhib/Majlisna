import { type CSSProperties, type ReactNode, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

/**
 * Halqa: the circle of seats (the majlis seen from above), sketch sections A and D.
 *
 * Seats sit on a brass ring, the host at the head (the ṣadr, top centre). Seats fill
 * clockwise in left-to-right languages and ANTICLOCKWISE in Arabic, following the
 * reading direction. A brass thread runs from the ṣadr through the seated players; when
 * the seated count reaches `quorum` the thread closes the whole ring (thicker): the
 * closed circle IS the "ready to start" signal. The centre holds the room code or the
 * player count, over the one warmth in the product (a static ember glow).
 *
 * The halqa fills (the CIRCLE gesture): the thread is ONE circle in every state, its arc a
 * dash on a pathLength of 1 (`--arc`), so the CSS transitions every change of the same
 * element. An arrival runs the thread to the new seat (320 ms, --ease-settle); the quorum
 * closes the ring (640 ms, --ease-ink, 1.6 → 2.6); a departure retracts it (211 ms,
 * --ease-in). A seat that arrives while the ring is on screen is pressed in once (its
 * lozenge .25 → 1, its label fades); the first drawing presses nothing. Reduced motion: no
 * transition, the new seat fades in.
 *
 * Seats are given in seating order starting with the host. Pass `capacity` to draw open
 * seats after them (dashed). Labels can carry a second line (`sub`: "ready",
 * "away · 9:58").
 *
 * The ring is a picture: give `label` (a one-sentence summary) and keep the real player
 * list in the DOM for assistive tech; without `label` the SVG is aria-hidden.
 *
 * <Halqa
 *   seats={[{ id, name: "Yusuf", sub: "you · host", state: "host", me: true }, …]}
 *   capacity={8} quorum={3}
 *   center={{ count: 5, label: "players" }}
 *   label="Five players seated, three seats open"
 * />
 */
export type SeatState = "host" | "in" | "away" | "spectator" | "open" | "you"

export interface HalqaSeat {
  id: string
  name: string
  /** Second line under the name ("ready", "away · 9:58"). */
  sub?: string
  state: Exclude<SeatState, "open">
  /** The viewer's own seat: name in full ink, medium weight. */
  me?: boolean
}

export type HalqaCenter = { code: string; label?: string } | { count: number; label?: string } | { node: ReactNode }

export interface HalqaProps {
  seats: HalqaSeat[]
  /** Total seats on the ring (open seats are drawn after the seated). Max 12. */
  capacity?: number
  /** Seated players needed to start: the ring closes at this count. */
  quorum?: number
  center?: HalqaCenter
  /** Label for open seats (defaults to the translated "open"). */
  openLabel?: string
  /** Force the fill direction; defaults to the document direction. */
  dir?: "ltr" | "rtl"
  /** One-sentence summary for assistive tech; omit to hide the picture. */
  label?: string
  /** Name font size in SVG units (the drawing scales with its box). Default 12. */
  fontSize?: number
  /** Ring radius in SVG units. Default 104. */
  radius?: number
  /**
   * Room left of and right of the ring for the labels, in SVG units (default: enough for
   * two-line labels at `fontSize`). Tighten it when the labels are short, so the ring
   * fills its box: the home's halqa card uses the sketch's 340 × 300 box (66 / 46).
   */
  padX?: number
  /** Room above and below the ring for the labels, in SVG units. */
  padY?: number
  className?: string
  style?: CSSProperties
}

const SEATED: ReadonlySet<SeatState> = new Set(["host", "in", "away"])

function documentDir(): "ltr" | "rtl" {
  if (typeof document === "undefined") return "ltr"
  return document.documentElement.dir === "rtl" ? "rtl" : "ltr"
}

export function Halqa({ seats, capacity, quorum, center, openLabel, dir, label, fontSize = 12, radius = 104, padX, padY, className, style }: HalqaProps) {
  const { t } = useTranslation()
  const uid = useId().replace(/:/g, "")
  const rtl = (dir ?? documentDir()) === "rtl"
  const R = radius
  const n = Math.min(12, Math.max(seats.length, capacity ?? seats.length, 3))
  const step = 360 / n
  // Room for two-line labels on every side.
  const pad = padX ?? R * 0.62 + fontSize * 2.2
  const w = 2 * (R + pad)
  const h = 2 * (R + (padY ?? fontSize * 4.2))
  const cx = w / 2
  const cy = h / 2
  const sign = rtl ? -1 : 1

  type Drawn = { key: string; state: SeatState; lines: string[]; cls: string }
  const drawn: Drawn[] = [
    ...seats.slice(0, n).map((s) => ({
      key: s.id,
      state: s.state as SeatState,
      lines: s.sub ? [s.name, s.sub] : [s.name],
      cls: s.me ? "me" : s.state === "host" ? "me" : "",
    })),
    ...Array.from({ length: Math.max(0, n - seats.length) }, (_, i) => ({
      key: `open-${i}`,
      state: "open" as SeatState,
      lines: [openLabel ?? t("ui.halqa.open")],
      cls: "",
    })),
  ]

  // consecutive seated players from the ṣadr
  let seated = 0
  for (const d of drawn) {
    if (SEATED.has(d.state)) seated += 1
    else break
  }
  const closed = quorum !== undefined && seated >= quorum && seated > 1
  const pt = (k: number, r = R) => {
    const a = ((-90 + sign * step * k) * Math.PI) / 180
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a), c: Math.cos(a), s: Math.sin(a) }
  }

  // What changed since the roster last moved: who sat down (pressed in), and whether the
  // thread retracts. Derived state, updated in render when the roster changes, so a seat
  // keeps its mark across re-renders that seat nobody (its press is never cut short).
  const ids = seats.slice(0, n).map((s) => s.id)
  const roster = `${seated}|${ids.join("\u0000")}`
  const [moved, setMoved] = useState<{ roster: string; ids: string[]; seated: number; fresh: ReadonlySet<string>; leaving: boolean }>(() => ({
    roster,
    ids,
    seated,
    fresh: new Set(),
    leaving: false,
  }))
  if (moved.roster !== roster) {
    const before = new Set(moved.ids)
    setMoved({ roster, ids, seated, fresh: new Set(ids.filter((id) => !before.has(id))), leaving: seated < moved.seated })
  }

  // the arc from the ṣadr to the last seated player, or the whole ring once closed
  const arc = closed ? 1 : seated > 1 ? (seated - 1) / n : 0
  // a circle's path starts at three o'clock and runs clockwise: turn it to the ṣadr, and
  // mirror it in Arabic so it runs anticlockwise
  const orient = rtl
    ? `translate(${(2 * cx).toFixed(1)} 0) scale(-1 1) rotate(-90 ${cx.toFixed(1)} ${cy.toFixed(1)})`
    : `rotate(-90 ${cx.toFixed(1)} ${cy.toFixed(1)})`

  const a11y = label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true as const }

  return (
    <svg
      className={cn("halqa", className)}
      viewBox={`0 0 ${w.toFixed(0)} ${h.toFixed(0)}`}
      style={{ "--halqa-font": `${fontSize}px`, ...style } as CSSProperties}
      {...a11y}
    >
      <defs>
        <radialGradient id={`fire-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="0" style={{ stopColor: "var(--fire)", stopOpacity: 0.6 }} />
          <stop offset=".7" style={{ stopColor: "var(--fire)", stopOpacity: 0.16 }} />
          <stop offset="1" style={{ stopColor: "var(--fire)", stopOpacity: 0 }} />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={R * 0.56} fill={`url(#fire-${uid})`} />
      <circle className="ring" cx={cx} cy={cy} r={R} />
      <circle className="ring-in" cx={cx} cy={cy} r={R * 0.77} />
      <circle
        className="thread"
        cx={cx}
        cy={cy}
        r={R}
        pathLength={1}
        transform={orient}
        data-closed={closed}
        data-leaving={moved.leaving}
        style={{ "--arc": arc } as CSSProperties}
      />
      {drawn.map((d, k) => {
        const p = pt(k)
        const size = d.state === "host" ? 20 : 14
        const lr = R + (d.state === "host" ? 26 : 20)
        const lp = pt(k, lr)
        const anchor = Math.abs(p.c) < 0.2 ? "middle" : p.c > 0 ? "start" : "end"
        const lineGap = fontSize + 3
        let ly: number
        if (k === 0 || (Math.abs(p.c) < 0.2 && p.s < 0)) ly = cy - R - 24 - (d.lines.length - 1) * lineGap
        else if (Math.abs(p.c) < 0.2) ly = cy + R + 28
        else ly = lp.y + 4 - ((d.lines.length - 1) * lineGap) / 2
        const cls = d.state === "you" ? "you" : d.cls
        const fresh = moved.fresh.has(d.key) ? "true" : undefined
        return (
          <g key={d.key}>
            {/* the lozenge's own group: it is scaled about its centre on arrival, which a
                transform-origin on the rotated rect itself would throw off */}
            <g className="seat" data-fresh={fresh}>
              <rect
                className={`s-${d.state}`}
                x={(p.x - size / 2).toFixed(1)}
                y={(p.y - size / 2).toFixed(1)}
                width={size}
                height={size}
                transform={`rotate(45 ${p.x.toFixed(1)} ${p.y.toFixed(1)})`}
              />
            </g>
            <text className={cls || undefined} x={lp.x.toFixed(1)} y={ly.toFixed(1)} textAnchor={anchor} data-fresh={fresh}>
              {d.lines.map((line, i) => (
                <tspan key={i} x={lp.x.toFixed(1)} dy={i === 0 ? 0 : lineGap} className={i ? "st" : undefined}>
                  {line}
                </tspan>
              ))}
            </text>
          </g>
        )
      })}
      {center ? <HalqaCenterView center={center} cx={cx} cy={cy} /> : null}
    </svg>
  )
}

function HalqaCenterView({ center, cx, cy }: { center: HalqaCenter; cx: number; cy: number }) {
  if ("node" in center) {
    return (
      <foreignObject x={cx - 60} y={cy - 40} width={120} height={80}>
        <div className="grid size-full place-items-center text-center">{center.node}</div>
      </foreignObject>
    )
  }
  if ("code" in center) {
    return (
      <>
        <text className="code" x={cx} y={cy} textAnchor="middle">
          {center.code}
        </text>
        {center.label ? (
          <text className="center-label" x={cx} y={cy + 22} textAnchor="middle">
            {center.label}
          </text>
        ) : null}
      </>
    )
  }
  return (
    <>
      <text className="count num" x={cx} y={cy + 4} textAnchor="middle">
        {center.count}
      </text>
      {center.label ? (
        <text className="center-label" x={cx} y={cy + 24} textAnchor="middle">
          {center.label}
        </text>
      ) : null}
    </>
  )
}
