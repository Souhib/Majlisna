import { type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Chip } from "@/components/ui/chip"
import { cn } from "@/lib/utils"

/**
 * The pieces every page of the player's space shares (profile, stats, achievements,
 * challenges, friends, leaderboard, a player's page). Operate mode: scanability first,
 * the brand in the details: Marcellus titles, hairlines, Readex tabular figures.
 */

/** The page's one title (Marcellus) with an optional lede and actions at the inline end. */
export function PageHeader({
  title,
  lede,
  end,
  className,
}: {
  title: ReactNode
  lede?: ReactNode
  end?: ReactNode
  className?: string
}) {
  return (
    <header
      className={cn("mb-[clamp(24px,3.5vw,44px)] flex flex-wrap items-end justify-between gap-x-8 gap-y-4", className)}
    >
      <div className="min-w-0 max-w-[46rem]">
        <h1 className="font-display text-[clamp(34px,3.2vw,50px)] leading-[1.06] text-balance [overflow-wrap:anywhere] rtl:leading-[1.35]">
          {title}
        </h1>
        {lede ? (
          <p className="mt-3 max-w-[56ch] text-[16px] leading-relaxed text-muted-foreground text-pretty">{lede}</p>
        ) : null}
      </div>
      {end ? <div className="flex flex-wrap items-center gap-2.5">{end}</div> : null}
    </header>
  )
}

export interface Figure {
  label: ReactNode
  value: ReactNode
  /** A short second line under the figure ("of 12 games"). */
  note?: ReactNode
  key?: string
}

/**
 * A row of figures divided by hairlines (a ledger, not a wall of cards). `framed` draws
 * the outer hairline when the figures stand alone on the page; inside a Panel leave it
 * off so nothing is boxed twice. Give it a count of items that fills its columns.
 */
export function Figures({
  items,
  className,
  framed = true,
  size = "lg",
}: {
  items: Figure[]
  className?: string
  framed?: boolean
  size?: "lg" | "md"
}) {
  return (
    <dl
      className={cn(
        "grid gap-px overflow-hidden bg-line",
        framed && "rounded-lg border border-line",
        className ?? "grid-cols-2 md:grid-cols-4",
      )}
    >
      {items.map((item, i) => (
        <div key={item.key ?? i} className={cn("min-w-0 bg-surface", framed ? "px-4 py-4 sm:px-5" : "px-4 py-3.5 sm:px-[22px]")}>
          <dt className="type-label">{item.label}</dt>
          <dd
            className={cn(
              "num mt-2 font-light leading-none text-foreground",
              size === "lg" ? "text-[clamp(28px,2.6vw,38px)]" : "text-[clamp(22px,1.8vw,26px)]",
            )}
          >
            {item.value}
          </dd>
          {item.note ? <dd className="type-meta mt-2">{item.note}</dd> : null}
        </div>
      ))}
    </dl>
  )
}

export interface SegmentOption<V extends string> {
  value: V
  label: ReactNode
  /** A count after the label (pending requests). */
  badge?: ReactNode
}

/**
 * A segmented strip of toggle buttons (the look of the lobby's game picker), for a
 * choice that changes the view below it: a sort, a list. Real buttons with
 * aria-pressed, inside a named group.
 */
export function Segmented<V extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string
  options: SegmentOption<V>[]
  value: V
  onChange: (value: V) => void
  className?: string
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn("grid auto-cols-fr grid-flow-col overflow-hidden rounded-sm border border-line-brass", className)}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "relative flex min-h-10 min-w-0 items-center justify-center gap-2 px-3 py-1.5 text-center text-[13.5px] font-medium leading-tight text-muted-foreground pointer-coarse:min-h-11 sm:px-4",
            "border-s border-line-brass first:border-s-0",
            "transition-[color,background-color,box-shadow] duration-(--dur-state) ease-out hover:text-foreground",
            "aria-pressed:bg-surface aria-pressed:text-foreground aria-pressed:shadow-[inset_0_-2px_0_var(--primary)]",
            "focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus",
          )}
        >
          <span className="min-w-0">{o.label}</span>
          {o.badge}
        </button>
      ))}
    </div>
  )
}

/** Won / lost / still playing, as a chip whose mark reads without colour. */
export function ResultChip({ won, finished }: { won: boolean | null | undefined; finished: boolean }) {
  const { t } = useTranslation()
  if (!finished) {
    return (
      <Chip tone="outline" mark={<Lozenge state="open" size={8} />}>
        {t("stats.inProgress")}
      </Chip>
    )
  }
  if (won === true) {
    return (
      <Chip tone="brass" mark={<Lozenge state="brass" size={8} />}>
        {t("stats.won")}
      </Chip>
    )
  }
  if (won === false) {
    return (
      <Chip mark={<Lozenge state="away" size={8} />}>
        {t("stats.lost")}
      </Chip>
    )
  }
  return null
}
