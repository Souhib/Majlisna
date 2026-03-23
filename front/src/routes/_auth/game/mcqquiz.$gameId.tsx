import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Eye, Loader2, LogOut, Trophy } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { cn } from "@/lib/utils"
import {
  useGetMcqquizStateApiV1McqquizGamesGameIdStateGet,
  useSubmitAnswerApiV1McqquizGamesGameIdAnswerPost,
  useTimerExpiredApiV1McqquizGamesGameIdTimerExpiredPost,
  useNextRoundApiV1McqquizGamesGameIdNextRoundPost,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { QuestionDisplay } from "@/components/games/mcqquiz/QuestionDisplay"
import { ChoiceButtons } from "@/components/games/mcqquiz/ChoiceButtons"
import { PlayerScoreboard } from "@/components/games/shared/PlayerScoreboard"
import { McqRoundResults } from "@/components/games/mcqquiz/McqRoundResults"
import { QuizGameOver } from "@/components/games/shared/QuizGameOver"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { useAuth } from "@/providers/AuthProvider"
import { retrieveRoomIdForGame } from "@/lib/room-session"

interface McqQuizState {
  game_id: string
  room_id: string
  is_host: boolean
  is_spectator: boolean
  current_round: number
  total_rounds: number
  round_phase: string
  question: string
  choices: string[]
  turn_duration_seconds: number
  round_started_at: string | null
  players: {
    user_id: string
    username: string
    total_score: number
    current_round_answered: boolean
    current_round_points: number
  }[]
  my_answered: boolean
  my_points: number
  round_results: {
    user_id: string
    username: string
    chose_correct: boolean
    points: number
  }[]
  correct_answer_index: number | null
  explanation: string | null
  winner: string | null
  leaderboard: {
    user_id: string
    username: string
    total_score: number
  }[]
  game_over: boolean
}

export const Route = createFileRoute("/_auth/game/mcqquiz/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <McqQuizGamePage />
    </ErrorBoundary>
  ),
})

