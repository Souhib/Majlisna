import { ChevronDown } from "lucide-react"
import { memo, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"
import { RoleMark, roleLabelKey } from "./Lawh"
import { type VerdictRound, VoteLines } from "./Verdict"

interface VoteHistoryProps {
  history: VerdictRound[]
  /** Open every round (the end of the game). Otherwise the latest is open. */
  expandAll?: boolean
}

/**
 * The rounds so far: whose seat emptied (with the role it held) and who voted for whom.
 * Each round is a disclosure; the latest is open. Lives below the vote so the E2E helpers'
 * `button:has-text(<name>)` finds a vote button first.
 */
export const VoteHistory = memo(function VoteHistory({ history, expandAll = false }: VoteHistoryProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set(history.length ? [history[history.length - 1].round] : []))

  // A new round opens itself; the ones a player opened stay open.
  const latest = history.length ? history[history.length - 1].round : null
  useEffect(() => {
    if (latest !== null) setExpanded((prev) => new Set(prev).add(latest))
  }, [latest])

  if (history.length === 0) return null

  const toggle = (round: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(round)) next.delete(round)
      else next.add(round)
      return next
    })

  return (
    <section aria-labelledby="uc-history-title" className="grid content-start gap-3">
      <h3 id="uc-history-title" className="type-label">
        {t("game.undercover.voteHistory")}
      </h3>
      <ul className="border-t border-line">
        {history.map((round) => {
          const open = expandAll || expanded.has(round.round)
          const panelId = `uc-round-${round.round}`
          const summary = (
            <>
              <span className="shrink-0 font-medium">{t("game.undercover.round", { number: round.round })}</span>
              <span className="flex min-w-0 flex-1 items-center justify-end gap-2 text-muted-foreground">
                {round.eliminated ? (
                  <>
                    <RoleMark role={round.eliminated.role} size={9} />
                    <span className="truncate text-foreground">{round.eliminated.username}</span>
                    <span className="shrink-0">· {t(roleLabelKey(round.eliminated.role))}</span>
                  </>
                ) : (
                  <span>{t("game.undercover.noElimination")}</span>
                )}
              </span>
            </>
          )
          return (
            <li key={round.round} className="border-b border-line">
              {expandAll ? (
                <div className="flex min-h-12 w-full items-center gap-3 py-2 text-[14.5px]">{summary}</div>
              ) : (
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={panelId}
                  onClick={() => toggle(round.round)}
                  className="flex min-h-12 w-full items-center gap-3 py-2 text-start text-[14.5px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                >
                  {summary}
                  <ChevronDown
                    aria-hidden="true"
                    className={cn(
                      "size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-state) motion-reduce:transition-none",
                      open && "rotate-180",
                    )}
                  />
                </button>
              )}
              <div id={panelId} hidden={!open} className="pb-3">
                <VoteLines votes={round.votes} />
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
})
