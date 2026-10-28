/**
 * Validates a post-login `redirect` search param. Only same-site absolute paths
 * are accepted: anything else ("//evil.example", "https://…", "/\\evil",
 * "javascript:…") would turn the login page into an open redirect.
 */
export function safeRedirect(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return undefined
  if (value.startsWith("/auth/")) return undefined
  return value
}
