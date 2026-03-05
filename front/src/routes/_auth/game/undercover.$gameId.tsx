import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Crown, Loader2, LogOut, MessageCircle } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import apiClient, { getApiErrorMessage } from "@/api/client"
import { DescriptionPhase } from "@/components/games/undercover/DescriptionPhase"
import { EliminationOverlay } from "@/components/games/undercover/EliminationOverlay"
import { GameOverScreen } from "@/components/games/undercover/GameOverScreen"
import { RoleRevealPhase } from "@/components/games/undercover/RoleRevealPhase"
import { VotingPhase } from "@/components/games/undercover/VotingPhase"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"

interface DescriptionOrderEntry {
  user_id: string
  username: string
}

interface GameState {
  players: { id: string; username: string; is_alive: boolean; is_mayor?: boolean }[]
  phase: "role_reveal" | "describing" | "playing" | "elimination" | "game_over"
  round: number
  my_role?: string
  my_word?: string
  eliminated_player_username?: string
  eliminated_player_role?: string
  winner?: string
  votedPlayers: string[]
  isHost: boolean
  descriptionOrder: DescriptionOrderEntry[]
  currentDescriberIndex: number
  descriptions: Record<string, string>
}

export const Route = createFileRoute("/_auth/game/undercover/$gameId")({
  component: UndercoverGamePage,
})

