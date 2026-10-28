import { type CSSProperties, type ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Seal: the brass achievement seal, a lozenge set in a ring. It is PRESSED ONCE when
 * it mounts (330 ms: scale 1.5 → 0.94 → 1) and then stays still; under reduced motion
 * it fades in. Achievements are sealed in the colophon at the end of the game, never
 * as mid-game toasts.
 *
 * - `progress` (0–1) draws a brass arc around it: the lawh's "hold to read" seal.
 * - `ground` is the colour the ring cuts out (defaults to --surface; pass "var(--surface-2)"
 *   on a sand tile).
 * - With `title`, renders the seal plus its label and an optional `caption` line
 *   ("Taste of Victory · Maryam"), as in the colophon.
 *
 * <Seal />  <Seal size={64} progress={0.3} pressed={false} />
 * <Seal title="Unanimous Decision" caption="the whole table" />
 */
export interface SealProps {
  /** Box size in px. Default 22 (the colophon list); 64 for the lawh seal. */
  size?: number
  /** Animate the press on mount. Default true. */
  pressed?: boolean
  /** 0–1: brass arc around the seal (hold progress). */
  progress?: number
  ground?: string
  title?: ReactNode
  caption?: ReactNode
  className?: string
}

export function Seal({ size = 22, pressed = true, progress, ground, title, caption, className }: SealProps) {
  const r = 29
  const c = 2 * Math.PI * r
  const mark = (
    <span
      aria-hidden="true"
      className={cn("brass-seal", pressed && "seal-press")}
      style={{ "--seal": `${size}px`, ...(ground ? { "--seal-ground": ground } : {}) } as CSSProperties}
    >
      {progress !== undefined ? (
        <svg viewBox="0 0 64 64">
          <circle cx="32" cy="32" r={r} stroke="var(--line-brass)" />
          <circle cx="32" cy="32" r={r} stroke="var(--brass)" strokeDasharray={`${Math.max(0, Math.min(1, progress)) * c} ${c}`} />
        </svg>
      ) : null}
    </span>
  )
  if (!title) return <span className={className}>{mark}</span>
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-[13.5px] font-medium leading-tight", className)}>
      {mark}
      <span className="block">
        {title}
        {caption ? <small className="block text-[12px] font-normal text-muted-foreground">{caption}</small> : null}
      </span>
    </span>
  )
}
