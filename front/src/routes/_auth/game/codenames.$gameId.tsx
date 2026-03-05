import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Users } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import apiClient, { getApiErrorMessage } from "@/api/client"
import { CluePanel } from "@/components/games/codenames/CluePanel"
import { GameBoard } from "@/components/games/codenames/GameBoard"
import { GameOverScreen } from "@/components/games/codenames/GameOverScreen"
import { ScorePanel } from "@/components/games/codenames/ScorePanel"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"

interface CodenamesCard {
  word: string
  card_type: "red" | "blue" | "neutral" | "assassin" | null
  revealed: boolean
}

interface CodenamesTurn {
  team: "red" | "blue"
  clue_word: string | null
  clue_number: number
  guesses_made: number
  max_guesses: number | null
}

interface CodenamesPlayer {
  user_id: string
  username: string
  team: string
  role: string
}

interface CodenamesGameState {
  board: CodenamesCard[]
  current_team: "red" | "blue"
  current_turn: CodenamesTurn | null
  my_team: "red" | "blue"
  my_role: "spymaster" | "operative"
  red_remaining: number
  blue_remaining: number
  status: "waiting" | "in_progress" | "finished"
  winner: "red" | "blue" | null
  players: CodenamesPlayer[]
  room_id?: string
}

export const Route = createFileRoute("/_auth/game/codenames/$gameId")({
  component: CodenamesGamePage,
})

