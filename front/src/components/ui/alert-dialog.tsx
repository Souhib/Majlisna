import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"
import { buttonVariants } from "./button"

/**
 * AlertDialog: confirmation that cannot be dismissed by clicking outside (kick a
 * player, delete the account, leave a game in progress). Same surface as <Dialog>.
 * The destructive action uses `variant="danger"` (ember hairline), never a red fill.
 *
 * <AlertDialog>
 *   <AlertDialogTrigger asChild><Button variant="danger">Remove Bilal</Button></AlertDialogTrigger>
 *   <AlertDialogContent>
 *     <AlertDialogTitle>…</AlertDialogTitle><AlertDialogDescription>…</AlertDialogDescription>
 *     <AlertDialogFooter>
 *       <AlertDialogCancel>Keep him</AlertDialogCancel>
 *       <AlertDialogAction variant="danger" onClick={kick}>Remove</AlertDialogAction>
 *     </AlertDialogFooter>
 *   </AlertDialogContent>
 * </AlertDialog>
 */
export const AlertDialog = AlertDialogPrimitive.Root
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger

export function AlertDialogContent({ className, ...props }: ComponentProps<typeof AlertDialogPrimitive.Content>) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Overlay
        className={cn(
          "fixed inset-0 z-50 bg-[oklch(0.1_0.01_50/0.62)]",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--dur-state)",
        )}
      />
      <AlertDialogPrimitive.Content
        data-slot="alert-dialog-content"
        className={cn(
          "fixed left-1/2 top-1/2 z-50 grid w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 gap-4",
          "rounded-lg border border-line-brass bg-popover p-5 text-popover-foreground shadow-[0_24px_48px_-24px_oklch(0_0_0/0.45)] sm:p-6",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--dur-state)",
          className,
        )}
        {...props}
      />
    </AlertDialogPrimitive.Portal>
  )
}

export function AlertDialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("grid gap-1.5 text-start", className)} {...props} />
}

export function AlertDialogFooter({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mt-2 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end", className)} {...props} />
}

export function AlertDialogTitle({ className, ...props }: ComponentProps<typeof AlertDialogPrimitive.Title>) {
  return <AlertDialogPrimitive.Title className={cn("type-title text-[24px]", className)} {...props} />
}

export function AlertDialogDescription({ className, ...props }: ComponentProps<typeof AlertDialogPrimitive.Description>) {
  return (
    <AlertDialogPrimitive.Description className={cn("text-[15px] leading-normal text-muted-foreground", className)} {...props} />
  )
}

export function AlertDialogAction({
  className,
  variant = "primary",
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Action> & { variant?: "primary" | "danger" }) {
  return <AlertDialogPrimitive.Action className={cn(buttonVariants({ variant }), className)} {...props} />
}

export function AlertDialogCancel({ className, ...props }: ComponentProps<typeof AlertDialogPrimitive.Cancel>) {
  return <AlertDialogPrimitive.Cancel className={cn(buttonVariants({ variant: "secondary" }), className)} {...props} />
}
