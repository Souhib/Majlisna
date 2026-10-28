import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import type { GamePause } from "@/api/generated"
import {
  useGetUndercoverStateApiV1UndercoverGamesGameIdStateGet,
  useSubmitVoteApiV1UndercoverGamesGameIdVotePost,
  useSubmitDescriptionApiV1UndercoverGamesGameIdDescribePost,
  useRecordHintViewedApiV1UndercoverGamesGameIdHintViewedPost,
  useTimerExpiredApiV1UndercoverGamesGameIdTimerExpiredPost,
  useStartNextRoundApiV1UndercoverGamesGameIdNextRoundPost,
  useMrWhiteGuessApiV1UndercoverGamesGameIdMrWhiteGuessPost,
  useLeaveRoomApiV1RoomsLeavePatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { isGamePausedError, isTimerStopAction } from "@/components/games/shared/prayer-pause/pause-utils"
import { roomErrorMessage } from "@/components/rooms/errors"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { deriveUndercoverPhase, derivePlayerList, deriveVotedPlayers, type UndercoverPhase } from "@/lib/game-state"
import { useAuth } from "@/providers/AuthProvider"
import { hasReadRole, rememberRoleRead } from "@/lib/undercover-session"
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
  round: number
  username: string
  role: string
  user_id: string
  votes: VoteEntry[]
}

interface GameState {
  players: { id: string; username: string; is_alive: boolean; is_mayor?: boolean }[]
  phase: UndercoverPhase
  round: number
  roundResolved: boolean
  mrWhiteGuesser: string | null
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

  const leaveAfterKick = useLeaveAfterKick()
  const { connected: socketConnected } = useSocket({ roomId: socketRoomId, gameId, gameType: "undercover", enabled: !!user, onKicked: leaveAfterKick })

  // the first reading, once dismissed, stays dismissed through a reload (per game, per tab)
  const [roleRevealed, setRoleRevealed] = useState(() => hasReadRole(gameId))
  const [selectedVote, setSelectedVote] = useState<string | null>(null)
  const [isSubmittingVote, setIsSubmittingVote] = useState(false)
  const [descriptionInput, setDescriptionInput] = useState("")
  const [descriptionError, setDescriptionError] = useState("")
  const [isSubmittingDescription, setIsSubmittingDescription] = useState(false)
  const previousWinnerRef = useRef<string | null>(null)
  const previousRoundRef = useRef<number>(0)
  // Rounds whose elimination has already been shown, so the overlay plays once
  // per round whether we saw the round resolve or only the next one start.
  const shownEliminationRoundsRef = useRef<Set<number>>(new Set())
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [showEliminationOverlay, setShowEliminationOverlay] = useState(false)
  const [mrWhiteGuessInput, setMrWhiteGuessInput] = useState("")
  const [isSubmittingMrWhiteGuess, setIsSubmittingMrWhiteGuess] = useState(false)
  const [isStartingNextRound, setIsStartingNextRound] = useState(false)
  const [eliminationData, setEliminationData] = useState<EliminationData | null>(null)

  const {
    data: serverState,
    isLoading,
    error: queryError,
  } = useGetUndercoverStateApiV1UndercoverGamesGameIdStateGet(
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
    data:
      | {
          my_role: string
          my_word: string
          my_word_ar?: string | null
          my_word_ar_vocalized?: string | null
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
          round_resolved?: boolean
          mr_white_guesser?: string | null
          description_order?: DescriptionOrderEntry[]
          current_describer_index?: number
          descriptions?: Record<string, string>
          vote_history?: {
            round: number
            votes: { voter: string; voter_id: string; target: string; target_id: string }[]
            eliminated: { username: string; role: string; user_id: string } | null
            mr_white_guess?: { word?: string | null; correct: boolean } | null
          }[]
          timer_config?: { description_seconds: number; voting_seconds: number }
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
          word_explanations?: {
            civilian_word: string
            civilian_word_ar?: string | null
            civilian_word_ar_vocalized?: string | null
            civilian_word_hint: string | null
            undercover_word: string
            undercover_word_ar?: string | null
            undercover_word_ar_vocalized?: string | null
            undercover_word_hint: string | null
          } | null
        }
      | undefined
    isLoading: boolean
    error: Error | null
  }