function CodenamesGamePage() {
  const { gameId } = Route.useParams()
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const roomIdRef = useRef<string | null>(null)
  const [clueWord, setClueWord] = useState("")
  const [clueNumber, setClueNumber] = useState(1)
  const [isSubmittingClue, setIsSubmittingClue] = useState(false)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)

  // Poll game state via REST every 2 seconds
  const { data: serverState, isLoading, error: queryError } = useQuery({
    queryKey: ["codenames", gameId],
    queryFn: async () => {
      const res = await apiClient({
        method: "GET",
        url: `/api/v1/codenames/games/${gameId}/board`,
      })
      return res.data as {
        game_id: string
        room_id?: string
        team: "red" | "blue"
        role: "spymaster" | "operative"
        board: CodenamesCard[]
        current_team: "red" | "blue"
        red_remaining: number
        blue_remaining: number
        status: string
        current_turn: CodenamesTurn | null
        winner: "red" | "blue" | null
        players?: CodenamesPlayer[]
      }
    },
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
    enabled: !!user,
  })

  // Derive game state from server data
  const gameState = useMemo<CodenamesGameState | null>(() => {
    if (!serverState) return null
    if (serverState.room_id) roomIdRef.current = serverState.room_id
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

  // Handle query error (game not found / cancelled)
  useEffect(() => {
    if (queryError) {
      const errMsg = getApiErrorMessage(queryError, "Game not found")
      if (errMsg.includes("not found") || errMsg.includes("cancelled") || errMsg.includes("removed")) {
        setCancelMessage(errMsg)
        setTimeout(() => navigate({ to: "/" }), 3000)
      }
    }
  }, [queryError, navigate])

  const handleGiveClue = useCallback(async () => {
    if (!clueWord.trim() || isSubmittingClue) return
    setIsSubmittingClue(true)
    try {
      await apiClient({
        method: "POST",
        url: `/api/v1/codenames/games/${gameId}/clue`,
        data: { clue_word: clueWord.trim(), clue_number: clueNumber },
      })
      setClueWord("")
      setClueNumber(1)
      queryClient.invalidateQueries({ queryKey: ["codenames", gameId] })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to give clue"))
    } finally {
      setIsSubmittingClue(false)
    }
  }, [gameId, clueWord, clueNumber, isSubmittingClue, queryClient])

  const handleGuessCard = useCallback(
    async (index: number) => {
      try {
        await apiClient({
          method: "POST",
          url: `/api/v1/codenames/games/${gameId}/guess`,
          data: { card_index: index },
        })
        queryClient.invalidateQueries({ queryKey: ["codenames", gameId] })
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to guess card"))
      }
    },
    [gameId, queryClient],
  )

  const handleEndTurn = useCallback(async () => {
    try {
      await apiClient({
        method: "POST",
        url: `/api/v1/codenames/games/${gameId}/end-turn`,
      })
      queryClient.invalidateQueries({ queryKey: ["codenames", gameId] })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to end turn"))
    }
  }, [gameId, queryClient])

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

  if (cancelMessage) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="rounded-xl border bg-destructive/10 p-8 text-center">
          <h2 className="text-xl font-bold text-destructive mb-2">{t("game.gameOver")}</h2>
          <p className="text-muted-foreground">{cancelMessage}</p>
          <p className="text-sm text-muted-foreground mt-2">Redirecting...</p>
        </div>
      </div>
    )
  }

  if (!gameState) {
    if (isLoading) {
      return (
        <div className="flex min-h-[60vh] items-center justify-center">
          <p className="text-muted-foreground">{t("common.loading")}</p>
        </div>
      )
    }
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="rounded-xl border bg-destructive/10 p-8 text-center">
          <h2 className="text-xl font-bold text-destructive mb-2">{t("common.error")}</h2>
          <p className="text-muted-foreground">Failed to load game state. The game may no longer exist.</p>
          <button
            type="button"
            onClick={() => navigate({ to: "/" })}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            {t("common.goHome")}
          </button>
        </div>
      </div>
    )
  }

  const isMyTurn = gameState.current_team === gameState.my_team
  const isSpymaster = gameState.my_role === "spymaster"
  const canGiveClue = isMyTurn && isSpymaster && !gameState.current_turn?.clue_word
  const canGuess = isMyTurn && !isSpymaster && !!gameState.current_turn?.clue_word

  const redPlayers = gameState.players.filter((p) => p.team === "red")
  const bluePlayers = gameState.players.filter((p) => p.team === "blue")

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      {/* Header + Score + Turn Info */}
      <ScorePanel
        redRemaining={gameState.red_remaining}
        blueRemaining={gameState.blue_remaining}
        currentTeam={gameState.current_team}
        currentTurn={gameState.current_turn}
        isMyTurn={isMyTurn}
        isFinished={gameState.status === "finished"}
      />

      {/* Board */}
      <GameBoard
        board={gameState.board}
        isSpymaster={isSpymaster}
        canGuess={canGuess}
        isFinished={gameState.status === "finished"}
        onGuessCard={handleGuessCard}
      />

      {/* Spymaster Clue Input */}
      {canGiveClue && (
        <CluePanel
          clueWord={clueWord}
          clueNumber={clueNumber}
          isSubmitting={isSubmittingClue}
          onClueWordChange={setClueWord}
          onClueNumberChange={setClueNumber}
          onSubmit={handleGiveClue}
        />
      )}

      {/* End Turn Button */}
      {canGuess && (
        <button
          type="button"
          onClick={handleEndTurn}
          className="w-full rounded-md border border-primary px-4 py-2 text-sm font-medium text-primary hover:bg-primary/5 transition-colors"
        >
          {t("game.codenames.endTurn")}
        </button>
      )}

      {/* Game Over */}
      {gameState.status === "finished" && gameState.winner && (
        <GameOverScreen
          winner={gameState.winner}
          roomId={roomIdRef.current}
          onBackToRoom={handleBackToRoom}
          onLeaveRoom={handleLeaveRoom}
        />
      )}

      {/* Player List */}
      {gameState.players.length > 0 && (
        <div className="mt-6 rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">{t("game.codenames.players")}</h3>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {/* Red Team */}
            <div>
              <h4 className="text-xs font-semibold text-red-600 dark:text-red-400 mb-2">
                {t("games.codenames.teams.red")}
              </h4>
              <div className="space-y-1">
                {redPlayers.map((p) => (
                  <div key={p.user_id} className="flex items-center justify-between rounded px-2 py-1 bg-red-50 dark:bg-red-950/20 text-sm">
                    <span>{p.username}</span>
                    <span className="text-xs text-muted-foreground">
                      {p.role === "spymaster" ? t("games.codenames.roles.spymaster") : t("games.codenames.roles.operative")}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            {/* Blue Team */}
            <div>
              <h4 className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-2">
                {t("games.codenames.teams.blue")}
              </h4>
              <div className="space-y-1">
                {bluePlayers.map((p) => (
                  <div key={p.user_id} className="flex items-center justify-between rounded px-2 py-1 bg-blue-50 dark:bg-blue-950/20 text-sm">
                    <span>{p.username}</span>
                    <span className="text-xs text-muted-foreground">
                      {p.role === "spymaster" ? t("games.codenames.roles.spymaster") : t("games.codenames.roles.operative")}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* My Info */}
      <div className="mt-6 rounded-lg bg-muted/50 p-3 text-center text-sm text-muted-foreground">
        {t("game.codenames.youAre")}{" "}
        <span
          className={cn(
            "font-semibold",
            gameState.my_team === "red" ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400",
          )}
        >
          {gameState.my_team === "red"
            ? t("games.codenames.teams.red")
            : t("games.codenames.teams.blue")}
        </span>{" "}
        <span className="font-semibold">
          {gameState.my_role === "spymaster"
            ? t("games.codenames.roles.spymaster")
            : t("games.codenames.roles.operative")}
        </span>
      </div>
    </div>
  )
}
