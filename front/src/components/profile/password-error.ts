import type { TFunction } from "i18next"
import { getApiErrorMessage } from "@/api/client"

/** What the server answers a wrong password with — the login's own error. */
const INVALID_CREDENTIALS_KEY = "errors.api.invalidCredentials"

/**
 * The refusal of a form that asks for the account's password alone (deleting the
 * account, changing the password). A wrong one is the login's 401, whose words are
 * "Please check your email and password." — and these forms have no email field
 * (review F6): it is said as a wrong password. Anything else in the server's words.
 */
export function passwordErrorMessage(error: unknown, t: TFunction): string {
  const data = (error as { response?: { data?: { error_key?: unknown } } } | null)?.response?.data
  return data?.error_key === INVALID_CREDENTIALS_KEY ? t("profile.wrongPassword") : getApiErrorMessage(error)
}
