import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  useGetUndercoverStateApiV1UndercoverGamesGameIdStateGet,
  useSubmitVoteApiV1UndercoverGamesGameIdVotePost,
  useSubmitDescriptionApiV1UndercoverGamesGameIdDescribePost,
  useRecordHintViewedApiV1UndercoverGamesGameIdHintViewedPost,
  useTimerExpiredApiV1UndercoverGamesGameIdTimerExpiredPost,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { useAchievementNotifications } from "@/components/achievements/AchievementToast"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { deriveUndercoverPhase, derivePlayerList, deriveVotedPlayers } from "@/lib/game-state"
import { useAuth } from "@/providers/AuthProvider"
import { retrieveRoomIdForGame } from "@/lib/room-session"

interface DescriptionOrderEntry {
  user_id: string
  username: string
}

interface VoteEntry {
  voter: string
  voter_id: string
  target: string
  target_id: string
}

interface EliminationData {
  username: string
  role: string
  votes: VoteEntry[]
}

interface GameState {
  players: { id: string; username: string; is_alive: boolean; is_mayor?: boolean }[]
  phase: "role_reveal" | "describing" | "playing" | "game_over"
  round: number
  my_role?: string
  my_word?: string
  winner?: string
  votedPlayers: string[]
  isHost: boolean
  descriptionOrder: DescriptionOrderEntry[]
  currentDescriberIndex: number
  descriptions: Record<string, string>
}

