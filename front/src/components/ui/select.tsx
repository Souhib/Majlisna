import * as SelectPrimitive from "@radix-ui/react-select"
import { Check, ChevronDown } from "lucide-react"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Select (Radix): a 48 px control that matches <Input>, opening a --popover-bg list
 * with a brass hairline. Use inside <Field> for the label (pass Field's id to the
 * trigger with `id`).
 *
 * <Select value={difficulty} onValueChange={setDifficulty}>
 *   <SelectTrigger id="difficulty"><SelectValue placeholder="…" /></SelectTrigger>
 *   <SelectContent>
 *     <SelectItem value="mixed">Mixed</SelectItem> …
 *   </SelectContent>
 * </Select>
 */
export const Select = SelectPrimitive.Root
export const SelectGroup = SelectPrimitive.Group
export const SelectValue = SelectPrimitive.Value

export function SelectTrigger({ className, children, ...props }: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        "flex h-12 w-full items-center justify-between gap-2 rounded-sm border border-line-field bg-surface px-3.5 text-start text-base font-normal text-foreground",
        "outline-2 outline-offset-2 outline-transparent transition-[border-color,outline-color] duration-(--dur-state)",
        "focus-visible:border-brass focus-visible:outline-[color-mix(in_oklch,var(--brass)_45%,transparent)]",
        "data-[placeholder]:text-muted-foreground aria-invalid:border-ember disabled:cursor-not-allowed disabled:opacity-60",
        "[&>span]:truncate",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.6} />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )
}

export function SelectContent({ className, children, position = "popper", ...props }: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        position={position}
        sideOffset={6}
        className={cn(
          "relative z-50 max-h-[min(var(--radix-select-content-available-height),320px)] min-w-[var(--radix-select-trigger-width)] overflow-hidden",
          "rounded-lg border border-line-brass bg-popover p-1.5 text-popover-foreground shadow-[0_18px_36px_-20px_oklch(0_0_0/0.45)]",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--dur-state)",
          className,
        )}
        {...props}
      >
        <SelectPrimitive.Viewport>{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  )
}

export function SelectItem({ className, children, ...props }: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex min-h-10 cursor-pointer select-none items-center rounded-sm pe-3 ps-8 text-[15px] outline-none pointer-coarse:min-h-11",
        "data-[highlighted]:bg-[color-mix(in_oklch,var(--brass)_12%,transparent)]",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <span className="absolute start-2.5 grid size-4 place-items-center">
        <SelectPrimitive.ItemIndicator>
          <Check className="size-4 text-brass" strokeWidth={1.8} />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  )
}

export function SelectSeparator({ className, ...props }: ComponentProps<typeof SelectPrimitive.Separator>) {
  return <SelectPrimitive.Separator className={cn("-mx-1.5 my-1.5 h-px bg-line", className)} {...props} />
}
