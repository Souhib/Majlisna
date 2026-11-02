import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useState } from "react"
import { listRoomInvitesApiV1RoomsInvitesGetQueryKey, type RoomInviteView, useListRoomInvitesApiV1RoomsInvitesGet } from "@/api/generated"

/** The caller's stored invites as one viewer reads them: a sign-in as someone else in the tab is another read. */
export function roomInvitesKey(viewer: string | null) {
  return [...listRoomInvitesApiV1RoomsInvitesGetQueryKey(), { viewer }] as const
}

export interface RoomInvites {
  /** The invite to show (the latest pushed, else the newest stored), or null. */
  invite: RoomInviteView | null
  /** A `room_invite` push. */
  receive: (invite: RoomInviteView) => void
  /** The player answered it (Not now, Close, or seated): it shows no more, until it is re-sent. */
  answer: (invite: RoomInviteView) => void
  /** Read the stored invites again (after the personal socket reconnects: pushes are not replayed). */
  refresh: () => void
  /** Banned from this room: its invites, pushed or stored, show no more, and the stored ones are read again (the ban deleted them). */
  forgetRoom: (roomId: string) => void
}

/**
 * The friend's invite the app shell shows (`RoomInviteStrip`). Invites are stored on the
 * server: one pushed on the personal socket (`room_invite`) shows at once, and those sent
 * while the page was closed come from `GET /rooms/invites` (live ones, newest first) when
 * it opens.
 *
 * An answered invite is remembered by id with the expiry it had: a re-invite keeps the id
 * and moves `expires_at` later, so it shows again, while the stored copy of the one just
 * answered does not.
 *
 * A ban (`you_were_kicked` with `banned`, on the personal socket) deletes the invites to
 * the banned player on the server; `forgetRoom` drops the one pushed before it and the
 * stored copies of that room's, so the strip never shows that room again (a member cannot
 * invite them any more, and the server takes back an invite that raced the ban).
 */
export function useRoomInvites(viewer: string | null): RoomInvites {
  const queryClient = useQueryClient()
  const [pushed, setPushed] = useState<RoomInviteView | null>(null)
  const [answered, setAnswered] = useState<ReadonlyMap<string, number>>(() => new Map())
  const stored = useListRoomInvitesApiV1RoomsInvitesGet({
    query: { enabled: viewer !== null, queryKey: roomInvitesKey(viewer), staleTime: Number.POSITIVE_INFINITY },
  })

  const isOpen = (invite: RoomInviteView) => {
    const answeredUntil = answered.get(invite.id)
    return answeredUntil === undefined || Date.parse(invite.expires_at) > answeredUntil
  }
  const invite = pushed && isOpen(pushed) ? pushed : ((stored.data ?? []).find(isOpen) ?? null)

  const receive = useCallback((next: RoomInviteView) => setPushed(next), [])
  const answer = useCallback((done: RoomInviteView) => {
    setAnswered((previous) => {
      const next = new Map(previous)
      next.set(done.id, Math.max(Date.parse(done.expires_at), previous.get(done.id) ?? Number.NEGATIVE_INFINITY))
      return next
    })
  }, [])
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: listRoomInvitesApiV1RoomsInvitesGetQueryKey() })
  }, [queryClient])
  const forgetRoom = useCallback(
    (roomId: string) => {
      setPushed((current) => (current?.room_id === roomId ? null : current))
      // the stored copy too, at once: the strip falls back on it while the re-read is on
      // its way, and for good if that read fails
      queryClient.setQueryData<RoomInviteView[]>(roomInvitesKey(viewer), (list) => list?.filter((stored) => stored.room_id !== roomId))
      refresh()
    },
    [queryClient, refresh, viewer],
  )

  return { invite, receive, answer, refresh, forgetRoom }
}
