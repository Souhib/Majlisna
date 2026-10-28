import { cva, type VariantProps } from "class-variance-authority"
import { type ComponentProps, type ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Chip and Badge.
 *
 * Chip: a 30 px label with a hairline on --surface-2 (team chips, role chips, seat
 * states, filters). A colour never carries meaning alone: pass `mark` (a <Lozenge>, a
 * <TeamGlyph>, a woven swatch) so the chip reads in greyscale too.
 *   <Chip mark={<TeamGlyph team="madder" />} swatch="teeth">Red <b className="num">7</b></Chip>
 *   <Chip mark={<Lozenge state="madder" />}>Undercover</Chip>
 *
 * tone: neutral (default) · brass (yours, current, earned) · ember (an error state).
 * Text on a tint always uses an -on-tint token (>= 4.5:1, see front/CLAUDE.md).
 *
 * Badge: the small inline count or status, 22 px, tabular figures.
 */
export const chipVariants = cva(
  "inline-flex h-[30px] max-w-full items-center gap-[7px] whitespace-nowrap rounded-sm border text-[13px] font-medium leading-none",
  {
    variants: {
      tone: {
        neutral: "border-line bg-surface-2 text-foreground",
        brass: "border-line-brass-strong bg-[color-mix(in_oklch,var(--brass)_10%,var(--surface))] text-primary-on-tint",
        ember: "border-[color-mix(in_oklch,var(--ember)_55%,transparent)] bg-[color-mix(in_oklch,var(--ember)_8%,var(--surface))] text-destructive-on-tint",
        outline: "border-line-brass bg-transparent text-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
)

export interface ChipProps extends ComponentProps<"span">, VariantProps<typeof chipVariants> {
  /** A shape before the label: Lozenge, TeamGlyph, an icon. */
  mark?: ReactNode
  /** A 20 px woven swatch at the start (team chips): the band's name. */
  swatch?: "teeth" | "ayn" | "plain" | "goat" | "madd"
}

export function Chip({ tone, mark, swatch, className, children, ...props }: ChipProps) {
  return (
    <span data-slot="chip" className={cn(chipVariants({ tone }), swatch ? "ps-1 pe-2.5" : "px-2.5", className)} {...props}>
      {swatch ? (
        <i
          aria-hidden="true"
          className="block size-5 shrink-0 rounded-[1px]"
          style={{ background: `var(--band-${swatch === "madd" ? "madd" : swatch}) left / auto 100% repeat-x` }}
        />
      ) : null}
      {mark}
      {children}
    </span>
  )
}

export interface BadgeProps extends ComponentProps<"span"> {
  tone?: "neutral" | "brass" | "ember"
}

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      data-slot="badge"
      className={cn(
        "inline-flex h-[22px] min-w-[22px] items-center justify-center gap-1 rounded-sm border px-1.5 text-[12px] font-medium leading-none num",
        tone === "neutral" && "border-line bg-surface-2 text-muted-foreground",
        tone === "brass" && "border-brass bg-brass text-on-brass",
        tone === "ember" && "border-[color-mix(in_oklch,var(--ember)_55%,transparent)] text-destructive-on-tint",
        className,
      )}
      {...props}
    />
  )
}
