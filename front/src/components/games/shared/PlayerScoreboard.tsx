import { type CSSProperties, memo, type RefObject, useEffect, useLayoutEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { bezier, dur, ease, stagger } from "@/lib/motion"
import { cn } from "@/lib/utils"
import { competitionRanks, Figure } from "./quiz-utils"

interface PlayerScore {
  user_id: string
  username: string
  total_score: number
  current_round_answered: boolean
  current_round_points?: number
}

interface PlayerScoreboardProps {
  players: PlayerScore[]
  currentUserId?: string
  /** Mark who has already answered this round (the playing phase). */
  showAnswered?: boolean
  /**
   * The most the game can give one player (its rounds × the best a round pays): what each
   * thread is a share of, so a thread only ever grows. Without it, the leader's score.
   */
  maxScore?: number
  /**
   * Hold the weave this long (ms) after the totals change: The Quiz's reveal waits for its
   * tally threads, the screen's authored moment (`tallyWeaveMs`). 0 elsewhere.
   */
  weaveAfter?: number
  className?: string
}

/**
 * The table's scores, beside the play panel (both quizzes). Tabular: place, name, score,
 * with ties sharing a place. Your row is brass. While a round is open, a lozenge says
 * who has answered (filled, like a ready seat in the halqa) and who is still thinking
 * (a muted outline), with words for screen readers; it never says what anyone answered.
 *
 * The scores are the server's as sent. The Quiz's state holds a round's points back while
 * its question is open (each total as it stood before the round), so the table's order
 * never tells who was right before the reveal.
 *
 * Woven (motion spec 9): under each name a thread, the player's share of `maxScore` (the
 * viewer's in the madd band), and beside the total what this round earned ("+3", the
 * server's `current_round_points`). When the totals change (The Quiz's reveal; in Kalimat,
 * a player finding the word, since its server sends the totals as they move) the list is
 * already in its new order and each row travels there from its old place (320 ms, settle,
 * 30 ms apart, 240 ms at most), then each thread is written longer from the reading start
 * (640 ms, the qalam's curve) and the gain fades in after 320 ms. A first state (a page
 * load) and the same totals sent again move nothing. `weaveAfter` holds all of it back (The
 * Quiz: until its tally threads are drawn). The gain's slot is on every row, gained or not,
 * so a first gain (Kalimat: mid-round) moves no total sideways.
 */
export const PlayerScoreboard = memo(function PlayerScoreboard({
  players,
  currentUserId,
  showAnswered = false,
  maxScore,
  weaveAfter = 0,
  className,
}: PlayerScoreboardProps) {
  const { t } = useTranslation()
  const sorted = [...players].sort((a, b) => b.total_score - a.total_score)
  const ranks = competitionRanks(sorted.map((p) => p.total_score))
  const answered = players.filter((p) => p.current_round_answered).length
  const ceiling = maxScore && maxScore > 0 ? maxScore : Math.max(0, ...players.map((p) => p.total_score))

  const listRef = useRef<HTMLOListElement>(null)
  useScoreWeave(listRef, `${sorted.map((p) => `${p.user_id}:${p.total_score}`).join(",")}/${ceiling}`, weaveAfter)

  return (
    <Panel className={className} aria-labelledby="quiz-scores-title">
      <PanelHeader
        title={<span id="quiz-scores-title">{t("game.quiz.scores")}</span>}
        sub={showAnswered && players.length > 0 ? t("game.quiz.answeredCount", { answered, total: players.length }) : undefined}
        className="mb-2"
      />
      <ol ref={listRef} data-testid="quiz-scoreboard" className="relative">
        {sorted.map((player, index) => {
          const isMe = player.user_id === currentUserId
          const gain = player.current_round_points ?? 0
          const share = ceiling > 0 ? Math.max(0, Math.min(1, player.total_score / ceiling)) : 0
          return (
            <li
              key={player.user_id}
              data-user={player.user_id}
              data-score={player.total_score}
              data-you={isMe || undefined}
              style={{ "--share": share } as CSSProperties}
              className="score-row grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 border-t border-line bg-surface py-2.5 first:border-t-0"
            >
              <span className="num text-[13px] text-muted-foreground">{ranks[index]}</span>
              <span className="flex min-w-0 items-center gap-2">
                {showAnswered ? (
                  <Lozenge
                    state={player.current_round_answered ? "ready" : "away"}
                    size={8}
                    label={player.current_round_answered ? t("game.quiz.hasAnswered") : t("game.quiz.stillThinking")}
                  />
                ) : null}
                <span className={cn("truncate text-[15px] font-medium", isMe && "text-brass")}>{player.username}</span>
                {isMe ? <span className="shrink-0 text-[13px] text-muted-foreground">{t("game.quiz.you")}</span> : null}
              </span>
              <span className="flex items-baseline justify-end">
                <Figure className={cn("score-total text-[15px] font-medium", isMe && "text-brass")}>{player.total_score}</Figure>
                {/* every row keeps the slot, gained or not: the totals stay aligned, and a first gain moves none */}
                <span className="score-gain-slot">{gain > 0 ? <Figure className="score-gain">+{gain}</Figure> : null}</span>
              </span>
              <span className="score-yarn" aria-hidden="true">
                <i />
              </span>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
})

/** Where a row stood at the last change of the totals: its place in the list, its total, its thread. */
interface Placed {
  index: number
  score: number
  share: number
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

const ms = (seconds: number) => Math.round(seconds * 1000)

/** A thread holding `share` of its length: the rest is hidden past the reading start. */
function threadAt(share: number, rtl: boolean) {
  const hidden = Math.round((1 - share) * 100_000) / 1000
  return `translateX(${rtl || hidden === 0 ? hidden : -hidden}%)`
}

/** The translation a running animation holds an element at, from its computed matrix. */
function heldTranslation(el: Element | null): { x: number; y: number } {
  if (!el) return { x: 0, y: 0 }
  const match = /^matrix\(([^)]+)\)$/.exec(getComputedStyle(el).transform)
  if (!match) return { x: 0, y: 0 }
  const parts = match[1].split(",").map(Number)
  return { x: parts[4] || 0, y: parts[5] || 0 }
}

/**
 * FLIP for the scoreboard: after a commit whose totals changed, each row is moved from where
 * it was seen back to its new place, and its thread from its old share to its new one. The
 * DOM is final from the first frame; only `transform` and `opacity` move, by Web Animations
 * on the compositor (`fill: "backwards"` holds each one where it starts during its delay, and
 * the CSS keeps the end). A change landing mid-weave cancels it and starts from where the eye
 * sees the rows. Under reduced motion only the gains fade in, at once. `after` (ms) delays
 * every part of a full weave (never the reduced fade).
 *
 * A row's old place is its old INDEX, read as that slot's position in the layout of the
 * moment (the rows are one line each, so the slots are the same before and after a
 * reorder): a pixel offset kept from an earlier change would be stale after a language
 * switch (Arabic sets rem at 110 %) or a late font. Nothing is laid out between changes.
 */
function useScoreWeave(listRef: RefObject<HTMLOListElement | null>, signature: string, after: number) {
  const placed = useRef<Map<string, Placed> | null>(null)
  const running = useRef<Animation[]>([])

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const rows = Array.from(list.children).filter((el): el is HTMLLIElement => el instanceof HTMLLIElement && !!el.dataset.user)
    const before = placed.current
    const now = new Map<string, Placed>()
    rows.forEach((row, index) => {
      now.set(row.dataset.user as string, {
        index,
        score: Number(row.dataset.score),
        share: Number(row.style.getPropertyValue("--share")) || 0,
      })
    })
    placed.current = now
    // a first state (a page load) is not a change
    if (!before) return
    const gained = rows.some((row) => {
      const was = before.get(row.dataset.user as string)
      return was != null && was.score !== now.get(row.dataset.user as string)?.score
    })
    if (!gained) return

    const rtl = list.closest("[dir]")?.getAttribute("dir") === "rtl"
    // A weave still running holds rows and threads away from their places: read where the
    // eye sees them before cancelling it.
    const inFlight = running.current.some((a) => a.playState === "running")
    const seen = rows.map((row) => {
      if (!inFlight) return null
      const thread = row.querySelector<HTMLElement>(".score-yarn > i")
      const width = thread?.offsetWidth ?? 0
      const x = heldTranslation(thread).x
      return { y: heldTranslation(row).y, share: width > 0 ? Math.max(0, Math.min(1, rtl ? 1 - x / width : 1 + x / width)) : null }
    })
    for (const animation of running.current) animation.cancel()
    running.current = []
    if (typeof list.animate !== "function") return

    const reduce = prefersReducedMotion()
    const out = bezier(ease.out)
    // the slots as laid out now; a slot past the end (a row that has left) extends the last
    const tops = reduce ? [] : rows.map((row) => row.offsetTop)
    const lastHeight = reduce ? 0 : (rows.at(-1)?.offsetHeight ?? 0)
    const slotTop = (index: number) => (index < tops.length ? tops[index] : (tops.at(-1) ?? 0) + (index - tops.length + 1) * lastHeight)
    rows.forEach((row, index) => {
      const id = row.dataset.user as string
      const was = before.get(id)
      const is = now.get(id)
      if (!was || !is) return
      const gain = was.score !== is.score ? row.querySelector<HTMLElement>(".score-gain") : null
      if (reduce) {
        if (gain) running.current.push(gain.animate([{ opacity: 0 }, { opacity: 1 }], { duration: ms(dur.state), easing: out, fill: "backwards" }))
        return
      }
      const delay = after + ms(Math.min(index * stagger.step, stagger.cap))
      const dy = slotTop(was.index) + (seen[index]?.y ?? 0) - tops[index]
      if (Math.abs(dy) >= 0.5) {
        running.current.push(
          // ends on the identity the row rests at (quiz.css): gaining or losing a transform lays it out
          row.animate([{ transform: `translateY(${Math.round(dy * 10) / 10}px)` }, { transform: "translateY(0px)" }], {
            duration: ms(dur.move),
            easing: bezier(ease.settle),
            delay,
            fill: "backwards",
          }),
        )
      }
      const thread = row.querySelector<HTMLElement>(".score-yarn > i")
      const from = seen[index]?.share ?? was.share
      if (thread && Math.abs(from - is.share) > 0.0005) {
        running.current.push(
          thread.animate([{ transform: threadAt(from, rtl) }, { transform: threadAt(is.share, rtl) }], {
            duration: ms(dur.authored),
            easing: bezier(ease.ink),
            delay: ms(dur.move) + delay,
            fill: "backwards",
          }),
        )
      }
      if (gain)
        running.current.push(
          gain.animate([{ opacity: 0 }, { opacity: 1 }], { duration: ms(dur.state), easing: out, delay: after + ms(dur.move), fill: "backwards" }),
        )
    })
    // a new `after` alone weaves nothing: the totals did not change
  }, [listRef, signature, after])

  useEffect(
    () => () => {
      for (const animation of running.current) animation.cancel()
    },
    [],
  )
}
