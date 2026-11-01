import { memo, useCallback, useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Seal } from "@/components/brand"
import { Figure } from "@/components/games/shared/quiz-utils"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"

/**
 * What a submitted answer comes back as: the server's verdict, a refusal the field says
 * itself (`refused`: the translated message, e.g. a 409 on a round whose tries are used),
 * or null when the page has already said what went wrong (a toast).
 */
export type AnswerSubmitResult = { correct: boolean; points_earned: number } | { refused: string } | null

interface AnswerInputProps {
  onSubmit: (answer: string) => Promise<AnswerSubmitResult>
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
  /**
   * Kalimat's tries left this round (owner rule (e), `my_attempts_left`): shown under the
   * field, which closes at 0. Absent or null (a spectator, the word of the day): no count.
   */
  attemptsLeft?: number | null
  /** The tries a round allows (`max_attempts`), for "You have used your 5 tries". */
  maxAttempts?: number
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
 *
 * With `attemptsLeft` it also counts the round's tries ("3 tries left", read with the
 * field). At 0 the field and the button close, the last miss reads "You have used your 5
 * tries" instead of "try again", and focus moves to that line rather than falling to the
 * page. A refusal the page hands back (`{ refused }`) is said in the field's alert, and
 * what was typed stays.
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
  attemptsLeft,
  maxAttempts,
}: AnswerInputProps) {
  const { t } = useTranslation()
  const [input, setInput] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [wrongGuess, setWrongGuess] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const triesRef = useRef<HTMLParagraphElement>(null)
  const fieldId = `answer-${useId()}`
  const triesId = `${fieldId}-tries`

  const counted = attemptsLeft != null
  const exhausted = counted && attemptsLeft <= 0
  const closed = disabled || exhausted

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = input.trim()
      if (!trimmed || isSubmitting || closed || answered) return
      setIsSubmitting(true)
      setWrongGuess(null)
      setRefusal(null)
      const result = await onSubmit(trimmed)
      if (result && "refused" in result) {
        setRefusal(result.refused)
      } else if (result) {
        setInput("")
        if (!result.correct) {
          setWrongGuess(trimmed)
          inputRef.current?.focus()
        }
      }
      setIsSubmitting(false)
    },
    [input, isSubmitting, closed, answered, onSubmit],
  )

  // The last try closes the field under the player's fingers: a disabled control drops
  // focus to <body>, and the next Tab would restart at the skip link. Focus goes to the
  // line that says why the field closed (only on that change, never when a page opens on
  // a round already used up).
  const wasExhausted = useRef(exhausted)
  useEffect(() => {
    if (exhausted && !wasExhausted.current) {
      const active = document.activeElement
      // the field and its button are the form's only controls
      const inField = !!active && (active === inputRef.current || active === formRef.current?.querySelector("button[type='submit']"))
      if (!active || active === document.body || inField) triesRef.current?.focus({ preventScroll: true })
    }
    wasExhausted.current = exhausted
  }, [exhausted])

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

  // the last miss of the round has nothing to try again: it says the tries are used
  const usedUp = maxAttempts ? t("errors.api.answerAttemptsExhausted", { max: maxAttempts }) : t("game.wordQuiz.triesLeft", { count: 0 })
  const wrongText = wrongGuess ? (exhausted ? usedUp : (wrongGuessMessage?.(wrongGuess) ?? t("game.quiz.kalimat.wrongGuess", { guess: wrongGuess }))) : null
  const error = refusal ?? wrongText ?? undefined
  const hintText = exhausted ? undefined : (hint ?? t("game.quiz.kalimat.spellings"))
  // the count is read with the field, after the Field's own hint or error (its ids)
  const describedBy = counted ? [error ? `${fieldId}-error` : hintText ? `${fieldId}-hint` : null, triesId].filter(Boolean).join(" ") : undefined

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="mt-4">
      <Field id={fieldId} label={t("game.quiz.kalimat.answerLabel")} hideLabel hint={hintText} error={error}>
        <div className="flex gap-2.5">
          <Input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              if (wrongGuess) setWrongGuess(null)
              if (refusal) setRefusal(null)
            }}
            placeholder={placeholder ?? t("game.wordQuiz.typeYourAnswer")}
            disabled={closed}
            maxLength={maxLength}
            aria-describedby={describedBy}
            dir="auto"
            enterKeyHint="send"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            className="min-w-0 flex-1"
          />
          <Button type="submit" disabled={!input.trim() || closed} loading={isSubmitting} className="max-sm:px-4">
            {t("game.quiz.kalimat.answer")}
          </Button>
        </div>
      </Field>
      {counted ? (
        <p ref={triesRef} id={triesId} tabIndex={-1} className="mt-1.5 text-[13px] leading-[1.45] text-muted-foreground outline-none">
          {t("game.wordQuiz.triesLeft", { count: Math.max(0, attemptsLeft) })}
        </p>
      ) : null}
    </form>
  )
})
