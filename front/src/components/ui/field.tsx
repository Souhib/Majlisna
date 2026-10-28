import { createContext, type ComponentProps, type ReactNode, useContext, useId } from "react"
import { cn } from "@/lib/utils"

/**
 * Field + Input + Textarea (sketch section C: "Display name", "Room code" with error).
 *
 * <Field label="Room code" hint="Five letters" error={err}>
 *   <Input value={code} onChange={…} />
 * </Field>
 *
 * Field wires the ids: the control gets `id` (or the one you pass to Field), the hint and
 * the error are linked through aria-describedby, and `aria-invalid` is set when there is
 * an error. The error renders with role="alert" and names the problem AND the repair
 * ("No open room with that code. Check the letters with your host.").
 * Controls are 48 px, a 1 px hairline on --surface; focus is a brass border plus a 45 %
 * brass outline; error is an ember border.
 */
interface FieldContextValue {
  id: string
  describedBy?: string
  invalid: boolean
}

const FieldContext = createContext<FieldContextValue | null>(null)

/** The ids and state of the enclosing Field, for custom controls. */
export function useField() {
  return useContext(FieldContext)
}

export interface FieldProps {
  label: ReactNode
  /** Short guidance under the control. Hidden while an error is shown. */
  hint?: ReactNode
  /** The problem and its repair. Rendered with role="alert". */
  error?: ReactNode
  /** Id for the control; generated when omitted. */
  id?: string
  /** Visually hide the label (it stays the accessible name). */
  hideLabel?: boolean
  /** Extra element at the end of the label row (e.g. "Forgot password?"). */
  labelEnd?: ReactNode
  className?: string
  children: ReactNode
  /** data-testid for the error message (the auth E2E suite reads "form-error"). */
  errorTestId?: string
}

export function Field({ label, hint, error, id, hideLabel, labelEnd, className, children, errorTestId }: FieldProps) {
  const generated = useId()
  const controlId = id ?? `field-${generated}`
  const hintId = hint ? `${controlId}-hint` : undefined
  const errorId = error ? `${controlId}-error` : undefined
  const describedBy = [errorId, error ? undefined : hintId].filter(Boolean).join(" ") || undefined
  return (
    <FieldContext.Provider value={{ id: controlId, describedBy, invalid: Boolean(error) }}>
      <div data-slot="field" className={cn("grid gap-1.5", className)}>
        <div className={cn("flex items-baseline justify-between gap-3", hideLabel && !labelEnd && "sr-only")}>
          <label htmlFor={controlId} className={cn("type-label", hideLabel && "sr-only")}>
            {label}
          </label>
          {labelEnd}
        </div>
        {children}
        {error ? (
          <p id={errorId} role="alert" data-testid={errorTestId} className="text-[13px] leading-[1.45] text-ember">
            {error}
          </p>
        ) : hint ? (
          <p id={hintId} className="text-[13px] leading-[1.45] text-muted-foreground">
            {hint}
          </p>
        ) : null}
      </div>
    </FieldContext.Provider>
  )
}

const controlBase = [
  "w-full rounded-sm border border-line-field bg-surface text-foreground font-sans font-normal",
  "placeholder:text-muted-foreground",
  "transition-[border-color,outline-color] duration-(--dur-state) ease-out",
  "outline-2 outline-offset-2 outline-transparent",
  "focus-visible:border-brass focus-visible:outline-[color-mix(in_oklch,var(--brass)_45%,transparent)]",
  "aria-invalid:border-ember",
  "disabled:cursor-not-allowed disabled:border-dashed disabled:opacity-70",
]

export function Input({ className, id, "aria-describedby": describedBy, "aria-invalid": invalid, ...props }: ComponentProps<"input">) {
  const field = useField()
  return (
    <input
      data-slot="input"
      id={id ?? field?.id}
      aria-describedby={describedBy ?? field?.describedBy}
      aria-invalid={invalid ?? (field?.invalid || undefined)}
      className={cn(controlBase, "h-12 px-3.5 text-base", className)}
      {...props}
    />
  )
}

export function Textarea({ className, id, "aria-describedby": describedBy, "aria-invalid": invalid, ...props }: ComponentProps<"textarea">) {
  const field = useField()
  return (
    <textarea
      data-slot="textarea"
      id={id ?? field?.id}
      aria-describedby={describedBy ?? field?.describedBy}
      aria-invalid={invalid ?? (field?.invalid || undefined)}
      className={cn(controlBase, "min-h-24 px-3.5 py-3 text-base leading-normal", className)}
      {...props}
    />
  )
}
