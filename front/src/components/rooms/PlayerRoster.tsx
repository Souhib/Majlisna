import { Ban, UserMinus } from "lucide-react"
import { useEffect, useId, useRef } from "react"
import { useTranslation } from "react-i18next"
import { formatClock, Lozenge } from "@/components/brand"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { useSeatErase } from "@/hooks/use-seat-erase"
import { cn } from "@/lib/utils"
import type { LobbyMember } from "./lobby"

interface PlayerRosterProps {
  /** Seated members, host first. */
  players: LobbyMember[]
  myId?: string
  /** The viewer hosts: every other row gets Remove and Ban. */
  canKick: boolean
  /** The seat being removed (a kick or a ban): its buttons are busy, every other row's disabled. */
  removingId?: string | null
  /** Remove (a kick): the seat goes, the player may come back. */
  onKick: (member: LobbyMember) => void
  /** Ban: the seat goes, and the player is kept out until the host lifts it. */
  onBan: (member: LobbyMember) => void
  /** Each away seat's countdown in seconds (awayCountdown): "away · 9:58". */
  awayLeft?: Map<string, number>
  className?: string
}

/** The row's two removals, and the data attribute each one's button carries (focus moves by it). */
type Removal = "kick" | "ban"
const REMOVAL_ATTRIBUTE: Record<Removal, string> = { kick: "data-remove", ban: "data-ban" }

/**
 * The real player list behind the ring (the halqa is a picture): "Players (N)", one row
 * per seat with its state lozenge, the full name, and the host's Remove and Ban. A seat
 * whose player lost the connection says how long it is still kept ("away · 9:58"), its name
 * and lozenge receded (rooms.css, `data-away`); a seat that empties on screen is erased into
 * that state, and restored when the player comes back (`useSeatErase`). A player who leaves
 * the room is no longer in its state: the row goes, never kept as a ghost.
 *
 * E2E reads this list: the heading text "Players (N)", and each row as a
 * `div.flex.items-center.justify-between` holding a `span` whose text is exactly the
 * username, then the row's two buttons, Remove and Ban, found by their accessible names
 * ("Remove {{name}} from the room", "Ban {{name}} from the room"). Keep that shape.
 *
 * Kick and ban are two actions (owner decision, 2 November 2026), each behind its own
 * AlertDialog; nothing is sent until its action. Remove is for someone who left without
 * quitting: the dialog says they may come back with the code and PIN, or an invite. Ban
 * is for someone the table does not want back: the dialog says it holds, invites
 * included, until the host lifts it (RoomBans), and that the PIN will change.
 *
 * Removing a player takes their row, and the focused button with it: focus then goes to
 * the same button of the next row (or the previous one, or the heading when none is
 * left), so a keyboard or screen-reader host keeps their place. The status line under
 * the ring says who was removed or banned.
 */
