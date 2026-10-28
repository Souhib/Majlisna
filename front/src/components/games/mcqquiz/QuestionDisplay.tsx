import { memo } from "react"
import { scriptAttrs } from "@/components/games/shared/quiz-utils"

interface QuestionDisplayProps {
  question: string
}

/**
 * The question (sketch C, D): Readex 500 at 21 px, balanced; an Arabic question in Amiri
 * 700 (`.quiz-question:lang(ar)`). The round counter lives in the panel head now.
 */
export const QuestionDisplay = memo(function QuestionDisplay({ question }: QuestionDisplayProps) {
  return (
    <h2 {...scriptAttrs(question)} className="quiz-question mb-4">
      {question}
    </h2>
  )
})
