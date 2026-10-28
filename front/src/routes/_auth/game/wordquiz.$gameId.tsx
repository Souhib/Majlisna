import { useIsFetching, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { type GamePause, type WordQuizCategory, wordQuizCategoryEnum } from "@/api/generated"
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
import { useHeldForPhase } from "@/components/games/shared/quiz-utils"
import { AnswerInput } from "@/components/games/wordquiz/AnswerInput"
import { HintDisplay } from "@/components/games/wordquiz/HintDisplay"
import { type LastRound, LastRoundCard, lastRoundFrom, recallLastRound, rememberLastRound } from "@/components/games/wordquiz/LastRoundCard"
import { RoundResults } from "@/components/games/wordquiz/RoundResults"
import { Panel } from "@/components/ui/panel"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { retrieveRoomIdForGame } from "@/lib/room-session"
import { serverNow } from "@/lib/server-clock"
import { useViewTransitionValue } from "@/lib/view-transition"
import { useAuth } from "@/providers/AuthProvider"

interface WordQuizState {
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
  hints_revealed: number
  /** Only the hints released so far — the server withholds the rest (see backend `_resolve_hints`). */
  hints: string[]
  /** Length of the full ladder, so "hint 2/6" doesn't read "2/2" off a prefix. */
  max_hints: number
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
    /** What they wrote (the answer that found it, else their last try) and how many tries. */
    typed_answer?: string | null
    attempts?: number
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
  difficulty?: string | null
  /** The word's theme, as a key the client words ("a prophet", "a place"…). */
  category?: WordQuizCategory | null
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

/** Each theme's key in `game.quiz.kalimat.category` (an unknown one is not shown). */
const CATEGORIES = new Set<string>(Object.values(wordQuizCategoryEnum))

/** The answer field's prompt for a theme: a person or a place is asked for as such, any other word as a word. */
function promptKey(category: string | null | undefined): string {
  if (category === "prophets" || category === "companions") return "game.quiz.kalimat.askWho"
  if (category === "places") return "game.quiz.kalimat.askWhere"
  return "game.quiz.kalimat.askWhat"
}

/**
 * How far into the round the game was when it was paused: the server's frozen countdown
 * when the round is timed, otherwise the pause's start against the round's (both on the
 * server's clock). The hint ladder stands still there until the resume.
 */
function roundElapsedAtPause(state: WordQuizState | null): number | null {
  const pause = state?.paused
  if (!pause || state.round_phase !== "playing") return null
  const fromClock = elapsedAtPause(pause, state.turn_duration_seconds)
  if (fromClock != null) return fromClock
  if (!state.round_started_at) return null
  const elapsed = (Date.parse(pause.since) - Date.parse(state.round_started_at)) / 1000
  return Number.isFinite(elapsed) ? Math.max(0, elapsed) : null
}

const DIFFICULTIES = new Set(["easy", "medium", "hard"])

export const Route = createFileRoute("/_auth/game/wordquiz/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <WordQuizGamePage />
    </ErrorBoundary>
  ),
})