export function PlayerRoster({ players, myId, canKick, removingId, onKick, onBan, awayLeft, className }: PlayerRosterProps) {
  const { t } = useTranslation()
  const headingId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  // The row being removed, its place among the removable rows, and which button took it.
  const removingRef = useRef<{ id: string; index: number; how: Removal } | null>(null)

  useEffect(() => {
    const removing = removingRef.current
    // wait until the row is gone AND the removal has settled: while it runs the other
    // rows' buttons are disabled, and a disabled button cannot take focus
    if (!removing || removingId != null || players.some((p) => p.id === removing.id)) return
    removingRef.current = null
    // only when focus went down with the row: never take it from somewhere else
    const active = document.activeElement
    if (active && active !== document.body && document.contains(active)) return
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>(`button[${REMOVAL_ATTRIBUTE[removing.how]}]`) ?? [])
    const next = buttons[Math.min(removing.index, buttons.length - 1)]
    ;(next ?? headingRef.current)?.focus()
  }, [players, removingId])

  const removable = players.filter((p) => p.id !== myId)
  // the host's seat says "host" even when its connection drops: only an "away" seat recedes
  const seatState = (player: LobbyMember) => (player.isHost ? "host" : player.isAway ? "away" : "ready")
  useSeatErase(
    listRef,
    players.map((p) => ({ id: p.id, out: seatState(p) === "away" })),
  )
  return (
    <Panel flush aria-labelledby={headingId} className={className}>
      <h2
        id={headingId}
        ref={headingRef}
        tabIndex={-1}
        className="type-panel px-4 pt-4 pb-3 outline-none focus-visible:outline-2 focus-visible:outline-focus sm:px-5"
      >
        {t("room.players")} <span className="num">({players.length})</span>
      </h2>
      {players.length === 0 ? (
        <p className="border-t border-line px-4 py-4 text-[14px] text-muted-foreground sm:px-5">{t("room.waitingForPlayers")}</p>
      ) : (
        <ul ref={listRef} className="lobby-roster border-t border-line">
          {players.map((player) => {
            const me = player.id === myId
            const state = seatState(player)
            const left = player.isAway ? awayLeft?.get(player.id) : undefined
            const note = player.isHost ? (
              t("room.lobbyPage.seatHost")
            ) : player.isAway ? (
              <>
                {t("room.lobbyPage.seatAway")}
                {left != null ? (
                  <>
                    {" · "}
                    <bdi dir="ltr" className="num">
                      {formatClock(left)}
                    </bdi>
                  </>
                ) : null}
              </>
            ) : null
            return (
              <li
                key={player.id}
                data-seat={player.id}
                data-away={state === "away" ? "" : undefined}
                className="border-b border-line px-4 last:border-b-0 sm:px-5"
              >
                <div className="flex min-h-12 items-center justify-between gap-3 py-1">
                  <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
                    <span data-erase="mark" className="inline-flex shrink-0 -translate-y-px self-center">
                      <Lozenge state={state} size={9} />
                    </span>
                    <span
                      data-erase="ink"
                      dir="auto"
                      className={cn("min-w-0 truncate text-[15px] leading-tight", me ? "font-medium text-foreground" : "text-foreground")}
                    >
                      {player.username}
                    </span>
                    {me ? <span className="type-meta shrink-0">{t("room.lobbyPage.rosterYou")}</span> : null}
                    {note ? (
                      <span data-erase={state === "away" ? "note" : undefined} className={cn("type-meta shrink-0", player.isHost && "text-brass")}>
                        {note}
                      </span>
                    ) : null}
                  </div>
                  {canKick && !me ? (
                    <div className="flex shrink-0 items-center gap-0.5">
                      {(["kick", "ban"] as const).map((how) => (
                        <RemoveSeatButton
                          key={how}
                          how={how}
                          player={player}
                          busy={removingId === player.id}
                          disabled={removingId != null && removingId !== player.id}
                          onConfirm={() => {
                            removingRef.current = { id: player.id, index: removable.findIndex((p) => p.id === player.id), how }
                            if (how === "kick") onKick(player)
                            else onBan(player)
                          }}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}

/** Each removal's words (`room.lobbyPage.*`) and icon. */
const REMOVAL_COPY = {
  kick: { label: "kick", title: "kickConfirmTitle", body: "kickConfirmBody", action: "kickConfirmAction", Icon: UserMinus },
  ban: { label: "ban", title: "banConfirmTitle", body: "banConfirmBody", action: "banConfirmAction", Icon: Ban },
} as const

/**
 * One of the host's two buttons on a row (Remove, then Ban): an icon button that opens its
 * own confirmation, portalled out of the row (E2E clicks the button by name, then the
 * dialog's "Remove" or "Ban"). On close Radix gives focus back to it, and when the row goes
 * the roster moves focus on (see above). Both buttons of the row are busy while either
 * request runs.
 */
function RemoveSeatButton({
  how,
  player,
  busy,
  disabled,
  onConfirm,
}: {
  how: Removal
  player: LobbyMember
  busy: boolean
  disabled: boolean
  onConfirm: () => void
}) {
  const { t } = useTranslation()
  const name = player.username
  const copy = REMOVAL_COPY[how]
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          loading={busy}
          disabled={disabled}
          data-remove={how === "kick" ? "" : undefined}
          data-ban={how === "ban" ? "" : undefined}
          aria-label={t(`room.lobbyPage.${copy.label}`, { name })}
          className="shrink-0 text-muted-foreground hover:bg-[color-mix(in_oklch,var(--ember)_10%,transparent)] hover:text-ember aria-busy:[&>svg]:hidden"
        >
          <copy.Icon aria-hidden="true" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t(`room.lobbyPage.${copy.title}`, { name })}</AlertDialogTitle>
          <AlertDialogDescription>{t(`room.lobbyPage.${copy.body}`, { name })}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction variant="danger" onClick={onConfirm}>
            {t(`room.lobbyPage.${copy.action}`)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
