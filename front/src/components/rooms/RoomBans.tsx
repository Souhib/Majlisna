import { useQueryClient } from "@tanstack/react-query"
import { UserCheck } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { type RoomBanView, useLiftRoomBanApiV1RoomsRoomIdBansUserIdDelete, useListRoomBansApiV1RoomsRoomIdBansGet } from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { LoadFailed } from "@/components/stats/LoadFailed"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { retryUnlessRefused, roomErrorKey, roomErrorMessage } from "./errors"

/** 404 on a lift: the ban is already gone (the host's other tab lifted it). */
const BAN_ALREADY_LIFTED_KEY = "errors.api.roomBanNotFound"

interface RoomBansProps {
  roomId: string
  /** Only the host reads (and lifts) the bans: anyone else gets nothing, and no request. */
  isHost: boolean
  className?: string
}

/**
 * The players the host BANNED from this room (a kick is no ban, and is not listed: owner
 * decision, 2 November 2026), each with "Let {{name}} come back"
 * (`DELETE /rooms/{id}/bans/{user_id}`). Lifting does not seat the player again nor bring
 * the old PIN back: they rejoin with the room's code and its current PIN, or an invite.
 *
 * It sits under the roster, for the host only, and only once someone has been banned: a
 * lobby where nobody was is not given an empty panel. Once shown it stays, so lifting the
 * last ban leaves "No one is banned from this room." under the host's hand, with focus on
 * the panel's title. It is read again after a ban and after a lift, and on a new PIN in
 * the room state (a ban from the host's other device: `useRoomLobby`).
 *
 * A failed read is said as such (LoadFailed), never as "no one removed" (FR-7). One lift
 * at a time: a synchronous in-flight ref, so a double tap sends one request (FR-4).
 */
export function RoomBans({ roomId, isHost, className }: RoomBansProps) {
  if (!isHost) return null
  return <HostRoomBans roomId={roomId} className={className} />
}

function HostRoomBans({ roomId, className }: { roomId: string; className?: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const headingId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const { data, error, refetch, isFetching } = useListRoomBansApiV1RoomsRoomIdBansGet({ room_id: roomId }, { query: { retry: retryUnlessRefused } })
  const liftMutation = useLiftRoomBanApiV1RoomsRoomIdBansUserIdDelete()
  const [liftingId, setLiftingId] = useState<string | null>(null)
  const liftingRef = useRef(false)
  // The row being lifted and its place among the buttons, to keep the host's place.
  const liftedRef = useRef<{ id: string; index: number } | null>(null)

  const bans: RoomBanView[] = Array.isArray(data) ? data : []
  // Listed at least once in this view: the panel stays when its last row is lifted.
  // Idempotent, so writing the ref while rendering is safe under StrictMode.
  const listedRef = useRef(false)
  if (bans.length > 0) listedRef.current = true

  // After a lift the row and its focused button are gone: focus goes to the next row's
  // button (or the previous one, or the title when none is left), as in the roster.
  useEffect(() => {
    const lifted = liftedRef.current
    if (!lifted || liftingId != null || bans.some((b) => b.user_id === lifted.id)) return
    liftedRef.current = null
    const active = document.activeElement
    if (active && active !== document.body && document.contains(active)) return
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button[data-lift]") ?? [])
    const next = buttons[Math.min(lifted.index, buttons.length - 1)]
    ;(next ?? headingRef.current)?.focus()
  }, [bans, liftingId])

  const liftBan = async (ban: RoomBanView, index: number) => {
    if (liftingRef.current) return
    liftingRef.current = true
    liftedRef.current = { id: ban.user_id, index }
    setLiftingId(ban.user_id)
    try {
      await liftMutation.mutateAsync({ room_id: roomId, user_id: ban.user_id })
      dropFromList(ban.user_id)
    } catch (err) {
      if (roomErrorKey(err) === BAN_ALREADY_LIFTED_KEY) {
        // what the host asked for is already so
        dropFromList(ban.user_id)
      } else {
        liftedRef.current = null
        toast.error(roomErrorMessage(err, t("room.lobbyPage.bans.liftFailed")))
      }
    } finally {
      liftingRef.current = false
      setLiftingId(null)
      // the server's list, whatever happened (another lift, another kick meanwhile)
      void queryClient.invalidateQueries({ queryKey: queryKeys.room.bans(roomId) })
    }
  }

  const dropFromList = (userId: string) =>
    queryClient.setQueryData(queryKeys.room.bans(roomId), (old: unknown) => (Array.isArray(old) ? old.filter((b: RoomBanView) => b.user_id !== userId) : old))

  const failed = data === undefined && !!error
  // nothing to say yet (the first read), or nothing to say at all (nobody was removed)
  if (!failed && !listedRef.current) return null

  return (
    <Panel flush aria-labelledby={headingId} className={className}>
      <h2
        id={headingId}
        ref={headingRef}
        tabIndex={-1}
        className="type-panel px-4 pt-4 pb-3 outline-none focus-visible:outline-2 focus-visible:outline-focus sm:px-5"
      >
        {t("room.lobbyPage.bans.title")}
        {failed ? null : (
          <>
            {" "}
            <span className="num">({bans.length})</span>
          </>
        )}
      </h2>
      {failed ? (
        <LoadFailed error={error} onRetry={() => void refetch()} retrying={isFetching} className="border-t border-line px-4 py-4 sm:px-5" />
      ) : bans.length === 0 ? (
        <p className="border-t border-line px-4 py-4 text-[14px] text-muted-foreground sm:px-5">{t("room.lobbyPage.bans.empty")}</p>
      ) : (
        <ul ref={listRef} className="border-t border-line">
          {bans.map((ban, index) => (
            <li key={ban.user_id} className="border-b border-line px-4 last:border-b-0 sm:px-5">
              <div className="flex min-h-12 items-center justify-between gap-3 py-1">
                <span dir="auto" className="min-w-0 flex-1 truncate text-[15px] leading-tight text-muted-foreground">
                  {ban.username}
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  data-lift=""
                  loading={liftingId === ban.user_id}
                  disabled={liftingId != null && liftingId !== ban.user_id}
                  onClick={() => void liftBan(ban, index)}
                  aria-label={t("room.lobbyPage.bans.liftBan", { name: ban.username })}
                  className={cn("shrink-0 text-muted-foreground hover:text-foreground aria-busy:[&>svg]:hidden")}
                >
                  <UserCheck aria-hidden="true" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
