/**
 * What an Undercover player has already done with their tablet in this tab, kept per
 * game in sessionStorage so a reload does not undo it: the first reading dismissed
 * ("I understand"), and how many times they held the tablet to read it.
 *
 * A reload during round 1 used to send the player back to the first reading, which hid
 * the describe input, whose turn it was and what others wrote (a describer could not
 * describe until they dismissed it), and reset the read counter to "not read yet".
 * Storage can be refused (private windows): every call degrades to "nothing kept".
 */
const REVEALED = "uc-revealed:"
const READS = "uc-reads:"

export function rememberRoleRead(gameId: string): void {
  try {
    sessionStorage.setItem(`${REVEALED}${gameId}`, "1")
  } catch {
    // storage refused: the first reading may come back after a reload
  }
}

export function hasReadRole(gameId: string): boolean {
  try {
    return sessionStorage.getItem(`${REVEALED}${gameId}`) === "1"
  } catch {
    return false
  }
}

export function rememberReads(gameId: string, reads: number): void {
  try {
    sessionStorage.setItem(`${READS}${gameId}`, String(reads))
  } catch {
    // storage refused
  }
}

export function storedReads(gameId: string): number {
  try {
    const n = Number(sessionStorage.getItem(`${READS}${gameId}`))
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
  } catch {
    return 0
  }
}
