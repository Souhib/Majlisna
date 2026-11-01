import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { isGamePausedError } from "@/components/games/shared/prayer-pause/pause-utils"
import { useNow } from "@/components/games/shared/quiz-utils"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { useTimerReport } from "@/hooks/use-timer-report"
import { trackEvent } from "@/lib/analytics"
import { retrieveRoomIdForGame } from "@/lib/room-session"
import { useAuth } from "@/providers/AuthProvider"

export interface McqQuizState {
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
export interface LockIn {
  round: number
  elapsed: number
}

/** How long the notice that the game is gone stays before the page goes home. */
export const GAME_GONE_REDIRECT_MS = 3000
/** How often the score band you are in is re-read while the question is open. */
export const BAND_TICK_MS = 500

/**
 * The Quiz's client logic (TQ-12), the same pattern as `useUndercoverGame`: the state and
 * its socket, your pick and its lock-in, the moves (lock in, the next round, leaving), the
 * timer report and the way out of a game that is gone. The page keeps what is drawn: the
 * phase on screen, focus, the bands, the pause veil.
 *
 * One answer per question: a lock-in sets an in-flight mark before it is sent (a second
 * tap lands before `isPending` reaches the button), and once the server has said yes the
 * round counts as locked in at once (`hasLockedIn`), before the refetch says so — in that
 * beat the button was live again and a second tap sent a second answer, which the server
 * refused with a toast and the pick on screen was cleared.
 */
export function useMcqQuizGame(gameId: string) {
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
  // the round the server accepted our answer for (before the state that says so arrives)
  const [lockedRound, setLockedRound] = useState<number | null>(null)

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

  const answerMutation = useSubmitAnswerApiV1McqquizGamesGameIdAnswerPost()
  const timerExpiredMutation = useTimerExpiredApiV1McqquizGamesGameIdTimerExpiredPost()
  const nextRoundMutation = useNextRoundApiV1McqquizGamesGameIdNextRoundPost()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  const state = useMemo(() => {
    if (!serverState) return null
    if (serverState.room_id) roomIdRef.current = serverState.room_id
    return serverState
  }, [serverState])

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) setSocketRoomId(serverState.room_id)
  }, [serverState?.room_id, socketRoomId])

  const invalidateGame = useCallback(() => queryClient.invalidateQueries({ queryKey: queryKeys.game.mcqquiz(gameId) }), [gameId, queryClient])

  const isPaused = !!state?.paused
  const pausedRef = useRef(isPaused)
  pausedRef.current = isPaused

  const hasLockedIn = !!state && (state.my_answered || lockedRound === state.current_round)

  // A new question: no pick, no lock-in mark.
  const previousRoundRef = useRef<number>(0)
  useEffect(() => {
    if (!state) return
    if (state.current_round !== previousRoundRef.current) {
      setSelectedChoice(null)
      setLockIn(null)
      previousRoundRef.current = state.current_round
    }
  }, [state])

  // Count the game's end once (on game_over: a shared win or a 0-0 game names no winner)
  useEffect(() => {
    if (state?.game_over && !trackedGameOverRef.current) {
      trackedGameOverRef.current = true
      trackEvent("game-over", { game: "mcq_quiz" })
    }
  }, [state?.game_over])

  // A game that is gone (ended elsewhere, removed): say so, then go home, once. Decided
  // on the status, not on the translated message (which never matched in AR or FR).
  useEffect(() => {
    if (queryError && isGameGoneError(queryError) && !redirectTimerRef.current) {
      setCancelMessage(getApiErrorMessage(queryError, t("errors.api.gameNotFound")))
      redirectTimerRef.current = setTimeout(() => navigate({ to: "/" }), GAME_GONE_REDIRECT_MS)
    }
  }, [queryError, navigate, t])

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [])

  // The band you are in moves with the clock until you lock in (and stands still while
  // the game is paused: the speed bonus is frozen too).
  const ticking = state?.round_phase === "playing" && !hasLockedIn && !!state.round_started_at && !isPaused
  const now = useNow(ticking, BAND_TICK_MS)

  const handleSelectChoice = useCallback(
    (index: number) => {
      if (hasLockedIn || state?.is_spectator) return
      setSelectedChoice(index)
    },
    [hasLockedIn, state?.is_spectator],
  )

  // One request per move, set before it is sent (FR-4).
  const answerInFlightRef = useRef(false)
  const nextRoundInFlightRef = useRef(false)
  const leavingRef = useRef(false)

  const handleConfirmChoice = useCallback(async () => {
    if (!state || selectedChoice === null || hasLockedIn || state.is_spectator || pausedRef.current || answerInFlightRef.current) return
    answerInFlightRef.current = true
    const round = state.current_round
    const tappedAt = Date.now()
    try {
      await answerMutation.mutateAsync({ game_id: gameId, data: { choice_index: selectedChoice } })
      setLockedRound(round)
      if (state.round_started_at) {
        setLockIn({ round, elapsed: (tappedAt - new Date(state.round_started_at).getTime()) / 1000 })
      }
      invalidateGame()
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("game.errors.answerFailed")))
      if (isGamePausedError(err)) {
        // paused under us: keep the pick for the resume, and fetch the state with the veil
        invalidateGame()
      } else {
        setSelectedChoice(null)
      }
    } finally {
      answerInFlightRef.current = false
    }
  }, [gameId, answerMutation, selectedChoice, hasLockedIn, state, invalidateGame, t])

  // Any player may report an expired timer (the server acts only once it has really run
  // out: gating it on the host stalled the game whenever the host's phone was locked);
  // the host at once, the others after a jittered wait that the round's next state
  // cancels (`useTimerReport`). The window is the round's server start: a stop answer
  // (`paused`, `round_already_resolved`) silences it until the next round or the resume.
  const handleTimerExpired = useTimerReport({
    isHost: !!state?.is_host,
    paused: isPaused,
    phaseKey: `${state?.current_round}:${state?.round_phase}:${state?.round_started_at}`,
    windowKey: state?.round_started_at ?? null,
    send: () => timerExpiredMutation.mutateAsync({ game_id: gameId }),
    onChanged: invalidateGame,
  })

  const handleNextRound = useCallback(async () => {
    if (pausedRef.current || nextRoundInFlightRef.current) return
    nextRoundInFlightRef.current = true
    try {
      await nextRoundMutation.mutateAsync({ game_id: gameId })
      invalidateGame()
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("game.errors.nextRoundFailed")))
      if (isGamePausedError(err)) invalidateGame()
    } finally {
      nextRoundInFlightRef.current = false
    }
  }, [gameId, nextRoundMutation, invalidateGame, t])

  const handleLeaveRoom = useCallback(async () => {
    if (leavingRef.current) return
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
    leavingRef.current = true
    try {
      await leaveMutation.mutateAsync({ data: { room_id: roomIdRef.current } })
    } catch {
      // Ignore
    }
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }, [user, navigate, t, leaveMutation])

  const handleBackToRoom = useCallback(() => {
    if (!roomIdRef.current) return
    queryClient.removeQueries({ queryKey: queryKeys.room.state(roomIdRef.current) })
    navigate({ to: "/rooms/$roomId", params: { roomId: roomIdRef.current } })
  }, [navigate, queryClient])

  return {
    user,
    state,
    isLoading,
    queryError,
    socketConnected,
    cancelMessage,
    roomIdRef,
    isPaused,
    now,
    selectedChoice,
    lockIn,
    hasLockedIn,
    isLockingIn: answerMutation.isPending,
    isAdvancing: nextRoundMutation.isPending,
    handleSelectChoice,
    handleConfirmChoice,
    handleTimerExpired,
    handleNextRound,
    handleLeaveRoom,
    handleBackToRoom,
  }
}
