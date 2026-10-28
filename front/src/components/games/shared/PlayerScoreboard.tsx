import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { competitionRanks, Figure } from "./quiz-utils"

interface PlayerScore {
  user_id: string
  username: string
  total_score: number
  current_round_answered: boolean
  current_round_points?: number
}

interface PlayerScoreboardProps {
  players: PlayerScore[]
  currentUserId?: string
  /** Mark who has already answered this round (the playing phase). */
  showAnswered?: boolean
  className?: string
}

/**
 * The table's scores, beside the play panel (both quizzes). Tabular: place, name, score,
 * with ties sharing a place. Your row is brass. While a round is open, a lozenge says
 * who has answered (filled, like a ready seat in the halqa) and who is still thinking
 * (a muted outline), with words for screen readers; it never says what anyone answered.
 *
 * The scores are the server's as sent. The Quiz's state holds a round's points back while
 * its question is open (each total as it stood before the round), so the table's order
 * never tells who was right before the reveal.
 */
export const PlayerScoreboard = memo(function PlayerScoreboard({ players, currentUserId, showAnswered = false, className }: PlayerScoreboardProps) {
  const { t } = useTranslation()
  const sorted = [...players].sort((a, b) => b.total_score - a.total_score)
  const ranks = competitionRanks(sorted.map((p) => p.total_score))
  const answered = players.filter((p) => p.current_round_answered).length

  return (
    <Panel className={className} aria-labelledby="quiz-scores-title">
      <PanelHeader
        title={<span id="quiz-scores-title">{t("game.quiz.scores")}</span>}
        sub={showAnswered && players.length > 0 ? t("game.quiz.answeredCount", { answered, total: players.length }) : undefined}
        className="mb-2"
      />
      <ol data-testid="quiz-scoreboard">
        {sorted.map((player, index) => {
          const isMe = player.user_id === currentUserId
          return (
            <li
              key={player.user_id}
              data-you={isMe || undefined}
              className="grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-t border-line py-2.5 first:border-t-0"
            >
              <span className="num text-[13px] text-muted-foreground">{ranks[index]}</span>
              <span className="flex min-w-0 items-center gap-2">
                {showAnswered ? (
                  <Lozenge
                    state={player.current_round_answered ? "ready" : "away"}
                    size={8}
                    label={player.current_round_answered ? t("game.quiz.hasAnswered") : t("game.quiz.stillThinking")}
                  />
                ) : null}
                <span className={cn("truncate text-[15px] font-medium", isMe && "text-brass")}>{player.username}</span>
                {isMe ? <span className="shrink-0 text-[13px] text-muted-foreground">{t("game.quiz.you")}</span> : null}
              </span>
              <Figure className={cn("text-[15px] font-medium", isMe && "text-brass")}>{player.total_score}</Figure>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
})
