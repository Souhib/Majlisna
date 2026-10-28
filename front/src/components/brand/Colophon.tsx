import { type ComponentProps, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { ArchFrame } from "./ArchFrame"
import { SaduBand } from "./SaduBand"
import { Seal } from "./Seal"

/**
 * Colophon: what the evening leaves behind (sketch section H). The single game-over
 * surface for all four games: the result, the words that were played with their
 * meaning, a brass seal for whatever someone earned, the actions, and one madd band
 * closing the card. Set in the arch (`arch`, default) or bare for narrow sidebars.
 *
 * Generic on purpose: Undercover passes the civilian and undercover words, Codenames
 * the board words, the quizzes the round words. Words are Amiri (the Arabic form) +
 * the transliteration + the meaning.
 *
 * The title is an <h2> by default: the E2E helpers wait for `h2:has-text("Game Over")`,
 * so keep "Game Over" (translated) in the title or a visually hidden h2 when you write
 * a custom sentence ("The table found Bilal."). Achievements arrive here as `seals`,
 * never as toasts during the game.
 *
 * <Colophon
 *   title={t("game.gameOver")}
 *   summary="Civilians win. Maryam read the room first."
 *   meta={<>Undercover · <span className="num">3 rounds · 21:40</span></>}
 *   words={[{ word: "صبر", translit: "Ṣabr", note: "held by 4", meaning: "Patience: …" }]}
 *   seals={[{ title: "Taste of Victory", caption: "Maryam" }]}
 *   actions={<><Button>Play again</Button><Button variant="secondary">Back to room</Button></>}
 * />
 */
export interface ColophonWord {
  /** Arabic form, set in Amiri. Optional: some Codenames words exist only in Latin. */
  word?: string
  /** Transliteration or Latin form ("Ṣabr"). Omit in the Arabic interface (no
   *  transliteration there), or when `word` is already Latin. */
  translit?: string
  /** Who held it, which team, which round ("held by 4"). */
  note?: ReactNode
  /** The meaning, in the player's language. */
  meaning?: ReactNode
  /** A control at the end of the row (the notebook's keep toggle). Optional. */
  action?: ReactNode
}

/**
 * The colophon's word rows on their own, for a list set somewhere else than right
 * under the meta line (Kalimat puts its words after the final scores). Same rows as
 * `<Colophon words>`: Amiri word, Latin form + note, meaning, optional end control.
 *
 * A row with a control, in a narrow card (the list is a container; below 24rem, a
 * phone), stacks: the Arabic and the control on one line, then the word and its
 * meaning across the whole width. Three columns there left the meaning a few words
 * wide. Rows without a control keep their two columns at every width.
 */
export function ColophonWordList({ words, className }: { words: ColophonWord[]; className?: string }) {
  if (words.length === 0) return null
  return (
    <ul className={cn("@container border-t border-line-brass", className)}>
      {words.map((w, i) => {
        const placed = w.action != null
        return (
          <li
            key={`${w.word ?? w.translit}-${i}`}
            className={cn(
              "grid items-center gap-x-[18px] gap-y-1 border-b border-line py-2.5",
              placed ? "grid-cols-[auto_minmax(0,1fr)_auto] @max-sm:grid-cols-[minmax(0,1fr)_auto]" : "grid-cols-[auto_1fr]",
            )}
          >
            {w.word ? (
              <span
                lang="ar"
                dir="rtl"
                className={cn(
                  "row-span-2 min-w-[2.6em] text-center type-word text-[38px] text-foreground",
                  placed && "col-start-1 row-start-1 @max-sm:row-span-1 @max-sm:min-w-0 @max-sm:justify-self-start",
                )}
              >
                {w.word}
              </span>
            ) : (
              <span
                aria-hidden="true"
                className={cn(
                  "row-span-2 grid min-w-[2.6em] place-items-center",
                  placed && "col-start-1 row-start-1 @max-sm:row-span-1 @max-sm:min-w-0 @max-sm:justify-self-start",
                )}
              >
                <span className="loz bg-brass [--loz:8px]" />
              </span>
            )}
            <span
              className={cn(
                "flex flex-wrap items-baseline gap-x-1.5 text-[15px] font-medium leading-tight",
                placed && "col-start-2 row-start-1 @max-sm:col-span-2 @max-sm:col-start-1 @max-sm:row-start-2",
              )}
            >
              {w.translit ? <span>{w.translit}</span> : null}
              {w.note ? <small className="text-[13px] font-normal text-muted-foreground">{w.note}</small> : null}
            </span>
            {w.meaning ? (
              <span
                className={cn(
                  "text-[13.5px] leading-[1.4] text-muted-foreground",
                  placed && "col-start-2 row-start-2 @max-sm:col-span-2 @max-sm:col-start-1 @max-sm:row-start-3",
                )}
              >
                {w.meaning}
              </span>
            ) : (
              <span className={cn(placed && "col-start-2 row-start-2 @max-sm:hidden")} />
            )}
            {placed ? (
              <span className="col-start-3 row-span-2 row-start-1 self-center @max-sm:col-start-2 @max-sm:row-span-1">{w.action}</span>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

export interface ColophonSeal {
  title: ReactNode
  caption?: ReactNode
}

export interface ColophonProps extends Omit<ComponentProps<"article">, "title"> {
  title: ReactNode
  titleAs?: "h1" | "h2" | "h3"
  summary?: ReactNode
  /** One short line: game · room · rounds · duration (use `num` on figures). */
  meta?: ReactNode
  words?: ColophonWord[]
  seals?: ColophonSeal[]
  actions?: ReactNode
  /** Anything else under the words (a scoreboard, the vote history). */
  children?: ReactNode
  /** Set the card in the arch with the Jabreen photograph. Default true. */
  arch?: boolean
}

export function Colophon({
  title,
  titleAs: Title = "h2",
  summary,
  meta,
  words,
  seals,
  actions,
  children,
  arch = true,
  className,
  ...props
}: ColophonProps) {
  const card = (
    <article
      data-slot="colophon"
      className={cn(
        "relative z-[1] overflow-hidden rounded-sm border border-line-brass-strong bg-surface px-5 pt-[22px] text-foreground sm:px-6",
        className,
      )}
      {...props}
    >
      <Title className="type-title">{title}</Title>
      {summary ? <p className="mt-1.5 text-sm leading-[1.45] text-muted-foreground">{summary}</p> : null}
      {meta ? <p className="mt-2 type-meta">{meta}</p> : null}

      {words && words.length > 0 ? <ColophonWordList words={words} className="mt-4" /> : null}

      {children ? <div className="mt-4">{children}</div> : null}

      {seals && seals.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-x-[22px] gap-y-2.5">
          {seals.map((s, i) => (
            <Seal key={i} title={s.title} caption={s.caption} />
          ))}
        </div>
      ) : null}

      {actions ? <div className="mb-5 mt-[18px] flex flex-wrap gap-2.5">{actions}</div> : <div className="h-5" />}
      <SaduBand className="-mx-5 sm:-mx-6" />
    </article>
  )
  return arch ? <ArchFrame>{card}</ArchFrame> : card
}
