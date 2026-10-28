import { Eye, EyeOff } from "lucide-react"
import { type ComponentProps, useState } from "react"
import { useTranslation } from "react-i18next"
import { Input, useField } from "@/components/ui/field"
import { cn } from "@/lib/utils"

/**
 * A password Input with a show/hide toggle at its inline end (left in Arabic). Used
 * inside a <Field>, which gives it its id, label and error wiring.
 *
 * The toggle is a plain type="button" (the auth E2E specs address the one
 * button[type="submit"] of each form), a 48 px square inside the 48 px control, named
 * "Show password" with aria-pressed telling whether the text is showing. It starts
 * hidden, so the field's type is "password" on load.
 */
export function PasswordInput({ className, id, ...props }: Omit<ComponentProps<"input">, "type">) {
  const { t } = useTranslation()
  const field = useField()
  const [visible, setVisible] = useState(false)
  const controlId = id ?? field?.id

  return (
    <div className="relative">
      <Input
        {...props}
        id={controlId}
        type={visible ? "text" : "password"}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        className={cn("pe-12", className)}
      />
      <button
        type="button"
        aria-label={t("auth.showPassword")}
        aria-pressed={visible}
        aria-controls={controlId}
        onClick={() => setVisible((v) => !v)}
        className={cn(
          "absolute inset-y-0 end-0 grid w-12 cursor-pointer place-items-center rounded-sm text-muted-foreground",
          "transition-colors duration-(--dur-state) ease-out hover:text-foreground",
          "focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-focus",
          "aria-pressed:text-brass [&_svg]:size-[18px]",
        )}
      >
        {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
      </button>
    </div>
  )
}
