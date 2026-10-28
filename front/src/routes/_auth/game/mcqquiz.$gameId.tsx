import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import type { GamePause } from "@/api/generated"
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
import { ChoiceButtons } from "@/components/games/mcqquiz/ChoiceButtons"
import { McqRoundResults } from "@/components/games/mcqquiz/McqRoundResults"
import { choiceNotes } from "@/components/games/mcqquiz/reveal"
import { QuestionDisplay } from "@/components/games/mcqquiz/QuestionDisplay"
import { ScoreBands } from "@/components/games/mcqquiz/ScoreBands"
import { useAchievementSeals } from "@/components/games/shared/achievement-seals"
import { ColophonMeta } from "@/components/games/shared/ColophonMeta"
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { PlayerScoreboard } from "@/components/games/shared/PlayerScoreboard"
import {
  AdhanSuggestion,
  elapsedAtPause,
  isGamePausedError,
  isTimerStopAction,
  PauseControl,
  PauseLayer,
  useAdhanSuggestion,
  usePrayerPause,
} from "@/components/games/shared/prayer-pause"
import { QuizGameOver } from "@/components/games/shared/QuizGameOver"
import { QuizFrame, QuizGoneNotice, QuizHeader, QuizLeaveButton, QuizLoading } from "@/components/games/shared/QuizLayout"
import { Figure, useHeldForPhase, useNow } from "@/components/games/shared/quiz-utils"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { retrieveRoomIdForGame } from "@/lib/room-session"
import { useViewTransitionValue } from "@/lib/view-transition"
import { useAuth } from "@/providers/AuthProvider"

interface McqQuizState {
  ready_players?: string[]
  ready_count?: number
  /** Every player but the host: the ready count's denominator (`_ready_quorum`). */
  total_players?: number
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
  /** 0 while the question is open (the server holds every score back until the reveal). */
  my_points: number
  round_results: {
    user_id: string
    username: string
    chose_correct: boolean
    points: number
    /** Which choice they locked in (null: no answer). */
    choice_index?: number | null
    answer_time_ms?: number | null
  }[]
  /** The reveal, from the server (all null while the question is open): how many locked in
   *  each choice, which one was yours, and when you locked it in (ms after the start). */
  choice_tallies?: number[] | null
  my_choice_index?: number | null
  my_answer_time_ms?: number | null
  correct_answer_index: number | null
  explanation: string | null
  winner: string | null
  leaderboard: {
    user_id: string
    username: string
    total_score: number
  }[]
  game_over: boolean
  difficulty?: string | null
  /** The prayer pause (null while the game runs) and what this caller may do about it. */
  paused?: GamePause | null
  can_pause?: boolean
  can_resume?: boolean
  newly_unlocked_achievements?: { user_id: string; achievements: { code: string; name: string; icon: string; tier: number }[] }[]
  /** The colophon: the host who started the game, and when it ran (UTC). */
  host_username?: string | null
  started_at?: string | null
  ended_at?: string | null
}

/**
 * When you locked in, on your own clock at the tap: shown only while the question is
 * open, when the server says nothing yet. Once revealed, the server's measure
 * (`my_answer_time_ms`) replaces it, and that one survives a reload.
 */
interface LockIn {
  round: number
  elapsed: number
}

export const Route = createFileRoute("/_auth/game/mcqquiz/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <McqQuizGamePage />
    </ErrorBoundary>
  ),
})

