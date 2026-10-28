import { type CSSProperties } from "react"
import { cn } from "@/lib/utils"

/**
 * SaduBand: a woven Sadu strip (the bands of scripts/brand/sadu.py, ported from the
 * sketch). Pixel-grid SVG tiles repeated along the inline axis, anchored at the
 * reading start (right in Arabic). Decorative: always aria-hidden.
 *
 * variant
 *   madd    al-madd, the kashida band: closes a section or a card. Follows the light
 *           (cream selvedge at night, goat-hair by day). ONE thick band per screen.
 *   teeth   ḍurūs: the red team's selvedge (madder wool) (a shape, not only a colour)
 *   ayn     ʿayn, the eye: the blue team's selvedge (indigo wool)
 *   goat    goat-hair twill: the assassin's selvedge
 *   plain   undyed weave: bystanders, neutral
 *   khayt   the thread: RESERVED for the clock (use <ThreadClock>)
 *
 * Never put a band under text.
 *
 * <SaduBand />                     // 12 px madd band
 * <SaduBand variant="teeth" height={8} />
 */
export type SaduVariant = "madd" | "teeth" | "ayn" | "goat" | "plain" | "khayt"

export interface SaduBandProps {
  variant?: SaduVariant
  /** Band height in px (the tile scales with it). Default 12; khayt defaults to 8. */
  height?: number
  className?: string
  style?: CSSProperties
}

export function SaduBand({ variant = "madd", height, className, style }: SaduBandProps) {
  const h = height ?? (variant === "khayt" ? 8 : 12)
  return (
    <span
      aria-hidden="true"
      data-variant={variant}
      className={cn("sadu-band", className)}
      style={{ "--h": `${h}px`, "--b": `var(--band-${variant})`, ...style } as CSSProperties}
    />
  )
}
