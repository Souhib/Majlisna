import { useQueryClient } from "@tanstack/react-query"
import { UserCheck } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  type RoomBanView,
  type RoomRemovalView,
  useBanPlayerApiV1RoomsRoomIdBansPost,
  useLiftRoomBanApiV1RoomsRoomIdBansUserIdDelete,
  useListRoomBansApiV1RoomsRoomIdBansGet,
  useListRoomRemovalsApiV1RoomsRoomIdRemovalsGet,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { LoadFailed } from "@/components/stats/LoadFailed"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { ROOM_ERROR_KEYS, retryUnlessRefused, roomErrorKey, roomErrorMessage } from "./errors"
import { RemovalConfirmButton } from "./RemovalConfirmButton"

/** 404 on a lift: the ban is already gone (the host's other tab lifted it). */
const BAN_ALREADY_LIFTED_KEY = "errors.api.roomBanNotFound"

interface RoomBansProps {
  roomId: string
  /** Only the host reads (and lifts) the bans: anyone else gets nothing, and no request. */
  isHost: boolean
  className?: string
}

/**
 * The players the host BANNED from this room (a kick is no ban: owner decision, 2 November
 * 2026), each with "Let {{name}} come back" (`DELETE /rooms/{id}/bans/{user_id}`), and under
 * them the players the host REMOVED (Remove, a kick) who are neither banned nor seated again,
 * each with Ban behind the roster's own confirmation (`RemovalConfirmButton`), so a host who
 * decides after a Remove that the table does not want them back can still ban them (owner
 * request, 3 November 2026; `GET /rooms/{id}/removals`, newest first). A ban moves the row to
 * the banned list. Lifting does not seat the player again nor bring the old PIN back: they
 * rejoin with the room's code and its current PIN, or an invite.
 *
 * It sits under the roster, for the host only, and only once someone has been banned or
 * removed: a lobby where nobody was is not given an empty panel. Once shown it stays, so
 * lifting the last ban leaves "No one is banned from this room." under the host's hand, with
 * focus on the panel's title. The Removed group shows only while it lists someone (or failed
 * to load). Both lists are read again after a ban and after a lift; `useRoomLobby` re-reads
 * them on a kick, on the room's word of a removal, on a newcomer at the table (a removed
 * player back) and on a new PIN (a ban from the host's other device).
 *
 * A failed read is said as such (LoadFailed), never as "no one removed" (FR-7). One action
 * at a time across the panel: a synchronous in-flight ref, so a double tap sends one request
 * (FR-4). After an action its row is gone, and focus goes to the same button of the next row
 * (or the previous one), else to the title of the banned list.
 */
export function RoomBans({ roomId, isHost, className }: RoomBansProps) {
  if (!isHost) return null
  return <HostRoomBans roomId={roomId} className={className} />
}

