import { ArrowRight } from "lucide-react"
import { type ReactNode } from "react"
import { Trans, useTranslation } from "react-i18next"
import { useGetGameSummaryApiV1GamesGameIdSummaryGet } from "@/api/generated"
import type { ClueHistoryEntry, GameSummary, GameSummaryPlayer, UndercoverWordExplanations, VoteRound } from "@/api/generated"
import { Lozenge, TeamGlyph } from "@/components/brand"
import { Alert } from "@/components/ui/alert"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { getApiErrorMessage } from "@/api/client"
import { cn } from "@/lib/utils"
import {
  cardGlyph,
  formatDuration,
  gameName,
  groupVotes,
  joinNames,
  latnLocale,
  roleLozenge,
  roleName,
  secondsBetween,
  teamName,
  teamOf,
  winnerLine,
} from "./format"

const ARABIC = /[\u0600-\u06FF]/

interface GameDetailModalProps {
  gameId: string
  gameType: string
  onClose: () => void
}

/**
 * A finished game, after the fact (the summary endpoint answers only for players who
 * took part, and only once the game is over). Who held which role, the words with their
 * Arabic in Amiri, and how the table got there: the votes (Undercover) or the clues
 * (Codenames). Roles read as in the game: Civilian undyed, Undercover madder, Mr. White
 * an empty lozenge; teams as wool + glyph.
 */
export function GameDetailModal({ gameId, gameType, onClose }: GameDetailModalProps) {
  const { t, i18n } = useTranslation()
  // the words' meanings (`*_hint`, `guesses[].hint`) come resolved in this language
  const { data: summary, isLoading, error } = useGetGameSummaryApiV1GamesGameIdSummaryGet({ game_id: gameId }, { lang: i18n.language }) as {
    data: GameSummary | undefined
    isLoading: boolean
    error: unknown
  }

  const type = summary?.type ?? gameType
  const result = summary ? winnerLine(type, summary.winner, t) : null
  const winnerTeam = type === "codenames" ? teamOf(summary?.winner) : null
  const when = summary?.start_time
    ? new Date(summary.start_time).toLocaleDateString(latnLocale(i18n.language), { day: "numeric", month: "long", year: "numeric" })
    : null
  const seconds = secondsBetween(summary?.start_time, summary?.end_time)
  const meta = [when, seconds ? formatDuration(seconds, t) : null, summary ? t("stats.playerCount", { count: summary.number_of_players }) : null]
    .filter(Boolean)
    .join(" · ")

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="max-w-xl gap-0">
        <DialogHeader className="mb-5">
          <DialogTitle>{gameName(type, t)}</DialogTitle>
          <DialogDescription>{meta || t("stats.gameDetail")}</DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="grid gap-3" aria-busy="true">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : !summary ? (
          <Alert>{error ? getApiErrorMessage(error, t("errors.loadFailed")) : t("errors.loadFailed")}</Alert>
        ) : (
          <div className="grid gap-6">
            {result ? (
              <p className="type-title flex items-center gap-3 text-[24px]">
                {winnerTeam ? <TeamMark team={winnerTeam} size="lg" /> : null}
                {result}
              </p>
            ) : null}
            {summary.word_explanations ? <Words words={summary.word_explanations} /> : null}
            <Players players={summary.players} type={type} />
            {summary.vote_history && summary.vote_history.length > 0 ? <Votes rounds={summary.vote_history} /> : null}
            {summary.clue_history && summary.clue_history.length > 0 ? <Clues clues={summary.clue_history} /> : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** A Codenames team as everywhere else: its wool with its glyph (never the colour alone). */
function TeamMark({ team, size = "md" }: { team: NonNullable<ReturnType<typeof teamOf>>; size?: "md" | "lg" }) {
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-[1px]",
        size === "lg" ? "size-7" : "size-5",
        team === "madder" ? "bg-wool-madder text-wool-ink" : "bg-wool-indigo text-wool-on-indigo",
      )}
    >
      <TeamGlyph team={team} size={size === "lg" ? 13 : 10} />
    </span>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2.5 border-t border-line pt-4">
      <h3 className="type-label">{title}</h3>
      {children}
    </section>
  )
}

/** The pair of Undercover words: Latin name, Arabic in Amiri beside it, then its meaning. */
function Words({ words }: { words: UndercoverWordExplanations }) {
  const { t } = useTranslation()
  const pairs = [
    {
      key: "civ",
      label: t("game.undercover.civilianWord"),
      mark: "undyed" as const,
      latin: words.civilian_word,
      arabic: words.civilian_word_ar_vocalized ?? words.civilian_word_ar,
      meaning: words.civilian_word_hint,
    },
    {
      key: "uc",
      label: t("game.undercover.undercoverWord"),
      mark: "madder" as const,
      latin: words.undercover_word,
      arabic: words.undercover_word_ar_vocalized ?? words.undercover_word_ar,
      meaning: words.undercover_word_hint,
    },
  ].filter((p) => p.latin)
  if (pairs.length === 0) return null
  return (
    <Section title={t("stats.words")}>
      <dl className="grid gap-3 sm:grid-cols-2">
        {pairs.map((p) => (
          <div key={p.key} className="rounded-sm border border-line bg-surface-2 px-4 py-3">
            <dt className="type-meta flex items-center gap-2">
              <Lozenge state={p.mark} size={8} />
              {p.label}
            </dt>
            <dd className="mt-1 flex flex-wrap items-baseline justify-between gap-x-4">
              <span lang="en" dir="ltr" className="bidi-isolate text-[17px] font-medium">
                {p.latin}
              </span>
              {p.arabic ? (
                <span lang="ar" dir="rtl" className="type-word text-[26px] leading-none">
                  {p.arabic}
                </span>
              ) : null}
            </dd>
            {p.meaning ? (
              // the server can fall back to another language for a meaning: it keeps its own direction
              <dd dir="auto" className="mt-1.5 text-[14px] leading-snug text-muted-foreground">
                {p.meaning}
              </dd>
            ) : null}
          </div>
        ))}
      </dl>
    </Section>
  )
}

