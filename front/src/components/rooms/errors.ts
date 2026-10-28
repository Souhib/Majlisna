import { getApiErrorMessage } from "@/api/client"

/**
 * The server's own words when it answered (translated through `error_key` by
 * getApiErrorMessage), our fallback when it did not. A timeout or a dropped connection
 * has no response, and getApiErrorMessage would otherwise show the raw transport error
 * ("Request timed out: PATCH http://…/api/v1/rooms/join") to the player.
 */
export function roomErrorMessage(error: unknown, fallback: string): string {
  const answered = typeof error === "object" && error !== null && "response" in error && Boolean((error as { response?: unknown }).response)
  return answered ? getApiErrorMessage(error, fallback) : fallback
}
