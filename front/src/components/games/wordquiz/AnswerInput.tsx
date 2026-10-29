import { memo, useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Seal } from "@/components/brand"
import { Figure } from "@/components/games/shared/quiz-utils"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"

interface AnswerInputProps {
  onSubmit: (answer: string) => Promise<{ correct: boolean; points_earned: number } | null>
  disabled: boolean
  answered: boolean
  pointsEarned: number
  /** A line under "You found it" once you have (what happens next). */
  answeredNote?: string
  /** The field's prompt, worded for the round's theme ("Where is it?"); defaults to "Type your answer". */
  placeholder?: string
  /** The line under the field; defaults to "Arabic, French and English spellings all count." */
  hint?: string
  /** What a wrong guess says; defaults to "“Zakari” is not it. Try again: the next hint may help." */
  wrongGuessMessage?: (guess: string) => string
  /** The longest answer the server takes; defaults to `ANSWER_MAX_LENGTH`. */
  maxLength?: number
}

/**
 * The longest answer either game's server accepts: Kalimat's `SubmitAnswerRequest.answer`
 * and the word of the day's `DailyWordGuessRequest.answer` (`DAILY_WORD_ANSWER_MAX_LENGTH`
 * in backend/majlisna/api/constants.py) are both 100. A longer one used to reach the
 * server and come back as a generic 422 the player could not act on.
 */
export const ANSWER_MAX_LENGTH = 100

/**
 * Kalimat's answer row (sketch C, D): one field and "Answer", with the reassurance
 * that every spelling counts. A wrong guess is named in the error ("“Zakari” is not
 * it") and the field is cleared for the next try, focus kept. Once you have found it,
 * the row locks: a brass seal, the points, and how many have found it so far.
 */
export const AnswerInput = memo(function AnswerInput({
  onSubmit,
  disabled,
  answered,
  pointsEarned,
  answeredNote,
  placeholder,
  hint,
  wrongGuessMessage,
  maxLength = ANSWER_MAX_LENGTH,
}: AnswerInputProps) {
  const { t } = useTranslation()
  const [input, setInput] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [wrongGuess, setWrongGuess] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = input.trim()
      if (!trimmed || isSubmitting || disabled || answered) return
      setIsSubmitting(true)
      setWrongGuess(null)
      const result = await onSubmit(trimmed)
      if (result) {
        setInput("")
        if (!result.correct) {
          setWrongGuess(trimmed)
          inputRef.current?.focus()
        }
      }
      setIsSubmitting(false)
    },
    [input, isSubmitting, disabled, answered, onSubmit],
  )

  if (answered) {
    return (
      <div
        role="status"
        className="mt-4 flex items-center gap-3.5 rounded-sm border border-line-brass-strong bg-[color-mix(in_oklch,var(--brass)_9%,var(--surface))] px-4 py-3"
      >
        <Seal size={26} />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-medium leading-tight">{t("game.quiz.kalimat.found")}</p>
          {answeredNote ? <p className="mt-0.5 text-[13px] text-muted-foreground">{answeredNote}</p> : null}
        </div>
        <span className="text-[18px] font-medium text-primary-on-tint">
          <span className="sr-only">{t("game.quiz.kalimat.pointsSr", { count: pointsEarned })}</span>
          <span aria-hidden="true">
            <Figure>+{pointsEarned}</Figure>
          </span>
        </span>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mt-4">
      <Field
        label={t("game.quiz.kalimat.answerLabel")}
        hideLabel
        hint={hint ?? t("game.quiz.kalimat.spellings")}
        error={wrongGuess ? (wrongGuessMessage?.(wrongGuess) ?? t("game.quiz.kalimat.wrongGuess", { guess: wrongGuess })) : undefined}
      >
        <div className="flex gap-2.5">
          <Input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              if (wrongGuess) setWrongGuess(null)
            }}
            placeholder={placeholder ?? t("game.wordQuiz.typeYourAnswer")}
            disabled={disabled}
            maxLength={maxLength}
            dir="auto"
            enterKeyHint="send"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            className="min-w-0 flex-1"
          />
          <Button type="submit" disabled={!input.trim() || disabled} loading={isSubmitting} className="max-sm:px-4">
            {t("game.quiz.kalimat.answer")}
          </Button>
        </div>
      </Field>
    </form>
  )
})
