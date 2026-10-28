import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Alert: a message about the whole form or page (a failed sign-in, a stale lobby).
 * Field-level errors belong in <Field error>, not here.
 *
 * tone="error" is an ember hairline with ember-on-tint text and role="alert";
 * tone="info" is a brass hairline and role="status". A lozenge marks the start. No
 * coloured side stripe, no fill colour behind the text.
 *
 *   <Alert data-testid="form-error">{error}</Alert>   // keeps the auth E2E hook
 */
export interface AlertProps extends ComponentProps<"div"> {
  tone?: "error" | "info"
}

export function Alert({ tone = "error", className, children, role, ...props }: AlertProps) {
  return (
    <div
      data-slot="alert"
      data-tone={tone}
      role={role ?? (tone === "error" ? "alert" : "status")}
      className={cn(
        "flex items-baseline gap-3 rounded-sm border px-4 py-3 text-sm leading-[1.5]",
        tone === "error"
          ? "border-[color-mix(in_oklch,var(--ember)_55%,transparent)] bg-[color-mix(in_oklch,var(--ember)_6%,var(--surface))] text-destructive-on-tint"
          : "border-line-brass bg-surface text-foreground",
        className,
      )}
      {...props}
    >
      <span aria-hidden="true" className={cn("loz -translate-y-px [--loz:6px]", tone === "error" ? "bg-ember" : "bg-brass")} />
      <div className="min-w-0">{children}</div>
    </div>
  )
}
