import { memo } from "react"
import { useTranslation } from "react-i18next"
import { motion } from "motion/react"
import { cn } from "@/lib/utils"

interface McqRoundResult {
  user_id: string
  username: string
  chose_correct: boolean
  points: number
}

interface McqRoundResultsProps {
  explanation: string | null
  roundResults: McqRoundResult[]
  isHost: boolean
  onNextRound: () => void
  isAdvancing: boolean
}

export const McqRoundResults = memo(function McqRoundResults({
  explanation,
  roundResults,
  isHost,
  onNextRound,
  isAdvancing,
}: McqRoundResultsProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-4">
      {/* Explanation */}
      {explanation && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass rounded-2xl border-border/30 p-5"
        >
          <h3 className="text-xs font-bold text-primary mb-2">{t("game.mcqQuiz.explanation")}</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{explanation}</p>
        </motion.div>
      )}

      {/* Player Results */}
      <div className="glass rounded-2xl border-border/30 p-5">
        <div className="space-y-2">
          {roundResults.map((result, index) => (
            <motion.div
              key={result.user_id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
              className={cn(
                "flex items-center justify-between rounded-xl px-4 py-2.5 border",
                result.chose_correct
                  ? "bg-emerald-500/10 border-emerald-500/30"
                  : "bg-destructive/5 border-destructive/20",
              )}
            >
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/70 text-xs font-bold text-primary-foreground">
                  {result.username.charAt(0).toUpperCase()}
                </div>
                <span className="text-sm font-medium">{result.username}</span>
              </div>
              <span className={cn(
                "text-xs font-bold",
                result.chose_correct ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
              )}>
                {result.chose_correct ? t("game.mcqQuiz.correctAnswer") : t("game.mcqQuiz.wrongAnswer")}
              </span>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Next Round Button (host only) */}
      {isHost && (
        <button
          type="button"
          onClick={onNextRound}
          disabled={isAdvancing}
          className="w-full rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-3 text-sm font-extrabold text-primary-foreground shadow-lg shadow-primary/25 hover:shadow-xl disabled:opacity-50 transition-all duration-200"
        >
          {isAdvancing ? t("common.loading") : t("game.mcqQuiz.nextRound")}
        </button>
      )}
    </div>
  )
})
