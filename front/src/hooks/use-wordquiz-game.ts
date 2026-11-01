import { useIsFetching, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import type { GamePause, WordQuizCategory } from "@/api/generated"
import {
  useGetWordquizStateApiV1WordquizGamesGameIdStateGet,
  useSubmitAnswerApiV1WordquizGamesGameIdAnswerPost,
  useTimerExpiredApiV1WordquizGamesGameIdTimerExpiredPost,
  useNextRoundApiV1WordquizGamesGameIdNextRoundPost,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { elapsedAtPause, isGamePausedError } from "@/components/games/shared/prayer-pause/pause-utils"
import { type LastRound, lastRoundFrom, recallLastRound, rememberLastRound } from "@/components/games/wordquiz/LastRoundCard"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { useTimerReport } from "@/hooks/use-timer-report"
import { trackEvent } from "@/lib/analytics"
import { retrieveRoomIdForGame } from "@/lib/room-session"
import { serverNow } from "@/lib/server-clock"
import { useAuth } from "@/providers/AuthProvider"

export interface WordQuizState {
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
  /**
   * Owner rule (e): the tries the caller has left in the open round (null for a spectator,
   * once they found the word, and outside the playing phase). At 0 the next try is a 409.
   */
  my_attempts_left?: number | null
  /** The rungs the caller's wrong tries cost them this round (one per miss). */
  my_rungs_lost?: number
  /** The tries a round allows (`WORDQUIZ_MAX_ATTEMPTS_PER_ROUND`). */
  max_attempts?: number
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

/** Where the hint ladder stands: the rung in play, and the whole seconds until the next one. */
export interface HintClock {
  revealed: number
  /** Null when no rung arrives before the round ends (or the last one is in play). */
  nextIn: number | null
}

/** The round's ladder rules, from the state. */
export interface HintClockRules {
  /** Seconds between two rungs; 0 or less releases the whole ladder at once (as the server does). */
  intervalSeconds: number
  maxHints: number
  /** The round's length in seconds; 0 or less is untimed. */
  turnSeconds: number
}

/**
 * The ladder `elapsedMs` into the round, by the server's rule (`_calculate_hints_revealed`:
 * one rung, then one more every interval, never past the ladder). The next rung is only
 * announced if it arrives before the round ends. Before the start (a clock a beat behind
 * the server's) it stands at the first rung.
 */
export function hintClockAt(elapsedMs: number, rules: HintClockRules): HintClock {
  if (!(rules.intervalSeconds > 0)) return { revealed: rules.maxHints, nextIn: null }
  const elapsed = Math.max(0, elapsedMs)
  const intervalMs = rules.intervalSeconds * 1000
  const revealed = Math.min(rules.maxHints, Math.floor(elapsed / intervalMs) + 1)
  const nextAtMs = revealed * intervalMs
  const announced = revealed < rules.maxHints && (rules.turnSeconds <= 0 || nextAtMs < rules.turnSeconds * 1000)
  return { revealed, nextIn: announced ? Math.ceil((nextAtMs - elapsed) / 1000) : null }
}

/**
 * Milliseconds from `elapsedMs` until `hintClockAt` answers something else: the next whole
 * second of the countdown while one is shown, else the next rung; null once nothing will
 * change. Integer arithmetic on milliseconds, so a rung lands on its exact millisecond.
 */
export function msUntilHintClockChanges(elapsedMs: number, rules: HintClockRules): number | null {
  if (elapsedMs < 0) {
    const fromStart = msUntilHintClockChanges(0, rules)
    return fromStart == null ? null : fromStart - elapsedMs
  }
  if (!(rules.intervalSeconds > 0)) return null
  const { revealed, nextIn } = hintClockAt(elapsedMs, rules)
  if (revealed >= rules.maxHints) return null
  const toNextRungMs = revealed * rules.intervalSeconds * 1000 - elapsedMs
  if (nextIn == null) return toNextRungMs
  return toNextRungMs - (Math.ceil(toNextRungMs / 1000) - 1) * 1000
}

/**
 * What a right answer is worth now: `max_hints - min(max_hints, rung + rungs lost) + 1`,
 * the server's price (owner rule (e): each wrong try of the round costs one rung), never
 * below 1.
 */
export function kalimatWorth(maxHints: number, rung: number, rungsLost = 0): number {
  return Math.max(1, maxHints - Math.min(maxHints, Math.max(1, rung) + Math.max(0, rungsLost)) + 1)
}

/** True when a try was refused because the round's tries are used (409 `errors.api.answerAttemptsExhausted`). */
export function isAnswerAttemptsExhaustedError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false
  const response = (error as { response?: { status?: number; data?: unknown } }).response
  if (response?.status !== 409) return false
  const data = response.data as { error_key?: unknown; error?: unknown } | null | undefined
  return data?.error_key === "errors.api.answerAttemptsExhausted" || data?.error === "AnswerAttemptsExhaustedError"
}

/** What a try comes back as: the server's verdict, a refusal said in the field, or nothing (a toast said it). */
export type AnswerOutcome = { correct: boolean; points_earned: number; hint_number: number } | { refused: string } | null

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

const sameClock = (a: HintClock, b: HintClock) => a.revealed === b.revealed && a.nextIn === b.nextIn

/** How long the notice that the game is gone stays before the page goes home. */
export const GAME_GONE_REDIRECT_MS = 3000
/** The one follow-up for a rung the server had not released yet when asked. */
export const HINT_FOLLOW_UP_MS = 1200

/**
 * Kalimat's client logic (TQ-12), the same pattern as `useUndercoverGame`: the state and
 * its socket, the hint ladder's clock, the per-rung fetch, the last round's card, the
 * moves (an answer, the next round, leaving), the timer report and the way out of a game
 * that is gone. The page keeps what is drawn: the phase on screen, focus, the pause veil.
 *
 * The ladder's clock is ONE timeout set for the next moment it changes (the next second
 * of "next hint in", or the next rung), on the server's clock: no half-second polling,
 * and a rung lands at `round_started_at + N × interval`, not up to 500 ms later.
 */
export function useWordQuizGame(gameId: string) {
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
  const [hintClock, setHintClock] = useState<HintClock>({ revealed: 1, nextIn: null })
  // what the last round's results said, kept in the tab so a reload still shows it
  const [lastRound, setLastRound] = useState<LastRound | null>(() => recallLastRound(gameId))

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

  const answerMutation = useSubmitAnswerApiV1WordquizGamesGameIdAnswerPost()
  const timerExpiredMutation = useTimerExpiredApiV1WordquizGamesGameIdTimerExpiredPost()
  const nextRoundMutation = useNextRoundApiV1WordquizGamesGameIdNextRoundPost()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  const state = useMemo(() => {
    if (!serverState) return null
    if (serverState.room_id) roomIdRef.current = serverState.room_id
    return serverState
  }, [serverState])

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) setSocketRoomId(serverState.room_id)
  }, [serverState?.room_id, socketRoomId])

  const invalidateGame = useCallback(() => queryClient.invalidateQueries({ queryKey: queryKeys.game.wordquiz(gameId) }), [gameId, queryClient])

  const isPaused = !!state?.paused
  const pausedRef = useRef(isPaused)
  pausedRef.current = isPaused
  const frozenElapsed = roundElapsedAtPause(state)

  // The ladder's clock: which rung is in play and how long until the next, from
  // round_started_at on the server's clock (a phone running ahead crossed a rung before
  // the server released it: lib/server-clock). Re-read at the moment it changes, not
  // polled. While the game is paused the ladder stands where the pause found it.
  const roundPhase = state?.round_phase
  const roundStartedAt = state?.round_started_at ?? null
  const hintsRevealedByServer = state?.hints_revealed
  const intervalSeconds = state?.hint_interval_seconds
  const maxHints = state?.max_hints
  const turnSeconds = state?.turn_duration_seconds
  useEffect(() => {
    if (hintsRevealedByServer == null || maxHints == null || intervalSeconds == null || turnSeconds == null) return
    const startedAt = roundStartedAt ? Date.parse(roundStartedAt) : Number.NaN
    const show = (next: HintClock) => setHintClock((prev) => (sameClock(prev, next) ? prev : next))
    if (roundPhase !== "playing" || !Number.isFinite(startedAt)) {
      show({ revealed: hintsRevealedByServer, nextIn: null })
      return
    }
    const rules: HintClockRules = { intervalSeconds, maxHints, turnSeconds }
    if (frozenElapsed != null) {
      show(hintClockAt(frozenElapsed * 1000, rules))
      return
    }
    let timer: ReturnType<typeof setTimeout> | undefined
    const tick = () => {
      const elapsedMs = serverNow() - startedAt
      show(hintClockAt(elapsedMs, rules))
      const wait = msUntilHintClockChanges(elapsedMs, rules)
      timer = wait == null ? undefined : setTimeout(tick, wait)
    }
    tick()
    return () => clearTimeout(timer)
  }, [roundPhase, roundStartedAt, intervalSeconds, maxHints, hintsRevealedByServer, turnSeconds, frozenElapsed])

  // The server only ships the hints it has actually released — sending the whole
  // ladder up front let anyone read the most specific hint at t=0 and take full
  // marks. So when the local clock crosses into a hint we don't hold yet, fetch it.
  // Socket.IO carries no hint event (nothing mutates), and polling is off while it
  // is connected, so this is the only thing that pulls the next one in.
  //
  // Fetched at most once per (round, rung), like PhaseTimer fires once per timer
  // window: an unguarded effect whose own `invalidateQueries` can re-trigger it is the
  // self-sustaining loop this codebase has already been burned by. A rung still missing
  // after its fetch (a cross-origin API that hides the Date header leaves the device
  // clock uncorrected) gets ONE follow-up a moment later: a bounded second look.
  const localHintsRevealed = hintClock.revealed
  const requestedHintRef = useRef<string>("")
  const followedUpHintRef = useRef<string>("")
  const hintsHeld = state?.hints.length ?? 0
  const currentRound = state?.current_round ?? 0
  const hintFetching = useIsFetching({ queryKey: queryKeys.game.wordquiz(gameId) }) > 0
  useEffect(() => {
    if (roundPhase !== "playing" || localHintsRevealed <= hintsHeld) return
    const rung = `${currentRound}:${localHintsRevealed}`
    if (requestedHintRef.current !== rung) {
      requestedHintRef.current = rung
      invalidateGame()
      return
    }
    if (hintFetching || followedUpHintRef.current === rung) return
    followedUpHintRef.current = rung
    console.warn(`Kalimat: rung ${localHintsRevealed} was not released yet when asked; asking once more`)
    const timer = setTimeout(invalidateGame, HINT_FOLLOW_UP_MS)
    return () => clearTimeout(timer)
  }, [localHintsRevealed, hintsHeld, currentRound, roundPhase, invalidateGame, hintFetching])

  // Keep the round that just ended, to show it under the next one ("Last round · Maryam
  // wrote …"). It is the server's results phase as it was sent: the next round's state
  // no longer carries it.
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

  // Count the game's end once (on game_over: a shared win or a 0-0 game names no winner)
  useEffect(() => {
    if (state?.game_over && !trackedGameOverRef.current) {
      trackedGameOverRef.current = true
      trackEvent("game-over", { game: "word_quiz" })
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

  // An answer. A try the server refuses because the round's tries are used (owner rule
  // (e)) is said in the field, in the player's language, and the state that closes the
  // field is fetched; any other refusal is a toast.
  const handleSubmitAnswer = useCallback(
    async (answer: string): Promise<AnswerOutcome> => {
      if (pausedRef.current) return null
      try {
        const result = await answerMutation.mutateAsync({ game_id: gameId, data: { answer } })
        invalidateGame()
        return result as { correct: boolean; points_earned: number; hint_number: number }
      } catch (err) {
        if (isAnswerAttemptsExhaustedError(err)) {
          invalidateGame()
          return { refused: getApiErrorMessage(err, t("game.errors.answerFailed")) }
        }
        toast.error(getApiErrorMessage(err, t("game.errors.answerFailed")))
        // refused because the game was paused under us: fetch the state with the veil
        if (isGamePausedError(err)) invalidateGame()
        return null
      }
    },
    [gameId, answerMutation, invalidateGame, t],
  )

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

  // One request per tap, set before it is sent: a second tap lands before `isPending`
  // reaches the button (FR-4). The answer field guards its own submit.
  const nextRoundInFlightRef = useRef(false)
  const leavingRef = useRef(false)

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
    hintClock,
    lastRound,
    isAdvancing: nextRoundMutation.isPending,
    handleSubmitAnswer,
    handleTimerExpired,
    handleNextRound,
    handleLeaveRoom,
    handleBackToRoom,
  }
}