function UndercoverGamePage() {
  const { gameId } = Route.useParams()
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const roomIdRef = useRef<string | null>(null)
  const [roleRevealed, setRoleRevealed] = useState(false)
  const [selectedVote, setSelectedVote] = useState<string | null>(null)
  const [descriptionInput, setDescriptionInput] = useState("")
  const [descriptionError, setDescriptionError] = useState("")
  const [isSubmittingDescription, setIsSubmittingDescription] = useState(false)
  const [showVotingTransition, setShowVotingTransition] = useState(false)
  const votingTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const previousPhaseRef = useRef<string | null>(null)
  const previousRoundRef = useRef<number>(0)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)

  // Poll game state via REST every 2 seconds
  const { data: serverState, isLoading, error: queryError } = useQuery({
    queryKey: ["undercover", gameId],
    queryFn: async () => {
      const res = await apiClient({
        method: "GET",
        url: `/api/v1/undercover/games/${gameId}/state`,
      })
      return res.data as {
        my_role: string
        my_word: string
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
      }
    },
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
    enabled: !!user,
  })

  // Derive game state from server data
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

    if (serverState.room_id) roomIdRef.current = serverState.room_id

    const votedPlayerIds = serverState.votes ? Object.keys(serverState.votes) : []

    let phase: GameState["phase"]
    if (serverState.winner) {
      phase = "game_over"
    } else if (serverState.turn_phase === "describing") {
      phase = roleRevealed || serverState.turn_number > 1 ? "describing" : "role_reveal"
    } else if (serverState.turn_number > 0) {
      phase = "playing"
    } else {
      phase = "role_reveal"
    }

    // Detect elimination
    const prevPhase = previousPhaseRef.current
    const lastEliminated = serverState.eliminated_players.length > 0
      ? serverState.eliminated_players[serverState.eliminated_players.length - 1]
      : null

    let eliminated_player_username: string | undefined
    let eliminated_player_role: string | undefined

    if (prevPhase === "playing" && serverState.turn_phase === "describing" && lastEliminated) {
      eliminated_player_username = lastEliminated.username
      eliminated_player_role = lastEliminated.role
    }

    return {
      players: serverState.players.map((p) => ({
        id: p.user_id,
        username: p.username,
        is_alive: p.is_alive,
        is_mayor: p.is_mayor,
      })),
      phase,
      round: serverState.turn_number,
      my_role: serverState.my_role,
      my_word: serverState.my_word,
      eliminated_player_username,
      eliminated_player_role,
      winner: serverState.winner || undefined,
      votedPlayers: votedPlayerIds,
      isHost: serverState.is_host ?? false,
      descriptionOrder: serverState.description_order || [],
      currentDescriberIndex: serverState.current_describer_index ?? 0,
      descriptions: serverState.descriptions || {},
    }
  }, [serverState, roleRevealed])

  // Track phase changes for transitions
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
    }

    if (previousPhaseRef.current === "describing" && currentPhase === "voting" && !showVotingTransition) {
      setShowVotingTransition(true)
      votingTransitionTimerRef.current = setTimeout(() => {
        setShowVotingTransition(false)
        votingTransitionTimerRef.current = null
      }, 2500)
    }

    previousPhaseRef.current = currentPhase || null
    previousRoundRef.current = currentRound
  }, [serverState])

  // Handle query error (game not found)
  useEffect(() => {
    if (queryError) {
      const errMsg = getApiErrorMessage(queryError, "Game not found")
      if (errMsg.includes("not found") || errMsg.includes("removed")) {
        setCancelMessage(errMsg)
        setTimeout(() => navigate({ to: "/" }), 3000)
      }
    }
  }, [queryError, navigate])

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
      await apiClient({
        method: "POST",
        url: `/api/v1/undercover/games/${gameId}/vote`,
        data: { voted_for: selectedVote },
      })
      queryClient.invalidateQueries({ queryKey: ["undercover", gameId] })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to submit vote"))
    }
  }, [selectedVote, hasVoted, gameId, user, gameState.players, t, queryClient])

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
      await apiClient({
        method: "POST",
        url: `/api/v1/undercover/games/${gameId}/describe`,
        data: { word },
      })
      setDescriptionInput("")
      queryClient.invalidateQueries({ queryKey: ["undercover", gameId] })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to submit description"))
    } finally {
      setIsSubmittingDescription(false)
    }
  }, [descriptionInput, user, gameId, isSubmittingDescription, t, queryClient])

  const handleNextRound = useCallback(async () => {
    if (!roomIdRef.current) return
    try {
      await apiClient({
        method: "POST",
        url: `/api/v1/undercover/games/${gameId}/next-round`,
        data: { room_id: roomIdRef.current },
      })
      queryClient.invalidateQueries({ queryKey: ["undercover", gameId] })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to start next round"))
    }
  }, [gameId, queryClient])

  const handleDismissRole = useCallback(() => {
    setRoleRevealed(true)
  }, [])

  const handleLeaveRoom = useCallback(async () => {
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await apiClient({
        method: "PATCH",
        url: "/api/v1/rooms/leave",
        data: { user_id: user.id, room_id: roomIdRef.current },
      })
    } catch {
      // Ignore errors — navigate anyway
    }
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }, [user, navigate, t])

  const handleBackToRoom = useCallback(() => {
    if (roomIdRef.current) {
      navigate({ to: "/rooms/$roomId", params: { roomId: roomIdRef.current } })
    }
  }, [navigate])

  const handleDescriptionInputChange = useCallback((value: string) => {
    setDescriptionInput(value)
    setDescriptionError("")
  }, [])

  const myPlayer = gameState.players.find((p) => p.id === user?.id)
  const isAlive = myPlayer?.is_alive !== false

  const isMyTurnToDescribe =
    gameState.phase === "describing" &&
    gameState.descriptionOrder.length > 0 &&
    gameState.currentDescriberIndex < gameState.descriptionOrder.length &&
    gameState.descriptionOrder[gameState.currentDescriberIndex]?.user_id === user?.id

  if (cancelMessage) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="rounded-xl border bg-destructive/10 p-8 text-center">
          <h2 className="text-xl font-bold text-destructive mb-2">{t("game.gameOver")}</h2>
          <p className="text-muted-foreground">{cancelMessage}</p>
          <p className="text-sm text-muted-foreground mt-2">Redirecting...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      {/* Voting Transition Overlay */}
      <AnimatePresence>
        {showVotingTransition && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/90 backdrop-blur-sm"
          >
            <motion.div className="text-center space-y-4">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", delay: 0.2 }}
              >
                <MessageCircle className="h-16 w-16 mx-auto text-primary" />
              </motion.div>
              <motion.h2
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="text-2xl font-bold"
              >
                {t("game.undercover.allDescriptionsIn")}
              </motion.h2>
              <motion.p
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.7 }}
                className="text-lg text-muted-foreground"
              >
                {t("game.undercover.timeToVote")}
              </motion.p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Game Header */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold">{t("games.undercover.name")}</h1>
        <p className="text-sm text-muted-foreground mt-1">Round {gameState.round}</p>
      </div>

      {/* Loading State */}
      {isLoading && !gameState.my_role && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          <Loader2 className="h-10 w-10 mx-auto animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">{t("common.loading")}</p>
        </div>
      )}

      {/* Role Reveal */}
      {gameState.phase === "role_reveal" && gameState.my_role && (
        <RoleRevealPhase
          myRole={gameState.my_role}
          myWord={gameState.my_word}
          onDismiss={handleDismissRole}
        />
      )}

      {/* Describing Phase */}
      {gameState.phase === "describing" && (
        <DescriptionPhase
          myRole={gameState.my_role}
          myWord={gameState.my_word}
          descriptionOrder={gameState.descriptionOrder}
          currentDescriberIndex={gameState.currentDescriberIndex}
          descriptions={gameState.descriptions}
          currentUserId={user?.id}
          isMyTurnToDescribe={isMyTurnToDescribe}
          isAlive={isAlive}
          descriptionInput={descriptionInput}
          descriptionError={descriptionError}
          isSubmittingDescription={isSubmittingDescription}
          onDescriptionInputChange={handleDescriptionInputChange}
          onSubmitDescription={handleSubmitDescription}
        />
      )}

      {/* Playing Phase (Voting) */}
      {gameState.phase === "playing" && (
        <VotingPhase
          players={gameState.players}
          myRole={gameState.my_role}
          myWord={gameState.my_word}
          descriptions={gameState.descriptions}
          descriptionOrder={gameState.descriptionOrder}
          isAlive={isAlive}
          hasVoted={hasVoted}
          selectedVote={selectedVote}
          votedPlayers={gameState.votedPlayers}
          currentUserId={user?.id}
          onSelectPlayer={handleSelectPlayer}
          onConfirmVote={handleConfirmVote}
        />
      )}

      {/* Elimination */}
      {gameState.phase === "elimination" && (
        <EliminationOverlay
          eliminatedUsername={gameState.eliminated_player_username}
          eliminatedRole={gameState.eliminated_player_role}
          onNextRound={handleNextRound}
        />
      )}

      {/* Game Over */}
      {gameState.phase === "game_over" && (
        <GameOverScreen
          winner={gameState.winner}
          roomId={roomIdRef.current}
          onBackToRoom={handleBackToRoom}
          onLeaveRoom={handleLeaveRoom}
        />
      )}

      {/* Player List */}
      <div className="rounded-xl border bg-card p-6">
        <h3 className="font-semibold mb-3">
          {t("room.players")} ({gameState.players.filter((p) => p.is_alive).length}/
          {gameState.players.length})
        </h3>
        <div className="space-y-2">
          {gameState.players.map((player) => (
            <div
              key={player.id}
              className={cn(
                "flex items-center justify-between rounded-lg px-4 py-2",
                player.is_alive ? "bg-muted/50" : "bg-destructive/5 line-through opacity-50",
              )}
            >
              <span className="text-sm flex items-center gap-2">
                {player.username}
                {player.is_mayor && <Crown className="h-3 w-3 text-yellow-500" />}
              </span>
              <span className="text-xs text-muted-foreground">
                {player.is_alive ? t("game.alive") : t("game.eliminated")}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Leave Game Button */}
      {gameState.phase !== "game_over" && gameState.phase !== "role_reveal" && (
        <div className="mt-4 text-center">
          <button
            type="button"
            onClick={handleLeaveRoom}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-destructive transition-colors"
          >
            <LogOut className="h-4 w-4" />
            {t("game.undercover.leaveGame")}
          </button>
        </div>
      )}
    </div>
  )
}