export function useUndercoverGame(gameId: string) {
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

  const { connected: socketConnected } = useSocket({ roomId: socketRoomId, gameId, gameType: "undercover", enabled: !!user })

  const [roleRevealed, setRoleRevealed] = useState(false)
  const [selectedVote, setSelectedVote] = useState<string | null>(null)
  const [descriptionInput, setDescriptionInput] = useState("")
  const [descriptionError, setDescriptionError] = useState("")
  const [isSubmittingDescription, setIsSubmittingDescription] = useState(false)
  const [showVotingTransition, setShowVotingTransition] = useState(false)
  const votingTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [showGameOverTransition, setShowGameOverTransition] = useState(false)
  const gameOverTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const previousWinnerRef = useRef<string | null>(null)
  const previousPhaseRef = useRef<string | null>(null)
  const previousRoundRef = useRef<number>(0)
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [showEliminationOverlay, setShowEliminationOverlay] = useState(false)
  const [eliminationData, setEliminationData] = useState<EliminationData | null>(null)

  const { data: serverState, isLoading, error: queryError } = useGetUndercoverStateApiV1UndercoverGamesGameIdStateGet(
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
    data: {
      my_role: string
      my_word: string
      my_word_hint: string | null
      is_alive: boolean
      players: { user_id: string; username: string; is_alive: boolean; is_mayor?: boolean }[]
      eliminated_players: { user_id: string; username: string; role: string }[]
      turn_number: number
      has_voted: boolean
      room_id?: string
      is_host?: boolean
      votes?: Record<string, string>
      winner?: string | null
      turn_phase?: string
      description_order?: DescriptionOrderEntry[]
      current_describer_index?: number
      descriptions?: Record<string, string>
      vote_history?: {
        round: number
        votes: { voter: string; voter_id: string; target: string; target_id: string }[]
        eliminated: { username: string; role: string; user_id: string } | null
      }[]
      timer_config?: { description_seconds: number; voting_seconds: number }
      timer_started_at?: string | null
      newly_unlocked_achievements?: { user_id: string; achievements: { code: string; name: string; icon: string; tier: number }[] }[]
      word_explanations?: {
        civilian_word: string
        civilian_word_hint: string | null
        undercover_word: string
        undercover_word_hint: string | null
      }
    } | undefined
    isLoading: boolean
    error: Error | null
  }

  const voteMutation = useSubmitVoteApiV1UndercoverGamesGameIdVotePost()
  const describeMutation = useSubmitDescriptionApiV1UndercoverGamesGameIdDescribePost()
  const hintViewedMutation = useRecordHintViewedApiV1UndercoverGamesGameIdHintViewedPost()
  const timerExpiredMutation = useTimerExpiredApiV1UndercoverGamesGameIdTimerExpiredPost()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  const gameState = useMemo<GameState>(() => {
    if (!serverState) {
      return {
        players: [],
        phase: "role_reveal",
        round: 1,
        votedPlayers: [],
        isHost: false,
        descriptionOrder: [],
        currentDescriberIndex: 0,
        descriptions: {},
      }
    }

    if (serverState.room_id) {
      roomIdRef.current = serverState.room_id
    }

    const votedPlayerIds = deriveVotedPlayers(serverState.votes)

    const phase = deriveUndercoverPhase({
      winner: serverState.winner,
      turn_phase: serverState.turn_phase,
      turn_number: serverState.turn_number,
      my_role: serverState.my_role,
      roleRevealed,
    })

    return {
      players: derivePlayerList(serverState.players),
      phase,
      round: serverState.turn_number,
      my_role: serverState.my_role,
      my_word: serverState.my_word,
      winner: serverState.winner || undefined,
      votedPlayers: votedPlayerIds,
      isHost: serverState.is_host ?? false,
      descriptionOrder: serverState.description_order || [],
      currentDescriberIndex: serverState.current_describer_index ?? 0,
      descriptions: serverState.descriptions || {},
    }
  }, [serverState, roleRevealed])

  useEffect(() => {
    if (serverState?.room_id && !socketRoomId) {
      setSocketRoomId(serverState.room_id)
    }
  }, [serverState?.room_id, socketRoomId])

  useEffect(() => {
    if (!serverState) return
    const currentPhase = serverState.turn_phase
    const currentRound = serverState.turn_number

    if (currentRound > previousRoundRef.current && previousRoundRef.current > 0) {
      setSelectedVote(null)
      setDescriptionInput("")
      setDescriptionError("")
      setIsSubmittingDescription(false)
      if (votingTransitionTimerRef.current) {
        clearTimeout(votingTransitionTimerRef.current)
        votingTransitionTimerRef.current = null
        setShowVotingTransition(false)
      }

      if (!serverState.winner) {
        const latestVoteRound = serverState.vote_history?.find(
          (r) => r.round === previousRoundRef.current,
        )
        if (latestVoteRound?.eliminated) {
          setEliminationData({
            username: latestVoteRound.eliminated.username,
            role: latestVoteRound.eliminated.role,
            votes: latestVoteRound.votes,
          })
          setShowEliminationOverlay(true)
        }
      }
    }

    if (previousPhaseRef.current === "describing" && currentPhase === "voting" && !showVotingTransition) {
      setShowVotingTransition(true)
      votingTransitionTimerRef.current = setTimeout(() => {
        setShowVotingTransition(false)
        votingTransitionTimerRef.current = null
      }, 2500)
    }

    const currentWinner = serverState.winner || null
    if (currentWinner && !previousWinnerRef.current && !showGameOverTransition) {
      trackEvent("game-over", { game: "undercover", winner: currentWinner })
      setShowGameOverTransition(true)
      gameOverTransitionTimerRef.current = setTimeout(() => {
        setShowGameOverTransition(false)
        gameOverTransitionTimerRef.current = null
      }, 3000)
    }
    previousWinnerRef.current = currentWinner

    previousPhaseRef.current = currentPhase || null
    previousRoundRef.current = currentRound
  }, [serverState])

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
      if (votingTransitionTimerRef.current) clearTimeout(votingTransitionTimerRef.current)
      if (gameOverTransitionTimerRef.current) clearTimeout(gameOverTransitionTimerRef.current)
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [])

  const hasVoted = useMemo(() => {
    if (!user) return false
    return gameState.votedPlayers.includes(user.id)
  }, [gameState.votedPlayers, user])

  const handleSelectPlayer = useCallback(
    (playerId: string) => {
      if (hasVoted) return
      setSelectedVote((prev) => (prev === playerId ? null : playerId))
    },
    [hasVoted],
  )

  const handleConfirmVote = useCallback(async () => {
    if (!selectedVote || hasVoted || !user) return
    const votedPlayer = gameState.players.find((p) => p.id === selectedVote)
    if (votedPlayer) {
      toast.info(t("game.undercover.votedFor", { username: votedPlayer.username }))
    }
    try {
      await voteMutation.mutateAsync({ game_id: gameId, data: { voted_for: selectedVote } })
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to submit vote"))
    }
  }, [selectedVote, hasVoted, gameId, user, gameState.players, t, queryClient, voteMutation])

  const handleSubmitDescription = useCallback(async () => {
    if (!user || isSubmittingDescription) return
    const word = descriptionInput.trim()
    if (!word) {
      setDescriptionError(t("game.undercover.wordMustBeSingleWord"))
      return
    }
    if (word.includes(" ")) {
      setDescriptionError(t("game.undercover.wordMustBeSingleWord"))
      return
    }
    if (word.length > 50) {
      setDescriptionError(t("game.undercover.wordMustBeSingleWord"))
      return
    }
    setDescriptionError("")
    setIsSubmittingDescription(true)
    try {
      await describeMutation.mutateAsync({ game_id: gameId, data: { word } })
      setDescriptionInput("")
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to submit description"))
    } finally {
      setIsSubmittingDescription(false)
    }
  }, [descriptionInput, user, gameId, isSubmittingDescription, t, queryClient, describeMutation])

  const handleDismissRole = useCallback(() => {
    setRoleRevealed(true)
  }, [])

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

  useAchievementNotifications(serverState?.newly_unlocked_achievements, user?.id)

  const timerExpiredRef = useRef(false)
  const handleTimerExpired = useCallback(async () => {
    if (!gameState.isHost || timerExpiredRef.current) return
    timerExpiredRef.current = true
    try {
      await timerExpiredMutation.mutateAsync({ game_id: gameId })
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch {
      // Ignore — another client may have already triggered it
    } finally {
      timerExpiredRef.current = false
    }
  }, [gameId, gameState.isHost, queryClient, timerExpiredMutation])

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

  const handleDismissElimination = useCallback(() => {
    setShowEliminationOverlay(false)
  }, [])

  const handleDescriptionInputChange = useCallback((value: string) => {
    setDescriptionInput(value)
    setDescriptionError("")
  }, [])

  const myPlayer = gameState.players.find((p) => p.id === user?.id)
  const isAlive = myPlayer?.is_alive !== false
  const isSpectator = gameState.my_role === "spectator"

  const isMyTurnToDescribe =
    gameState.phase === "describing" &&
    gameState.descriptionOrder.length > 0 &&
    gameState.currentDescriberIndex < gameState.descriptionOrder.length &&
    gameState.descriptionOrder[gameState.currentDescriberIndex]?.user_id === user?.id

  return {
    gameState,
    serverState,
    isLoading,
    socketConnected,
    cancelMessage,
    isAlive,
    isSpectator,
    isMyTurnToDescribe,
    hasVoted,
    selectedVote,
    descriptionInput,
    descriptionError,
    isSubmittingDescription,
    showVotingTransition,
    showGameOverTransition,
    showEliminationOverlay,
    eliminationData,
    roomIdRef,
    user,
    handleSelectPlayer,
    handleConfirmVote,
    handleSubmitDescription,
    handleDismissRole,
    handleHintViewed,
    handleTimerExpired,
    handleLeaveRoom,
    handleBackToRoom,
    handleDismissElimination,
    handleDescriptionInputChange,
  }
}