/**
 * Kalimat (sketch C bottom-left, D Kalimat phone): guess the word from a ladder of six
 * hints, released one by one; the sooner you find it, the more it is worth. Phases
 * swap through a view transition (no blank exit before the next phase); the end of the
 * game is the colophon, where achievements are pressed as seals.
 */
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

  const leaveAfterKick = useLeaveAfterKick()
  const { connected: socketConnected } = useSocket({
    roomId: socketRoomId,
    gameId,
    gameType: "word_quiz",
    enabled: !!user,
    onKicked: leaveAfterKick,
  })

  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const trackedGameOverRef = useRef(false)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [hintClock, setHintClock] = useState<{ revealed: number; nextIn: number | null }>({ revealed: 1, nextIn: null })
  // what the last round's results said, kept in the tab so a reload still shows it
  const [lastRound, setLastRound] = useState<LastRound | null>(() => recallLastRound(gameId))

  // Poll game state
  const {
    data: serverState,
    isLoading,
    error: queryError,
  } = useGetWordquizStateApiV1WordquizGamesGameIdStateGet(
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

  // The phase on screen follows the server's through a view transition (180 ms crossfade).
  const phase = useViewTransitionValue(state?.round_phase ?? null)
  // ...and is drawn from the state it belongs to, so the outgoing frame stays true.
  const held = useHeldForPhase(state, phase)

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) {
      setSocketRoomId(serverState.room_id)
    }
  }, [serverState?.room_id, socketRoomId])

  const roundPhase = state?.round_phase

  // The prayer pause: the host's control, the veil over the whole game, the adhan strip.
  const isPaused = !!state?.paused
  const pausedRef = useRef(isPaused)
  pausedRef.current = isPaused
  const frozenElapsed = roundElapsedAtPause(state)
  const prayerPause = usePrayerPause("wordquiz", gameId, state)
  const adhan = useAdhanSuggestion({ gameId, canPause: prayerPause.canPause, paused: isPaused })
  const gameRef = useRef<HTMLDivElement>(null)
  const { answer: answerAdhan } = adhan
  const { pause: pauseGame } = prayerPause
  const pauseFromStrip = useCallback(() => {
    answerAdhan()
    pauseGame()
  }, [answerAdhan, pauseGame])

  // Client-side hint clock: which rung we are on and how long until the next one, from
  // round_started_at. The next one is only announced if it arrives before the round ends.
  // While the game is paused the ladder stands where the pause found it (no interval).
  useEffect(() => {
    if (!state || state.round_phase !== "playing" || !state.round_started_at) {
      if (state) setHintClock({ revealed: state.hints_revealed, nextIn: null })
      return
    }
    const hintInterval = state.hint_interval_seconds || 10
    const maxHints = state.max_hints
    const turn = state.turn_duration_seconds
    const startedAt = new Date(state.round_started_at).getTime()

    const computeHintsAt = (elapsed: number) => {
      const revealed = Math.min(maxHints, Math.floor(elapsed / hintInterval) + 1)
      const nextAt = revealed * hintInterval
      const announced = revealed < maxHints && (turn <= 0 || nextAt < turn)
      return { revealed, nextIn: announced ? Math.max(0, Math.ceil(nextAt - elapsed)) : null }
    }
    // the server's clock, not the device's: a phone running ahead crossed a rung before
    // the server released it (lib/server-clock)
    const computeHints = () => computeHintsAt((serverNow() - startedAt) / 1000)

    if (frozenElapsed != null) {
      setHintClock(computeHintsAt(frozenElapsed))
      return
    }

    setHintClock(computeHints())

    const interval = setInterval(() => {
      setHintClock(computeHints())
    }, 500)

    return () => clearInterval(interval)
  }, [
    state?.round_phase,
    state?.round_started_at,
    state?.hint_interval_seconds,
    state?.max_hints,
    state?.hints_revealed,
    state?.turn_duration_seconds,
    frozenElapsed,
  ])
  const localHintsRevealed = hintClock.revealed

  // The server only ships the hints it has actually released — sending the whole
  // ladder up front let anyone read the most specific hint at t=0 and take full
  // marks. So when the local clock crosses into a hint we don't hold yet, fetch it.
  // Socket.IO carries no hint event (nothing mutates), and polling is off while it
  // is connected, so this is the only thing that pulls the next one in.
  //
  // Fetched at most once per (round, rung), like PhaseTimer fires once per timer
  // window. A client clock running ahead of the server's leaves the condition
  // true after the refetch returns the same data, and an unguarded effect whose
  // own `invalidateQueries` can re-trigger it is precisely the self-sustaining
  // loop this codebase has already been burned by.
  //
  // The clock is the server's (serverNow), so the rung should be there when asked for.
  // When it is not (a cross-origin API that hides the Date header leaves the device
  // clock uncorrected), the answer that came back without it gets ONE follow-up a
  // moment later, still once per rung: a bounded second look, never a loop.
  const requestedHintRef = useRef<string>("")
  const followedUpHintRef = useRef<string>("")
  const hintsHeld = state?.hints.length ?? 0
  const currentRound = state?.current_round ?? 0
  const hintFetching = useIsFetching({ queryKey: queryKeys.game.wordquiz(gameId) }) > 0
  useEffect(() => {
    if (roundPhase !== "playing" || localHintsRevealed <= hintsHeld) return
    const window = `${currentRound}:${localHintsRevealed}`
    if (requestedHintRef.current !== window) {
      requestedHintRef.current = window
      queryClient.invalidateQueries({ queryKey: queryKeys.game.wordquiz(gameId) })
      return
    }
    if (hintFetching || followedUpHintRef.current === window) return
    followedUpHintRef.current = window
    console.warn(`Kalimat: rung ${localHintsRevealed} was not released yet when asked; asking once more`)
    const timer = setTimeout(() => queryClient.invalidateQueries({ queryKey: queryKeys.game.wordquiz(gameId) }), 1200)
    return () => clearTimeout(timer)
  }, [localHintsRevealed, hintsHeld, currentRound, roundPhase, gameId, queryClient, hintFetching])

  // Keep the round that just ended, to show it under the next one ("Last round · Maryam
  // wrote …"). It is the server's results phase as it was sent (who found it, what they
  // wrote, at which hint): the next round's state no longer carries it.
  useEffect(() => {
    if (!state || state.round_phase !== "results") return
    const last = lastRoundFrom(state)
    if (!last) return
    rememberLastRound(gameId, last)
    setLastRound((prev) =>
      prev?.round === last.round && prev.answer === last.answer && prev.finder?.username === last.finder?.username && prev.finder?.wrote === last.finder?.wrote
        ? prev
        : last,
    )
  }, [state, gameId])

  // Count the game's end once
  useEffect(() => {
    if (state?.winner && !trackedGameOverRef.current) {
      trackedGameOverRef.current = true
      trackEvent("game-over", { game: "word_quiz" })
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

  const handleSubmitAnswer = useCallback(
    async (answer: string) => {
      if (pausedRef.current) return null
      try {
        const result = await answerMutation.mutateAsync({ game_id: gameId, data: { answer } })
        queryClient.invalidateQueries({
          queryKey: queryKeys.game.wordquiz(gameId),
        })
        return result as { correct: boolean; points_earned: number; hint_number: number }
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to submit answer"))
        // refused because the game was paused under us: fetch the state with the veil
        if (isGamePausedError(err)) queryClient.invalidateQueries({ queryKey: queryKeys.game.wordquiz(gameId) })
        return null
      }
    },
    [gameId, queryClient, answerMutation],
  )

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
        queryKey: queryKeys.game.wordquiz(gameId),
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
        queryKey: queryKeys.game.wordquiz(gameId),
      })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to advance round"))
      if (isGamePausedError(err)) queryClient.invalidateQueries({ queryKey: queryKeys.game.wordquiz(gameId) })
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

  const gameName = t("games.wordQuiz.name")

  if (cancelMessage) return <QuizGoneNotice message={cancelMessage} />
  if (!state) {
    // a game that is gone gets its notice (set by the effect above), not a crash screen
    if (queryError && !isLoading && !isGameGoneError(queryError)) return <GameErrorFallback error={queryError} />
    return <QuizLoading title={gameName} />
  }
  const view = held ?? state

  // Never claim to reveal a hint we haven't been given: the local clock can run a
  // beat ahead of the fetch that brings the next one in.
  const localRevealed = Math.min(localHintsRevealed, view.hints.length)
  const effectiveHintsRevealed = view.round_phase === "playing" ? localRevealed : view.hints_revealed
  const maxHints = view.max_hints ?? 6
  const worth = Math.max(0, maxHints - effectiveHintsRevealed + 1)
  const answeredCount = view.players.filter((p) => p.current_round_answered).length
  const answeredNote = t("game.quiz.answeredCount", { answered: answeredCount, total: view.players.length })
  // The header names the word's theme ("Round 3 of 7 · a prophet"); the difficulty stands
  // in only for a state that carries no theme.
  const category = view.category && CATEGORIES.has(view.category) ? view.category : null
  const difficulty = !category && view.difficulty && DIFFICULTIES.has(view.difficulty) ? view.difficulty : null
  const prompt = promptKey(category)
  const showLastRound = lastRound != null && lastRound.round === view.current_round - 1
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

  const sub = (
    <>
      {t("game.quiz.kalimat.roundOf", { current: view.current_round, total: view.total_rounds })}
      {category ? ` · ${t(`game.quiz.kalimat.category.${category}`)}` : null}
      {difficulty ? ` · ${t(`room.difficulty${difficulty.charAt(0).toUpperCase()}${difficulty.slice(1)}`)}` : null}
    </>
  )

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
            winnerI18nKey="game.wordQuiz.winner"
            finalScoresI18nKey="game.wordQuiz.finalScores"
            currentUserId={user?.id}
            roomId={roomIdRef.current}
            isHost={view.is_host}
            seals={seals}
            meta={
              <ColophonMeta
                game={gameName}
                host={view.host_username}
                count={t("game.quiz.roundsCount", { count: view.total_rounds })}
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
                phase === "playing" || pauseControl ? (
                  <>
                    {phase === "playing" ? <span className="text-[13px] text-muted-foreground">{answeredNote}</span> : null}
                    {pauseControl}
                  </>
                ) : undefined
              }
            />

            {phase === "playing" ? (
              <>
                <div className="mb-3.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <p className="text-[14px] leading-snug text-muted-foreground">
                    <Trans i18nKey="game.quiz.kalimat.worthNow" count={worth} components={{ b: <b className="font-medium text-foreground" /> }} />
                  </p>
                  {view.round_started_at && view.turn_duration_seconds > 0 ? (
                    <PhaseTimer
                      timerStartedAt={view.round_started_at}
                      durationSeconds={view.turn_duration_seconds}
                      onExpired={handleTimerExpired}
                      paused={isPaused}
                      frozenRemaining={state.paused?.remaining_seconds}
                      className="w-[150px] sm:w-[220px]"
                    />
                  ) : null}
                </div>
                <HintDisplay hints={view.hints} hintsRevealed={effectiveHintsRevealed} maxHints={maxHints} nextHintIn={hintClock.nextIn} />
                {view.is_spectator ? (
                  <p className="mt-4 text-[14px] text-muted-foreground">{t("game.spectatorView")}</p>
                ) : (
                  <AnswerInput
                    onSubmit={handleSubmitAnswer}
                    disabled={view.is_spectator || isPaused}
                    answered={view.my_answered}
                    pointsEarned={view.my_points}
                    answeredNote={t("game.quiz.kalimat.waitingNote")}
                    placeholder={t(prompt)}
                  />
                )}
                {showLastRound ? <LastRoundCard last={lastRound} /> : null}
              </>
            ) : null}

            {phase === "results" ? (
              <RoundResults
                correctAnswer={view.correct_answer || ""}
                explanation={view.explanation}
                roundResults={view.round_results}
                isHost={view.is_host}
                isReady={!!user && (view.ready_players ?? []).includes(user.id)}
                readyCount={view.ready_count ?? 0}
                readyTotal={view.total_players}
                isLastRound={view.current_round >= view.total_rounds}
                onNextRound={handleNextRound}
                isAdvancing={nextRoundMutation.isPending}
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
          clockTotal={state.turn_duration_seconds}
          onRefresh={prayerPause.refresh}
          gameRef={gameRef}
        />
      </QuizFrame>
    </>
  )
}
