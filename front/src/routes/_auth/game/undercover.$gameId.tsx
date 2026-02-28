import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Crown, Loader2, LogOut, MessageCircle, Shield, Skull, ThumbsUp, User } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useSocket } from "@/hooks/use-socket"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"

interface UndercoverPlayer {
  id: string
  username: string
  is_alive: boolean
  is_mayor?: boolean
  role?: string
}

interface DescriptionOrderEntry {
  user_id: string
  username: string
}

interface GameState {
  players: UndercoverPlayer[]
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
  const { emit, on, isConnected } = useSocket()
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)

  const roomIdRef = useRef<string | null>(null)

  const [gameState, setGameState] = useState<GameState>(() => {
    const initial: GameState = {
      players: [],
      phase: "role_reveal",
      round: 1,
      votedPlayers: [],
      isHost: false,
      descriptionOrder: [],
      currentDescriberIndex: 0,
      descriptions: {},
    }
    try {
      const stored = sessionStorage.getItem(`ibg-game-init-${gameId}`)
      if (stored) {
        sessionStorage.removeItem(`ibg-game-init-${gameId}`)
        const { roleData, players: playerNames, roomId, ownerId } = JSON.parse(stored) as {
          roleData?: { role: string; word: string | null }
          players?: string[]
          mayor?: string
          roomId?: string
          ownerId?: string
        }
        if (roomId) roomIdRef.current = roomId
        if (ownerId && user) {
          initial.isHost = ownerId === user.id
        }
        if (roleData) {
          initial.my_role = roleData.role
          initial.my_word = roleData.word || undefined
        }
        if (playerNames) {
          initial.players = playerNames.map((username) => ({
            id: username,
            username,
            is_alive: true,
          }))
        }
      }
    } catch {}
    return initial
  })
  const [selectedVote, setSelectedVote] = useState<string | null>(null)
  const [hasVoted, setHasVoted] = useState(false)
  const [isLoadingState, setIsLoadingState] = useState(!gameState.my_role)
  const [loadingTimedOut, setLoadingTimedOut] = useState(false)
  const lastServerRoundRef = useRef(0)
  const [descriptionInput, setDescriptionInput] = useState("")
  const [descriptionError, setDescriptionError] = useState("")
  const [isSubmittingDescription, setIsSubmittingDescription] = useState(false)
  const [showVotingTransition, setShowVotingTransition] = useState(false)

  // Always request authoritative state from server on mount
  useEffect(() => {
    if (!isConnected || !user) return
    emit("get_undercover_state", { game_id: gameId, user_id: user.id })

    // Retry if no state received within 2s (socket may have missed the initial emit)
    const retryTimer = setTimeout(() => {
      if (gameState.players.length === 0 && isConnected) {
        emit("get_undercover_state", { game_id: gameId, user_id: user.id })
      }
    }, 2000)
    return () => clearTimeout(retryTimer)
  }, [isConnected, user, emit, gameId])

  useEffect(() => {
    if (!isConnected) return

    const offRoleAssigned = on("role_assigned", (data: unknown) => {
      try {
        const roleData = data as { role: string; word: string | null }
        setGameState((prev) => ({
          ...prev,
          my_role: roleData.role,
          my_word: roleData.word || undefined,
          phase: "role_reveal",
        }))
        setIsLoadingState(false)
      } catch {
        toast.error(t("common.error"))
      }
    })

    // vote_casted: your vote was recorded
    const offVoteCasted = on("vote_casted", () => {
      toast.success(t("toast.voteCasted"))
    })

    // waiting_other_votes: shows who has voted
    const offWaitingVotes = on("waiting_other_votes", (data: unknown) => {
      try {
        const d = data as { message: string; players_that_voted: { username: string; user_id: string }[] }
        setGameState((prev) => ({
          ...prev,
          votedPlayers: d.players_that_voted.map((p) => p.user_id),
        }))
      } catch {
        toast.error(t("common.error"))
      }
    })

    // you_died: you were eliminated
    const offYouDied = on("you_died", (data: unknown) => {
      try {
        const d = data as { message: string }
        toast.error(d.message)
        setGameState((prev) => ({
          ...prev,
          players: prev.players.map((p) =>
            p.id === user?.id ? { ...p, is_alive: false } : p,
          ),
        }))
      } catch {
        toast.error(t("common.error"))
      }
    })

    // turn_started: new turn with description order
    const offTurnStarted = on("turn_started", (data: unknown) => {
      try {
        const d = data as {
          message: string
          description_order: DescriptionOrderEntry[]
          current_describer_index: number
          phase: string
        }
        setGameState((prev) => ({
          ...prev,
          phase: "describing",
          round: prev.round + 1,
          votedPlayers: [],
          eliminated_player_username: undefined,
          eliminated_player_role: undefined,
          descriptionOrder: d.description_order,
          currentDescriberIndex: d.current_describer_index,
          descriptions: {},
        }))
        setHasVoted(false)
        setSelectedVote(null)
        setDescriptionInput("")
        setDescriptionError("")
        setIsSubmittingDescription(false)
      } catch {
        toast.error(t("common.error"))
      }
    })

    // description_submitted: a player submitted their word
    const offDescriptionSubmitted = on("description_submitted", (data: unknown) => {
      try {
        const d = data as {
          user_id: string
          username: string
          word: string
          next_describer_id: string | null
          next_describer_username: string | null
        }
        if (d.user_id === user?.id) {
          toast.success(t("game.undercover.descriptionSubmitted"))
        }
        setGameState((prev) => ({
          ...prev,
          descriptions: { ...prev.descriptions, [d.user_id]: d.word },
          currentDescriberIndex: prev.currentDescriberIndex + 1,
        }))
        setIsSubmittingDescription(false)
        setDescriptionInput("")
        setDescriptionError("")
      } catch {
        toast.error(t("common.error"))
      }
    })

    // descriptions_complete: all descriptions submitted, transition to voting
    const offDescriptionsComplete = on("descriptions_complete", (data: unknown) => {
      try {
        const d = data as { descriptions: Record<string, string> }
        setShowVotingTransition(true)
        setTimeout(() => {
          setGameState((prev) => ({
            ...prev,
            phase: "playing",
            descriptions: d.descriptions,
          }))
          setShowVotingTransition(false)
        }, 2500)
      } catch {
        toast.error(t("common.error"))
      }
    })

    // your_turn_to_describe: it's my turn
    const offYourTurn = on("your_turn_to_describe", () => {
      toast.info(t("game.undercover.yourTurn"))
    })

    // notification: legacy turn updates from backend (backward compat)
    const offNotification = on("notification", (data: unknown) => {
      try {
        const d = data as { message: string }
        toast.info(d.message)
        setGameState((prev) => ({
          ...prev,
          phase: "describing",
          round: prev.round + 1,
          votedPlayers: [],
          eliminated_player_username: undefined,
          eliminated_player_role: undefined,
        }))
        setHasVoted(false)
        setSelectedVote(null)
      } catch {
        toast.error(t("common.error"))
      }
    })

    const offPlayerEliminated = on("player_eliminated", (data: unknown) => {
      try {
        toast.warning(t("toast.playerEliminated"))
        const d = data as {
          message: string
          eliminated_player_role: string
          eliminated_player_username: string
          eliminated_player_user_id: string
        }
        setGameState((prev) => ({
          ...prev,
          phase: "elimination",
          eliminated_player_username: d.eliminated_player_username,
          eliminated_player_role: d.eliminated_player_role,
          players: prev.players.map((p) =>
            p.id === d.eliminated_player_user_id ? { ...p, is_alive: false } : p,
          ),
        }))
      } catch {
        toast.error(t("common.error"))
      }
    })

    const offGameOver = on("game_over", (data: unknown) => {
      try {
        toast.success(t("toast.gameOver"))
        const d = data as { data: string; winner: string }
        setGameState((prev) => ({
          ...prev,
          phase: "game_over",
          winner: d.winner,
        }))
      } catch {
        toast.error(t("common.error"))
      }
    })

    // undercover_game_state: full state recovery for reconnecting players
    const offUndercoverState = on("undercover_game_state", (data: unknown) => {
      try {
        const d = data as {
          my_role: string
          my_word: string
          is_alive: boolean
          players: { user_id: string; username: string; is_alive: boolean; is_mayor?: boolean }[]
          eliminated_players: { user_id: string; username: string; role: string }[]
          turn_number: number
          has_voted: boolean
          room_id?: string
          votes?: Record<string, string>
          winner?: string | null
          turn_phase?: string
          description_order?: DescriptionOrderEntry[]
          current_describer_index?: number
          descriptions?: Record<string, string>
        }
        if (d.room_id) roomIdRef.current = d.room_id
        const votedPlayerIds = d.votes ? Object.keys(d.votes) : []

        // Determine phase based on server state
        let phase: GameState["phase"]
        if (d.winner) {
          phase = "game_over"
        } else if (d.turn_phase === "describing") {
          phase = "describing"
        } else if (d.turn_number > 0) {
          phase = "playing"
        } else {
          phase = "role_reveal"
        }

        // Only reset vote state when the round actually changes
        const roundChanged = d.turn_number !== lastServerRoundRef.current
        lastServerRoundRef.current = d.turn_number

        setGameState((prev) => ({
          ...prev,
          my_role: d.my_role,
          my_word: d.my_word,
          round: d.turn_number,
          phase,
          winner: d.winner || prev.winner,
          votedPlayers: votedPlayerIds,
          players: d.players.map((p) => ({
            id: p.user_id,
            username: p.username,
            is_alive: p.is_alive,
            is_mayor: p.is_mayor,
          })),
          descriptionOrder: d.description_order || [],
          currentDescriberIndex: d.current_describer_index ?? 0,
          descriptions: d.descriptions || {},
        }))
        setIsLoadingState(false)

        if (roundChanged || d.winner) {
          setHasVoted(d.has_voted)
          setSelectedVote(null)
        } else if (d.has_voted) {
          setHasVoted(true)
        }
      } catch {
        toast.error(t("common.error"))
        setIsLoadingState(false)
      }
    })

    // game_cancelled: not enough players, navigate back
    const offGameCancelled = on("game_cancelled", (data: unknown) => {
      toast.error(t("toast.gameCancelled"))
      const payload = data as { message: string }
      setCancelMessage(payload.message || "Game cancelled: not enough players.")
      setTimeout(() => {
        navigate({ to: "/" })
      }, 3000)
    })

    // error: catch backend errors (e.g. game not found)
    const offError = on("error", (data: unknown) => {
      const payload = data as { name?: string; frontend_message?: string; message?: string }
      toast.error(payload.frontend_message || payload.message || "An error occurred")
      setIsLoadingState(false)
      setIsSubmittingDescription(false)

      // Fatal game errors — game no longer exists or player was removed
      if (payload.name === "GameNotFoundError" || payload.name === "PlayerRemovedFromGameError") {
        setTimeout(() => navigate({ to: "/" }), 2000)
      }
    })

    return () => {
      offRoleAssigned()
      offVoteCasted()
      offWaitingVotes()
      offYouDied()
      offTurnStarted()
      offDescriptionSubmitted()
      offDescriptionsComplete()
      offYourTurn()
      offNotification()
      offPlayerEliminated()
      offGameOver()
      offUndercoverState()
      offGameCancelled()
      offError()
    }
  }, [isConnected, on, navigate, user, t])

  // Loading timeout: if state never arrives after 15s, show error
  useEffect(() => {
    if (!isLoadingState) return
    const timer = setTimeout(() => {
      setLoadingTimedOut(true)
    }, 15000)
    return () => clearTimeout(timer)
  }, [isLoadingState])

  const handleSelectPlayer = useCallback(
    (playerId: string) => {
      if (hasVoted) return
      setSelectedVote((prev) => (prev === playerId ? null : playerId))
    },
    [hasVoted],
  )

  const handleConfirmVote = useCallback(() => {
    if (!selectedVote || hasVoted || !user) return
    const votedPlayer = gameState.players.find((p) => p.id === selectedVote)
    setHasVoted(true)
    if (votedPlayer) {
      toast.info(t("game.undercover.votedFor", { username: votedPlayer.username }))
    }
    emit("vote_for_a_player", {
      room_id: roomIdRef.current,
      game_id: gameId,
      user_id: user.id,
      voted_user_id: selectedVote,
    })
  }, [selectedVote, hasVoted, emit, gameId, user, gameState.players, t])

  const handleSubmitDescription = useCallback(() => {
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
    emit("submit_description_event", {
      room_id: roomIdRef.current,
      game_id: gameId,
      user_id: user.id,
      word,
    })
  }, [descriptionInput, user, emit, gameId, isSubmittingDescription, t])

  const handleNextRound = useCallback(() => {
    emit("start_new_turn_event", {
      room_id: roomIdRef.current,
      game_id: gameId,
    })
  }, [emit, gameId])

  const handleDismissRole = useCallback(() => {
    setGameState((prev) => ({ ...prev, phase: "describing" }))
  }, [])

  const handleLeaveRoom = useCallback(() => {
    if (!user || !roomIdRef.current) {
      navigate({ to: "/rooms" })
      return
    }
    emit("leave_room", {
      user_id: user.id,
      room_id: roomIdRef.current,
      username: user.username,
    })
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }, [user, emit, navigate, t])

  const myPlayer = gameState.players.find((p) => p.id === user?.id)
  const isAlive = myPlayer?.is_alive !== false

  // Check if it's my turn to describe
  const isMyTurnToDescribe =
    gameState.phase === "describing" &&
    gameState.descriptionOrder.length > 0 &&
    gameState.currentDescriberIndex < gameState.descriptionOrder.length &&
    gameState.descriptionOrder[gameState.currentDescriberIndex]?.user_id === user?.id

  // Current describer info
  const currentDescriber =
    gameState.descriptionOrder.length > 0 && gameState.currentDescriberIndex < gameState.descriptionOrder.length
      ? gameState.descriptionOrder[gameState.currentDescriberIndex]
      : null

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
      {isLoadingState && !gameState.my_role && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          {loadingTimedOut ? (
            <>
              <p className="text-destructive font-semibold mb-2">{t("common.error")}</p>
              <p className="text-muted-foreground mb-4">Failed to load game state. The game may no longer exist.</p>
              <button
                type="button"
                onClick={() => navigate({ to: "/" })}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                {t("common.goHome")}
              </button>
            </>
          ) : (
            <>
              <Loader2 className="h-10 w-10 mx-auto animate-spin text-primary mb-4" />
              <p className="text-muted-foreground">{t("common.loading")}</p>
            </>
          )}
        </div>
      )}

      {/* Role Reveal */}
      {gameState.phase === "role_reveal" && gameState.my_role && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          <Shield className="h-12 w-12 mx-auto text-primary mb-4" />
          <h2 className="text-xl font-bold mb-2">{t("game.yourRole")}</h2>
          <div className="inline-block rounded-full bg-primary/10 px-6 py-2 text-lg font-bold text-primary">
            {gameState.my_role === "civilian"
              ? t("games.undercover.roles.civilian")
              : gameState.my_role === "undercover"
                ? t("games.undercover.roles.undercover")
                : t("games.undercover.roles.mrWhite")}
          </div>
          {gameState.my_word && (
            <div className="mt-4">
              <p className="text-sm text-muted-foreground">{t("game.yourWord")}</p>
              <p className="text-2xl font-bold mt-1">{gameState.my_word}</p>
            </div>
          )}
          <button
            type="button"
            onClick={handleDismissRole}
            className="mt-6 rounded-md bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {t("game.undercover.iUnderstand")}
          </button>
        </div>
      )}

      {/* Describing Phase */}
      {gameState.phase === "describing" && (
        <div className="mb-8">
          {/* Role/Word reminder */}
          {gameState.my_role && gameState.my_role !== "mr_white" && gameState.my_word && (
            <div className="rounded-lg bg-primary/5 border border-primary/20 p-3 mb-4 text-center">
              <span className="text-sm text-muted-foreground">{t("game.undercover.yourWordReminder")}:</span>{" "}
              <span className="font-bold text-primary">{gameState.my_word}</span>
            </div>
          )}

          <h2 className="text-xl font-bold text-center mb-4">{t("game.undercover.describeYourWord")}</h2>

          {/* Description Order */}
          {gameState.descriptionOrder.length > 0 && (
            <div className="rounded-lg border bg-card p-4 mb-4">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                {t("game.undercover.descriptionOrder")}
              </h3>
              <div className="space-y-1.5">
                {gameState.descriptionOrder.map((entry, idx) => {
                  const hasDescribed = !!gameState.descriptions[entry.user_id]
                  const isCurrent = idx === gameState.currentDescriberIndex && !hasDescribed
                  return (
                    <div
                      key={entry.user_id}
                      className={cn(
                        "flex items-center justify-between rounded-md px-3 py-1.5 text-sm",
                        isCurrent && "bg-primary/10 border border-primary/30",
                        hasDescribed && "opacity-60",
                      )}
                    >
                      <span className={cn("font-medium", isCurrent && "text-primary")}>
                        {idx + 1}. {entry.username}
                        {entry.user_id === user?.id && " (you)"}
                      </span>
                      {hasDescribed && (
                        <span className="text-xs bg-muted rounded-full px-2 py-0.5">
                          {gameState.descriptions[entry.user_id]}
                        </span>
                      )}
                      {isCurrent && !hasDescribed && (
                        <span className="text-xs text-primary font-semibold">
                          {entry.user_id === user?.id ? t("game.undercover.yourTurn") : "..."}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Description Input (my turn) */}
          {isMyTurnToDescribe && isAlive && (
            <div className="rounded-lg border bg-card p-4 mb-4">
              <label htmlFor="description-input" className="block text-sm font-medium mb-2">
                {t("game.undercover.describeYourWord")}
              </label>
              <div className="flex gap-2">
                <input
                  id="description-input"
                  type="text"
                  value={descriptionInput}
                  onChange={(e) => {
                    setDescriptionInput(e.target.value)
                    setDescriptionError("")
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSubmitDescription()
                  }}
                  placeholder={t("game.undercover.describeYourWord")}
                  maxLength={50}
                  disabled={isSubmittingDescription}
                  className="flex-1 rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <button
                  type="button"
                  onClick={handleSubmitDescription}
                  disabled={isSubmittingDescription || !descriptionInput.trim()}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {isSubmittingDescription ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    t("game.undercover.submitDescription")
                  )}
                </button>
              </div>
              {descriptionError && (
                <p className="text-xs text-destructive mt-1">{descriptionError}</p>
              )}
            </div>
          )}

          {/* Waiting message (not my turn) */}
          {!isMyTurnToDescribe && currentDescriber && (
            <div className="rounded-lg bg-muted/50 p-3 mb-4 text-center">
              <p className="text-sm text-muted-foreground">
                {t("game.undercover.waitingForDescription", { username: currentDescriber.username })}
              </p>
            </div>
          )}

          {/* All descriptions done but event not received yet */}
          {gameState.currentDescriberIndex >= gameState.descriptionOrder.length && gameState.descriptionOrder.length > 0 && (
            <div className="rounded-lg bg-muted/50 p-3 mb-4 text-center">
              <Loader2 className="h-4 w-4 inline animate-spin mr-2" />
              <span className="text-sm text-muted-foreground">{t("common.loading")}</span>
            </div>
          )}
        </div>
      )}

      {/* Playing Phase (Voting) */}
      {gameState.phase === "playing" && (
        <div className="mb-8">
          {/* Role/Word reminder */}
          {gameState.my_role && gameState.my_role !== "mr_white" && gameState.my_word && (
            <div className="rounded-lg bg-primary/5 border border-primary/20 p-3 mb-4 text-center">
              <span className="text-sm text-muted-foreground">{t("game.undercover.yourWordReminder")}:</span>{" "}
              <span className="font-bold text-primary">{gameState.my_word}</span>
            </div>
          )}

          {/* Show descriptions from the describing phase */}
          {Object.keys(gameState.descriptions).length > 0 && (
            <div className="rounded-lg border bg-card p-4 mb-4">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                {t("game.undercover.descriptionOrder")}
              </h3>
              <div className="flex flex-wrap gap-2">
                {gameState.descriptionOrder.map((entry) => {
                  const word = gameState.descriptions[entry.user_id]
                  if (!word) return null
                  return (
                    <div key={entry.user_id} className="rounded-md bg-muted px-3 py-1.5 text-sm">
                      <span className="font-medium">{entry.username}:</span>{" "}
                      <span className="text-primary font-semibold">{word}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {!isAlive && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 mb-4 text-center">
              <Skull className="h-5 w-5 inline mr-2 text-destructive" />
              <span className="text-sm font-medium text-destructive">{t("game.undercover.youAreDead")}</span>
            </div>
          )}

          <h2 className="text-xl font-bold text-center mb-2">{t("game.undercover.discussAndVote")}</h2>
          <p className="text-sm text-muted-foreground text-center mb-4">{t("game.undercover.selectPlayerToVote")}</p>

          {hasVoted && (
            <div className="rounded-lg bg-muted/50 p-3 mb-4 text-center">
              <p className="text-sm text-muted-foreground">{t("game.undercover.waitingForVotes")}</p>
            </div>
          )}

          {isAlive && <div className="grid gap-3 sm:grid-cols-2">
            {gameState.players
              .filter((p) => p.is_alive && p.id !== user?.id)
              .map((player) => {
                const hasPlayerVoted = gameState.votedPlayers.includes(player.id)
                return (
                  <button
                    key={player.id}
                    type="button"
                    onClick={() => handleSelectPlayer(player.id)}
                    disabled={hasVoted || !isAlive}
                    className={cn(
                      "flex items-center gap-3 rounded-lg border p-4 transition-colors",
                      selectedVote === player.id
                        ? "border-primary bg-primary/10 ring-2 ring-primary/30"
                        : "hover:border-primary/50",
                      (hasVoted || !isAlive) && "opacity-50 cursor-not-allowed",
                    )}
                  >
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                      <User className="h-5 w-5" />
                    </div>
                    <div className="text-left flex-1">
                      <div className="font-medium flex items-center gap-2">
                        {player.username}
                        {player.is_mayor && (
                          <Crown className="h-3.5 w-3.5 text-yellow-500" />
                        )}
                      </div>
                      {selectedVote === player.id && !hasVoted && (
                        <div className="flex items-center gap-1 text-xs text-primary">
                          <ThumbsUp className="h-3 w-3" />
                          Selected
                        </div>
                      )}
                      {hasVoted && selectedVote === player.id && (
                        <div className="flex items-center gap-1 text-xs text-primary">
                          <ThumbsUp className="h-3 w-3" />
                          {t("game.undercover.voted")}
                        </div>
                      )}
                    </div>
                    {hasPlayerVoted && (
                      <span className="text-xs bg-muted rounded-full px-2 py-0.5 text-muted-foreground">
                        {t("game.undercover.voted")}
                      </span>
                    )}
                  </button>
                )
              })}
          </div>}

          {/* Vote Confirmation Button */}
          {isAlive && !hasVoted && (
            <button
              type="button"
              onClick={handleConfirmVote}
              disabled={!selectedVote}
              className={cn(
                "mt-4 w-full rounded-md px-6 py-3 text-sm font-semibold transition-colors",
                selectedVote
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed",
              )}
            >
              {t("game.undercover.voteToEliminate")}
            </button>
          )}
        </div>
      )}

      {/* Elimination */}
      {gameState.phase === "elimination" && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          <Skull className="h-12 w-12 mx-auto text-destructive mb-4" />
          <h2 className="text-xl font-bold">{t("game.eliminated")}</h2>
          {gameState.eliminated_player_username && (
            <p className="text-lg mt-2">{gameState.eliminated_player_username}</p>
          )}
          {gameState.eliminated_player_role && (
            <p className="text-sm text-muted-foreground mt-1">
              {t("game.yourRole")}: {gameState.eliminated_player_role}
            </p>
          )}
          <button
            type="button"
            onClick={handleNextRound}
            className="mt-6 rounded-md bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {t("game.undercover.nextRound")}
          </button>
        </div>
      )}

      {/* Game Over */}
      {gameState.phase === "game_over" && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          <h2 className="text-3xl font-bold">{t("game.gameOver")}</h2>
          <p className="text-xl mt-4">
            {t("game.winner")}: {gameState.winner}
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            {roomIdRef.current && (
              <button
                type="button"
                onClick={() => navigate({ to: "/rooms/$roomId", params: { roomId: roomIdRef.current! } })}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                {t("game.backToRoom")}
              </button>
            )}
            <button
              type="button"
              onClick={handleLeaveRoom}
              className="inline-flex items-center gap-2 rounded-md border px-6 py-2.5 text-sm font-semibold text-muted-foreground hover:bg-muted transition-colors"
            >
              <LogOut className="h-4 w-4" />
              {t("room.leave")}
            </button>
          </div>
        </div>
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
