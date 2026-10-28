import { UserMinus } from "lucide-react"
import { useEffect, useId, useRef } from "react"
import { useTranslation } from "react-i18next"
import { formatClock, Lozenge } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import type { LobbyMember } from "./lobby"

interface PlayerRosterProps {
  /** Seated members, host first. */
  players: LobbyMember[]
  myId?: string
  /** The viewer hosts: every other row gets a Remove button. */
  canKick: boolean
  kickingId?: string | null
  onKick: (member: LobbyMember) => void
  /** Each away seat's countdown in seconds (awayCountdown): "away · 9:58". */
  awayLeft?: Map<string, number>
  className?: string
}

/**
 * The real player list behind the ring (the halqa is a picture): "Players (N)", one row
 * per seat with its state lozenge, the full name, and the host's Remove button. A seat
 * whose player lost the connection says how long it is still kept ("away · 9:58").
 *
 * E2E reads this list: the heading text "Players (N)", and each row as a
 * `div.flex.items-center.justify-between` holding a `span` whose text is exactly the
 * username, with Remove as the row's last button. Keep that shape.
 *
 * Removing a player takes their row, and the focused Remove button with it: focus then
 * goes to the next row's Remove (or the previous one, or the heading when none is
 * left), so a keyboard or screen-reader host keeps their place. The status line under
 * the ring says who left.
 */
export function PlayerRoster({ players, myId, canKick, kickingId, onKick, awayLeft, className }: PlayerRosterProps) {
  const { t } = useTranslation()
  const headingId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  // The row being removed and its place among the Remove buttons.
  const removingRef = useRef<{ id: string; index: number } | null>(null)

  useEffect(() => {
    const removing = removingRef.current
    // wait until the row is gone AND the removal has settled: while it runs the other
    // Remove buttons are disabled, and a disabled button cannot take focus
    if (!removing || kickingId != null || players.some((p) => p.id === removing.id)) return
    removingRef.current = null
    // only when focus went down with the row: never take it from somewhere else
    const active = document.activeElement
    if (active && active !== document.body && document.contains(active)) return
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button[data-remove]") ?? [])
    const next = buttons[Math.min(removing.index, buttons.length - 1)]
    ;(next ?? headingRef.current)?.focus()
  }, [players, kickingId])

  const removable = players.filter((p) => p.id !== myId)
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
        <ul ref={listRef} className="border-t border-line">
          {players.map((player) => {
            const me = player.id === myId
            const state = player.isHost ? "host" : player.isAway ? "away" : "ready"
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
              <li key={player.id} className="border-b border-line px-4 last:border-b-0 sm:px-5">
                <div className="flex min-h-12 items-center justify-between gap-3 py-1">
                  <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
                    <Lozenge state={state} size={9} className="-translate-y-px self-center" />
                    <span dir="auto" className={cn("min-w-0 truncate text-[15px] leading-tight", me ? "font-medium text-foreground" : "text-foreground")}>
                      {player.username}
                    </span>
                    {me ? <span className="type-meta shrink-0">{t("room.lobbyPage.rosterYou")}</span> : null}
                    {note ? <span className={cn("type-meta shrink-0", player.isHost && "text-brass")}>{note}</span> : null}
                  </div>
                  {canKick && !me ? (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      loading={kickingId === player.id}
                      disabled={kickingId != null && kickingId !== player.id}
                      data-remove=""
                      onClick={() => {
                        removingRef.current = { id: player.id, index: removable.findIndex((p) => p.id === player.id) }
                        onKick(player)
                      }}
                      aria-label={t("room.lobbyPage.kick", { name: player.username })}
                      className="shrink-0 text-muted-foreground hover:bg-[color-mix(in_oklch,var(--ember)_10%,transparent)] hover:text-ember aria-busy:[&>svg]:hidden"
                    >
                      <UserMinus aria-hidden="true" />
                    </Button>
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
