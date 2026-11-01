import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  getActiveRoomApiV1RoomsActiveGetQueryKey,
  useGetActiveRoomApiV1RoomsActiveGet,
  useJoinRoomApiV1RoomsJoinPatch,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { ROOM_ERROR_KEYS, roomErrorKey, roomErrorMessage } from "./errors"

/** The room the player sits in now, when the server refused a join for it (409). */
export interface SeatElsewhere {
  /** Its id, for "Return to the room"; null until read. */
  roomId: string | null
  /** Its code, for "Leave {{room}} and join"; null until read. */
  code: string | null
}

export interface JoinRoomFlow {
  /** Ask to sit at the table with this code and PIN. */
  join: (code: string, pin: string) => Promise<void>
  /** After a 409: leave the room the player sits in NOW, then ask again for this one. */
  leaveAndJoin: () => Promise<void>
  /** What to say about the last attempt, already in the player's words; null if none. */
  error: string | null
  /** The server's `error_key` for that refusal (null without one): it picks the repair (`joinRepairFor`). */
  errorKey: string | null
  /** Set by a 409 (one room at a time): the offer to leave that room and sit here. */
  seatElsewhere: SeatElsewhere | null
  busy: boolean
}

/**
 * Joining by code and PIN, for the share link (/rooms/join) and the lobby's "Join this
 * room". The server seats a player in one room at a time and answers 409
 * (`userAlreadyInRoom`) otherwise: the flow then names the other room and offers to leave
 * it. That button reads the active room again when pressed (it may have changed since the
 * offer was drawn), leaves it through the normal leave, then joins.
 *
 * Every other refusal is said in the server's words and offers nothing: a ban (403
 * `roomBanned`) is not lifted by leaving another room, and asking again changes nothing.
 * `mutateAsync` throughout: per-call callbacks are lost to StrictMode's remount.
 */
export function useJoinRoom(onJoined: (roomId: string) => void): JoinRoomFlow {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const joinMutation = useJoinRoomApiV1RoomsJoinPatch()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()
  const [error, setError] = useState<string | null>(null)
  const [errorKey, setErrorKey] = useState<string | null>(null)
  const [seatedElsewhere, setSeatedElsewhere] = useState(false)
  // In flight, tracked here rather than read from `joinMutation.isPending`: StrictMode's
  // mount, unmount, mount detaches the mutation observer of the join sent at mount, so
  // isPending never cleared and the "Leave {{room}} and join" offer stayed busy, its
  // presses ignored, under `bun dev` (review F8).
  const [joining, setJoining] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const lastAskRef = useRef<{ code: string; pin: string } | null>(null)
  const onJoinedRef = useRef(onJoined)
  onJoinedRef.current = onJoined

  // read only once the server says the player sits elsewhere: it names the offer
  const activeRoom = useGetActiveRoomApiV1RoomsActiveGet({ query: { enabled: seatedElsewhere } })

  const join = useCallback(
    async (code: string, pin: string) => {
      lastAskRef.current = { code, pin }
      setError(null)
      setErrorKey(null)
      setJoining(true)
      try {
        const room = (await joinMutation.mutateAsync({ data: { public_room_id: code, password: pin } })) as { id?: string }
        setSeatedElsewhere(false)
        if (room.id) onJoinedRef.current(room.id)
      } catch (err) {
        const key = roomErrorKey(err)
        const elsewhere = key === ROOM_ERROR_KEYS.alreadyInRoom
        setSeatedElsewhere(elsewhere)
        setErrorKey(key)
        setError(elsewhere ? t("room.joinPage.alreadyInRoom") : roomErrorMessage(err, t("room.joinPage.unreachable")))
      } finally {
        setJoining(false)
      }
    },
    [joinMutation, t],
  )

  const { refetch: refetchActiveRoom } = activeRoom
  const leaveAndJoin = useCallback(async () => {
    const ask = lastAskRef.current
    if (!ask) return
    setLeaving(true)
    setError(null)
    try {
      const { data: current, error: readError } = await refetchActiveRoom()
      if (readError) {
        setError(roomErrorMessage(readError, t("room.indexPage.leaveFailed")))
        return
      }
      if (current) {
        try {
          await leaveMutation.mutateAsync({ data: { room_id: current.room_id } })
        } catch (err) {
          // already gone from it (the grace sweep, another tab): nothing left to leave
          if (roomErrorKey(err) !== ROOM_ERROR_KEYS.notInRoom) {
            setError(roomErrorMessage(err, t("room.indexPage.leaveFailed")))
            return
          }
        }
        void queryClient.invalidateQueries({ queryKey: getActiveRoomApiV1RoomsActiveGetQueryKey() })
      }
      await join(ask.code, ask.pin)
    } finally {
      setLeaving(false)
    }
  }, [join, leaveMutation, queryClient, refetchActiveRoom, t])

  const seated = activeRoom.data
  return {
    join,
    leaveAndJoin,
    error,
    errorKey,
    seatElsewhere: seatedElsewhere ? { roomId: seated?.room_id ?? null, code: seated?.public_id ?? null } : null,
    busy: joining || leaving,
  }
}
