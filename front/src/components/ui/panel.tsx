import { Slot } from "@radix-ui/react-slot"
import { type ComponentProps, type ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Panel: the one container (sketch section C). A 1 px hairline on --surface, 3 px
 * radius, 22 px padding (16 on phones). Never nest panels: inside a panel, group with
 * spacing and <Separator>.
 *
 * - `tone="brass"` swaps the hairline for brass (an invitation, the halqa card)
 * - `nodes` adds the two brass lozenges riding the top edge (the hero halqa card)
 * - `flush` drops the padding (lists, boards that run to the edge)
 *
 * <Panel>
 *   <PanelHeader title="Kalimat" sub="Round 3 of 7 · a person" end={<ThreadClock … />} />
 *   …
 * </Panel>
 */
export interface PanelProps extends ComponentProps<"section"> {
  tone?: "line" | "brass"
  nodes?: boolean
  flush?: boolean
  asChild?: boolean
}

export function Panel({ tone = "line", nodes = false, flush = false, asChild, className, ...props }: PanelProps) {
  const Comp = asChild ? Slot : "section"
  return (
    <Comp
      data-slot="panel"
      className={cn(
        "relative min-w-0 rounded-lg border bg-surface text-foreground",
        tone === "brass" ? "border-line-brass" : "border-line",
        !flush && "p-4 sm:p-[22px]",
        nodes && "panel-nodes",
        className,
      )}
      {...props}
    />
  )
}

export interface PanelHeaderProps extends Omit<ComponentProps<"div">, "title"> {
  title: ReactNode
  /** Secondary line beside the title (muted). */
  sub?: ReactNode
  /** Status or controls at the inline end (wraps under on phones). */
  end?: ReactNode
  /** Heading element for the title; h2 by default so the outline stays correct. */
  titleAs?: "h2" | "h3" | "h4"
}

export function PanelHeader({ title, sub, end, titleAs: Title = "h2", className, ...props }: PanelHeaderProps) {
  return (
    <div data-slot="panel-header" className={cn("mb-4 flex flex-wrap items-center gap-x-3.5 gap-y-2", className)} {...props}>
      <Title className="type-panel">{title}</Title>
      {sub ? <span className="text-[13px] leading-tight text-muted-foreground">{sub}</span> : null}
      {end ? <div className="flex w-full items-center gap-2 sm:ms-auto sm:w-auto">{end}</div> : null}
    </div>
  )
}
