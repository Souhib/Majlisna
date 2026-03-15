import { Crown, Trophy } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { motion } from "motion/react"
import { cn } from "@/lib/utils"

interface LeaderboardEntry {
  user_id: string
  username: string
  total_score: number
}

interface McqQuizGameOverProps {
  winner: string | null
  leaderboard: LeaderboardEntry[]
  onBackToRoom: () => void
  onLeaveRoom: () => void
}

export const McqQuizGameOver = memo(function McqQuizGameOver({
  winner,
  leaderboard,
  onBackToRoom,
  onLeaveRoom,
}: McqQuizGameOverProps) {
  const { t } = useTranslation()
  const sorted = [...leaderboard].sort((a, b) => b.total_score - a.total_score)

  return (
    <div className="space-y-6">
      {winner && (
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="glass rounded-2xl border-primary/30 p-6 text-center"
        >
          <Trophy className="h-12 w-12 mx-auto text-yellow-500 mb-3 drop-shadow-lg" />
          <h2 className="text-xl font-extrabold tracking-tight gradient-text">
            {t("game.mcqQuiz.winner", { username: winner })}
          </h2>
        </motion.div>
      )}

      <div className="glass rounded-2xl border-border/30 p-5">
        <h3 className="text-sm font-extrabold tracking-tight mb-4">{t("game.mcqQuiz.finalScores")}</h3>
        <div className="space-y-2">
          {sorted.map((entry, index) => (
            <motion.div
              key={entry.user_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className={cn(
                "flex items-center justify-between rounded-xl px-4 py-3 border transition-all duration-200",
                index === 0
                  ? "bg-yellow-500/10 border-yellow-500/30"
                  : index === 1
                    ? "bg-muted/30 border-border/30"
                    : index === 2
                      ? "bg-amber-800/10 border-amber-800/20"
                      : "border-border/20",
              )}
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-muted-foreground w-5">#{index + 1}</span>
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/70 text-xs font-bold text-primary-foreground">
                  {entry.username.charAt(0).toUpperCase()}
                </div>
                <span className="text-sm font-medium">{entry.username}</span>
                {index === 0 && <Crown className="h-4 w-4 text-yellow-500" />}
              </div>
              <span className="font-mono tabular-nums font-bold">{entry.total_score}</span>
            </motion.div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onBackToRoom}
          className="flex-1 rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-3 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg transition-all duration-200"
        >
          {t("game.mcqQuiz.backToRoom")}
        </button>
        <button
          type="button"
          onClick={onLeaveRoom}
          className="rounded-xl border border-border/50 px-5 py-3 text-sm font-medium hover:bg-muted/50 transition-all duration-200"
        >
          {t("room.leave")}
        </button>
      </div>
    </div>
  )
})
