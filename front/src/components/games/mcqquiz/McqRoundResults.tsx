import { memo } from "react"
import { useTranslation } from "react-i18next"
import { currentLanguage } from "@/components/layout/language-switch"
import { RoundAdvanceButton } from "@/components/games/shared/RoundAdvanceButton"
import { Figure } from "@/components/games/shared/quiz-utils"
import { cn } from "@/lib/utils"
import { choiceLetter } from "./ChoiceButtons"
import { emphasize } from "./emphasize"

interface McqRoundResult {
  user_id: string
  username: string
  chose_correct: boolean
  points: number
  /** The choice they locked in; null when they did not answer (absent from older states). */
  choice_index?: number | null
}

interface McqRoundResultsProps {
  explanation: string | null
  roundResults: McqRoundResult[]
  isHost: boolean
  isReady?: boolean
  readyCount?: number
  /** Every player but the host: what the ready count is measured against. */
  readyTotal?: number
  isLastRound?: boolean
  onNextRound: () => void
  isAdvancing: boolean
  /** The right choice's text, set in bold where the explanation names it. */
  correctChoice?: string | null
  currentUserId?: string
  isSpectator?: boolean
  /** The question's choices, to name each player's pick by its letter. */
  choices?: string[]
}

/**
 * After the reveal (sketch C): the story behind the answer, in Amiri, under a brass
 * rule, with the answer in bold; then how each player did this round (the letter they
 * chose, right or missed, the points), and the way to the next question (the ready system). The explanation's text is kept character for
 * character (the E2E suite looks for it verbatim).
 */
export const McqRoundResults = memo(function McqRoundResults({
  explanation,
  roundResults,
  isHost,
  isReady = false,
  readyCount = 0,
  readyTotal,
  isLastRound,
  onNextRound,
  isAdvancing,
  correctChoice,
  currentUserId,
  isSpectator = false,
  choices,
}: McqRoundResultsProps) {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"

  return (
    <div>
      {explanation ? (
        <section className="mt-4">
          <h3 className="sr-only">{t("game.mcqQuiz.explanation")}</h3>
          <p className="quiz-why">{emphasize(explanation, correctChoice)}</p>
        </section>
      ) : null}

      <h3 className="sr-only">{t("game.quiz.mcq.thisRound")}</h3>
      <ul className="mt-4 border-t border-line" data-testid="mcq-round-results">
        {roundResults.map((result) => {
          const isMe = result.user_id === currentUserId
          // null: they did not answer; undefined: a state from before picks were sent
          const noAnswer = result.choice_index === null && !result.chose_correct
          const letter = result.choice_index != null && choices && result.choice_index < choices.length ? choiceLetter(result.choice_index, arabic) : null
          return (
            <li key={result.user_id} data-you={isMe || undefined} className="flex items-center gap-3 border-b border-line py-2.5">
              <span aria-hidden="true" className={cn("loz [--loz:8px]", result.chose_correct ? "bg-foreground" : "border border-line-field")} />
              <span className={cn("min-w-0 flex-1 truncate text-[15px] font-medium", isMe && "text-brass")}>
                {result.username}
                {isMe ? <span className="ms-2 text-[13px] font-normal text-muted-foreground">{t("game.quiz.you")}</span> : null}
              </span>
              <span className="shrink-0 text-[13px] text-muted-foreground">
                {letter ? (
                  <>
                    <span className="sr-only">{t("game.quiz.mcq.chose")} </span>
                    <span className="font-medium text-foreground">{letter}</span>
                    {" · "}
                  </>
                ) : null}
                {noAnswer ? t("game.quiz.mcq.noAnswer") : result.chose_correct ? t("game.quiz.mcq.right") : t("game.quiz.mcq.missed")}
              </span>
              <Figure
                className={cn(
                  "min-w-[2.5ch] shrink-0 text-end text-[15px] font-medium",
                  !result.chose_correct ? "text-muted-foreground" : isMe ? "text-brass" : undefined,
                )}
              >
                {result.chose_correct ? `+${result.points}` : "0"}
              </Figure>
            </li>
          )
        })}
      </ul>

      <RoundAdvanceButton
        className="mt-5"
        isHost={isHost}
        isReady={isReady}
        readyCount={readyCount}
        readyTotal={readyTotal}
        isAdvancing={isAdvancing}
        isSpectator={isSpectator}
        advanceLabel={isLastRound ? t("game.mcqQuiz.seeResults") : t("game.mcqQuiz.nextRound")}
        onAdvance={onNextRound}
      />
    </div>
  )
})
