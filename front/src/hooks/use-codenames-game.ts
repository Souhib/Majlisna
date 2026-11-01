import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import type { GamePause } from "@/api/generated"
import {
  useGetCodenamesBoardApiV1CodenamesGamesGameIdBoardGet,
  useGiveClueApiV1CodenamesGamesGameIdCluePost,
  useGuessCardApiV1CodenamesGamesGameIdGuessPost,
  useEndTurnApiV1CodenamesGamesGameIdEndTurnPost,
  useRecordHintViewedApiV1CodenamesGamesGameIdHintViewedPost,
  useTimerExpiredApiV1CodenamesGamesGameIdTimerExpiredPost,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { isGamePausedError } from "@/components/games/shared/prayer-pause/pause-utils"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { useTimerReport } from "@/hooks/use-timer-report"
import { trackEvent } from "@/lib/analytics"
import { withViewTransition } from "@/lib/view-transition"
import { useAuth } from "@/providers/AuthProvider"
import { retrieveRoomIdForGame } from "@/lib/room-session"

import type { ClueHistoryEntry, CodenamesCard, CodenamesPlayer, CodenamesTurn } from "@/components/games/codenames/model"

export interface CodenamesGameState {
  board: CodenamesCard[]
  current_team: "red" | "blue"
  current_turn: CodenamesTurn | null
  my_team: "red" | "blue" | "spectator"
  my_role: "spymaster" | "operative" | "spectator"
  red_remaining: number
  blue_remaining: number
  status: "waiting" | "in_progress" | "finished"
  winner: "red" | "blue" | null
  players: CodenamesPlayer[]
  room_id?: string
}

export interface CodenamesServerState {
  game_id: string
  room_id?: string
  team: "red" | "blue" | "spectator"
  role: "spymaster" | "operative" | "spectator"
  is_host?: boolean
  board: CodenamesCard[]
  current_team: "red" | "blue"
  red_remaining: number
  blue_remaining: number
  status: string
  current_turn: CodenamesTurn | null
  winner: "red" | "blue" | null
  players?: CodenamesPlayer[]
  clue_history?: ClueHistoryEntry[]
  timer_config?: { clue_seconds: number; guess_seconds: number }
  timer_started_at?: string | null
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
 * The end of a game (F3). The decisive card is woven first: its colour and selvedge take
 * `--dur-authored` (640 ms), and the veil used to cover it 80 ms after the click, so the
 * most dramatic reveal (the assassin turning black) was never seen.
 */
const VEIL_DELAY_MS = 640
/** The veil's ceremony (`--dur-ceremony`, 1100 ms: the band is woven) plus a beat to read it. */
const VEIL_HOLD_MS = 1100 + 180
/** Under reduced motion nothing is woven: the veil says who won, briefly, and lifts. */
const VEIL_HOLD_REDUCED_MS = 600

/** The game's end, as the page shows it: nothing yet, the last card weaving, the veil. */
type GameOverCeremony = "none" | "weaving" | "veiled"

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

export function useCodenamesGame(gameId: string) {
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
  const { connected: socketConnected } = useSocket({ roomId: socketRoomId, gameId, gameType: "codenames", enabled: !!user, onKicked: leaveAfterKick })

  const [clueWord, setClueWord] = useState("")
  const [clueNumber, setClueNumber] = useState(1)
  const [isSubmittingClue, setIsSubmittingClue] = useState(false)
  const [isEndingTurn, setIsEndingTurn] = useState(false)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [ceremony, setCeremony] = useState<GameOverCeremony>("none")
  const ceremonyTimersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const ceremonyFrameRef = useRef<number | null>(null)
  const previousStatusRef = useRef<string | null>(null)
  // One request per move at a time, set before the request is sent: a double tap lands
  // before `isPending` reaches the page (FR-4).
  const clueInFlightRef = useRef(false)
  const guessInFlightRef = useRef(false)
  const endTurnInFlightRef = useRef(false)
  const leavingRef = useRef(false)

  // Poll game state via REST only when Socket.IO is disconnected (safety net)
  const {
    data: serverState,
    isLoading,
    error: queryError,
  } = useGetCodenamesBoardApiV1CodenamesGamesGameIdBoardGet(
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
  ) as {
    data: CodenamesServerState | undefined
    isLoading: boolean
    error: Error | null
  }

  const clueMutation = useGiveClueApiV1CodenamesGamesGameIdCluePost()
  const guessMutation = useGuessCardApiV1CodenamesGamesGameIdGuessPost()
  const endTurnMutation = useEndTurnApiV1CodenamesGamesGameIdEndTurnPost()
  const hintViewedMutation = useRecordHintViewedApiV1CodenamesGamesGameIdHintViewedPost()
  const timerExpiredMutation = useTimerExpiredApiV1CodenamesGamesGameIdTimerExpiredPost()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  const gameState = useMemo<CodenamesGameState | null>(() => {
    if (!serverState) return null
    if (serverState.room_id) {
      roomIdRef.current = serverState.room_id
    }
    return {
      board: serverState.board,
      current_team: serverState.current_team,
      current_turn: serverState.current_turn,
      my_team: serverState.team,
      my_role: serverState.role,
      red_remaining: serverState.red_remaining,
      blue_remaining: serverState.blue_remaining,
      status: serverState.status as "waiting" | "in_progress" | "finished",
      winner: serverState.winner,
      players: serverState.players || [],
      room_id: serverState.room_id,
    }
  }, [serverState])

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) {
      setSocketRoomId(serverState.room_id)
    }
  }, [serverState?.room_id, socketRoomId])

  // The game ends on screen (not a page opened on a finished game): the decisive card is
  // woven, then the veil holds the ceremony, then lifts through a view transition so the
  // colophon crossfades in. The colophon waits for all of it (`colophonHeld`): its own
  // "Game Over" must never sit beside the veil's.
  useEffect(() => {
    if (!serverState) return
    const currentStatus = serverState.status
    if (currentStatus === "finished" && previousStatusRef.current && previousStatusRef.current !== "finished") {
      trackEvent("game-over", { game: "codenames", winner: serverState.winner || "" })
      const timers = ceremonyTimersRef.current
      const lift = () => void withViewTransition(() => setCeremony("none"))
      if (prefersReducedMotion()) {
        setCeremony("veiled")
        timers.push(setTimeout(lift, VEIL_HOLD_REDUCED_MS))
      } else {
        setCeremony("weaving")
        // The weave is counted from the frame that draws the turned card, not from this
        // effect: it can run inside the very task that commits the board, and on a slow
        // phone (CI's runner: ~340 ms) the rest of that task delayed the paint, so the veil
        // came while the decisive card had barely been seen.
        ceremonyFrameRef.current = requestAnimationFrame(() => {
          ceremonyFrameRef.current = null
          timers.push(
            setTimeout(() => {
              setCeremony("veiled")
              timers.push(setTimeout(lift, VEIL_HOLD_MS))
            }, VEIL_DELAY_MS),
          )
        })
      }
    }
    previousStatusRef.current = currentStatus
  }, [serverState])

  useEffect(() => {
    // A game that is gone (ended elsewhere, cancelled, removed): say so, then go home.
    // Decided on the status, not on the translated message (which never matched in AR or FR).
    if (queryError && isGameGoneError(queryError) && !redirectTimerRef.current) {
      setCancelMessage(getApiErrorMessage(queryError, t("errors.api.gameNotFound")))
      redirectTimerRef.current = setTimeout(() => navigate({ to: "/" }), 3000)
    }
  }, [queryError, navigate, t])

  useEffect(() => {
    const ceremonyTimers = ceremonyTimersRef.current
    return () => {
      for (const timer of ceremonyTimers) clearTimeout(timer)
      if (ceremonyFrameRef.current !== null) cancelAnimationFrame(ceremonyFrameRef.current)
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [])

  const invalidateBoard = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.game.codenames(gameId) })
  }, [gameId, queryClient])

  // The prayer pause: while the host has paused the game no move is sent (the page also
  // makes the board inert under the veil) and the clock is never reported as expired.
  const isPaused = !!serverState?.paused
  const pausedRef = useRef(isPaused)
  pausedRef.current = isPaused
  // A move refused because the game was paused under us (409 gamePaused): its translated
  // error is shown, and the board that carries the veil is fetched at once.
  const moveFailed = useCallback(
    (err: unknown, fallback: string) => {
      toast.error(getApiErrorMessage(err, fallback))
      if (isGamePausedError(err)) invalidateBoard()
    },
    [invalidateBoard],
  )

  const handleHintViewed = useCallback(
    async (word: string) => {
      try {
        await hintViewedMutation.mutateAsync({ game_id: gameId, data: { word } })
      } catch {
        // Silent — hint tracking is best-effort
      }
    },
    [gameId, hintViewedMutation],
  )

  const handleGiveClue = useCallback(async () => {
    if (!clueWord.trim() || clueInFlightRef.current || pausedRef.current) return
    clueInFlightRef.current = true
    setIsSubmittingClue(true)
    try {
      await clueMutation.mutateAsync({ game_id: gameId, data: { clue_word: clueWord.trim(), clue_number: clueNumber } })
      setClueWord("")
      setClueNumber(1)
      invalidateBoard()
    } catch (err) {
      moveFailed(err, t("game.errors.moveFailed"))
    } finally {
      clueInFlightRef.current = false
      setIsSubmittingClue(false)
    }
  }, [gameId, clueWord, clueNumber, clueMutation, invalidateBoard, moveFailed, t])

  const handleGuessCard = useCallback(
    async (index: number) => {
      if (pausedRef.current || guessInFlightRef.current) return
      guessInFlightRef.current = true
      try {
        const data = (await guessMutation.mutateAsync({ game_id: gameId, data: { card_index: index } })) as {
          all_voted?: boolean
          vote_changed?: boolean
          tied?: boolean
        }
        if (data.all_voted === false) {
          toast.info(data.vote_changed ? t("game.codenames.voteChanged") : t("game.codenames.voteSubmitted"))
        } else if (data.tied) {
          toast.warning(t("game.codenames.tieWarning"))
        }
        invalidateBoard()
      } catch (err) {
        moveFailed(err, t("game.errors.moveFailed"))
      } finally {
        guessInFlightRef.current = false
      }
    },
    [gameId, t, guessMutation, invalidateBoard, moveFailed],
  )

  const handleEndTurn = useCallback(async () => {
    if (pausedRef.current || endTurnInFlightRef.current) return
    endTurnInFlightRef.current = true
    setIsEndingTurn(true)
    try {
      await endTurnMutation.mutateAsync({ game_id: gameId })
      invalidateBoard()
    } catch (err) {
      moveFailed(err, t("game.errors.moveFailed"))
    } finally {
      endTurnInFlightRef.current = false
      setIsEndingTurn(false)
    }
  }, [gameId, endTurnMutation, invalidateBoard, moveFailed, t])

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
      // Ignore errors — navigate anyway
    }
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }, [user, navigate, t, leaveMutation])

  const handleBackToRoom = useCallback(() => {
    if (roomIdRef.current) {
      queryClient.removeQueries({ queryKey: queryKeys.room.state(roomIdRef.current) })
      navigate({ to: "/rooms/$roomId", params: { roomId: roomIdRef.current } })
    }
  }, [navigate, queryClient])

  // Achievements are pressed as seals in the colophon (GameOverScreen), not toasted.

  // Any player may report an expired timer (the server acts only once it has really run
  // out); the host at once, the others after a jittered wait that the turn's next state
  // cancels (`useTimerReport`). The window is the turn's server start: a stop answer
  // (`paused`, `round_already_resolved`) silences it until the next turn or the resume.
  const timerWindow = serverState?.timer_started_at ?? null
  const turn = serverState?.current_turn
  const handleTimerExpired = useTimerReport({
    isHost: !!serverState?.is_host,
    paused: isPaused,
    phaseKey: `${serverState?.status}:${serverState?.current_team}:${turn?.clue_word ?? ""}:${timerWindow}`,
    windowKey: timerWindow,
    send: () => timerExpiredMutation.mutateAsync({ game_id: gameId }),
    onChanged: invalidateBoard,
  })

  return {
    user,
    gameState,
    serverState,
    isLoading,
    socketConnected,
    cancelMessage,
    isPaused,
    /** The veil is up (GameOverTransition). */
    showGameOverTransition: ceremony === "veiled",
    /** The colophon waits: the last card is still being woven, or the veil is up. */
    colophonHeld: ceremony !== "none",
    roomIdRef,
    clueWord,
    setClueWord,
    clueNumber,
    setClueNumber,
    isSubmittingClue,
    isEndingTurn,
    handleGiveClue,
    handleGuessCard,
    handleEndTurn,
    handleLeaveRoom,
    handleBackToRoom,
    handleHintViewed,
    handleTimerExpired,
    navigate,
  }
}
