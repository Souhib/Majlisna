import { type ReactNode, useId } from "react"
import { Trans, useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"
import { Said } from "./DescriptionList"
import { type LawhWord, TurnedLawh } from "./Lawh"

export interface VoteEntry {
  voter: string
  voter_id: string
  target: string
  target_id: string
}

export interface EliminatedInfo {
  username: string
  role: string
  user_id: string
}

/** What the voted-out Mr. White guessed (`word` null: his time ran out). */
export interface MrWhiteGuess {
  word?: string | null
  correct: boolean
}

export interface VerdictRound {
  round: number
  votes: VoteEntry[]
  eliminated?: EliminatedInfo | null
  mr_white_guess?: MrWhiteGuess | null
}

/** One line for the whole table on Mr. White's guess: what he guessed, and whether it was the word. */
export function MrWhiteGuessLine({ guess, className }: { guess: MrWhiteGuess; className?: string }) {
  const key = !guess.word ? "game.undercover.verdict.guessTimeout" : guess.correct ? "game.undercover.verdict.guessRight" : "game.undercover.verdict.guessWrong"
  return (
    <p data-testid="mr-white-guess" className={cn("text-[15px] leading-normal", className)}>
      <Trans i18nKey={key} components={{ said: guess.word ? <Said text={guess.word} /> : <span /> }} />
    </p>
  )
}

export interface VoteGroup {
  targetId: string
  target: string
  voters: string[]
}

/** Votes grouped by target, the most voted first ("Maryam, Idris and Yusuf voted for Bilal"). */
export function groupVotes(votes: VoteEntry[]): VoteGroup[] {
  const groups = new Map<string, VoteGroup>()
  for (const v of votes) {
    const g = groups.get(v.target_id) ?? { targetId: v.target_id, target: v.target, voters: [] }
    g.voters.push(v.voter)
    groups.set(v.target_id, g)
  }
  return [...groups.values()].sort((a, b) => b.voters.length - a.voters.length)
}

/** "Maryam, Idris and Yusuf" / "Maryam, Idris et Yusuf" / "مريم وإدريس ويوسف". */
export function formatNames(names: string[], lang: string) {
  try {
    return new Intl.ListFormat(lang, { style: "long", type: "conjunction" }).format(names)
  } catch {
    return names.join(", ")
  }
}

/** Who voted for whom, one line per target. */
export function VoteLines({ votes, className }: { votes: VoteEntry[]; className?: string }) {
  const { t, i18n } = useTranslation()
  const groups = groupVotes(votes)
  if (groups.length === 0) return null
  return (
    <ul className={cn("uc-votes", className)}>
      {groups.map((g) => (
        <li key={g.targetId}>
          <b>{formatNames(g.voters, i18n.language)}</b> {t("game.undercover.verdict.votedFor", { count: g.voters.length, target: g.target })}
        </li>
      ))}
    </ul>
  )
}

/**
 * The verdict (sketch D, "The table chose Bilal."): the seat empties and its tablet turns
 * over for everyone, showing the role it held; what a voted-out Mr. White guessed (one line
 * for the whole table, which used to learn nothing of it); then who voted for whom. Used when the round
 * resolves (RoundOverPanel), while Mr. White guesses, and as a notice for a player who
 * missed the moment.
 */
export function Verdict({
  round,
  currentUserId,
  myWord,
  compact = false,
  headingLevel = "h2",
  action,
  className,
  testId,
}: {
  round: VerdictRound
  currentUserId?: string
  /** Your own word, shown on your tablet if the seat that emptied is yours. */
  myWord?: LawhWord | null
  /** One column at every width (inside a narrow column). */
  compact?: boolean
  headingLevel?: "h2" | "h3"
  action?: ReactNode
  className?: string
  testId?: string
}) {
  const { t } = useTranslation()
  const titleId = useId()
  const Heading = headingLevel
  const out = round.eliminated ?? null
  const isMe = !!out && out.user_id === currentUserId
  const title = !out
    ? t("game.undercover.verdict.noOne")
    : isMe
      ? t("game.undercover.verdict.choseYou")
      : t("game.undercover.verdict.chose", { name: out.username })

  return (
    <section className={cn("uc-verdict", className)} data-compact={compact ? "" : undefined} data-testid={testId} aria-labelledby={titleId}>
      <div className="uc-verdict-text">
        <Heading id={titleId} className="type-title text-[26px] sm:text-[30px]">
          {title}
        </Heading>
        {out ? (
          <p className={cn("mt-1.5 max-w-[42ch] text-[15px] leading-normal text-muted-foreground", !compact && "mx-auto lg:mx-0")}>
            {t("game.undercover.verdict.sub")}
          </p>
        ) : null}
        {round.mr_white_guess ? <MrWhiteGuessLine guess={round.mr_white_guess} className={cn("mt-2 max-w-[42ch]", !compact && "mx-auto lg:mx-0")} /> : null}
      </div>
      {out ? (
        <TurnedLawh name={isMe ? t("game.undercover.you") : out.username} round={round.round} role={out.role} word={isMe ? myWord : null} band={!compact} />
      ) : null}
      <VoteLines votes={round.votes} />
      {action ? <div className="uc-verdict-act">{action}</div> : null}
    </section>
  )
}
