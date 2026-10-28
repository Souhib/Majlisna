import { type ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * EmptyState: nothing here yet, said plainly, with the next action. A lozenge on bare
 * warp marks the empty place (no illustration, no floating object, no emoji).
 *
 * <EmptyState
 *   title="No friends yet"
 *   description="Invite the people you play with; they will show up here."
 *   action={<Button>Invite a friend</Button>}
 * />
 */
export interface EmptyStateProps {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  /** Replace the default lozenge mark (e.g. a lucide icon at 1.6 px stroke). */
  mark?: ReactNode
  /** Heading level for the title. */
  titleAs?: "h1" | "h2" | "h3" | "p"
  className?: string
}

export function EmptyState({ title, description, action, mark, titleAs: Title = "h3", className }: EmptyStateProps) {
  return (
    <div data-slot="empty-state" className={cn("flex flex-col items-center px-4 py-10 text-center", className)}>
      <div aria-hidden="true" className="mb-5 grid h-12 w-24 place-items-center rounded-sm bg-surface-2 warp-threads text-brass">
        {mark ?? <span className="loz bg-brass [--loz:12px]" />}
      </div>
      <Title className="type-panel text-foreground">{title}</Title>
      {description ? <p className="mt-2 max-w-[46ch] text-[15px] leading-normal text-muted-foreground text-pretty">{description}</p> : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2.5">{action}</div> : null}
    </div>
  )
}
