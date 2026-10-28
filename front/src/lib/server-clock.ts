/**
 * The server's clock, as this device can know it. Round and phase anchors
 * (`round_started_at`, `timer_started_at`) are server timestamps; reading them against
 * the device's own clock made a phone whose clock runs ahead cross a Kalimat rung before
 * the server released it (and, behind, show a rung as "now" after the server already
 * scored the next one).
 *
 * Every API response carries a `Date` header (whole seconds, stamped before the
 * response travelled), so at receipt the server's clock reads AT LEAST that value:
 * `date - receivedAt` is a lower bound of the offset. The largest one seen is the
 * tightest, and a clock corrected by it is never ahead of the server, at most about a
 * second behind. A device clock changed by hand (a jump of more than 5 s) starts again.
 * Without any header (a cross-origin API that does not expose it) the offset is 0.
 */
const CLOCK_JUMP_MS = 5000

let offsetMs: number | null = null

/** Note a response's `Date` header, received at `receivedAt` (device ms). */
export function noteServerDate(dateHeader: string | null | undefined, receivedAt = Date.now()): void {
  if (!dateHeader) return
  const server = Date.parse(dateHeader)
  if (!Number.isFinite(server)) return
  const bound = server - receivedAt
  if (offsetMs === null || bound > offsetMs || offsetMs - bound > CLOCK_JUMP_MS) offsetMs = bound
}

/** The device's estimate of the server's current time, in ms since the epoch. */
export function serverNow(): number {
  return Date.now() + (offsetMs ?? 0)
}

/** For tests: forget every sample. */
export function resetServerClock(): void {
  offsetMs = null
}
