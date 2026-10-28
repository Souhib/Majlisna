import { memo } from "react"
import { useTranslation } from "react-i18next"
import { RoundAdvanceButton } from "@/components/games/shared/RoundAdvanceButton"
import { competitionRanks, Figure, isArabicScript, scriptAttrs } from "@/components/games/shared/quiz-utils"
import { cn } from "@/lib/utils"

interface RoundResult {
  user_id: string
  username: string
  answered_at_hint: number | null
  points: number
  /** What they wrote: the answer that found it, else their last wrong try (from the results phase on). */
  typed_answer?: string | null
  /** How many tries they made this round. */
  attempts?: number
}

/** What a player wrote, in their hand when it is Arabic (Aref Ruqaa), as typed otherwise. */
function Written({ text }: { text: string }) {
  return isArabicScript(text) ? (
    <span lang="ar" dir="rtl" className="type-hand bidi-isolate text-[19px] leading-none text-foreground">
      {text}
    </span>
  ) : (
    <bdi dir="auto" className="font-medium text-foreground">
      {text}
    </bdi>
  )
}

interface RoundResultsProps {
  correctAnswer: string
  explanation?: string | null
  roundResults: RoundResult[]
  isHost: boolean
  isReady?: boolean
  readyCount?: number
  /** Every player but the host: what the ready count is measured against. */
  readyTotal?: number
  isLastRound?: boolean
  onNextRound: () => void
  isAdvancing: boolean
  currentUserId?: string
  isSpectator?: boolean
}

/**
 * The end of a Kalimat round: the word, revealed in Amiri, with its explanation; then
 * who found it, at which hint, with what they wrote (the server's `typed_answer`, in their
 * hand when Arabic), for how many points (yours in brass); who missed it, with their last
 * try and how many they made; and the way to the next round (the ready system). "The
 * answer was" stays in the text: the E2E suite reads it.
 */
export const RoundResults = memo(function RoundResults({
  correctAnswer,
  explanation,
  roundResults,
  isHost,
  isReady = false,
  readyCount = 0,
  readyTotal,
  isLastRound,
  onNextRound,
  isAdvancing,
  currentUserId,
  isSpectator = false,
}: RoundResultsProps) {
  const { t } = useTranslation()
  const sorted = [...roundResults].sort((a, b) => b.points - a.points)
  const ranks = competitionRanks(sorted.map((r) => r.points))

  return (
    <div>
      <section aria-labelledby="kalimat-answer" className="border-t border-line-brass pt-4 pb-5">
        <p id="kalimat-answer" className="type-label">
          {t("game.quiz.kalimat.answerWas")}
        </p>
        <p {...scriptAttrs(correctAnswer)} className="ink mt-1 type-word text-[clamp(34px,6vw,44px)] text-foreground">
          {correctAnswer}
        </p>
        {explanation ? <p className="quiz-why mt-1 max-w-[62ch] border-t-0 px-0 pt-1">{explanation}</p> : null}
      </section>

      <h2 className="sr-only">{t("game.quiz.kalimat.whoFound")}</h2>
      <ol className="border-t border-line" data-testid="kalimat-round-results">
        {sorted.map((result, index) => {
          const isMe = result.user_id === currentUserId
          const found = result.answered_at_hint != null && result.points > 0
          const written = result.typed_answer?.trim() || null
          const tries = result.attempts ?? 0
          return (
            <li
              key={result.user_id}
              data-you={isMe || undefined}
              className="grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line py-2.5"
            >
              <span className="num text-[13px] text-muted-foreground">{ranks[index]}</span>
              <span className="min-w-0">
                <span className={cn("block truncate text-[15px] font-medium", isMe && "text-brass")}>
                  {result.username}
                  {isMe ? <span className="ms-2 text-[13px] font-normal text-muted-foreground">{t("game.quiz.you")}</span> : null}
                </span>
                <span className="flex flex-wrap items-baseline gap-x-1.5 text-[13px] text-muted-foreground">
                  {found ? (
                    <>
                      <span>{t("game.quiz.kalimat.atHint", { number: result.answered_at_hint })}</span>
                      {written ? (
                        <>
                          <span aria-hidden="true">·</span>
                          <Written text={written} />
                        </>
                      ) : null}
                    </>
                  ) : written && tries > 0 ? (
                    <>
                      <span>{t("game.quiz.kalimat.lastTry")}</span>
                      <Written text={written} />
                      <span aria-hidden="true">·</span>
                      <span className="num">{t("game.quiz.kalimat.tries", { count: tries })}</span>
                    </>
                  ) : (
                    <span>{t("game.wordQuiz.notAnswered")}</span>
                  )}
                </span>
              </span>
              {found ? (
                <Figure className={cn("text-[17px] font-medium", isMe && "text-brass")}>+{result.points}</Figure>
              ) : (
                <Figure className="text-[15px] text-muted-foreground">0</Figure>
              )}
            </li>
          )
        })}
      </ol>

      <RoundAdvanceButton
        className="mt-5"
        isHost={isHost}
        isReady={isReady}
        readyCount={readyCount}
        readyTotal={readyTotal}
        isAdvancing={isAdvancing}
        isSpectator={isSpectator}
        advanceLabel={isLastRound ? t("game.wordQuiz.seeResults") : t("game.wordQuiz.nextRound")}
        onAdvance={onNextRound}
      />
    </div>
  )
})