function HostRoomBans({ roomId, className }: { roomId: string; className?: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const headingId = useId()
  const removedHeadingId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const removedListRef = useRef<HTMLUListElement>(null)
  const bansQuery = useListRoomBansApiV1RoomsRoomIdBansGet({ room_id: roomId }, { query: { retry: retryUnlessRefused } })
  const removalsQuery = useListRoomRemovalsApiV1RoomsRoomIdRemovalsGet({ room_id: roomId }, { query: { retry: retryUnlessRefused } })
  const liftMutation = useLiftRoomBanApiV1RoomsRoomIdBansUserIdDelete()
  const banMutation = useBanPlayerApiV1RoomsRoomIdBansPost()
  // The row being lifted or banned: one at a time across the panel.
  const [actingId, setActingId] = useState<string | null>(null)
  const actingRef = useRef(false)
  // The row acted on, its list, and its place among that list's buttons, to keep the host's place.
  const actedRef = useRef<{ id: string; index: number; list: "bans" | "removals" } | null>(null)

  const bans: RoomBanView[] = Array.isArray(bansQuery.data) ? bansQuery.data : []
  const removals: RoomRemovalView[] = Array.isArray(removalsQuery.data) ? removalsQuery.data : []
  // Listed at least once in this view: the panel stays when its last row goes.
  // Idempotent, so writing the ref while rendering is safe under StrictMode.
  const listedRef = useRef(false)
  if (bans.length > 0 || removals.length > 0) listedRef.current = true

  // After an action the row and its focused button are gone: focus goes to the next row's
  // button of the same list (or the previous one, or the title when none is left).
  useEffect(() => {
    const acted = actedRef.current
    if (!acted || actingId != null) return
    const rows: { user_id: string }[] = acted.list === "bans" ? bans : removals
    if (rows.some((row) => row.user_id === acted.id)) return
    actedRef.current = null
    const active = document.activeElement
    if (active && active !== document.body && document.contains(active)) return
    const list = acted.list === "bans" ? listRef.current : removedListRef.current
    const buttons = Array.from(list?.querySelectorAll<HTMLButtonElement>(acted.list === "bans" ? "button[data-lift]" : "button[data-ban]") ?? [])
    const next = buttons[Math.min(acted.index, buttons.length - 1)]
    ;(next ?? headingRef.current)?.focus()
  }, [bans, removals, actingId])

  const startAction = (id: string, index: number, list: "bans" | "removals") => {
    if (actingRef.current) return false
    actingRef.current = true
    actedRef.current = { id, index, list }
    setActingId(id)
    return true
  }

  const endAction = () => {
    actingRef.current = false
    setActingId(null)
    // the server's lists, whatever happened (another lift, a kick or a return meanwhile)
    void queryClient.invalidateQueries({ queryKey: queryKeys.room.bans(roomId) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.room.removals(roomId) })
  }

  const dropFrom = (queryKey: readonly unknown[], userId: string) =>
    queryClient.setQueryData(queryKey, (old: unknown) => (Array.isArray(old) ? old.filter((row: { user_id: string }) => row.user_id !== userId) : old))

  const liftBan = async (ban: RoomBanView, index: number) => {
    if (!startAction(ban.user_id, index, "bans")) return
    try {
      await liftMutation.mutateAsync({ room_id: roomId, user_id: ban.user_id })
      dropFrom(queryKeys.room.bans(roomId), ban.user_id)
    } catch (err) {
      if (roomErrorKey(err) === BAN_ALREADY_LIFTED_KEY) {
        // what the host asked for is already so
        dropFrom(queryKeys.room.bans(roomId), ban.user_id)
      } else {
        actedRef.current = null
        toast.error(roomErrorMessage(err, t("room.lobbyPage.bans.liftFailed")))
      }
    } finally {
      endAction()
    }
  }

  const banRemoved = async (removal: RoomRemovalView, index: number) => {
    if (!startAction(removal.user_id, index, "removals")) return
    try {
      const ban = await banMutation.mutateAsync({ room_id: roomId, data: { user_id: removal.user_id } })
      dropFrom(queryKeys.room.removals(roomId), removal.user_id)
      queryClient.setQueryData(queryKeys.room.bans(roomId), (old: unknown) =>
        Array.isArray(old) && !old.some((b: RoomBanView) => b.user_id === ban.user_id) ? [...old, ban] : old,
      )
      // the new PIN: the code tiles (the room state) and the share link
      void queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.room.shareLink(roomId) })
    } catch (err) {
      if (roomErrorKey(err) === ROOM_ERROR_KEYS.notInRoom) {
        // neither seated nor removed any more: back at the table, or banned from another
        // device. The server's words ("You are not in this room.") are not the host's case.
        toast.info(t("room.lobbyPage.bans.removedGone", { name: removal.username }))
      } else {
        actedRef.current = null
        toast.error(roomErrorMessage(err, t("room.lobbyPage.banFailed")))
      }
    } finally {
      endAction()
    }
  }

  const bansFailed = bansQuery.data === undefined && !!bansQuery.error
  const removalsFailed = removalsQuery.data === undefined && !!removalsQuery.error
  // nothing to say yet (the first reads), or nothing to say at all (nobody banned or removed)
  if (!bansFailed && !removalsFailed && !listedRef.current) return null

  return (
    <Panel flush aria-labelledby={headingId} className={className}>
      <h2
        id={headingId}
        ref={headingRef}
        tabIndex={-1}
        className="type-panel px-4 pt-4 pb-3 outline-none focus-visible:outline-2 focus-visible:outline-focus sm:px-5"
      >
        {t("room.lobbyPage.bans.title")}
        {bansFailed ? null : (
          <>
            {" "}
            <span className="num">({bans.length})</span>
          </>
        )}
      </h2>
      {bansFailed ? (
        <LoadFailed
          error={bansQuery.error}
          onRetry={() => void bansQuery.refetch()}
          retrying={bansQuery.isFetching}
          className="border-t border-line px-4 py-4 sm:px-5"
        />
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
                  loading={actingId === ban.user_id}
                  disabled={actingId != null && actingId !== ban.user_id}
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
      {removalsFailed || removals.length > 0 ? (
        <section aria-labelledby={removedHeadingId} className="border-t border-line">
          <h3 id={removedHeadingId} className="type-label px-4 pt-4 sm:px-5">
            {t("room.lobbyPage.bans.removedTitle")}
            {removalsFailed ? null : (
              <>
                {" "}
                <span className="num">({removals.length})</span>
              </>
            )}
          </h3>
          {removalsFailed ? (
            <LoadFailed
              error={removalsQuery.error}
              onRetry={() => void removalsQuery.refetch()}
              retrying={removalsQuery.isFetching}
              className="px-4 py-4 sm:px-5"
            />
          ) : (
            <>
              <p className="type-meta px-4 pt-1 pb-2 text-pretty sm:px-5">{t("room.lobbyPage.bans.removedHint")}</p>
              <ul ref={removedListRef}>
                {removals.map((removal, index) => (
                  <li key={removal.user_id} className="border-t border-line px-4 sm:px-5">
                    <div className="flex min-h-12 items-center justify-between gap-3 py-1">
                      <span dir="auto" className="min-w-0 flex-1 truncate text-[15px] leading-tight text-foreground">
                        {removal.username}
                      </span>
                      <RemovalConfirmButton
                        how="ban"
                        name={removal.username}
                        bodyKey="banRemovedConfirmBody"
                        busy={actingId === removal.user_id}
                        disabled={actingId != null && actingId !== removal.user_id}
                        onConfirm={() => void banRemoved(removal, index)}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      ) : null}
    </Panel>
  )
}