function McqQuizGamePage() {
  const { gameId } = Route.useParams()
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const roomIdRef = useRef<string | null>(null)
  const [socketRoomId, setSocketRoomId] = useState<string | null>(() => {
    const stored = retrieveRoomIdForGame(gameId)
    if (stored) roomIdRef.current = stored
    return stored
  })

  const { connected: socketConnected } = useSocket({
    roomId: socketRoomId,
    gameId,
    gameType: "mcq_quiz",
    enabled: !!user,
  })

  const [showGameOverTransition, setShowGameOverTransition] = useState(false)
  const gameOverTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const previousWinnerRef = useRef<string | null>(null)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [selectedChoice, setSelectedChoice] = useState<number | null>(null)

  // Poll game state
  const { data: serverState, isLoading, error: queryError } = useGetMcqquizStateApiV1McqquizGamesGameIdStateGet(
    { game_id: gameId },
    { lang: i18n.language },
    {
      query: {
        refetchOnWindowFocus: true,
        refetchInterval: socketConnected ? false : 2_000,
        refetchIntervalInBackground: true,
        enabled: !!user,
      },
    },
  ) as { data: McqQuizState | undefined; isLoading: boolean; error: Error | null }

  // Mutations
  const answerMutation = useSubmitAnswerApiV1McqquizGamesGameIdAnswerPost()
  const timerExpiredMutation = useTimerExpiredApiV1McqquizGamesGameIdTimerExpiredPost()
  const nextRoundMutation = useNextRoundApiV1McqquizGamesGameIdNextRoundPost()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  // Derive state
  const state = useMemo(() => {
    if (!serverState) return null
    if (serverState.room_id) {
      roomIdRef.current = serverState.room_id
    }
    return serverState
  }, [serverState])

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) {
      setSocketRoomId(serverState.room_id)
    }
  }, [serverState?.room_id, socketRoomId])

  // Reset selected choice on round change
  const previousRoundRef = useRef<number>(0)
  useEffect(() => {
    if (!state) return
    if (state.current_round !== previousRoundRef.current) {
      setSelectedChoice(null)
      previousRoundRef.current = state.current_round
    }
  }, [state])

  // Track game over
  useEffect(() => {
    if (!state) return
    const currentWinner = state.winner || null
    if (currentWinner && !previousWinnerRef.current && !showGameOverTransition) {
      trackEvent("game-over", { game: "mcq_quiz" })
      setShowGameOverTransition(true)
      gameOverTransitionTimerRef.current = setTimeout(() => {
        setShowGameOverTransition(false)
        gameOverTransitionTimerRef.current = null
      }, 3000)
    }
    previousWinnerRef.current = currentWinner
  }, [state])

  // Handle query error
  useEffect(() => {
    if (queryError) {
      const errMsg = getApiErrorMessage(queryError, "Game not found")
      if (errMsg.includes("not found") || errMsg.includes("removed")) {
        setCancelMessage(errMsg)
        redirectTimerRef.current = setTimeout(() => navigate({ to: "/" }), 3000)
      }
    }
  }, [queryError, navigate])

  useEffect(() => {
    return () => {
      if (gameOverTransitionTimerRef.current) clearTimeout(gameOverTransitionTimerRef.current)
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [])

  const handleSelectChoice = useCallback(
    (index: number) => {
      if (state?.my_answered || state?.is_spectator) return
      setSelectedChoice(index)
    },
    [state?.my_answered, state?.is_spectator],
  )

  const handleConfirmChoice = useCallback(async () => {
    if (selectedChoice === null || state?.my_answered || state?.is_spectator) return
    try {
      await answerMutation.mutateAsync({ game_id: gameId, data: { choice_index: selectedChoice } })
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.mcqquiz(gameId),
      })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to submit answer"))
      setSelectedChoice(null)
    }
  }, [gameId, queryClient, answerMutation, selectedChoice, state?.my_answered, state?.is_spectator])

  const timerExpiredRef = useRef(false)
  const handleTimerExpired = useCallback(async () => {
    if (!state?.is_host || timerExpiredRef.current) return
    timerExpiredRef.current = true
    try {
      await timerExpiredMutation.mutateAsync({ game_id: gameId })
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.mcqquiz(gameId),
      })
    } catch {
      // Ignore — another client may have triggered it
    } finally {
      timerExpiredRef.current = false
    }
  }, [gameId, state?.is_host, queryClient, timerExpiredMutation])

  const handleNextRound = useCallback(async () => {
    try {
      await nextRoundMutation.mutateAsync({ game_id: gameId })
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.mcqquiz(gameId),
      })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to advance round"))
    }
  }, [gameId, queryClient, nextRoundMutation])

  const handleLeaveRoom = useCallback(async () => {
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await leaveMutation.mutateAsync({ data: { user_id: user.id, room_id: roomIdRef.current } })
    } catch {
      // Ignore
    }
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }, [user, navigate, t, leaveMutation])

  const handleBackToRoom = useCallback(() => {
    if (roomIdRef.current) {
      queryClient.removeQueries({
        queryKey: queryKeys.room.state(roomIdRef.current),
      })
      navigate({ to: "/rooms/$roomId", params: { roomId: roomIdRef.current } })
    }
  }, [navigate, queryClient])

  if (cancelMessage) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="glass rounded-2xl border-border/30 p-8 text-center bg-destructive/10">
          <h2 className="text-xl font-extrabold tracking-tight text-destructive mb-2">{t("game.gameOver")}</h2>
          <p className="text-muted-foreground">{cancelMessage}</p>
          <p className="text-sm text-muted-foreground mt-2">Redirecting...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 min-h-screen">
      <ConnectionStatus connected={socketConnected} />
      {/* Game Over Transition Overlay */}
      <AnimatePresence>
        {showGameOverTransition && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/90 backdrop-blur-md"
          >
            <motion.div className="glass rounded-2xl border-border/30 p-10 text-center space-y-4">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", delay: 0.2 }}
              >
                <Trophy className="h-16 w-16 mx-auto text-yellow-500 drop-shadow-lg" />
              </motion.div>
              <motion.h2
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="text-2xl font-extrabold tracking-tight gradient-text"
              >
                {t("game.gameOver")}
              </motion.h2>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Game Header */}
      <div className="text-center mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight gradient-text">{t("games.mcqQuiz.name")}</h1>
        {state && (
          <p className="text-sm text-muted-foreground mt-2 font-mono tabular-nums">
            {t("game.mcqQuiz.round", { current: state.current_round, total: state.total_rounds })}
          </p>
        )}
        {state?.is_spectator && (
          <div className="mt-3 glass inline-flex items-center gap-1.5 rounded-full border-border/30 px-4 py-1.5 text-xs font-medium text-muted-foreground">
            <Eye className="h-3 w-3" />
            {t("game.spectating")}
          </div>
        )}
      </div>

      {/* Loading State */}
      {isLoading && !state && (
        <div className="glass rounded-2xl border-border/30 p-8 text-center mb-8">
          <Loader2 className="h-10 w-10 mx-auto animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">{t("common.loading")}</p>
        </div>
      )}

      {state && (
        <div className="space-y-6">
          {/* Phase Timer (during playing phase) */}
          {state.round_phase === "playing" && state.round_started_at && state.turn_duration_seconds > 0 && (
            <PhaseTimer
              timerStartedAt={state.round_started_at}
              durationSeconds={state.turn_duration_seconds}
              onExpired={handleTimerExpired}
            />
          )}

          {/* Playing Phase */}
          {state.round_phase === "playing" && (
            <>
              <QuestionDisplay
                question={state.question}
                currentRound={state.current_round}
                totalRounds={state.total_rounds}
              />
              {!state.is_spectator && (
                <>
                  <ChoiceButtons
                    choices={state.choices}
                    onSelect={handleSelectChoice}
                    disabled={state.my_answered || answerMutation.isPending}
                    selectedIndex={selectedChoice}
                    correctIndex={null}
                    roundPhase={state.round_phase}
                  />
                  {!state.my_answered && (
                    <motion.div
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex justify-center"
                    >
                      <button
                        type="button"
                        onClick={handleConfirmChoice}
                        disabled={selectedChoice === null || answerMutation.isPending}
                        className={cn(
                          "rounded-xl px-8 py-3 text-sm font-semibold shadow-md transition-all duration-200",
                          selectedChoice !== null && !answerMutation.isPending
                            ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-primary/20 hover:shadow-lg hover:-translate-y-px"
                            : "bg-muted text-muted-foreground cursor-not-allowed opacity-60",
                        )}
                      >
                        {answerMutation.isPending ? (
                          <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                        ) : (
                          t("common.confirm")
                        )}
                      </button>
                    </motion.div>
                  )}
                </>
              )}
              {state.my_answered && (
                <motion.p
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center text-sm text-muted-foreground"
                >
                  {t("game.mcqQuiz.waitingForPlayers")}
                </motion.p>
              )}
            </>
          )}

          {/* Results Phase */}
          {state.round_phase === "results" && (
            <>
              <QuestionDisplay
                question={state.question}
                currentRound={state.current_round}
                totalRounds={state.total_rounds}
              />
              <ChoiceButtons
                choices={state.choices}
                onSelect={() => {}}
                disabled={true}
                selectedIndex={selectedChoice}
                correctIndex={state.correct_answer_index}
                roundPhase={state.round_phase}
              />
              <McqRoundResults
                explanation={state.explanation}
                roundResults={state.round_results}
                isHost={state.is_host}
                onNextRound={handleNextRound}
                isAdvancing={nextRoundMutation.isPending}
              />
            </>
          )}

          {/* Game Over */}
          {state.round_phase === "game_over" && !showGameOverTransition && (
            <QuizGameOver
              winner={state.winner}
              leaderboard={state.leaderboard}
              onBackToRoom={handleBackToRoom}
              onLeaveRoom={handleLeaveRoom}
              winnerI18nKey="game.mcqQuiz.winner"
              finalScoresI18nKey="game.mcqQuiz.finalScores"
              backToRoomI18nKey="game.mcqQuiz.backToRoom"
            />
          )}

          {/* Scoreboard (always visible) */}
          <PlayerScoreboard players={state.players} currentUserId={user?.id} />

          {/* Leave Game Button */}
          {state.round_phase !== "game_over" && (
            <div className="text-center">
              <button
                type="button"
                onClick={handleLeaveRoom}
                className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-destructive transition-all duration-200 rounded-2xl px-4 py-2 hover:bg-destructive/5"
              >
                <LogOut className="h-4 w-4" />
                {t("room.leave")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
