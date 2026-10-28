import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import { type ComponentProps } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

/**
 * Dialog and Sheet (Radix Dialog). Use a dialog only when the task needs protected
 * focus or an interruption (confirm a kick, invite a friend); otherwise stay inline.
 *
 * The overlay is a flat dim (no blur); the content is a --surface panel with a brass
 * hairline, entering with a 180 ms fade (motion grammar: state). <Sheet> is the same
 * primitive anchored to the bottom on phones (side="bottom") or to the inline start/end.
 *
 * <Dialog open={open} onOpenChange={setOpen}>
 *   <DialogContent>
 *     <DialogHeader><DialogTitle>…</DialogTitle><DialogDescription>…</DialogDescription></DialogHeader>
 *     …
 *     <DialogFooter><Button>…</Button></DialogFooter>
 *   </DialogContent>
 * </Dialog>
 */
export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close
export const DialogPortal = DialogPrimitive.Portal

export function DialogOverlay({ className, ...props }: ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-[oklch(0.1_0.01_50/0.62)]",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
        "duration-(--dur-state)",
        className,
      )}
      {...props}
    />
  )
}

function CloseButton() {
  const { t } = useTranslation()
  return (
    <DialogPrimitive.Close
      className="absolute end-3 top-3 grid size-11 place-items-center rounded-sm text-muted-foreground transition-colors duration-(--dur-state) hover:text-foreground focus-visible:outline-2 focus-visible:outline-focus"
      aria-label={t("ui.close")}
    >
      <X className="size-[18px]" strokeWidth={1.6} />
    </DialogPrimitive.Close>
  )
}

export interface DialogContentProps extends ComponentProps<typeof DialogPrimitive.Content> {
  /** Hide the corner close button (when the footer carries the only way out). */
  hideClose?: boolean
}

export function DialogContent({ className, children, hideClose, ...props }: DialogContentProps) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn(
          "fixed left-1/2 top-1/2 z-50 grid max-h-[calc(100dvh-32px)] w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 overflow-y-auto",
          "rounded-lg border border-line-brass bg-popover p-5 text-popover-foreground shadow-[0_24px_48px_-24px_oklch(0_0_0/0.45)] sm:p-6",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          "duration-(--dur-state)",
          className,
        )}
        {...props}
      >
        {children}
        {hideClose ? null : <CloseButton />}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

export function DialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="dialog-header" className={cn("grid gap-1.5 pe-10 text-start", className)} {...props} />
}

export function DialogFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn("mt-2 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  )
}

export function DialogTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title data-slot="dialog-title" className={cn("type-title text-[26px]", className)} {...props} />
}

export function DialogDescription({ className, ...props }: ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-[15px] leading-normal text-muted-foreground", className)}
      {...props}
    />
  )
}

/* ---------------------------------------------------------------------------
   Sheet: the same dialog, docked. On phones a bottom sheet is the natural reach.
   --------------------------------------------------------------------------- */
export const Sheet = DialogPrimitive.Root
export const SheetTrigger = DialogPrimitive.Trigger
export const SheetClose = DialogPrimitive.Close

const sheetSide = {
  bottom: "inset-x-0 bottom-0 max-h-[85dvh] rounded-t-lg border-t data-[state=open]:slide-in-from-bottom-4",
  start: "inset-y-0 start-0 h-full w-[min(88vw,380px)] border-e ltr:data-[state=open]:slide-in-from-left-4 rtl:data-[state=open]:slide-in-from-right-4",
  end: "inset-y-0 end-0 h-full w-[min(88vw,380px)] border-s ltr:data-[state=open]:slide-in-from-right-4 rtl:data-[state=open]:slide-in-from-left-4",
} as const

export interface SheetContentProps extends ComponentProps<typeof DialogPrimitive.Content> {
  side?: keyof typeof sheetSide
  hideClose?: boolean
}

export function SheetContent({ side = "bottom", className, children, hideClose, ...props }: SheetContentProps) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="sheet-content"
        data-side={side}
        className={cn(
          "fixed z-50 flex flex-col gap-4 overflow-y-auto border-line-brass bg-popover p-5 text-popover-foreground",
          "pb-[max(20px,env(safe-area-inset-bottom))]",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          "duration-(--dur-move) ease-(--ease-settle)",
          sheetSide[side],
          className,
        )}
        {...props}
      >
        {children}
        {hideClose ? null : <CloseButton />}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

export const SheetHeader = DialogHeader
export const SheetTitle = DialogTitle
export const SheetDescription = DialogDescription
export const SheetFooter = DialogFooter
