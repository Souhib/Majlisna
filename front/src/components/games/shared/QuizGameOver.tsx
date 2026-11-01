import { memo, type ReactNode, useId } from "react"
import { useTranslation } from "react-i18next"
import { Colophon, type ColophonSeal } from "@/components/brand"
import type { ColophonShare } from "@/components/brand/share-card/game-card"
import { GameWordsList } from "@/components/notebook/KeepWords"
import { useRouteNotebookGameId } from "@/components/notebook/route-game"
import { useColophonNotebook } from "@/components/notebook/use-colophon-notebook"
import { cn } from "@/lib/utils"
import { ColophonActions } from "./ColophonActions"
import { competitionRanks, Figure, listFormat } from "./quiz-utils"

interface LeaderboardEntry {
  user_id: string
  username: string
  total_score: number
}

interface QuizGameOverProps {
  winner: string | null
  leaderboard: LeaderboardEntry[]
  onBackToRoom: () => void
  onLeaveRoom: () => void
  winnerI18nKey?: string
  finalScoresI18nKey?: string
  currentUserId?: string
  /** The room it was played in (the way back, and the host's "Play again"). */
  roomId?: string | null
  /** The viewer hosts the room: only they get "Play again". */
  isHost?: boolean
  /** One short line under the title: game · rounds · players. */
  meta?: ReactNode
  /** Achievements earned in this game, pressed as seals (never mid-game toasts). */
  seals?: ColophonSeal[]
  /** Actions set before "Back to room". */
  extraActions?: ReactNode
  /**
   * The Kalimat game whose words the colophon lists and keeps. Defaults to the id in
   * the page's URL when it is a Kalimat page (`/game/wordquiz/<id>`); MCQ has no words.
   */
  wordQuizGameId?: string
  /** The game as the colophon card names it (spec 11): "Share", for a player only (as Keep). */
  share?: ColophonShare
}

/**
 * The end of a quiz, as the colophon (sketch section H): the result as the title, the
 * final scores, a brass seal for each achievement someone earned, and the way back,
 * all in the Jabreen arch. The title is the colophon's h2 and always carries "Game
 * Over" (visually hidden when a sentence says who won), which the E2E helpers wait on.
 *
 * The result follows owner rule (a), read from the final leaderboard (leavers are not on
 * it), the same rule the server records the wins by:
 * - several top scorers above 0 share the win, all of them named ("Umar and Aisha share
 *   the win.", then "4 points each."); the server's `winner` is null then;
 * - a game where nobody scored has no winner ("No one scored: no winner this time.");
 * - a game of one is never a win: it says the player's score ("You finished with 7 points.");
 * - one top scorer wins ("Umar wins.", then "3 points clear of Aisha."), named by the
 *   server's `winner`. Without it (a state from before the end) the title is "Game Over".
 *
 * Kalimat also lists the game's words after the scores (from the notebook's read of
 * the game: the quiz state only holds the current round's answer) and offers "Keep
 * the words", the brass action until they are all kept. A spectator, who is not on the
 * leaderboard, and the MCQ quiz get neither.
 */
export const QuizGameOver = memo(function QuizGameOver({
  winner,
  leaderboard,
  onBackToRoom,
  onLeaveRoom,
  winnerI18nKey = "game.winner",
  finalScoresI18nKey = "game.finalScores",
  currentUserId,
  roomId = null,
  isHost = false,
  meta,
  seals,
  extraActions,
  wordQuizGameId,
  share,
}: QuizGameOverProps) {
  const { t, i18n } = useTranslation()
  const routeGameId = useRouteNotebookGameId("word_quiz")
  const gameId = wordQuizGameId ?? routeGameId
  const isPlayer = !currentUserId || leaderboard.some((e) => e.user_id === currentUserId)
  const notebook = useColophonNotebook(gameId, { enabled: isPlayer })
  const wordsTitleId = useId()
  const sorted = [...leaderboard].sort((a, b) => b.total_score - a.total_score)
  const ranks = competitionRanks(sorted.map((e) => e.total_score))
  const leaders = sorted.filter((_, i) => ranks[i] === 1)
  const solo = sorted.length === 1
  // Only a score above 0 wins anything: a 0-0 game has no winner, and no one is first.
  const topScore = sorted[0]?.total_score ?? 0
  const someoneScored = topScore > 0

  let sentence: string | null = null
  let summary: string | undefined
  if (solo) {
    sentence = t("game.quiz.soloScore", { count: sorted[0].total_score })
  } else if (sorted.length > 0 && !someoneScored) {
    sentence = t("game.quiz.noWinner")
  } else if (leaders.length > 1) {
    sentence = t("game.quiz.sharedWin", {
      names: listFormat(
        leaders.map((e) => e.username),
        i18n.language,
      ),
    })
    summary = t("game.quiz.tieSummary", { count: topScore })
  } else if (winner) {
    sentence = t(winnerI18nKey, { username: leaders[0]?.username ?? winner })
    const runnerUp = sorted[1]
    if (leaders[0] && runnerUp) {
      summary = t("game.quiz.winSummary", { count: leaders[0].total_score - runnerUp.total_score, name: runnerUp.username })
    }
  }

  const title = sentence ? (
    <>
      <span className="sr-only">{t("game.gameOverLead")}</span>
      <span className="ink inline-block">{sentence}</span>
    </>
  ) : (
    t("game.gameOver")
  )

  return (
    <Colophon
      title={title}
      summary={summary}
      meta={meta}
      seals={seals}
      actions={
        <>
          {extraActions}
          <ColophonActions
            notebook={gameId && isPlayer ? notebook : undefined}
            roomId={roomId}
            isHost={isHost}
            onBackToRoom={onBackToRoom}
            onLeaveRoom={onLeaveRoom}
            share={isPlayer ? share : undefined}
          />
        </>
      }
    >
      <h3 className="type-label">{t(finalScoresI18nKey)}</h3>
      <ol className="mt-1.5 border-t border-line-brass" data-testid="quiz-final-scores">
        {sorted.map((entry, index) => {
          const isMe = entry.user_id === currentUserId
          const first = ranks[index] === 1 && !solo && someoneScored
          return (
            <li
              key={entry.user_id}
              data-you={isMe || undefined}
              className="grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line py-2.5"
            >
              <span className="num text-[13px] text-muted-foreground">{ranks[index]}</span>
              <span className="flex min-w-0 items-center gap-2">
                {first ? <span aria-hidden="true" className="loz bg-brass [--loz:7px]" /> : null}
                <span className={cn("truncate text-[15px] font-medium", isMe && "text-brass")}>{entry.username}</span>
                {isMe ? <span className="shrink-0 text-[13px] text-muted-foreground">{t("game.quiz.you")}</span> : null}
              </span>
              <Figure className={cn("text-[17px] font-medium", (first || isMe) && "text-brass")}>{entry.total_score}</Figure>
            </li>
          )
        })}
      </ol>
      {gameId && isPlayer && (notebook.isLoading || notebook.available) ? (
        <section aria-labelledby={wordsTitleId} className="mt-6">
          <h3 id={wordsTitleId} className="type-label">
            {t("notebook.colophon.wordsTitle")}
          </h3>
          <GameWordsList notebook={notebook} className="mt-1.5" />
        </section>
      ) : null}
    </Colophon>
  )
})
