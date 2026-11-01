import { getApiErrorMessage } from "@/api/client"

/** The room refusals the pages answer in their own way, by the server's `error_key`. */
export const ROOM_ERROR_KEYS = {
  /** 409 on join: seated in another room (the one-room rule). */
  alreadyInRoom: "errors.api.userAlreadyInRoom",
  /** 403 on join: the host removed this player from the room (owner rule (c)). */
  banned: "errors.api.roomBanned",
  /** 404 on the room state: the caller has no seat in that room. */
  notInRoom: "errors.api.userNotInRoom",
  /** 403 on join: not the room's PIN — which a kick rotates (owner rule (c)). */
  wrongPin: "errors.api.wrongRoomPassword",
} as const

/**
 * What follows a refused join: how to repair it, or nothing when nothing would.
 *
 * - `none`: a ban (it holds whatever the code and PIN; review F2) and a seat in another
 *   room (its own offer, "Leave {{room}} and join", is the repair);
 * - `pinChanged`: the PIN was refused. A link or an invite keeps the PIN it was made
 *   with, and every kick rotates it (review F1): the repair is a new link or invite;
 * - `generic`: anything else (the room closed, a code that names no room).
 */
export type JoinRepair = "none" | "pinChanged" | "generic"

export function joinRepairFor(errorKey: string | null): JoinRepair {
  if (errorKey === ROOM_ERROR_KEYS.banned || errorKey === ROOM_ERROR_KEYS.alreadyInRoom) return "none"
  if (errorKey === ROOM_ERROR_KEYS.wrongPin) return "pinChanged"
  return "generic"
}

/** Tries for the room state beyond the first, for a failure that is not a refusal. */
const ROOM_STATE_RETRIES = 2

/** The response the ky client hangs on its error (`data` is the parsed body), if any. */
function responseOf(error: unknown): { status?: unknown; data?: unknown } | null {
  if (typeof error !== "object" || error === null || !("response" in error)) return null
  const response = (error as { response?: unknown }).response
  return typeof response === "object" && response !== null ? (response as { status?: unknown; data?: unknown }) : null
}

/**
 * The server's own words when it answered (translated through `error_key` by
 * getApiErrorMessage), our fallback when it did not. A timeout or a dropped connection
 * has no response, and getApiErrorMessage would otherwise show the raw transport error
 * ("Request timed out: PATCH http://…/api/v1/rooms/join") to the player.
 */
export function roomErrorMessage(error: unknown, fallback: string): string {
  return responseOf(error) ? getApiErrorMessage(error, fallback) : fallback
}

/** The server's `error_key` ("errors.api.userAlreadyInRoom"); null without an answer. */
export function roomErrorKey(error: unknown): string | null {
  const data = responseOf(error)?.data
  const key = typeof data === "object" && data !== null ? (data as { error_key?: unknown }).error_key : undefined
  return typeof key === "string" ? key : null
}

/** A 4xx: the server answered no, and asking again will not change its answer. */
export function isRefusal(error: unknown): boolean {
  const status = responseOf(error)?.status
  return typeof status === "number" && status >= 400 && status < 500
}

/**
 * TanStack's `retry` for the room state: a refusal (a 404 for a player with no seat) is
 * final, anything else (a 5xx, a dropped connection) gets two more tries.
 */
export function retryUnlessRefused(failureCount: number, error: unknown): boolean {
  return !isRefusal(error) && failureCount < ROOM_STATE_RETRIES
}
