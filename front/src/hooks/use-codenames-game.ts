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
import { isGamePausedError, isTimerStopAction } from "@/components/games/shared/prayer-pause/pause-utils"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { useAuth } from "@/providers/AuthProvider"
import { retrieveRoomIdForGame } from "@/lib/room-session"

import type {
  ClueHistoryEntry,
  CodenamesCard,
  CodenamesPlayer,
  CodenamesTurn,
} from "@/components/games/codenames/model"

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
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [showGameOverTransition, setShowGameOverTransition] = useState(false)
  const gameOverTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const previousStatusRef = useRef<string | null>(null)

  // Poll game state via REST only when Socket.IO is disconnected (safety net)
  const { data: serverState, isLoading, error: queryError } = useGetCodenamesBoardApiV1CodenamesGamesGameIdBoardGet(
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

  useEffect(() => {
    if (!serverState) return
    const currentStatus = serverState.status
    if (currentStatus === "finished" && previousStatusRef.current && previousStatusRef.current !== "finished" && !showGameOverTransition) {
      trackEvent("game-over", { game: "codenames", winner: serverState.winner || "" })
      setShowGameOverTransition(true)
      gameOverTransitionTimerRef.current = setTimeout(() => {
        setShowGameOverTransition(false)
        gameOverTransitionTimerRef.current = null
      }, 3000)
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
    return () => {
      if (gameOverTransitionTimerRef.current) clearTimeout(gameOverTransitionTimerRef.current)
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
    if (!clueWord.trim() || isSubmittingClue || pausedRef.current) return
    setIsSubmittingClue(true)
    try {
      await clueMutation.mutateAsync({ game_id: gameId, data: { clue_word: clueWord.trim(), clue_number: clueNumber } })
      setClueWord("")
      setClueNumber(1)
      invalidateBoard()
    } catch (err) {
      moveFailed(err, "Failed to give clue")
    } finally {
      setIsSubmittingClue(false)
    }
  }, [gameId, clueWord, clueNumber, isSubmittingClue, clueMutation, invalidateBoard, moveFailed])

  const handleGuessCard = useCallback(
    async (index: number) => {
      if (pausedRef.current) return
      try {
        const data = await guessMutation.mutateAsync({ game_id: gameId, data: { card_index: index } }) as { all_voted?: boolean; vote_changed?: boolean; tied?: boolean }
        if (data.all_voted === false) {
          toast.info(data.vote_changed ? t("game.codenames.voteChanged") : t("game.codenames.voteSubmitted"))
        } else if (data.tied) {
          toast.warning(t("game.codenames.tieWarning"))
        }
        invalidateBoard()
      } catch (err) {
        moveFailed(err, "Failed to guess card")
      }
    },
    [gameId, t, guessMutation, invalidateBoard, moveFailed],
  )

  const handleEndTurn = useCallback(async () => {
    if (pausedRef.current) return
    try {
      await endTurnMutation.mutateAsync({ game_id: gameId })
      invalidateBoard()
    } catch (err) {
      moveFailed(err, "Failed to end turn")
    }
  }, [gameId, endTurnMutation, invalidateBoard, moveFailed])

  const handleLeaveRoom = useCallback(async () => {
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
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

  const timerExpiredRef = useRef(false)
  // The timer window (its server start) the server told us to stop reporting: the game
  // was paused, or the turn was already resolved. A new window (the next turn, or the
  // start the resume moved forward) re-arms it.
  const timerWindowRef = useRef<string | null>(null)
  timerWindowRef.current = serverState?.timer_started_at ?? null
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
      invalidateBoard()
    } catch {
      // Ignore — another client may have already triggered it
    } finally {
      timerExpiredRef.current = false
    }
  }, [gameId, timerExpiredMutation, invalidateBoard])

  return {
    user,
    gameState,
    serverState,
    isLoading,
    socketConnected,
    cancelMessage,
    isPaused,
    showGameOverTransition,
    roomIdRef,
    clueWord,
    setClueWord,
    clueNumber,
    setClueNumber,
    isSubmittingClue,
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
