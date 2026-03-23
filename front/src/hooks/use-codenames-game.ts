import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
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
import { useAchievementNotifications } from "@/components/achievements/AchievementToast"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { useAuth } from "@/providers/AuthProvider"
import { retrieveRoomIdForGame } from "@/lib/room-session"

interface CodenamesCard {
  word: string
  card_type: "red" | "blue" | "neutral" | "assassin" | null
  revealed: boolean
  hint?: string | null
}

interface CodenamesTurn {
  team: "red" | "blue"
  clue_word: string | null
  clue_number: number
  guesses_made: number
  max_guesses: number | null
  card_votes?: Record<string, number>
}

interface CodenamesPlayer {
  user_id: string
  username: string
  team: string
  role: string
}

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
  clue_history?: {
    team: "red" | "blue"
    clue_word: string
    clue_number: number
    guesses: { word: string; card_type: string; correct: boolean }[]
  }[]
  timer_config?: { clue_seconds: number; guess_seconds: number }
  timer_started_at?: string | null
  newly_unlocked_achievements?: { user_id: string; achievements: { code: string; name: string; icon: string; tier: number }[] }[]
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

  const { connected: socketConnected } = useSocket({ roomId: socketRoomId, gameId, gameType: "codenames", enabled: !!user })

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
    if (queryError) {
      const errMsg = getApiErrorMessage(queryError, "Game not found")
      if (errMsg.includes("not found") || errMsg.includes("cancelled") || errMsg.includes("removed")) {
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

  const invalidateBoard = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.game.codenames(gameId) })
  }, [gameId, queryClient])

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
    if (!clueWord.trim() || isSubmittingClue) return
    setIsSubmittingClue(true)
    try {
      await clueMutation.mutateAsync({ game_id: gameId, data: { clue_word: clueWord.trim(), clue_number: clueNumber } })
      setClueWord("")
      setClueNumber(1)
      invalidateBoard()
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to give clue"))
    } finally {
      setIsSubmittingClue(false)
    }
  }, [gameId, clueWord, clueNumber, isSubmittingClue, clueMutation, invalidateBoard])

  const handleGuessCard = useCallback(
    async (index: number) => {
      try {
        const data = await guessMutation.mutateAsync({ game_id: gameId, data: { card_index: index } }) as { all_voted?: boolean; vote_changed?: boolean; tied?: boolean }
        if (data.all_voted === false) {
          toast.info(data.vote_changed ? t("game.codenames.voteChanged") : t("game.codenames.voteSubmitted"))
        } else if (data.tied) {
          toast.warning(t("game.codenames.tieWarning"))
        }
        invalidateBoard()
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to guess card"))
      }
    },
    [gameId, t, guessMutation, invalidateBoard],
  )

  const handleEndTurn = useCallback(async () => {
    try {
      await endTurnMutation.mutateAsync({ game_id: gameId })
      invalidateBoard()
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to end turn"))
    }
  }, [gameId, endTurnMutation, invalidateBoard])

  const handleLeaveRoom = useCallback(async () => {
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await leaveMutation.mutateAsync({ data: { user_id: user.id, room_id: roomIdRef.current } })
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

  useAchievementNotifications(serverState?.newly_unlocked_achievements, user?.id)

  const timerExpiredRef = useRef(false)
  const handleTimerExpired = useCallback(async () => {
    if (!serverState?.is_host || timerExpiredRef.current) return
    timerExpiredRef.current = true
    try {
      await timerExpiredMutation.mutateAsync({ game_id: gameId })
      invalidateBoard()
    } catch {
      // Ignore — another client may have already triggered it
    } finally {
      timerExpiredRef.current = false
    }
  }, [gameId, serverState?.is_host, timerExpiredMutation, invalidateBoard])

  return {
    user,
    gameState,
    serverState,
    isLoading,
    socketConnected,
    cancelMessage,
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
