/**
 * A word for the rooms page about what just happened to the player elsewhere: the host
 * removed them from a room ("kicked": they may join again with the code and PIN, or an
 * invite) or banned them from it ("banned": until the host lifts it). "removed" is the
 * lobby's polling fallback, where the seat is gone and no event said which it was: it
 * promises nothing (a "kicked" there told a banned player they could come back). It is not a toast
 * (toasts are only for the result of the player's own action): the page notes it here
 * before sending the player to /rooms, and /rooms takes it once and says it in an
 * inline Alert.
 *
 * In memory on purpose: a reload of /rooms later must not repeat it.
 */
export type RoomNotice = "kicked" | "banned" | "removed"

let pending: RoomNotice | null = null

export function noteRoomNotice(notice: RoomNotice): void {
  pending = notice
}

/** The notice left for the rooms page, if any; reading it clears it. */
export function takeRoomNotice(): RoomNotice | null {
  const notice = pending
  pending = null
  return notice
}
