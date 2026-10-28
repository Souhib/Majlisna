import { Slot, Slottable } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { type ComponentProps, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

/**
 * Button: the Samar control (sketch section C).
 *
 * - primary   brass fill at night, ink fill in the afternoon (`bg-primary`)
 * - secondary 1 px brass hairline, no fill
 * - ghost     no frame until hover (toolbars, icon buttons)
 * - danger    ember hairline and ember text, never an ember fill
 * - link      underlined in brass with a 6 px offset
 *
 * Hover mixes 12–14 % toward the text colour; press sinks 1 px for 90 ms. No gradient,
 * glow or lift. Disabled is a dashed hairline in muted ink: say WHY next to it
 * ("Waiting for 1 more player"). `loading` keeps the label and adds three lozenges,
 * sets aria-busy and blocks clicks. Heights: sm 40, md 48, lg 56, and at least 44 on
 * touch screens.
 */
export const buttonVariants = cva(
  [
    "relative inline-flex items-center justify-center gap-2.5 whitespace-nowrap rounded-sm border border-transparent",
    "font-sans font-medium leading-none select-none cursor-pointer",
    "transition-[background-color,border-color,color,translate] duration-(--dur-state) ease-out",
    "active:translate-y-px active:duration-(--dur-tap)",
    "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-focus",
    "disabled:cursor-not-allowed disabled:border-dashed disabled:border-line-brass disabled:bg-transparent disabled:text-muted-foreground disabled:active:translate-y-0",
    "aria-busy:cursor-progress",
    "[&_svg]:size-[18px] [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-[color-mix(in_oklch,var(--primary),var(--text)_14%)]",
        secondary: "border-line-brass-strong text-foreground hover:bg-[color-mix(in_oklch,var(--brass)_12%,transparent)]",
        ghost: "text-foreground hover:bg-[color-mix(in_oklch,var(--brass)_10%,transparent)]",
        danger:
          "border-[color-mix(in_oklch,var(--ember)_70%,transparent)] text-ember hover:bg-[color-mix(in_oklch,var(--ember)_10%,transparent)]",
        link: "h-auto! px-0! text-foreground underline decoration-line-brass-strong decoration-1 underline-offset-[6px] hover:decoration-brass",
      },
      size: {
        sm: "h-10 px-4 text-sm pointer-coarse:h-11",
        md: "h-12 px-[22px] text-[15px]",
        lg: "h-14 px-[26px] text-[17px]",
        icon: "size-11 p-0",
        "icon-sm": "size-9 p-0 pointer-coarse:size-11",
      },
      block: {
        true: "w-full",
        false: "",
      },
    },
    defaultVariants: { variant: "primary", size: "md", block: false },
  },
)

export interface ButtonProps extends ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  /** Render the child element (a Link, an <a>) with the button's look. */
  asChild?: boolean
  /** Keeps the label, adds three lozenges, sets aria-busy, ignores clicks. */
  loading?: boolean
  /** Icon before the label (mirrors nothing; flip directional icons with `rtl-flip`). */
  iconStart?: ReactNode
  /** Icon after the label, e.g. an arrow with `className="rtl-flip"`. */
  iconEnd?: ReactNode
}

/** The three loading lozenges ("Starting ◆◆◆"), drawn, not typed. */
export function BusyLozenges({ className }: { className?: string }) {
  return (
    <span className={cn("busy-lozenges", className)} aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  )
}

export function Button({
  className,
  variant,
  size,
  block,
  asChild = false,
  loading = false,
  iconStart,
  iconEnd,
  children,
  disabled,
  onClick,
  type,
  ...props
}: ButtonProps) {
  const { t } = useTranslation()
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, block }), className)}
      aria-busy={loading || undefined}
      disabled={asChild ? undefined : disabled}
      type={asChild ? undefined : (type ?? "button")}
      onClick={loading ? (e) => e.preventDefault() : onClick}
      {...props}
    >
      {iconStart}
      <Slottable>{children}</Slottable>
      {loading ? (
        <>
          <BusyLozenges />
          <span className="sr-only">{t("ui.loading")}</span>
        </>
      ) : (
        iconEnd
      )}
    </Comp>
  )
}
