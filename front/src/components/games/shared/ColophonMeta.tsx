import { Fragment, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { formatDuration } from "@/components/stats/format"

/** Whole seconds between the game's start and end (server instants, UTC), or null. */
export function gameSeconds(startedAt?: string | null, endedAt?: string | null): number | null {
  if (!startedAt || !endedAt) return null
  const ms = Date.parse(endedAt) - Date.parse(startedAt)
  return Number.isFinite(ms) && ms >= 0 ? Math.round(ms / 1000) : null
}

/** How long a game lasted, as a clock: "21:40", "1:02:05" (Western digits in every language). */
export function formatLasted(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const pad = (n: number) => String(n).padStart(2, "0")
  return h > 0 ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`
}

/** Who hosted a game and when it ran, as every game state carries it (`host_username`,
 *  `started_at`, `ended_at`; UTC, `ended_at` null while the game runs). */
export interface GameColophon {
  hostUsername?: string | null
  startedAt?: string | null
  endedAt?: string | null
}

/** The colophon fields of a game state, in the shape the game-over screens take. */
export function colophonOf(state: { host_username?: string | null; started_at?: string | null; ended_at?: string | null } | null | undefined): GameColophon {
  return { hostUsername: state?.host_username, startedAt: state?.started_at, endedAt: state?.ended_at }
}

/** First-strong isolates: a name keeps its own direction inside a translated sentence. */
const isolate = (text: string) => `⁨${text}⁩`

interface ColophonMetaProps {
  /** The game's name (`games.*.name`). */
  game: string
  /** Who hosted it (the state's `host_username`): "Yusuf’s majlis". */
  host?: string | null
  /** The game's own count: "3 rounds", "10 questions", "9 clues". */
  count?: ReactNode
  /** The game's start and end (`started_at`, `ended_at`): the duration, once it has ended. */
  startedAt?: string | null
  endedAt?: string | null
}

/**
 * The colophon's meta line (sketch H): "Undercover · Yusuf’s majlis · 3 rounds · 21:40",
 * the game, whose majlis it was, its count and how long it lasted, all from the server
 * (`host_username`, `started_at`, `ended_at`). A part the state does not carry is left
 * out. Figures are Readex tabular; the duration is a clock for the eye and a sentence
 * for screen readers ("21 min 40 s of play").
 */
export function ColophonMeta({ game, host, count, startedAt, endedAt }: ColophonMetaProps) {
  const { t } = useTranslation()
  const seconds = gameSeconds(startedAt, endedAt)
  const parts: ReactNode[] = [game]
  if (host) parts.push(t("game.colophon.majlis", { name: isolate(host) }))
  if (count != null && count !== false) parts.push(<span className="num">{count}</span>)
  if (seconds != null && seconds > 0) {
    parts.push(
      <span className="num">
        <span className="sr-only">{t("game.colophon.lasted", { duration: formatDuration(seconds, t) })}</span>
        <time dateTime={`PT${seconds}S`} aria-hidden="true" data-testid="colophon-duration">
          {formatLasted(seconds)}
        </time>
      </span>,
    )
  }
  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {i > 0 ? " · " : null}
          {part}
        </Fragment>
      ))}
    </>
  )
}
