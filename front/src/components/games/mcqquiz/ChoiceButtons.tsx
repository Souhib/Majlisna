import { type KeyboardEvent, memo, type ReactNode, useRef } from "react"
import { useTranslation } from "react-i18next"
import { currentLanguage } from "@/components/layout/language-switch"
import { scriptAttrs } from "@/components/games/shared/quiz-utils"

interface ChoiceButtonsProps {
  choices: string[]
  onSelect: (index: number) => void
  disabled: boolean
  selectedIndex: number | null
  correctIndex: number | null // only set during results/game_over
  roundPhase: string
  /** A short note at the end of each choice: "you", "+2 · 3 players". */
  tags?: (ReactNode | null | undefined)[]
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
 */
export const ChoiceButtons = memo(function ChoiceButtons({ choices, onSelect, disabled, selectedIndex, correctIndex, roundPhase, tags }: ChoiceButtonsProps) {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"
  const letters = arabic ? ABJAD : LATIN
  const showResults = roundPhase === "results" || roundPhase === "game_over"
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
      <ul className="grid gap-2" aria-label={t("game.quiz.mcq.choices")}>
        {choices.map((choice, index) => {
          const isRight = correctIndex === index
          const isWrongPick = selectedIndex === index && !isRight
          const state = isRight ? "right" : isWrongPick ? "wrong" : undefined
          return (
            <li key={index} className="quiz-choice" data-state={state}>
              <span className="choice-letter" aria-hidden="true">
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