function Players({ players, type }: { players: GameSummaryPlayer[]; type: string }) {
  const { t } = useTranslation()
  return (
    <Section title={t("stats.playerRoles")}>
      <ul className="grid">
        {players.map((p) => {
          const team = teamOf(p.team)
          const mark = roleLozenge(p.role)
          return (
            <li key={p.user_id} className="flex min-h-11 items-center justify-between gap-3 border-b border-line py-2 last:border-b-0">
              <span className="flex min-w-0 items-center gap-2.5">
                {team ? <TeamMark team={team} /> : null}
                <span className="truncate font-medium">{p.username}</span>
              </span>
              {p.role ? (
                <span className="flex shrink-0 items-center gap-2 text-[14px] text-muted-foreground">
                  {mark ? <Lozenge state={mark} size={9} /> : null}
                  {roleName(p.role, t)}
                  {team ? <span className="sr-only">, {teamName(p.team, t)}</span> : null}
                </span>
              ) : type === "codenames" && p.team ? (
                <span className="text-[14px] text-muted-foreground">{teamName(p.team, t)}</span>
              ) : null}
            </li>
          )
        })}
      </ul>
    </Section>
  )
}

/** Each round's votes grouped by who they named, and who left the table. */
function Votes({ rounds }: { rounds: VoteRound[] }) {
  const { t, i18n } = useTranslation()
  return (
    <Section title={t("stats.voteHistory")}>
      <ol className="grid gap-4">
        {rounds.map((round) => (
          <li key={round.round} className="grid gap-1.5">
            <p className="text-[13px] font-medium text-brass">{t("game.undercover.round", { number: round.round })}</p>
            <ul className="grid gap-1 text-[15px] leading-snug">
              {groupVotes(round.votes).map((line) => (
                <li key={line.target}>
                  <Trans
                    i18nKey="stats.votedFor"
                    values={{ voters: joinNames(line.voters, i18n.language), target: line.target }}
                    components={{ b: <bdi className="font-medium" /> }}
                  />
                </li>
              ))}
            </ul>
            {round.eliminated ? (
              <p className="flex flex-wrap items-center gap-x-2 text-[14px] text-muted-foreground">
                <ArrowRight className="size-3.5 shrink-0 text-brass rtl-flip" aria-hidden="true" />
                <span>
                  <Trans
                    i18nKey="stats.leftTable"
                    values={{ name: round.eliminated.username }}
                    components={{ b: <bdi className="font-medium text-foreground" /> }}
                  />
                </span>
                <span className="inline-flex items-center gap-1.5 text-foreground">
                  {roleLozenge(round.eliminated.role) ? <Lozenge state={roleLozenge(round.eliminated.role)!} size={8} /> : null}
                  {roleName(round.eliminated.role, t)}
                </span>
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </Section>
  )
}

/** Codenames: each clue with its team, and the cards it turned (each named by its glyph). */
function Clues({ clues }: { clues: ClueHistoryEntry[] }) {
  const { t } = useTranslation()
  const cardLabel: Record<string, string> = {
    madder: t("game.codenames.teams.red"),
    indigo: t("game.codenames.teams.blue"),
    bystander: t("stats.card.bystander"),
    assassin: t("stats.card.assassin"),
  }
  return (
    <Section title={t("stats.clueHistory")}>
      <ol className="grid">
        {clues.map((clue, i) => {
          const team = teamOf(clue.team)
          return (
            <li key={i} className="grid gap-2 border-b border-line py-3 first:pt-1 last:border-b-0">
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {team ? (
                  <span className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
                    <TeamMark team={team} />
                    {teamName(clue.team, t)}
                  </span>
                ) : null}
                {/* what the spymaster wrote: their hand when it is Arabic, Marcellus caps otherwise */}
                <span
                  dir="auto"
                  className={cn(
                    "bidi-isolate",
                    ARABIC.test(clue.clue_word) ? "type-hand text-[22px]" : "font-display text-[20px] uppercase tracking-[0.04em]",
                  )}
                >
                  {clue.clue_word}
                </span>
                <span className="num text-[18px] font-medium text-brass">{clue.clue_number}</span>
              </p>
              {clue.guesses && clue.guesses.length > 0 ? (
                <ul className="flex flex-wrap gap-1.5">
                  {clue.guesses.map((g, j) => {
                    const glyph = cardGlyph(g.card_type)
                    return (
                      <li
                        key={j}
                        className="inline-flex h-[30px] items-center gap-2 rounded-sm border border-line bg-surface-2 px-2.5 text-[13.5px]"
                      >
                          <TeamGlyph team={glyph} size={10} label={cardLabel[glyph]} />
                          <span lang="en" dir="ltr" className="bidi-isolate font-medium">
                            {g.word}
                          </span>
                          {g.word_ar ? (
                            <span lang="ar" dir="rtl" className="font-nass text-[16px] leading-none">
                              {g.word_ar_vocalized ?? g.word_ar}
                            </span>
                          ) : null}
                      </li>
                    )
                  })}
                </ul>
              ) : null}
            </li>
          )
        })}
      </ol>
    </Section>
  )
}
