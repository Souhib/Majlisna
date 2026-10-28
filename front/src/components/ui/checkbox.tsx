import * as CheckboxPrimitive from "@radix-ui/react-checkbox"
import { Check, Minus } from "lucide-react"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Checkbox (Radix): a 20 px square with a hairline; checked fills with --primary and
 * draws a 1.8 px check in --on-primary. The hit area extends to 44 px. Pair it with a
 * <label htmlFor> (or wrap both in a <label>).
 */
export function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative grid size-5 shrink-0 cursor-pointer place-items-center rounded-sm border border-line-brass-strong bg-surface",
        "before:absolute before:-inset-3 before:content-['']",
        "transition-[background-color,border-color] duration-(--dur-tap) ease-out",
        "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
        "data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground",
        "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-focus",
        "aria-invalid:border-ember disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="grid place-items-center">
        {props.checked === "indeterminate" ? <Minus className="size-3.5" strokeWidth={2} /> : <Check className="size-3.5" strokeWidth={2} />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}
