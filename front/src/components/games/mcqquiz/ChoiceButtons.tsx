import { type CSSProperties, type KeyboardEvent, memo, type ReactNode, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { currentLanguage } from "@/components/layout/language-switch"
import { scriptAttrs } from "@/components/games/shared/quiz-utils"
import { cn } from "@/lib/utils"
import { tallyShares } from "./reveal"

interface ChoiceButtonsProps {
  choices: string[]
  onSelect: (index: number) => void
  disabled: boolean
  selectedIndex: number | null
  correctIndex: number | null // only set during results/game_over
  roundPhase: string
  /** A short note at the end of each choice: "you", "+2 · 3 players". */
  tags?: (ReactNode | null | undefined)[]
  /** The server's tallies at the reveal (`choice_tallies`), one count per choice. */
  tallies?: number[] | null
  /** How many play: what each tally thread is a share of. */
  players?: number
}

const LATIN = ["A", "B", "C", "D"]
/** The Arabic interface letters its choices with the abjad order (DESIGN.md §8). */
const ABJAD = ["أ", "ب", "ج", "د"]

/** A choice's letter in the interface's alphabet: A B C D, or أ ب ج د in Arabic. */
export function choiceLetter(index: number, arabic: boolean): string | null {
  return (arabic ? ABJAD : LATIN)[index] ?? null
}

/**
 * The four choices (sketch C, D), each with its letter in a brass lozenge. While the
 * question is open they are radio buttons: the one you pick takes an ink lozenge and a
 * brass hairline until you lock it in. Once the answer is revealed they become a list:
 * the right one in brass, a wrong pick struck through on its LETTER, never over the
 * words (a choice may be a name of the Prophet or of Allah: nothing passes over it).
 *
 * The radio group follows the ARIA pattern: one tab stop (the chosen choice, or the
 * first), the arrow keys move between choices and choose (Left/Right mirrored in the
 * Arabic interface), Home/End jump to the first/last.
 *
 * At the reveal each choice draws its tally (the server's `choice_tallies`) as a 3 px
 * khayt thread under its words: its share of the players, the right one in brass. The
 * threads are a picture (`aria-hidden`); the tag at the end of the row stays the words.
 * When the reveal happens on screen (the question was open here a moment ago) the
 * threads are woven in from the reading start, 640 ms on the qalam's curve, 30 ms apart,
 * and the right choice's letter is pressed as a seal once the phase crossfade is done
 * (`seal-press`, `data-seal-index`); a page opened at the reveal shows the final lengths
 * still. All of it is CSS on `data-weave` (styles/pages/quiz.css), reduced motion
 * included: the final lengths, faded in over 140 ms.
 */
export const ChoiceButtons = memo(function ChoiceButtons({
  choices,
  onSelect,
  disabled,
  selectedIndex,
  correctIndex,
  roundPhase,
  tags,
  tallies,
  players = 0,
}: ChoiceButtonsProps) {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"
  const letters = arabic ? ABJAD : LATIN
  const showResults = roundPhase === "results" || roundPhase === "game_over"
  // The reveal seen happening here (the previous render had the question open), as
  // opposed to a page opened at it: only then is it woven. Kept for the whole reveal, so a
  // refetch or a push of the same state restarts nothing.
  const [shownBefore, setShownBefore] = useState(showResults)
  const [weave, setWeave] = useState(false)
  if (shownBefore !== showResults) {
    setShownBefore(showResults)
    setWeave(showResults)
  }
  const shares = showResults ? tallyShares(tallies, players) : null
  const radios = useRef<(HTMLButtonElement | null)[]>([])
  const tabStop = selectedIndex != null && selectedIndex >= 0 && selectedIndex < choices.length ? selectedIndex : 0

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const n = choices.length
    if (n === 0 || disabled) return
    const forward = arabic ? "ArrowLeft" : "ArrowRight"
    const backward = arabic ? "ArrowRight" : "ArrowLeft"
    const from = Math.max(
      0,
      radios.current.findIndex((el) => el === document.activeElement),
    )
    let next: number | null = null
    if (e.key === "ArrowDown" || e.key === forward) next = (from + 1) % n
    else if (e.key === "ArrowUp" || e.key === backward) next = (from - 1 + n) % n
    else if (e.key === "Home") next = 0
    else if (e.key === "End") next = n - 1
    if (next == null) return
    e.preventDefault()
    radios.current[next]?.focus()
    onSelect(next)
  }

  if (showResults) {
    return (
      <ul className="quiz-choices grid gap-2" aria-label={t("game.quiz.mcq.choices")} data-weave={weave || undefined}>
        {choices.map((choice, index) => {
          const isRight = correctIndex === index
          const isWrongPick = selectedIndex === index && !isRight
          const state = isRight ? "right" : isWrongPick ? "wrong" : undefined
          const share = shares?.[index]
          const pressed = weave && isRight
          return (
            <li key={index} className="quiz-choice" data-state={state} data-tally={share != null || undefined}>
              <span className={cn("choice-letter", pressed && "seal-press")} data-seal-index={pressed ? 0 : undefined} aria-hidden="true">
                {letters[index]}
              </span>
              <span className="min-w-0">
                <span className="sr-only">{letters[index]}: </span>
                <span {...scriptAttrs(choice)} className="choice-text">
                  {choice}
                </span>
                {isRight ? <span className="sr-only">, {t("game.quiz.mcq.rightAnswer")}</span> : null}
                {isWrongPick ? <span className="sr-only">, {t("game.quiz.mcq.yourWrongAnswer")}</span> : null}
              </span>
              <span className="choice-tag">{tags?.[index]}</span>
              {share != null ? (
                <span className="choice-tally" aria-hidden="true" style={{ "--share": share, "--i": index } as CSSProperties}>
                  {/* nobody's choice keeps its bare warp: nothing to weave */}
                  {share > 0 ? <i /> : null}
                </span>
              ) : null}
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div role="radiogroup" aria-label={t("game.quiz.mcq.choices")} className="grid gap-2" onKeyDown={handleKeyDown}>
      {choices.map((choice, index) => {
        const isSelected = selectedIndex === index
        return (
          <button
            key={index}
            ref={(el) => {
              radios.current[index] = el
            }}
            type="button"
            role="radio"
            aria-checked={isSelected}
            tabIndex={index === tabStop ? 0 : -1}
            aria-label={`${letters[index]}: ${choice}`}
            onClick={() => !disabled && onSelect(index)}
            disabled={disabled}
            className="quiz-choice"
            data-state={isSelected ? "chosen" : undefined}
          >
            <span className="choice-letter" aria-hidden="true">
              {letters[index]}
            </span>
            <span {...scriptAttrs(choice)} className="choice-text min-w-0">
              {choice}
            </span>
            <span className="choice-tag">{tags?.[index]}</span>
          </button>
        )
      })}
    </div>
  )
})
