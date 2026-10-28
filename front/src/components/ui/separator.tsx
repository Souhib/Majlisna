import * as SeparatorPrimitive from "@radix-ui/react-separator"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Separator. `variant="brass"` (default) is Qandil's rule: a brass hairline broken
 * once, at its centre, by a lozenge. `variant="line"` is a plain 1 px --line divider
 * for lists. Vertical separators are always plain.
 *
 * <Separator />                      // brass rule with lozenge
 * <Separator variant="line" />       // list divider
 * <Separator orientation="vertical" className="h-5" />
 */
export interface SeparatorProps extends ComponentProps<typeof SeparatorPrimitive.Root> {
  variant?: "brass" | "line"
}

export function Separator({ variant = "brass", orientation = "horizontal", decorative = true, className, ...props }: SeparatorProps) {
  if (orientation === "vertical") {
    return (
      <SeparatorPrimitive.Root
        data-slot="separator"
        orientation="vertical"
        decorative={decorative}
        className={cn("w-px self-stretch bg-line-brass", className)}
        {...props}
      />
    )
  }
  if (variant === "line") {
    return <SeparatorPrimitive.Root data-slot="separator" decorative={decorative} className={cn("h-px w-full bg-line", className)} {...props} />
  }
  return (
    <SeparatorPrimitive.Root data-slot="separator" decorative={decorative} className={cn("relative flex h-[9px] w-full items-center", className)} {...props}>
      <span aria-hidden="true" className="h-px flex-1 bg-line-brass" />
      <span aria-hidden="true" className="mx-[9px] size-[7px] rotate-45 bg-brass" />
      <span aria-hidden="true" className="h-px flex-1 bg-line-brass" />
    </SeparatorPrimitive.Root>
  )
}
