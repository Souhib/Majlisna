import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Loader2, LogOut, Shield, Skull, ThumbsUp, User } from "lucide-react"
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
  role?: string
  word?: string
  vote_count?: number
}

interface GameState {
  players: UndercoverPlayer[]
  phase: "role_reveal" | "discussion" | "voting" | "elimination" | "game_over"
  round: number
  my_role?: string
  my_word?: string
  eliminated_player?: UndercoverPlayer
  winner?: string
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
    }
    // Read initial state passed from lobby via sessionStorage
    try {
      const stored = sessionStorage.getItem(`ibg-game-init-${gameId}`)
      if (stored) {
        sessionStorage.removeItem(`ibg-game-init-${gameId}`)
        const { roleData, players: playerNames, roomId } = JSON.parse(stored) as {
          roleData?: { role: string; word: string | null }
          players?: string[]
          mayor?: string
          roomId?: string
        }
        if (roomId) roomIdRef.current = roomId
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

  // Always request authoritative state from server on mount
  useEffect(() => {
    if (!isConnected || !user) return
    emit("get_undercover_state", { game_id: gameId, user_id: user.id })
  }, [isConnected, user, emit, gameId])

  useEffect(() => {
    if (!isConnected) return

    const offRoleAssigned = on("role_assigned", (data: unknown) => {
      const roleData = data as { role: string; word: string | null }
      setGameState((prev) => ({
        ...prev,
        my_role: roleData.role,
        my_word: roleData.word || undefined,
        phase: "role_reveal",
      }))
      setIsLoadingState(false)
    })

    const offVotingStarted = on("voting_started", () => {
      toast.info(t("toast.votingStarted"))
      setGameState((prev) => ({ ...prev, phase: "voting" }))
      setSelectedVote(null)
      setHasVoted(false)
    })

    const offPlayerEliminated = on("player_eliminated", (data: unknown) => {
      toast.warning(t("toast.playerEliminated"))
      const elimData = data as { player: UndercoverPlayer }
      setGameState((prev) => ({
        ...prev,
        phase: "elimination",
        eliminated_player: elimData.player,
        players: prev.players.map((p) =>
          p.id === elimData.player.id ? { ...p, is_alive: false } : p,
        ),
      }))
    })

    const offGameOver = on("game_over", (data: unknown) => {
      toast.success(t("toast.gameOver"))
      const gameOverData = data as { winner: string; players: UndercoverPlayer[] }
      setGameState((prev) => ({
        ...prev,
        phase: "game_over",
        winner: gameOverData.winner,
        players: gameOverData.players || prev.players,
      }))
    })

    const offGameState = on("game_state", (data: unknown) => {
      const state = data as Partial<GameState>
      setGameState((prev) => ({ ...prev, ...state }))
    })

    // undercover_game_state: full state recovery for reconnecting players
    const offUndercoverState = on("undercover_game_state", (data: unknown) => {
      const d = data as {
        my_role: string
        my_word: string
        is_alive: boolean
        players: { user_id: string; username: string; is_alive: boolean }[]
        eliminated_players: { user_id: string; username: string; role: string }[]
        turn_number: number
        has_voted: boolean
      }
      setGameState((prev) => ({
        ...prev,
        my_role: d.my_role,
        my_word: d.my_word,
        round: d.turn_number,
        players: d.players.map((p) => ({
          id: p.user_id,
          username: p.username,
          is_alive: p.is_alive,
        })),
      }))
      setIsLoadingState(false)
      if (d.has_voted) {
        setHasVoted(true)
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
      const payload = data as { frontend_message?: string; message?: string }
      toast.error(payload.frontend_message || payload.message || "An error occurred")
      setIsLoadingState(false)
    })

    return () => {
      offRoleAssigned()
      offVotingStarted()
      offPlayerEliminated()
      offGameOver()
      offGameState()
      offUndercoverState()
      offGameCancelled()
      offError()
    }
  }, [isConnected, on, navigate])

  // Loading timeout: if state never arrives after 15s, show error
  useEffect(() => {
    if (!isLoadingState) return
    const timer = setTimeout(() => {
      setLoadingTimedOut(true)
    }, 15000)
    return () => clearTimeout(timer)
  }, [isLoadingState])

  const handleVote = useCallback(
    (playerId: string) => {
      if (hasVoted) return
      setSelectedVote(playerId)
      emit("vote", { game_id: gameId, voted_for: playerId })
      setHasVoted(true)
      toast.success(t("toast.voteCasted"))
    },
    [hasVoted, emit, gameId, t],
  )

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
    navigate({ to: "/rooms" })
  }, [user, emit, navigate])

  const myPlayer = gameState.players.find((p) => p.id === user?.id)
  const isAlive = myPlayer?.is_alive !== false

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
        </div>
      )}

      {/* Voting Phase */}
      {gameState.phase === "voting" && (
        <div className="mb-8">
          <h2 className="text-xl font-bold text-center mb-4">{t("game.vote")}</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {gameState.players
              .filter((p) => p.is_alive && p.id !== user?.id)
              .map((player) => (
                <button
                  key={player.id}
                  type="button"
                  onClick={() => handleVote(player.id)}
                  disabled={hasVoted || !isAlive}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border p-4 transition-colors",
                    selectedVote === player.id
                      ? "border-primary bg-primary/5"
                      : "hover:border-primary/50",
                    (hasVoted || !isAlive) && "opacity-50 cursor-not-allowed",
                  )}
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                    <User className="h-5 w-5" />
                  </div>
                  <div className="text-left">
                    <div className="font-medium">{player.username}</div>
                    {selectedVote === player.id && (
                      <div className="flex items-center gap-1 text-xs text-primary">
                        <ThumbsUp className="h-3 w-3" />
                        Voted
                      </div>
                    )}
                  </div>
                </button>
              ))}
          </div>
        </div>
      )}

      {/* Elimination */}
      {gameState.phase === "elimination" && gameState.eliminated_player && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          <Skull className="h-12 w-12 mx-auto text-destructive mb-4" />
          <h2 className="text-xl font-bold">{t("game.eliminated")}</h2>
          <p className="text-lg mt-2">{gameState.eliminated_player.username}</p>
          {gameState.eliminated_player.role && (
            <p className="text-sm text-muted-foreground mt-1">
              Role: {gameState.eliminated_player.role}
            </p>
          )}
        </div>
      )}

      {/* Game Over */}
      {gameState.phase === "game_over" && (
        <div className="rounded-xl border bg-card p-8 text-center mb-8">
          <h2 className="text-3xl font-bold">{t("game.gameOver")}</h2>
          <p className="text-xl mt-4">
            {t("game.winner")}: {gameState.winner}
          </p>
          <button
            type="button"
            onClick={handleLeaveRoom}
            className="mt-6 inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            {t("room.leave")}
          </button>
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
              <span className="text-sm">{player.username}</span>
              <span className="text-xs text-muted-foreground">
                {player.is_alive ? t("game.alive") : t("game.eliminated")}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
