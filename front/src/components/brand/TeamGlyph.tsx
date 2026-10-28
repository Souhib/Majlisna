import { cn } from "@/lib/utils"

/**
 * TeamGlyph: the shape that goes with every team colour, so a colour never carries
 * information alone (colour-blind players, greyscale screens).
 *
 *   madder     ▲ the tooth (ḍurūs)         team 1 (the old "red" team)
 *   indigo     ◆ the eye (ʿayn)            team 2 (the old "blue" team)
 *   bystander  ▬ plain weave
 *   assassin   ◇ crossed: black cloth
 *
 * Drawn SVG in currentColor (the assassin's is ember by default). 12 px by default.
 */
export type Team = "madder" | "indigo" | "bystander" | "assassin"

export interface TeamGlyphProps {
  team: Team
  size?: number
  /** Accessible name when no visible label accompanies it. */
  label?: string
  className?: string
}

export function TeamGlyph({ team, size = 12, label, className }: TeamGlyphProps) {
  const a11y = label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true as const }
  return (
    <svg
      viewBox="0 0 12 12"
      width={size}
      height={size}
      className={cn("shrink-0", team === "assassin" && "text-ember", className)}
      fill="currentColor"
      {...a11y}
    >
      {team === "madder" ? <path d="M6 1.2L11 10.4H1z" /> : null}
      {team === "indigo" ? <path d="M6 .8L11.2 6 6 11.2.8 6z" /> : null}
      {team === "bystander" ? <rect x="1" y="4.9" width="10" height="2.2" /> : null}
      {team === "assassin" ? (
        <>
          <path d="M6 1.2L10.8 6 6 10.8 1.2 6z" fill="none" stroke="currentColor" strokeWidth="1.3" />
          <path d="M1.8 10.2L10.2 1.8" stroke="currentColor" strokeWidth="1.4" />
        </>
      ) : null}
    </svg>
  )
}
