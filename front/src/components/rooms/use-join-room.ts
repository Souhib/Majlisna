import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  getActiveRoomApiV1RoomsActiveGetQueryKey,
  useAcceptRoomInviteApiV1RoomsInvitesInviteIdAcceptPost,
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

/** Where a request for a seat stands, whatever the door (a code and PIN, or an invite). */
interface SeatRequestState {
  /** What to say about the last attempt, already in the player's words; null if none. */
  error: string | null
  /** The server's `error_key` for that refusal (null without one): it picks the repair (`joinRepairFor`). */
  errorKey: string | null
  /** Set by a 409 (one room at a time): the offer to leave that room and sit here. */
  seatElsewhere: SeatElsewhere | null
  busy: boolean
}

export interface JoinRoomFlow extends SeatRequestState {
  /** Ask to sit at the table with this code and PIN. */
  join: (code: string, pin: string) => Promise<void>
  /** After a 409: leave the room the player sits in NOW, then ask again for this one. */
  leaveAndJoin: () => Promise<void>
}

export interface AcceptInviteFlow extends SeatRequestState {
  /** Sit at the table of this friend's invite (stored on the server: no PIN). */
  accept: (inviteId: string) => Promise<void>
  /** After a 409: leave the room the player sits in NOW, then accept the invite again. */
  leaveAndAccept: () => Promise<void>
}

/**
 * One request for a seat, by any door (`send`). The server seats a player in one room at
 * a time and answers 409 (`userAlreadyInRoom`) otherwise: the flow then names the other
 * room and offers to leave it. That offer reads the active room again when pressed (it
 * may have changed since the offer was drawn), leaves it through the normal leave, then
 * asks again with what was asked last.
 *
 * Every other refusal is said in the server's words and offers nothing: a ban (403
 * `roomBanned`) is not lifted by leaving another room, and asking again changes nothing.
 * `mutateAsync` throughout: per-call callbacks are lost to StrictMode's remount.
 */
function useSeatRequest<Ask>(send: (ask: Ask) => Promise<{ id?: string }>, onJoined: (roomId: string) => void) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()
  const [error, setError] = useState<string | null>(null)
  const [errorKey, setErrorKey] = useState<string | null>(null)
  const [seatedElsewhere, setSeatedElsewhere] = useState(false)
  // In flight, tracked here rather than read from the mutation's `isPending`: StrictMode's
  // mount, unmount, mount detaches the mutation observer of the request sent at mount, so
  // isPending never cleared and the "Leave {{room}} and join" offer stayed busy, its
  // presses ignored, under `bun dev` (review F8).
  const [asking, setAsking] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const lastAskRef = useRef<{ ask: Ask } | null>(null)
  const onJoinedRef = useRef(onJoined)
  onJoinedRef.current = onJoined

  // read only once the server says the player sits elsewhere: it names the offer
  const activeRoom = useGetActiveRoomApiV1RoomsActiveGet({ query: { enabled: seatedElsewhere } })

  const request = useCallback(
    async (ask: Ask) => {
      lastAskRef.current = { ask }
      setError(null)
      setErrorKey(null)
      setAsking(true)
      try {
        const room = await send(ask)
        setSeatedElsewhere(false)
        if (room.id) onJoinedRef.current(room.id)
      } catch (err) {
        const key = roomErrorKey(err)
        const elsewhere = key === ROOM_ERROR_KEYS.alreadyInRoom
        setSeatedElsewhere(elsewhere)
        setErrorKey(key)
        setError(elsewhere ? t("room.joinPage.alreadyInRoom") : roomErrorMessage(err, t("room.joinPage.unreachable")))
      } finally {
        setAsking(false)
      }
    },
    [send, t],
  )

  const { refetch: refetchActiveRoom } = activeRoom
  const leaveAndAsk = useCallback(async () => {
    const last = lastAskRef.current
    if (!last) return
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
      await request(last.ask)
    } finally {
      setLeaving(false)
    }
  }, [request, leaveMutation, queryClient, refetchActiveRoom, t])

  const seated = activeRoom.data
  const state: SeatRequestState = {
    error,
    errorKey,
    seatElsewhere: seatedElsewhere ? { roomId: seated?.room_id ?? null, code: seated?.public_id ?? null } : null,
    busy: asking || leaving,
  }
  return { request, leaveAndAsk, state }
}

/**
 * Joining by code and PIN, for the share link (/rooms/join) and the lobby's "Join this
 * room": a seat request (`useSeatRequest`: the 409 offer, the server's words for the rest).
 */
export function useJoinRoom(onJoined: (roomId: string) => void): JoinRoomFlow {
  const { mutateAsync } = useJoinRoomApiV1RoomsJoinPatch()
  const send = useCallback(
    async ({ code, pin }: { code: string; pin: string }) => (await mutateAsync({ data: { public_room_id: code, password: pin } })) as { id?: string },
    [mutateAsync],
  )
  const { request, leaveAndAsk, state } = useSeatRequest(send, onJoined)
  const join = useCallback((code: string, pin: string) => request({ code, pin }), [request])
  return { ...state, join, leaveAndJoin: leaveAndAsk }
}

/**
 * Accepting a friend's invite (`RoomInviteStrip`). The invite is stored on the server and
 * opens its room without the PIN, so a ban (of someone else) that rotated the PIN since it
 * was sent does not stop it. The same doors as a join otherwise (`useSeatRequest`): a seat elsewhere is
 * offered "Leave {{room}} and join"; a ban (403), an expired invite (410
 * `roomInviteExpired`) or one no longer valid (404) is said in the server's words.
 */
export function useAcceptInvite(onJoined: (roomId: string) => void): AcceptInviteFlow {
  const { mutateAsync } = useAcceptRoomInviteApiV1RoomsInvitesInviteIdAcceptPost()
  const send = useCallback(async (inviteId: string) => (await mutateAsync({ invite_id: inviteId })) as { id?: string }, [mutateAsync])
  const { request, leaveAndAsk, state } = useSeatRequest(send, onJoined)
  return { ...state, accept: request, leaveAndAccept: leaveAndAsk }
}
