/**
 * True when a game-state request failed because the game is gone for this player: it
 * no longer exists (404), was cancelled, or they were removed from it. The pages then
 * say so and take the player home instead of showing a crash screen.
 *
 * Decided on the status and the server's untranslated message, never on the text the
 * player sees: `getApiErrorMessage` translates through `error_key`, so in Arabic or
 * French a "not found" test on it never matched and the redirect never happened.
 */
export function isGameGoneError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false
  const response = (error as { response?: { status?: number; data?: unknown } }).response
  if (response?.status === 404 || response?.status === 410) return true
  const data = response?.data as { message?: unknown; error?: unknown } | null | undefined
  const raw = [data?.message, data?.error].filter((v): v is string => typeof v === "string").join(" ")
  return /not ?found|cancell?ed|removed/i.test(raw)
}
