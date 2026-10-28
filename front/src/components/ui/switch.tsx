import * as SwitchPrimitive from "@radix-ui/react-switch"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Switch (Radix): a 2 px-radius track with a lozenge thumb. Off is a hairline track
 * with a muted lozenge; on fills the track with --primary and the lozenge takes
 * --on-primary. The hit area is 44 px tall around a 24 px track.
 *
 * <label className="flex items-center gap-3"><Switch checked={…} onCheckedChange={…} /> Mr. White</label>
 */
export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "group/switch relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-sm border border-line-brass-strong bg-surface-2",
        "before:absolute before:-inset-y-2.5 before:inset-x-0 before:content-['']",
        "transition-[background-color,border-color] duration-(--dur-state) ease-out",
        "data-[state=checked]:border-primary data-[state=checked]:bg-primary",
        "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-focus",
        "disabled:cursor-not-allowed disabled:border-dashed disabled:opacity-60",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          "pointer-events-none block size-[11px] rotate-45 bg-muted-foreground",
          "translate-x-[6px] rtl:-translate-x-[6px]",
          "transition-[translate,background-color] duration-(--dur-state) ease-out",
          "data-[state=checked]:translate-x-[26px] data-[state=checked]:bg-primary-foreground rtl:data-[state=checked]:-translate-x-[26px]",
        )}
      />
    </SwitchPrimitive.Root>
  )
}
