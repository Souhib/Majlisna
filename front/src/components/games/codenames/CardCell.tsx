import { type CSSProperties, memo, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { TeamGlyph } from "@/components/brand"
import { initialsOf } from "@/components/ui/avatar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { arabicForm, cardFace, cardGlyph, type CodenamesCard, fitLatin, longestSegment } from "./model"

export interface CardVoter {
  id: string
  name: string
}

interface CardCellProps {
  card: CodenamesCard
  index: number
  isSpymaster: boolean
  canGuess: boolean
  isFinished: boolean
  onGuess: (index: number) => void
  /** Teammates pointing at this card (the current team's operatives). */
  voters?: CardVoter[]
  /** Legacy count, used when the voters are not known by name. */
  voteCount?: number
  isMyVote?: boolean
  onHintViewed?: (word: string) => void
  /** End of game: whether the card was turned during play (unturned cards read as the key). */
  played?: boolean
  /** The interface is Arabic: the Arabic word leads. */
  arabicLeads?: boolean
}

const MAX_BADGES = 3

/**
 * One card of the 5 × 5 board (sketch C/D). A card is cloth: face down it is the bare
 * card with bare warp at its edge; turned over it is dyed in its team's wool with the
 * team's glyph and woven selvedge; the spymaster sees the glyph and the selvedge on the
 * bare card. Teammates pointing draw a dashed brass outline and their initials.
 *
 * The card is ONE control. While the viewer may guess it, a tap points at it (votes);
 * otherwise, when the server has given its meaning, a tap opens the meaning; otherwise
 * it is inert. (The old card nested an info button inside the card button.)
 */
export const CardCell = memo(function CardCell({
  card,
  index,
  isSpymaster,
  canGuess,
  isFinished,
  onGuess,
  voters,
  voteCount,
  isMyVote = false,
  onHintViewed,
  played,
  arabicLeads = false,
}: CardCellProps) {
  const { t } = useTranslation()
  const face = cardFace(card, { isSpymaster, isFinished, played })
  const team = face === "bare" ? null : cardGlyph(card.card_type)
  const ar = arabicForm(card)
  const latin = fitLatin(card.word)
  const canVote = canGuess && !card.revealed && !isFinished
  const hasMeaning = !canVote && !!card.hint && face !== "bare"
  const act = canVote ? "vote" : hasMeaning ? "meaning" : undefined

  const pointing = !card.revealed && !isFinished ? (voters ?? []) : []
  const count = !card.revealed && !isFinished ? Math.max(pointing.length, voteCount ?? 0) : 0
  const pointed = count > 0
  const mine = isMyVote && !card.revealed && !isFinished

  // A card turned while this screen is open weaves its selvedge once (not on load).
  const previousFace = useRef(face)
  const [fresh, setFresh] = useState(false)
  useEffect(() => {
    if (previousFace.current !== "wool" && face === "wool") setFresh(true)
    previousFace.current = face
  }, [face])

  const notified = useRef(false)
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (open && !notified.current && onHintViewed) {
        notified.current = true
        onHintViewed(card.word)
      }
    },
    [onHintViewed, card.word],
  )

  // The accessible name starts with the word (the E2E helpers match /^Word\b/).
  const words = arabicLeads && ar ? `${ar}، ${card.word}` : card.word
  const state: string[] = []
  if (team) {
    const teamName = t(`game.codenames.card.${team}`)
    state.push(face === "wool" && !isFinished ? t("game.codenames.card.turned", { team: teamName }) : teamName)
  }
  if (mine) state.push(t("game.codenames.card.yourChoice"))
  if (pointing.length > 0) state.push(t("game.codenames.card.pointedBy", { names: pointing.map((v) => v.name).join(", ") }))
  else if (count > 0) state.push(t("game.codenames.card.pointedCount", { count }))
  if (hasMeaning) state.push(t("game.codenames.card.meaning"))
  const label = [words, ...state].join(", ")

  const badges = pointing.length > 0 ? pointing.slice(0, MAX_BADGES).map((v) => initialsOf(v.name)) : count > 0 ? [String(count)] : []
  const extra = pointing.length > MAX_BADGES ? pointing.length - MAX_BADGES : 0

  const button = (
    <button
      data-testid="codenames-card"
      type="button"
      className="cn-card"
      data-face={face}
      data-team={team ?? undefined}
      data-act={act}
      data-pointed={pointed && !mine ? "true" : undefined}
      data-mine={mine ? "true" : undefined}
      data-lead={arabicLeads ? "ar" : "lat"}
      data-fresh={fresh ? "true" : undefined}
      dir={arabicLeads ? "rtl" : "ltr"}
      aria-label={label}
      disabled={!act}
      onClick={canVote ? () => onGuess(index) : undefined}
    >
      {team ? <TeamGlyph team={team} className="cn-glyph" /> : null}
      {badges.length > 0 ? (
        <span className="cn-ptr" aria-hidden="true">
          {badges.map((b, i) => (
            <span key={i}>{b}</span>
          ))}
          {extra > 0 ? <span>+{extra}</span> : null}
        </span>
      ) : null}
      <span className="cn-words" aria-hidden="true">
        <span
          className="cn-lat"
          dir="ltr"
          // hyphenation needs a Latin dictionary: the Arabic page's own lang has none
          lang={arabicLeads ? "en" : undefined}
          style={{ "--em": latin.em } as CSSProperties}
        >
          {latin.text}
        </span>
        {ar ? (
          <span className="cn-ar" lang="ar" dir="rtl" style={{ "--seg": longestSegment(ar) } as CSSProperties}>
            {ar}
          </span>
        ) : null}
      </span>
    </button>
  )

  if (act !== "meaning") return button

  return (
    <Popover onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>{button}</PopoverTrigger>
      <PopoverContent arrow className="w-72">
        {ar ? (
          <p lang="ar" dir="rtl" className="type-word text-start text-[30px] text-foreground">
            {ar}
          </p>
        ) : null}
        <p className="flex items-center gap-2 text-[15px] font-medium leading-tight">
          {team ? <TeamGlyph team={team} className={team === "assassin" ? undefined : "text-muted-foreground"} /> : null}
          <span dir="ltr">{card.word}</span>
        </p>
        <p className="mt-2 text-[14px] leading-normal text-muted-foreground">{card.hint}</p>
      </PopoverContent>
    </Popover>
  )
})
