/**
 * A word for the rooms page about what just happened to the player elsewhere: the host
 * removed them from a room. It is not a toast (toasts are only for the result of the
 * player's own action): the lobby notes it here before sending the player to /rooms,
 * and /rooms takes it once and says it in an inline Alert.
 *
 * In memory on purpose: a reload of /rooms later must not repeat it.
 */
export type RoomNotice = "kicked"

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
