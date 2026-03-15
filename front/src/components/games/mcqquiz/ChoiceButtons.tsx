import { memo } from "react"
import { motion } from "motion/react"
import { Check, X } from "lucide-react"
import { cn } from "@/lib/utils"

interface ChoiceButtonsProps {
  choices: string[]
  onSelect: (index: number) => void
  disabled: boolean
  selectedIndex: number | null
  correctIndex: number | null // only set during results/game_over
  roundPhase: string
}

const LABELS = ["A", "B", "C", "D"]

export const ChoiceButtons = memo(function ChoiceButtons({
  choices,
  onSelect,
  disabled,
  selectedIndex,
  correctIndex,
  roundPhase,
}: ChoiceButtonsProps) {
  const showResults = roundPhase === "results" || roundPhase === "game_over"

  return (
    <div className="grid grid-cols-1 gap-3">
      {choices.map((choice, index) => {
        const isSelected = selectedIndex === index
        const isCorrect = correctIndex === index
        const isWrong = showResults && isSelected && !isCorrect

        let buttonClass = "glass hover:bg-muted/80 border-border/30"
        if (showResults) {
          if (isCorrect) {
            buttonClass = "bg-emerald-500/15 border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
          } else if (isWrong) {
            buttonClass = "bg-destructive/10 border-destructive/30 text-destructive"
          } else {
            buttonClass = "opacity-50 border-border/20"
          }
        } else if (isSelected) {
          buttonClass = "bg-primary/15 border-primary/40 shadow-md shadow-primary/10"
        }

        return (
          <motion.button
            key={index}
            type="button"
            onClick={() => !disabled && onSelect(index)}
            disabled={disabled}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className={cn(
              "flex items-center gap-3 rounded-xl border px-4 py-3.5 text-left transition-all duration-200",
              disabled && !showResults && "cursor-not-allowed opacity-60",
              buttonClass,
            )}
          >
            <span className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold",
              showResults && isCorrect
                ? "bg-emerald-500 text-white"
                : showResults && isWrong
                  ? "bg-destructive text-destructive-foreground"
                  : isSelected
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted/50",
            )}>
              {showResults && isCorrect ? <Check className="h-4 w-4" /> :
               showResults && isWrong ? <X className="h-4 w-4" /> :
               LABELS[index]}
            </span>
            <span className="text-sm font-medium flex-1">{choice}</span>
          </motion.button>
        )
      })}
    </div>
  )
})
