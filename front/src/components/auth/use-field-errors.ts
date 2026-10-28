import { useCallback, useState } from "react"
import type { AuthField, AuthFieldErrors } from "./validation"

/**
 * The per-field errors of an auth form (i18n keys). `clear(field)` drops one as soon as
 * the player edits that field, so a message never outlives the mistake it names.
 */
export function useFieldErrors() {
  const [errors, setErrors] = useState<AuthFieldErrors>({})
  const clear = useCallback((field: AuthField) => {
    setErrors((prev) => {
      if (!prev[field]) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })
  }, [])
  return { errors, setErrors, clear }
}
