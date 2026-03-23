import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Eye, Loader2, LogOut, Trophy } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  useGetWordquizStateApiV1WordquizGamesGameIdStateGet,
  useSubmitAnswerApiV1WordquizGamesGameIdAnswerPost,
  useTimerExpiredApiV1WordquizGamesGameIdTimerExpiredPost,
  useNextRoundApiV1WordquizGamesGameIdNextRoundPost,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { HintDisplay } from "@/components/games/wordquiz/HintDisplay"
import { AnswerInput } from "@/components/games/wordquiz/AnswerInput"
import { PlayerScoreboard } from "@/components/games/shared/PlayerScoreboard"
import { QuizGameOver } from "@/components/games/shared/QuizGameOver"
import { RoundResults } from "@/components/games/wordquiz/RoundResults"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { useAuth } from "@/providers/AuthProvider"
import { retrieveRoomIdForGame } from "@/lib/room-session"

interface WordQuizState {
  game_id: string
  room_id: string
  is_host: boolean
  is_spectator: boolean
  current_round: number
  total_rounds: number
  round_phase: string
  hints_revealed: number
  hints: string[]
  turn_duration_seconds: number
  hint_interval_seconds: number
  round_started_at: string | null
  players: {
    user_id: string
    username: string
    total_score: number
    current_round_answered: boolean
    current_round_points: number
    answered_at_hint: number | null
  }[]
  my_answered: boolean
  my_points: number
  round_results: {
    user_id: string
    username: string
    answered_at_hint: number | null
    points: number
  }[]
  correct_answer: string | null
  explanation: string | null
  winner: string | null
  leaderboard: {
    user_id: string
    username: string
    total_score: number
    current_round_answered: boolean
    current_round_points: number
  }[]
  game_over: boolean
  timer_config: { turn_duration_seconds: number; hint_interval_seconds: number } | null
}

export const Route = createFileRoute("/_auth/game/wordquiz/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <WordQuizGamePage />
    </ErrorBoundary>
  ),
})

function WordQuizGamePage() {
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
    gameType: "word_quiz",
    enabled: !!user,
  })

  const [showGameOverTransition, setShowGameOverTransition] = useState(false)
  const gameOverTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const previousWinnerRef = useRef<string | null>(null)
  const previousRoundRef = useRef<number>(0)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [localHintsRevealed, setLocalHintsRevealed] = useState(1)

  // Poll game state
  const { data: serverState, isLoading, error: queryError } = useGetWordquizStateApiV1WordquizGamesGameIdStateGet(
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
  ) as { data: WordQuizState | undefined; isLoading: boolean; error: Error | null }

  // Mutations
  const answerMutation = useSubmitAnswerApiV1WordquizGamesGameIdAnswerPost()
  const timerExpiredMutation = useTimerExpiredApiV1WordquizGamesGameIdTimerExpiredPost()
  const nextRoundMutation = useNextRoundApiV1WordquizGamesGameIdNextRoundPost()
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

  // Client-side hint timer: calculate hints_revealed locally from round_started_at
  useEffect(() => {
    if (!state || state.round_phase !== "playing" || !state.round_started_at) {
      if (state) setLocalHintsRevealed(state.hints_revealed)
      return
    }
    const hintInterval = state.hint_interval_seconds || 10
    const maxHints = Math.max(state.hints.length, 6)
    const startedAt = new Date(state.round_started_at).getTime()

    const computeHints = () => {
      const elapsed = (Date.now() - startedAt) / 1000
      return Math.min(maxHints, Math.floor(elapsed / hintInterval) + 1)
    }

    setLocalHintsRevealed(computeHints())

    const interval = setInterval(() => {
      setLocalHintsRevealed(computeHints())
    }, 1000)

    return () => clearInterval(interval)
  }, [state?.round_phase, state?.round_started_at, state?.hint_interval_seconds, state?.hints.length, state?.hints_revealed])

  // Track round/phase changes
  useEffect(() => {
    if (!state) return
    const currentWinner = state.winner || null
    if (currentWinner && !previousWinnerRef.current && !showGameOverTransition) {
      trackEvent("game-over", { game: "word_quiz" })
      setShowGameOverTransition(true)
      gameOverTransitionTimerRef.current = setTimeout(() => {
        setShowGameOverTransition(false)
        gameOverTransitionTimerRef.current = null
      }, 3000)
    }
    previousWinnerRef.current = currentWinner
    previousRoundRef.current = state.current_round
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

  const handleSubmitAnswer = useCallback(
    async (answer: string) => {
      try {
        const result = await answerMutation.mutateAsync({ game_id: gameId, data: { answer } })
        queryClient.invalidateQueries({
          queryKey: queryKeys.game.wordquiz(gameId),
        })
        return result as { correct: boolean; points_earned: number; hint_number: number }
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to submit answer"))
        return null
      }
    },
    [gameId, queryClient, answerMutation],
  )

  const timerExpiredRef = useRef(false)
  const handleTimerExpired = useCallback(async () => {
    if (!state?.is_host || timerExpiredRef.current) return
    timerExpiredRef.current = true
    try {
      await timerExpiredMutation.mutateAsync({ game_id: gameId })
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.wordquiz(gameId),
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
        queryKey: queryKeys.game.wordquiz(gameId),
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

  const effectiveHintsRevealed = state?.round_phase === "playing" ? localHintsRevealed : (state?.hints_revealed ?? 1)
  const maxHints = state ? Math.max(state.hints.length, effectiveHintsRevealed) : 6

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
        <h1 className="text-3xl font-extrabold tracking-tight gradient-text">{t("games.wordQuiz.name")}</h1>
        {state && (
          <p className="text-sm text-muted-foreground mt-2 font-mono tabular-nums">
            {t("game.wordQuiz.round", { current: state.current_round, total: state.total_rounds })}
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
              <HintDisplay hints={state.hints} hintsRevealed={effectiveHintsRevealed} maxHints={maxHints} />
              {!state.is_spectator && (
                <AnswerInput
                  onSubmit={handleSubmitAnswer}
                  disabled={state.is_spectator}
                  answered={state.my_answered}
                  pointsEarned={state.my_points}
                />
              )}
            </>
          )}

          {/* Results Phase */}
          {state.round_phase === "results" && (
            <RoundResults
              correctAnswer={state.correct_answer || ""}
              explanation={state.explanation}
              roundResults={state.round_results}
              isHost={state.is_host}
              onNextRound={handleNextRound}
              isAdvancing={nextRoundMutation.isPending}
            />
          )}

          {/* Game Over */}
          {state.round_phase === "game_over" && !showGameOverTransition && (
            <QuizGameOver
              winner={state.winner}
              leaderboard={state.leaderboard}
              onBackToRoom={handleBackToRoom}
              onLeaveRoom={handleLeaveRoom}
              winnerI18nKey="game.wordQuiz.winner"
              finalScoresI18nKey="game.wordQuiz.finalScores"
              backToRoomI18nKey="game.wordQuiz.backToRoom"
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
