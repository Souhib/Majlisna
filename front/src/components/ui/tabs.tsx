import * as TabsPrimitive from "@radix-ui/react-tabs"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Tabs, segmented (the lobby's game picker in sketch D): one brass-hairline strip,
 * equal cells divided by hairlines, the selected cell raised to --surface with a 2 px
 * underline in --primary. Arrow keys move between cells (Radix), and the order follows
 * the reading direction.
 *
 * <Tabs value={game} onValueChange={setGame}>
 *   <TabsList aria-label="Game">
 *     <TabsTrigger value="undercover">Undercover</TabsTrigger> …
 *   </TabsList>
 *   <TabsContent value="undercover">…</TabsContent>
 * </Tabs>
 *
 * For a choice that is a setting rather than a view (no panels), keep the same look on a
 * radio group: TabsList/TabsTrigger without TabsContent is fine, since Radix still
 * exposes a tablist; prefer a native radio group when the choice submits with a form.
 */
export const Tabs = TabsPrimitive.Root

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn("grid auto-cols-fr grid-flow-col overflow-hidden rounded-sm border border-line-brass", className)}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "relative flex h-10 min-w-0 items-center justify-center gap-2 px-2 text-[13px] font-medium leading-none text-muted-foreground",
        "border-s border-line-brass first:border-s-0 pointer-coarse:h-11",
        "transition-[color,background-color,box-shadow] duration-(--dur-state) ease-out",
        "hover:text-foreground",
        "data-[state=active]:bg-surface data-[state=active]:text-foreground data-[state=active]:shadow-[inset_0_-2px_0_var(--primary)]",
        "focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content data-slot="tabs-content" className={cn("mt-4 outline-none", className)} {...props} />
}
