import * as ProgressPrimitive from "@radix-ui/react-progress"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Progress: how far along a challenge or an achievement is (not time: time is the
 * ThreadClock). A 4 px hairline track in --line, filled with brass from the reading
 * start. `value` is 0–100.
 *
 * <Progress value={60} aria-label="3 of 5 games" />
 */
export function Progress({ value = 0, className, ...props }: ComponentProps<typeof ProgressPrimitive.Root>) {
  const pct = Math.max(0, Math.min(100, value ?? 0))
  return (
    <ProgressPrimitive.Root data-slot="progress" value={pct} className={cn("relative h-1 w-full overflow-hidden rounded-[1px] bg-line", className)} {...props}>
      <ProgressPrimitive.Indicator
        className="absolute inset-y-0 start-0 bg-brass transition-[width] duration-(--dur-move) ease-out"
        style={{ width: `${pct}%` }}
      />
    </ProgressPrimitive.Root>
  )
}