/**
 * The Quiz (sketch C bottom-right, D Arabic phone): four choices, one answer, and the
 * story behind it. The three score bands say what a right answer is worth as the clock
 * runs; the reveal brasses the right choice and strikes a wrong pick on its letter.
 * Phases swap through a view transition; the end of the game is the colophon.
 */
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

  const leaveAfterKick = useLeaveAfterKick()
  const { connected: socketConnected } = useSocket({
    roomId: socketRoomId,
    gameId,
    gameType: "mcq_quiz",
    enabled: !!user,
    onKicked: leaveAfterKick,
  })

  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const trackedGameOverRef = useRef(false)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [selectedChoice, setSelectedChoice] = useState<number | null>(null)
  const [lockIn, setLockIn] = useState<LockIn | null>(null)

  // Poll game state
  const {
    data: serverState,
    isLoading,
    error: queryError,
  } = useGetMcqquizStateApiV1McqquizGamesGameIdStateGet(
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

  // The phase on screen follows the server's through a view transition (180 ms crossfade).
  const phase = useViewTransitionValue(state?.round_phase ?? null)
  // ...and is drawn from the state it belongs to, so the outgoing frame stays true.
  const held = useHeldForPhase(state, phase)

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) {
      setSocketRoomId(serverState.room_id)
    }
  }, [serverState?.room_id, socketRoomId])

  // The prayer pause: the host's control, the veil over the whole game, the adhan strip.
  const isPaused = !!state?.paused
  const pausedRef = useRef(isPaused)
  pausedRef.current = isPaused
  const prayerPause = usePrayerPause("mcqquiz", gameId, state)
  const adhan = useAdhanSuggestion({ gameId, canPause: prayerPause.canPause, paused: isPaused })
  const gameRef = useRef<HTMLDivElement>(null)
  const { answer: answerAdhan } = adhan
  const { pause: pauseGame } = prayerPause
  const pauseFromStrip = useCallback(() => {
    answerAdhan()
    pauseGame()
  }, [answerAdhan, pauseGame])

  // Reset the choice and the lock-in mark on round change
  const previousRoundRef = useRef<number>(0)
  useEffect(() => {
    if (!state) return
    if (state.current_round !== previousRoundRef.current) {
      setSelectedChoice(null)
      setLockIn(null)
      previousRoundRef.current = state.current_round
    }
  }, [state])

  // Count the game's end once
  useEffect(() => {
    if (state?.winner && !trackedGameOverRef.current) {
      trackedGameOverRef.current = true
      trackEvent("game-over", { game: "mcq_quiz" })
    }
  }, [state?.winner])

  // Handle query error
  useEffect(() => {
    // A game that is gone (ended elsewhere, removed): say so, then go home. Decided on
    // the status, not on the translated message (which never matched in AR or FR).
    if (queryError && isGameGoneError(queryError) && !redirectTimerRef.current) {
      setCancelMessage(getApiErrorMessage(queryError, t("errors.api.gameNotFound")))
      redirectTimerRef.current = setTimeout(() => navigate({ to: "/" }), 3000)
    }
  }, [queryError, navigate, t])

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [])

  // The band you are in moves with the clock until you lock in (and stands still while
  // the game is paused: the speed bonus is frozen too).
  const ticking = state?.round_phase === "playing" && !state.my_answered && !!state.round_started_at && !isPaused
  const now = useNow(ticking, 500)

  const handleSelectChoice = useCallback(
    (index: number) => {
      if (state?.my_answered || state?.is_spectator) return
      setSelectedChoice(index)
    },
    [state?.my_answered, state?.is_spectator],
  )

  const handleConfirmChoice = useCallback(async () => {
    if (selectedChoice === null || state?.my_answered || state?.is_spectator || pausedRef.current) return
    const tappedAt = Date.now()
    try {
      await answerMutation.mutateAsync({ game_id: gameId, data: { choice_index: selectedChoice } })
      if (state?.round_started_at) {
        setLockIn({
          round: state.current_round,
          elapsed: (tappedAt - new Date(state.round_started_at).getTime()) / 1000,
        })
      }
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.mcqquiz(gameId),
      })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to submit answer"))
      if (isGamePausedError(err)) {
        // paused under us: keep the pick for the resume, and fetch the state with the veil
        queryClient.invalidateQueries({ queryKey: queryKeys.game.mcqquiz(gameId) })
      } else {
        setSelectedChoice(null)
      }
    }
  }, [gameId, queryClient, answerMutation, selectedChoice, state?.my_answered, state?.is_spectator, state?.round_started_at, state?.current_round])

  const timerExpiredRef = useRef(false)
  const seals = useAchievementSeals(state?.newly_unlocked_achievements, state?.leaderboard, user?.id)

  // The round (its server start) the server told us to stop reporting: the game was
  // paused, or the round was already resolved. A new round, or the start the resume
  // moved forward, re-arms it.
  const timerWindowRef = useRef<string | null>(null)
  timerWindowRef.current = state?.round_started_at ?? null
  const stoppedWindowRef = useRef<string | null>(null)

  // Any player may report an expired timer — the server only acts once it has
  // really elapsed. Gating this on the host stalled the game whenever the host's
  // phone was locked or their tab backgrounded.
  const handleTimerExpired = useCallback(async () => {
    const timerKey = timerWindowRef.current
    if (timerExpiredRef.current || pausedRef.current) return
    if (timerKey !== null && stoppedWindowRef.current === timerKey) return
    timerExpiredRef.current = true
    try {
      const result = await timerExpiredMutation.mutateAsync({ game_id: gameId })
      if (isTimerStopAction(result?.action)) stoppedWindowRef.current = timerKey
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.mcqquiz(gameId),
      })
    } catch {
      // Ignore — another client may have triggered it
    } finally {
      timerExpiredRef.current = false
    }
  }, [gameId, queryClient, timerExpiredMutation])

  const handleNextRound = useCallback(async () => {
    if (pausedRef.current) return
    try {
      await nextRoundMutation.mutateAsync({ game_id: gameId })
      queryClient.invalidateQueries({
        queryKey: queryKeys.game.mcqquiz(gameId),
      })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to advance round"))
      if (isGamePausedError(err)) queryClient.invalidateQueries({ queryKey: queryKeys.game.mcqquiz(gameId) })
    }
  }, [gameId, queryClient, nextRoundMutation])

  const handleLeaveRoom = useCallback(async () => {
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await leaveMutation.mutateAsync({ data: { room_id: roomIdRef.current } })
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

  const gameName = t("games.mcqQuiz.name")

  if (cancelMessage) return <QuizGoneNotice message={cancelMessage} />
  if (!state) {
    // a game that is gone gets its notice (set by the effect above), not a crash screen
    if (queryError && !isLoading && !isGameGoneError(queryError)) return <GameErrorFallback error={queryError} />
    return <QuizLoading title={gameName} />
  }
  const view = held ?? state

  const duration = view.turn_duration_seconds
  const startedAt = view.round_started_at ? new Date(view.round_started_at).getTime() : null
  // While paused, the band stands where the server froze the clock.
  const frozenElapsed = isPaused ? elapsedAtPause(state.paused, duration) : null
  const elapsedRatio =
    phase === "playing" && !view.my_answered && startedAt != null && duration > 0
      ? Math.max(0, Math.min(1, (frozenElapsed ?? (now - startedAt) / 1000) / duration))
      : null
  const showResults = phase === "results"
  // When you locked in: the server's measure once the answer is revealed (it survives a
  // reload); while the question is open the server keeps it, so your own tap stands in.
  const lockedElapsed = showResults
    ? view.my_answer_time_ms != null
      ? view.my_answer_time_ms / 1000
      : null
    : lockIn && lockIn.round === view.current_round
      ? lockIn.elapsed
      : null
  const lockedRatio = lockedElapsed != null && duration > 0 ? Math.max(0, Math.min(1, lockedElapsed / duration)) : null
  const lockedRemaining = lockedElapsed != null && duration > 0 ? Math.max(0, duration - lockedElapsed) : null

  const myResult = view.round_results.find((r) => r.user_id === user?.id)
  const correctIndex = view.correct_answer_index
  // Your pick: the server's once revealed (after a reload too); while open, what you tapped.
  const myIndex = view.is_spectator ? null : showResults ? (view.my_choice_index ?? null) : selectedChoice
  const answeredCount = view.players.filter((p) => p.current_round_answered).length
  const answeredNote = t("game.quiz.answeredCount", { answered: answeredCount, total: view.players.length })
  const resultsBand = showResults && myResult?.chose_correct && myResult.points >= 1 ? (Math.min(3, myResult.points) as 1 | 2 | 3) : null

  // The note at the end of each choice: "you" once you have locked in; at the reveal, how
  // many chose it ("3 players", "you and 2 others", "+2 · you"), from the server's tallies.
  const notes = choiceNotes({
    count: view.choices.length,
    revealed: showResults,
    tallies: view.choice_tallies,
    myIndex,
    myAnswered: view.my_answered,
    correctIndex,
    myPoints: myResult?.chose_correct ? myResult.points : null,
  })
  const tags: ReactNode[] = notes.map((note) => {
    if (!note) return null
    if (note.kind === "picked") {
      if (note.count > 0) return t("game.quiz.mcq.pickedBy", { count: note.count })
      return (
        <>
          <Figure>
            <span aria-hidden="true">0</span>
          </Figure>
          <span className="sr-only">{t("game.quiz.mcq.pickedBy", { count: 0 })}</span>
        </>
      )
    }
    const who = note.others > 0 ? t("game.quiz.mcq.youAndOthers", { count: note.others }) : t("game.quiz.you")
    if (note.points == null) return who
    return (
      <>
        <Figure>+{note.points}</Figure>
        {" · "}
        {who}
      </>
    )
  })

  const pauseControl =
    prayerPause.canPause || prayerPause.canResume ? (
      <PauseControl
        canPause={prayerPause.canPause}
        canResume={prayerPause.canResume}
        paused={isPaused}
        onPause={prayerPause.pause}
        onResume={prayerPause.resume}
        pending={prayerPause.isPausing || prayerPause.isResuming}
      />
    ) : null
  const clock =
    phase === "playing" && view.round_started_at && duration > 0 ? (
      <PhaseTimer
        timerStartedAt={view.round_started_at}
        durationSeconds={duration}
        onExpired={handleTimerExpired}
        paused={isPaused}
        frozenRemaining={state.paused?.remaining_seconds}
        className="w-[138px] sm:w-[150px]"
      />
    ) : null

  const sub = t("game.quiz.mcq.questionOf", { current: view.current_round, total: view.total_rounds })

  if (phase === "game_over") {
    return (
      <>
        <ConnectionStatus connected={socketConnected} />
        <QuizFrame>
          <h1 className="sr-only">{gameName}</h1>
          <QuizGameOver
            winner={view.winner}
            leaderboard={view.leaderboard}
            onBackToRoom={handleBackToRoom}
            onLeaveRoom={handleLeaveRoom}
            winnerI18nKey="game.mcqQuiz.winner"
            finalScoresI18nKey="game.mcqQuiz.finalScores"
            currentUserId={user?.id}
            roomId={roomIdRef.current}
            isHost={view.is_host}
            seals={seals}
            meta={
              <ColophonMeta
                game={gameName}
                host={view.host_username}
                count={t("game.quiz.questionsCount", { count: view.total_rounds })}
                startedAt={view.started_at}
                endedAt={view.ended_at}
              />
            }
          />
        </QuizFrame>
      </>
    )
  }

  return (
    <>
      <ConnectionStatus connected={socketConnected} />
      <QuizFrame
        aside={
          // the scores are under the veil too (display: contents keeps the column's gaps)
          <div inert={isPaused} className="contents">
            <PlayerScoreboard players={view.players} currentUserId={user?.id} showAnswered={phase === "playing"} />
            <QuizLeaveButton onLeave={handleLeaveRoom} />
          </div>
        }
      >
        <div ref={gameRef} inert={isPaused} tabIndex={-1} className="outline-none">
          {adhan.prayer ? (
            <AdhanSuggestion prayerKey={adhan.prayer.key} onPause={pauseFromStrip} onDismiss={adhan.answer} pausing={prayerPause.isPausing} className="mb-4" />
          ) : null}
          <Panel>
            <QuizHeader
              title={gameName}
              sub={sub}
              spectating={view.is_spectator}
              end={
                clock || pauseControl ? (
                  <>
                    {pauseControl}
                    {clock}
                  </>
                ) : undefined
              }
            />

            {phase === "playing" || showResults ? (
              <>
                <ScoreBands
                  elapsedRatio={elapsedRatio}
                  lockedRatio={lockedRatio}
                  lockedRemaining={lockedRemaining}
                  band={resultsBand}
                  missed={showResults && !!myResult && !myResult.chose_correct}
                />
                <QuestionDisplay question={view.question} />
                <ChoiceButtons
                  choices={view.choices}
                  onSelect={showResults ? () => {} : handleSelectChoice}
                  disabled={showResults || view.is_spectator || view.my_answered || answerMutation.isPending || isPaused}
                  selectedIndex={showResults ? myIndex : selectedChoice}
                  correctIndex={showResults ? correctIndex : null}
                  roundPhase={showResults ? "results" : "playing"}
                  tags={tags}
                />
              </>
            ) : null}

            {phase === "playing" && !view.is_spectator && !view.my_answered ? (
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
                <Button onClick={handleConfirmChoice} disabled={selectedChoice === null || isPaused} loading={answerMutation.isPending}>
                  {t("game.quiz.mcq.lockIn")}
                </Button>
                {selectedChoice === null ? <p className="text-[13px] text-muted-foreground">{t("game.quiz.mcq.chooseFirst")}</p> : null}
              </div>
            ) : null}

            {phase === "playing" && view.my_answered ? (
              <p role="status" className="mt-4 text-[14px] text-muted-foreground">
                <span className="font-medium text-foreground">{t("game.quiz.mcq.lockedIn")}</span> · {answeredNote}
              </p>
            ) : null}

            {phase === "playing" && view.is_spectator ? <p className="mt-4 text-[14px] text-muted-foreground">{t("game.spectatorView")}</p> : null}

            {showResults ? (
              <McqRoundResults
                explanation={view.explanation}
                roundResults={view.round_results}
                isHost={view.is_host}
                isReady={!!user && (view.ready_players ?? []).includes(user.id)}
                readyCount={view.ready_count ?? 0}
                readyTotal={view.total_players}
                isLastRound={view.current_round >= view.total_rounds}
                onNextRound={handleNextRound}
                isAdvancing={nextRoundMutation.isPending}
                correctChoice={correctIndex != null ? view.choices[correctIndex] : null}
                choices={view.choices}
                currentUserId={user?.id}
                isSpectator={view.is_spectator}
              />
            ) : null}
          </Panel>
        </div>
        <PauseLayer
          pause={state.paused ?? null}
          canResume={prayerPause.canResume}
          onResume={prayerPause.resume}
          resuming={prayerPause.isResuming}
          isHost={state.is_host}
          isSpectator={state.is_spectator}
          currentUserId={user?.id}
          clockTotal={duration}
          onRefresh={prayerPause.refresh}
          gameRef={gameRef}
        />
      </QuizFrame>
    </>
  )
}
