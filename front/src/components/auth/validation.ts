/**
 * Client-side checks for the auth forms. They mirror the server's rules (backend
 * constants PASSWORD_MIN_LENGTH 8, USERNAME_MIN/MAX_LENGTH 3/30, the username pattern
 * `^[^\s<>/\\@]+$`) so a player hears what to fix in their own language, before a round
 * trip, instead of the browser's validation bubble (which speaks the browser's language,
 * not the page's). The server stays the authority: its errors still reach the form.
 *
 * Every function returns an i18n KEY (or undefined): the page translates it, so a
 * language switch re-renders the message.
 */
export const PASSWORD_MIN_LENGTH = 8
export const USERNAME_MIN_LENGTH = 3
export const USERNAME_MAX_LENGTH = 30

export type AuthField = "username" | "email" | "password" | "confirmPassword"
export type AuthFieldErrors = Partial<Record<AuthField, string>>

/** Something@something.tld, no spaces: what the server's EmailStr will accept at least. */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
/** The characters the server's username pattern refuses. */
const USERNAME_FORBIDDEN = /[\s<>/\\@]/

export function emailError(email: string): string | undefined {
  const value = email.trim()
  if (!value) return "auth.errors.emailRequired"
  if (!EMAIL_SHAPE.test(value)) return "auth.errors.emailInvalid"
  return undefined
}

/** The password of an existing account: only presence is checked. */
export function currentPasswordError(password: string): string | undefined {
  return password ? undefined : "auth.errors.passwordRequired"
}

/** A password being chosen (register, reset): the server's minimum length. */
export function newPasswordError(password: string): string | undefined {
  return password.length < PASSWORD_MIN_LENGTH ? "auth.passwordTooShort" : undefined
}

export function usernameError(username: string): string | undefined {
  const length = Array.from(username).length
  if (length < USERNAME_MIN_LENGTH || length > USERNAME_MAX_LENGTH) return "auth.errors.usernameLength"
  if (USERNAME_FORBIDDEN.test(username)) return "auth.errors.usernameCharacters"
  return undefined
}

export function confirmError(password: string, confirmation: string): string | undefined {
  return password === confirmation ? undefined : "auth.passwordsDoNotMatch"
}

/** Drop the fields without an error; an empty result means the form may be sent. */
export function compactErrors(errors: AuthFieldErrors): AuthFieldErrors {
  return Object.fromEntries(Object.entries(errors).filter(([, v]) => Boolean(v))) as AuthFieldErrors
}

/** The server's error key for a reset or verification link it refuses. */
export const TOKEN_REJECTED_KEY = "errors.api.invalidOrExpiredToken"

/** The `error_key` of an API error, when the server sent one. */
export function apiErrorKey(error: unknown): string | undefined {
  const data = (error as { response?: { data?: { error_key?: unknown } } } | null)?.response?.data
  return typeof data?.error_key === "string" ? data.error_key : undefined
}

/**
 * Put the caret in the first field (in the form's order) that needs fixing, so a
 * keyboard or screen-reader user lands on the repair. The ids are the inputs' own.
 */
export function focusFirstError(errors: AuthFieldErrors, order: AuthField[]) {
  const first = order.find((field) => errors[field])
  if (!first) return
  document.getElementById(first)?.focus()
}
