import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Skeleton: bare warp. Unloaded content is shown as the loom before weaving: 1 px
 * vertical threads on --surface-2, still. No shimmer, no pulse (nothing loops but the
 * clock). Give it the size of what it stands for.
 *
 * <Skeleton className="h-5 w-40" />
 */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="skeleton" aria-hidden="true" className={cn("rounded-sm bg-surface-2 warp-threads", className)} {...props} />
}
