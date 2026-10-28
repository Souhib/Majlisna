import { memo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { cn } from "@/lib/utils"
import { isArabicScript, RoleMark, roleLabelKey } from "./Lawh"

export interface DescriptionOrderEntry {
  user_id: string
  username: string
}

/** A seat at the table: the game state's `players`. */
export interface TableSeat {
  id: string
  username: string
  is_alive: boolean
  is_mayor?: boolean
}

/**
 * What a player wrote: Arabic script in Aref Ruqaa (the hand), anything else in quotes.
 */
export function Said({ text }: { text: string }) {
  const { t } = useTranslation()
  if (isArabicScript(text)) {
    return (
      <span className="uc-hand bidi-isolate" lang="ar" dir="rtl">
        {text}
      </span>
    )
  }
  return (
    <span className="uc-said">
      {t("game.undercover.quoteOpen")}
      <bdi>{text}</bdi>
      {t("game.undercover.quoteClose")}
    </span>
  )
}

interface DescriptionListProps {
  order: DescriptionOrderEntry[]
  descriptions: Record<string, string>
  /** Index of the player describing now; past the end once everyone has spoken. */
  currentIndex: number
  currentUserId?: string
  /** "describing" marks whose turn it is; "voting" recalls what was said and who has voted. */
  mode: "describing" | "voting"
  /** Every seat, alive or not: the Mayor's mark, and the seats that emptied. */
  players?: TableSeat[]
  /** Roles of the seats that emptied (public once a tablet turns over). */
  eliminated?: { user_id: string; role: string }[]
  /** While voting: who has voted (never for whom). */
  voted?: string[]
  /** While voting, for a player who may still vote: the other seats are the candidates. */
  choice?: { selected: string | null; onSelect: (playerId: string) => void }
}

interface Row {
  id: string
  username: string
  alive: boolean
  mayor: boolean
  /** Index in the speaking order (-1: not speaking this round). */
  turn: number
}

/**
 * The table, as ONE list per phase (sketch D third phone): every seat in speaking order,
 * each row carrying all of its state, so the screen never lists the same people twice.
 *
 * - The lozenge: ink once spoken, brass for the speaker, an open outline for those still
 *   to come; a seat that emptied shows its role's mark and "Eliminated · Undercover".
 * - The Mayor (whose vote breaks a tie) is named on their row, in ink: not yours.
 * - While voting, a second line says who has voted ("voted" / "not yet", never for whom),
 *   and for a player who may vote the other seats ARE the candidates: each row is a
 *   button named after the player (the E2E helpers click `button:has-text(<name>)`);
 *   the chosen one takes the brass outline and lozenge.
 */
export const DescriptionList = memo(function DescriptionList({
  order,
  descriptions,
  currentIndex,
  currentUserId,
  mode,
  players = [],
  eliminated = [],
  voted,
  choice,
}: DescriptionListProps) {
  const { t } = useTranslation()
  const bySeat = new Map(players.map((p) => [p.id, p]))
  const roles = new Map(eliminated.map((e) => [e.user_id, e.role]))
  const rows: Row[] = order.map((entry, idx) => {
    const seat = bySeat.get(entry.user_id)
    return { id: entry.user_id, username: entry.username, alive: seat?.is_alive ?? true, mayor: !!seat?.is_mayor, turn: idx }
  })
  const listed = new Set(rows.map((r) => r.id))
  for (const p of players) {
    if (!listed.has(p.id)) rows.push({ id: p.id, username: p.username, alive: p.is_alive, mayor: !!p.is_mayor, turn: -1 })
  }
  // the living first, in speaking order; the emptied seats recede to the end
  rows.sort((a, b) => Number(!a.alive) - Number(!b.alive))
  if (rows.length === 0) return null

  return (
    <ol className="uc-descs" aria-label={t("game.undercover.descriptionOrder")} data-mode={mode} data-choosing={choice ? "" : undefined}>
      {rows.map((row) => {
        const said = descriptions[row.id]
        const isMe = row.id === currentUserId
        const isCurrent = mode === "describing" && row.alive && row.turn === currentIndex && !said
        const role = roles.get(row.id)
        const candidate = !!choice && row.alive && !isMe
        const chosen = candidate && choice.selected === row.id
        const hasVoted = !!voted && voted.includes(row.id)

        const mark = !row.alive ? (
          role ? (
            <RoleMark role={role} size={8} />
          ) : (
            <Lozenge state="away" size={8} />
          )
        ) : candidate ? (
          <Lozenge state={chosen ? "brass" : "open"} size={9} />
        ) : (
          <Lozenge state={said || mode === "voting" ? "ink" : isCurrent ? "brass" : "open"} size={8} />
        )

        const notes: ReactNode[] = []
        if (row.mayor && row.alive) {
          notes.push(
            <span key="mayor" className="inline-flex items-center gap-1">
              <Lozenge state="ink" size={6} />
              {t("game.undercover.mayorLabel")}
              <span className="sr-only">: {t("game.undercover.mayorNote")}</span>
            </span>,
          )
        }
        if (mode === "voting" && voted && row.alive) {
          notes.push(
            <span key="voted" className={hasVoted ? "text-foreground" : undefined}>
              {hasVoted ? t("game.undercover.hasVoted") : t("game.undercover.notVotedYet")}
            </span>,
          )
        }

        const start = (
          <span className="grid min-w-0 gap-0.5">
            <span className="flex min-w-0 items-center gap-2.5">
              {mark}
              <span className={cn("truncate", row.alive && (isMe || candidate) && "font-medium text-foreground", isMe && "text-foreground")}>
                {isMe ? t("game.undercover.you") : row.username}
              </span>
            </span>
            {notes.length > 0 ? (
              <span className="flex flex-wrap items-center gap-x-2 ps-[18px] text-[12.5px] leading-tight text-muted-foreground">
                {notes.map((n, i) => (
                  <span key={i} className="inline-flex items-center gap-2">
                    {i > 0 ? <span aria-hidden="true">·</span> : null}
                    {n}
                  </span>
                ))}
              </span>
            ) : null}
          </span>
        )

        const end = !row.alive ? (
          <span className="shrink-0 text-[13px]">
            {t("game.eliminated")}
            {role ? ` · ${t(roleLabelKey(role))}` : ""}
          </span>
        ) : said ? (
          <Said text={said} />
        ) : isCurrent ? (
          isMe ? (
            <span className="font-medium text-brass">{t("game.undercover.yourTurn")}</span>
          ) : (
            <span>{t("game.undercover.describingNow")}</span>
          )
        ) : (
          <span className="sr-only">{t("game.undercover.notYet")}</span>
        )

        return (
          <li key={row.id} data-current={isCurrent ? "" : undefined} data-out={!row.alive ? "" : undefined} data-candidate={candidate ? "" : undefined}>
            {candidate ? (
              <button
                type="button"
                className="uc-seat"
                aria-pressed={chosen}
                aria-label={t("game.undercover.voteFor", { username: row.username })}
                onClick={() => choice.onSelect(row.id)}
              >
                {start}
                {end}
              </button>
            ) : (
              <>
                {start}
                {end}
              </>
            )}
          </li>
        )
      })}
    </ol>
  )
})
