import { memo, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Badge } from "@/components/ui/chip"
import { useSeatErase } from "@/hooks/use-seat-erase"
import { cn } from "@/lib/utils"
import { RoleMark, roleLabelKey } from "./Lawh"

interface Player {
  id: string
  username: string
  is_alive: boolean
  is_mayor?: boolean
}

interface UndercoverPlayerListProps {
  players: Player[]
  /** Roles of the seats that emptied (public once a tablet turns over). */
  eliminated?: { user_id: string; role: string }[]
  /** During the vote: who has voted (never for whom). */
  voted?: string[]
  currentUserId?: string
}

/**
 * The table: who is still seated, the Mayor (their vote breaks ties), and every emptied
 * seat with the role its tablet showed. What is finished recedes to secondary ink: the
 * name at the muted token's level, the lozenge further (undercover.css, `data-out`); a seat
 * that empties on screen is erased into that state (`useSeatErase`), never jumps.
 */
export const UndercoverPlayerList = memo(function UndercoverPlayerList({ players, eliminated = [], voted, currentUserId }: UndercoverPlayerListProps) {
  const { t } = useTranslation()
  const listRef = useRef<HTMLUListElement>(null)
  const aliveCount = players.filter((p) => p.is_alive).length
  const roles = new Map(eliminated.map((e) => [e.user_id, e.role]))
  useSeatErase(
    listRef,
    players.map((p) => ({ id: p.id, out: !p.is_alive })),
  )

  return (
    <section aria-labelledby="uc-table-title" className="grid content-start gap-3">
      <h3 id="uc-table-title" className="flex items-center gap-2.5 type-label">
        {t("room.players")}
        <Badge>
          <span className="sr-only">{t("game.undercover.seatedSr")} </span>
          {aliveCount}/{players.length}
        </Badge>
      </h3>
      <ul ref={listRef} className="uc-table border-t border-line">
        {players.map((player) => {
          const role = roles.get(player.id)
          return (
            <li
              key={player.id}
              data-seat={player.id}
              data-out={!player.is_alive ? "" : undefined}
              className={cn("flex min-h-11 items-center gap-3 border-b border-line py-2 text-[14.5px]", !player.is_alive && "text-muted-foreground")}
            >
              <span data-erase="mark" className="inline-flex shrink-0">
                {player.is_alive ? (
                  <Lozenge state={player.id === currentUserId ? "brass" : "ready"} size={9} />
                ) : role ? (
                  <RoleMark role={role} size={9} />
                ) : (
                  <Lozenge state="away" size={9} />
                )}
              </span>
              <span data-erase="ink" className={cn("min-w-0 flex-1 truncate", player.is_alive && "font-medium")}>
                {player.username}
                {/* receded, the whole name carries the opacity: a muted colour under it would fall below 4.5:1 */}
                {player.id === currentUserId ? (
                  <span className={cn("font-normal", player.is_alive && "text-muted-foreground")}> · {t("game.undercover.youLower")}</span>
                ) : null}
              </span>
              {player.is_mayor ? (
                <span className="inline-flex shrink-0 items-center gap-1.5 text-[13px] text-muted-foreground">
                  <Lozenge state="ink" size={7} />
                  {t("game.undercover.mayorLabel")}
                  <span className="sr-only">: {t("game.undercover.mayorNote")}</span>
                </span>
              ) : null}
              {player.is_alive && voted ? (
                <span className={cn("shrink-0 text-[13px]", voted.includes(player.id) ? "text-foreground" : "text-muted-foreground")}>
                  {voted.includes(player.id) ? t("game.undercover.hasVoted") : t("game.undercover.notVotedYet")}
                </span>
              ) : null}
              {!player.is_alive ? (
                <span data-erase="note" className="shrink-0 text-[13px]">
                  {t("game.eliminated")}
                  {role ? ` · ${t(roleLabelKey(role))}` : ""}
                </span>
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
})