  const voteMutation = useSubmitVoteApiV1UndercoverGamesGameIdVotePost()
  const describeMutation = useSubmitDescriptionApiV1UndercoverGamesGameIdDescribePost()
  const hintViewedMutation = useRecordHintViewedApiV1UndercoverGamesGameIdHintViewedPost()
  const timerExpiredMutation = useTimerExpiredApiV1UndercoverGamesGameIdTimerExpiredPost()
  const nextRoundMutation = useStartNextRoundApiV1UndercoverGamesGameIdNextRoundPost()
  const mrWhiteGuessMutation = useMrWhiteGuessApiV1UndercoverGamesGameIdMrWhiteGuessPost()
  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  // The prayer pause: while the host has paused the game no move is sent (the page also
  // makes the game inert under the veil) and the clock is never reported as expired.
  const isPaused = !!serverState?.paused
  const pausedRef = useRef(isPaused)
  pausedRef.current = isPaused
  // A move refused because the game was paused under us (409 gamePaused): its translated
  // error is shown, and the state that carries the veil is fetched at once.
  const refetchIfPaused = useCallback(
    (err: unknown) => {
      if (isGamePausedError(err)) queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    },
    [gameId, queryClient],
  )

  const gameState = useMemo<GameState>(() => {
    if (!serverState) {
      return {
        players: [],
        phase: "role_reveal",
        round: 1,
        roundResolved: false,
        mrWhiteGuesser: null,
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
      // once anyone has described, the table is past the first reading: a player who
      // lost the tab's memory (storage refused) is not held back on it
      roleRevealed: roleRevealed || Object.keys(serverState.descriptions ?? {}).length > 0,
      round_resolved: serverState.round_resolved,
    })

    return {
      players: derivePlayerList(serverState.players),
      phase,
      round: serverState.turn_number,
      roundResolved: serverState.round_resolved ?? false,
      mrWhiteGuesser: serverState.mr_white_guesser ?? null,
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
    const currentRound = serverState.turn_number

    if (currentRound > previousRoundRef.current && previousRoundRef.current > 0) {
      setSelectedVote(null)
      setDescriptionInput("")
      setDescriptionError("")
      setIsSubmittingDescription(false)
      setMrWhiteGuessInput("")
    }

    // A round that resolves ON SCREEN is told by the round-over screen itself (the
    // verdict, derived from vote_history: "The table chose Bilal."), or by the Mr. White
    // panel when he was the one found. Only a client that MISSED the resolved state (it
    // saw the next round start directly) gets the verdict as a notice to dismiss. Each
    // round's elimination is told once.
    // Any resolved round on screen has been told by that screen, including on a page
    // that loaded mid-verdict.
    if (serverState.round_resolved === true) shownEliminationRoundsRef.current.add(currentRound)
    const skippedResolution = currentRound > previousRoundRef.current && previousRoundRef.current > 0
    const missedRound = skippedResolution ? previousRoundRef.current : null
    if (missedRound !== null && !serverState.winner && !shownEliminationRoundsRef.current.has(missedRound)) {
      const roundVotes = serverState.vote_history?.find((r) => r.round === missedRound)
      if (roundVotes?.eliminated) {
        shownEliminationRoundsRef.current.add(missedRound)
        setEliminationData({
          round: missedRound,
          username: roundVotes.eliminated.username,
          role: roundVotes.eliminated.role,
          user_id: roundVotes.eliminated.user_id,
          votes: roundVotes.votes,
        })
        setShowEliminationOverlay(true)
      }
    }

    const currentWinner = serverState.winner || null
    if (currentWinner && !previousWinnerRef.current) {
      trackEvent("game-over", { game: "undercover", winner: currentWinner })
      // the game is over: a notice about an earlier round has nothing left to say
      setShowEliminationOverlay(false)
    }
    previousWinnerRef.current = currentWinner

    previousRoundRef.current = currentRound
  }, [serverState])

  useEffect(() => {
    // a game that is gone is told by its status, never by the (translated) text
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

  // The vote itself is confirmed on screen ("You voted for Bilal"), not by a toast.
  // One request at a time: a double tap used to send the vote twice.
  const handleConfirmVote = useCallback(async () => {
    if (!selectedVote || hasVoted || !user || isSubmittingVote || pausedRef.current) return
    setIsSubmittingVote(true)
    try {
      await voteMutation.mutateAsync({ game_id: gameId, data: { voted_for: selectedVote } })
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch (err) {
      toast.error(roomErrorMessage(err, t("game.undercover.errors.vote")))
      refetchIfPaused(err)
    } finally {
      setIsSubmittingVote(false)
    }
  }, [selectedVote, hasVoted, gameId, user, isSubmittingVote, queryClient, voteMutation, t, refetchIfPaused])

  const handleSubmitDescription = useCallback(async () => {
    if (!user || isSubmittingDescription || pausedRef.current) return
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
      toast.error(roomErrorMessage(err, t("game.undercover.errors.describe")))
      refetchIfPaused(err)
    } finally {
      setIsSubmittingDescription(false)
    }
  }, [descriptionInput, user, gameId, isSubmittingDescription, t, queryClient, describeMutation, refetchIfPaused])

  const handleDismissRole = useCallback(() => {
    rememberRoleRead(gameId)
    setRoleRevealed(true)
  }, [gameId])

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

  // Achievements earned this game are sealed in the colophon (GameOverScreen), never
  // announced as toasts while the game runs.

  const timerExpiredRef = useRef(false)
  // The timer window (its server start) the server told us to stop reporting: the game
  // was paused, or the round was already resolved. A new window (the next phase, or the
  // start the resume moved forward) re-arms it.
  const timerWindow = serverState?.timer_started_at ?? null
  const timerWindowRef = useRef(timerWindow)
  timerWindowRef.current = timerWindow
  const stoppedWindowRef = useRef<string | null>(null)
  // Any player may report an expired timer — the server only acts once the timer
  // has really elapsed. Gating this on the host stalled the round whenever the
  // host's phone was locked or their tab backgrounded.
  const handleTimerExpired = useCallback(async () => {
    const timerKey = timerWindowRef.current
    if (timerExpiredRef.current || pausedRef.current) return
    if (timerKey !== null && stoppedWindowRef.current === timerKey) return
    timerExpiredRef.current = true
    try {
      const result = await timerExpiredMutation.mutateAsync({ game_id: gameId })
      if (isTimerStopAction(result?.action)) stoppedWindowRef.current = timerKey
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch {
      // Ignore — another client may have already triggered it
    } finally {
      timerExpiredRef.current = false
    }
  }, [gameId, queryClient, timerExpiredMutation])

  const handleStartNextRound = useCallback(async () => {
    if (!gameState.isHost || !roomIdRef.current || isStartingNextRound || pausedRef.current) return
    setIsStartingNextRound(true)
    try {
      await nextRoundMutation.mutateAsync({ game_id: gameId, data: { room_id: roomIdRef.current } })
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch (err) {
      toast.error(roomErrorMessage(err, t("game.undercover.errors.nextRound")))
      refetchIfPaused(err)
    } finally {
      setIsStartingNextRound(false)
    }
  }, [gameId, gameState.isHost, isStartingNextRound, nextRoundMutation, queryClient, t, refetchIfPaused])

  const handleSubmitMrWhiteGuess = useCallback(async () => {
    const guess = mrWhiteGuessInput.trim()
    if (!guess || isSubmittingMrWhiteGuess || pausedRef.current) return
    setIsSubmittingMrWhiteGuess(true)
    try {
      // the outcome is the round's verdict for the whole table (vote_history's
      // mr_white_guess), not a toast for the guesser alone
      await mrWhiteGuessMutation.mutateAsync({ game_id: gameId, data: { guess_word: guess } })
      setMrWhiteGuessInput("")
      queryClient.invalidateQueries({ queryKey: queryKeys.game.undercover(gameId) })
    } catch (err) {
      toast.error(roomErrorMessage(err, t("game.undercover.errors.guess")))
      refetchIfPaused(err)
    } finally {
      setIsSubmittingMrWhiteGuess(false)
    }
  }, [gameId, isSubmittingMrWhiteGuess, mrWhiteGuessInput, mrWhiteGuessMutation, queryClient, t, refetchIfPaused])

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

  const isMrWhiteGuesser = gameState.phase === "mr_white_guessing" && gameState.mrWhiteGuesser === user?.id

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
    isPaused,
    isAlive,
    isSpectator,
    isMyTurnToDescribe,
    isMrWhiteGuesser,
    mrWhiteGuessInput,
    isSubmittingMrWhiteGuess,
    isStartingNextRound,
    setMrWhiteGuessInput,
    handleStartNextRound,
    handleSubmitMrWhiteGuess,
    hasVoted,
    selectedVote,
    isSubmittingVote,
    descriptionInput,
    descriptionError,
    isSubmittingDescription,
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
