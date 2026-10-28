import * as Menu from "@radix-ui/react-dropdown-menu"
import { Check } from "lucide-react"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * DropdownMenu (Radix). A --popover-bg sheet with a brass hairline; items are 40 px
 * rows (44 on touch), the highlighted row takes a faint brass wash, the checked radio
 * or checkbox shows a lozenge or a check. Keyboard and typeahead come from Radix.
 * Keep the trigger's existing aria-label/data-testid (E2E: "user-menu-trigger",
 * "View profile and more", "Switch language").
 *
 * <DropdownMenu>
 *   <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="…">…</Button></DropdownMenuTrigger>
 *   <DropdownMenuContent align="end">
 *     <DropdownMenuLabel>…</DropdownMenuLabel>
 *     <DropdownMenuItem onSelect={…}>…</DropdownMenuItem>
 *     <DropdownMenuSeparator />
 *   </DropdownMenuContent>
 * </DropdownMenu>
 */
export const DropdownMenu = Menu.Root
export const DropdownMenuTrigger = Menu.Trigger
export const DropdownMenuGroup = Menu.Group
export const DropdownMenuRadioGroup = Menu.RadioGroup
export const DropdownMenuSub = Menu.Sub

const itemBase = [
  "relative flex min-h-10 cursor-pointer select-none items-center gap-2.5 rounded-sm px-3 text-[14.5px] leading-tight outline-none",
  "pointer-coarse:min-h-11",
  "data-[highlighted]:bg-[color-mix(in_oklch,var(--brass)_12%,transparent)] data-[highlighted]:text-foreground",
  "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
  "[&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
]

export function DropdownMenuContent({ className, sideOffset = 6, ...props }: ComponentProps<typeof Menu.Content>) {
  return (
    <Menu.Portal>
      <Menu.Content
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-[12rem] overflow-hidden rounded-lg border border-line-brass bg-popover p-1.5 text-popover-foreground",
          "shadow-[0_18px_36px_-20px_oklch(0_0_0/0.45)]",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--dur-state)",
          className,
        )}
        {...props}
      />
    </Menu.Portal>
  )
}

export function DropdownMenuItem({ className, inset, ...props }: ComponentProps<typeof Menu.Item> & { inset?: boolean }) {
  return <Menu.Item data-slot="dropdown-menu-item" className={cn(itemBase, inset && "ps-8", className)} {...props} />
}

export function DropdownMenuCheckboxItem({ className, children, ...props }: ComponentProps<typeof Menu.CheckboxItem>) {
  return (
    <Menu.CheckboxItem className={cn(itemBase, "ps-8", className)} {...props}>
      <span className="absolute start-2.5 grid size-4 place-items-center">
        <Menu.ItemIndicator>
          <Check className="text-brass!" strokeWidth={1.8} />
        </Menu.ItemIndicator>
      </span>
      {children}
    </Menu.CheckboxItem>
  )
}

export function DropdownMenuRadioItem({ className, children, ...props }: ComponentProps<typeof Menu.RadioItem>) {
  return (
    <Menu.RadioItem className={cn(itemBase, "ps-8", className)} {...props}>
      <span className="absolute start-3 grid size-3 place-items-center">
        <Menu.ItemIndicator>
          <span className="loz bg-brass [--loz:7px]" aria-hidden="true" />
        </Menu.ItemIndicator>
      </span>
      {children}
    </Menu.RadioItem>
  )
}

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof Menu.Label>) {
  return <Menu.Label className={cn("px-3 pb-1.5 pt-2 type-meta", className)} {...props} />
}

export function DropdownMenuSeparator({ className, ...props }: ComponentProps<typeof Menu.Separator>) {
  return <Menu.Separator className={cn("-mx-1.5 my-1.5 h-px bg-line", className)} {...props} />
}

export const DropdownMenuSubTrigger = Menu.SubTrigger
export const DropdownMenuSubContent = Menu.SubContent
