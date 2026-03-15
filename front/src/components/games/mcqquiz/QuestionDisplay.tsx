import { memo } from "react"
import { useTranslation } from "react-i18next"

interface QuestionDisplayProps {
  question: string
  currentRound: number
  totalRounds: number
}

export const QuestionDisplay = memo(function QuestionDisplay({
  question,
  currentRound,
  totalRounds,
}: QuestionDisplayProps) {
  const { t } = useTranslation()

  return (
    <div className="glass rounded-2xl border-border/30 p-6 text-center">
      <p className="text-xs font-mono tabular-nums text-muted-foreground mb-3">
        {t("game.mcqQuiz.round", { current: currentRound, total: totalRounds })}
      </p>
      <h2 className="text-lg font-extrabold tracking-tight leading-relaxed">{question}</h2>
    </div>
  )
})
