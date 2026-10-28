import { type CSSProperties } from "react"
import { cn } from "@/lib/utils"

/**
 * Lozenge: the diamond, taken from the eye of the Sadu, and the ONLY geometry in the
 * product: bullets, seats, list markers, clock beats, rule nodes.
 *
 * state
 *   host       filled brass (the ṣadr, the host's seat)
 *   ready      filled ink/cream (a seated, ready player)
 *   brass      filled brass (a bullet, a node, "yours")
 *   ink        filled text colour
 *   away       muted outline (away, in the grace period)
 *   spectator  text-colour outline
 *   open       dashed brass outline (a free seat)
 *   you        dashed brass, heavier (your seat, still to take)
 *   madder     wool madder (the Undercover role)
 *   undyed     undyed wool (the Civilian role)
 *   seal       brass with a ring (an earned mark at icon size; see <Seal> for the pressed one)
 *
 * Decorative by default (aria-hidden). Give `label` when it carries meaning alone.
 *
 * <Lozenge state="host" />  <Lozenge state="open" size={9} />
 */
export type LozengeState = "host" | "ready" | "brass" | "ink" | "away" | "spectator" | "open" | "you" | "madder" | "undyed" | "seal"

export interface LozengeProps {
  state?: LozengeState
  /** Side of the square before rotation, in px. Default 10. */
  size?: number
  /** Accessible text when the lozenge is the only carrier of the meaning. */
  label?: string
  className?: string
  style?: CSSProperties
}

export function Lozenge({ state = "brass", size = 10, label, className, style }: LozengeProps) {
  return (
    <i
      data-state={state}
      className={cn("loz", className)}
      style={{ "--loz": `${size}px`, ...style } as CSSProperties}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    />
  )
}
