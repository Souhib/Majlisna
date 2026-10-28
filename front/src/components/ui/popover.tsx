import * as PopoverPrimitive from "@radix-ui/react-popover"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Popover (Radix): a word's meaning one tap away (HintButton), the prayer times, a
 * city picker. A --popover-bg card with a brass hairline and a small brass arrow.
 *
 * <Popover>
 *   <PopoverTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="…" /></PopoverTrigger>
 *   <PopoverContent>…</PopoverContent>
 * </Popover>
 */
export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger
export const PopoverAnchor = PopoverPrimitive.Anchor
export const PopoverClose = PopoverPrimitive.Close

export interface PopoverContentProps extends ComponentProps<typeof PopoverPrimitive.Content> {
  /** Draw the small arrow toward the trigger. */
  arrow?: boolean
}

export function PopoverContent({ className, sideOffset = 8, arrow = false, children, ...props }: PopoverContentProps) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        sideOffset={sideOffset}
        collisionPadding={16}
        className={cn(
          "z-50 w-72 max-w-[calc(100vw-32px)] rounded-lg border border-line-brass bg-popover p-4 text-[15px] leading-normal text-popover-foreground",
          "shadow-[0_18px_36px_-20px_oklch(0_0_0/0.45)] outline-none",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--dur-state)",
          className,
        )}
        {...props}
      >
        {children}
        {arrow ? <PopoverPrimitive.Arrow className="fill-[var(--brass)]" width={10} height={5} /> : null}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  )
}
