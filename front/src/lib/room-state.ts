/**
 * Of two reads of a room's state, the one read last. The server stamps each state with
 * the moment it was read (`as_of_ms`, before its first query). Two reads can reach the
 * page out of order: a socket's connect read the room just before the host picked
 * another game and sent it after the pick's own push, so the lobby stayed on the old game
 * for good, with no polling while the socket is up (CI, 2026-11-01). Every change is
 * pushed by a read made after its commit, so the newest read is the true one.
 *
 * A state without the stamp (a server from before it) is taken as it comes.
 */
export function newerRoomState<T>(current: T | undefined, incoming: T): T {
  const held = readAt(current)
  const read = readAt(incoming)
  return held !== null && read !== null && read < held ? (current as T) : incoming
}

function readAt(state: unknown): number | null {
  if (!state || typeof state !== "object") return null
  const asOf = (state as { as_of_ms?: unknown }).as_of_ms
  return typeof asOf === "number" ? asOf : null
}
