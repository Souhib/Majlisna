import { useNavigate } from "@tanstack/react-router"
import { useCallback, useRef } from "react"
import { noteRoomNotice } from "@/lib/room-notice"

/**
 * What a page does when the host removes this player from the room (`you_were_kicked`
 * on the socket): note it for /rooms — a ban (`banned` true) or a kick (false), which
 * /rooms says differently, in an inline Alert (not a toast: the player did not cause it)
 * — and go there. Once, however many times it is called. Without `banned` (the lobby's
 * polling fallback, where no event arrives) nobody said which: the notice is "removed",
 * which promises nothing (a banned player must not read that they may come back).
 *
 * The game pages need it as much as the lobby: a kicked player is out of the room's
 * socket rooms, so no `game_updated` reaches them any more, and without this they sat
 * on a frozen game (still a seat at the table, still "describing…") with no way to
 * know they had been removed.
 */
export function useLeaveAfterKick(): (roomId?: string, banned?: boolean) => void {
  const navigate = useNavigate()
  const doneRef = useRef(false)
  return useCallback(
    (_roomId?: string, banned?: boolean) => {
      if (doneRef.current) return
      doneRef.current = true
      noteRoomNotice(banned === undefined ? "removed" : banned ? "banned" : "kicked")
      navigate({ to: "/rooms" })
    },
    [navigate],
  )
}
