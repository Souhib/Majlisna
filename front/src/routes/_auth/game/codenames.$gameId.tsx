import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { LogOut, Users } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useSocket } from "@/hooks/use-socket"
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
}

export const Route = createFileRoute("/_auth/game/codenames/$gameId")({
  component: CodenamesGamePage,
})

function CodenamesGamePage() {
  const { gameId } = Route.useParams()
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { emit, on, isConnected } = useSocket()
  const roomIdRef = useRef<string | null>(
    sessionStorage.getItem(`ibg-game-room-${gameId}`) || null,
  )
  const [gameState, setGameState] = useState<CodenamesGameState | null>(null)
  const [clueWord, setClueWord] = useState("")
  const [clueNumber, setClueNumber] = useState(1)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSubmittingClue, setIsSubmittingClue] = useState(false)
  const [loadingTimedOut, setLoadingTimedOut] = useState(false)

  // Request board state on mount (handles navigation from lobby where initial event is missed)
  useEffect(() => {
    if (!isConnected || !user) return
    emit("get_board", { game_id: gameId, user_id: user.id })

    // Retry if no state received within 2s (socket may have missed the initial emit)
    const retryTimer = setTimeout(() => {
      if (!gameState && isConnected) {
        emit("get_board", { game_id: gameId, user_id: user.id })
      }
    }, 2000)
    return () => clearTimeout(retryTimer)
  }, [isConnected, user, emit, gameId])

  useEffect(() => {
    if (!isConnected) return

    const offGameStarted = on("codenames_game_started", (data: unknown) => {
      try {
        const d = data as {
          game_id: string
          team: "red" | "blue"
          role: "spymaster" | "operative"
          current_team: "red" | "blue"
          red_remaining: number
          blue_remaining: number
          board: CodenamesCard[]
          players: CodenamesPlayer[]
        }
        setGameState({
          board: d.board,
          current_team: d.current_team,
          current_turn: null,
          my_team: d.team,
          my_role: d.role,
          red_remaining: d.red_remaining,
          blue_remaining: d.blue_remaining,
          status: "in_progress",
          winner: null,
          players: d.players || [],
        })
      } catch {
        toast.error(t("common.error"))
      }
    })

    // codenames_board: response from get_board request (used on mount to fetch initial state)
    const offBoard = on("codenames_board", (data: unknown) => {
      try {
        const d = data as {
          game_id: string
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
        setGameState((prev) => ({
          board: d.board,
          current_team: d.current_team,
          current_turn: d.current_turn,
          my_team: d.team,
          my_role: d.role,
          red_remaining: d.red_remaining,
          blue_remaining: d.blue_remaining,
          status: d.status as "waiting" | "in_progress" | "finished",
          winner: d.winner,
          players: d.players || prev?.players || [],
        }))
      } catch {
        toast.error(t("common.error"))
      }
    })

    const offClueGiven = on("codenames_clue_given", (data: unknown) => {
      try {
        const d = data as { clue_word: string; clue_number: number; team: "red" | "blue"; max_guesses: number }
        const teamName = d.team === "red" ? t("games.codenames.teams.red") : t("games.codenames.teams.blue")
        toast.info(t("toast.clueGiven", { team: teamName, word: d.clue_word, number: d.clue_number }))
        setIsSubmittingClue(false)
        setGameState((prev) =>
          prev
            ? {
                ...prev,
                current_turn: {
                  team: d.team,
                  clue_word: d.clue_word,
                  clue_number: d.clue_number,
                  guesses_made: 0,
                  max_guesses: d.max_guesses,
                },
              }
            : prev,
        )
      } catch {
        toast.error(t("common.error"))
        setIsSubmittingClue(false)
      }
    })

    const offCardRevealed = on("codenames_card_revealed", (data: unknown) => {
      try {
        const d = data as {
          board: CodenamesCard[]
          current_team: "red" | "blue"
          red_remaining: number
          blue_remaining: number
          guesses_made: number
          max_guesses: number
          word?: string
        }
        if (d.word) {
          toast(t("toast.cardRevealed", { word: d.word }))
        }
        setGameState((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            board: d.board,
            current_team: d.current_team,
            red_remaining: d.red_remaining,
            blue_remaining: d.blue_remaining,
            current_turn: prev.current_turn
              ? { ...prev.current_turn, guesses_made: d.guesses_made, max_guesses: d.max_guesses }
              : prev.current_turn,
          }
        })
      } catch {
        toast.error(t("common.error"))
      }
    })

    const offTurnEnded = on("codenames_turn_ended", (data: unknown) => {
      try {
        const d = data as { current_team: "red" | "blue"; reason: string }
        const teamName = d.current_team === "red" ? t("games.codenames.teams.red") : t("games.codenames.teams.blue")
        toast.info(t("toast.turnEnded", { team: teamName }))
        setGameState((prev) =>
          prev ? { ...prev, current_team: d.current_team, current_turn: null } : prev,
        )
      } catch {
        toast.error(t("common.error"))
      }
    })

    const offGameOver = on("codenames_game_over", (data: unknown) => {
      try {
        toast.success(t("toast.gameOver"))
        const d = data as { winner: "red" | "blue"; board: CodenamesCard[] }
        setGameState((prev) =>
          prev ? { ...prev, status: "finished", winner: d.winner, board: d.board } : prev,
        )
      } catch {
        toast.error(t("common.error"))
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

    // error: catch backend errors (e.g. game not found, invalid move)
    const offError = on("error", (data: unknown) => {
      const payload = data as { name?: string; frontend_message?: string; message?: string; status_code?: number }
      const msg = payload.frontend_message || payload.message || "An error occurred"
      toast.error(msg)
      // Only show fatal error state for non-validation errors (e.g. game not found)
      if (payload.status_code !== 422) {
        setErrorMessage(msg)
      }

      // Fatal game errors — game no longer exists or player was removed
      if (payload.name === "GameNotFoundError" || payload.name === "PlayerRemovedFromGameError") {
        setTimeout(() => navigate({ to: "/" }), 2000)
      }
    })

    return () => {
      offGameStarted()
      offBoard()
      offClueGiven()
      offCardRevealed()
      offTurnEnded()
      offGameOver()
      offGameCancelled()
      offError()
    }
  }, [isConnected, on, navigate, t])

  // Loading timeout: if gameState is still null after 15s, show error
  useEffect(() => {
    if (gameState) return
    const timer = setTimeout(() => {
      setLoadingTimedOut(true)
    }, 15000)
    return () => clearTimeout(timer)
  }, [gameState])

  const handleGiveClue = useCallback(() => {
    if (!clueWord.trim() || isSubmittingClue) return
    setIsSubmittingClue(true)
    emit("give_clue", {
      room_id: roomIdRef.current,
      game_id: gameId,
      user_id: user?.id,
      clue_word: clueWord.trim(),
      clue_number: clueNumber,
    })
    setClueWord("")
    setClueNumber(1)
  }, [emit, gameId, user?.id, clueWord, clueNumber, isSubmittingClue])

  const handleGuessCard = useCallback(
    (index: number) => {
      emit("guess_card", { room_id: roomIdRef.current, game_id: gameId, user_id: user?.id, card_index: index })
    },
    [emit, gameId, user?.id],
  )

  const handleEndTurn = useCallback(() => {
    emit("end_turn", { room_id: roomIdRef.current, game_id: gameId, user_id: user?.id })
  }, [emit, gameId, user?.id])

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

  if (errorMessage) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="rounded-xl border bg-destructive/10 p-8 text-center">
          <h2 className="text-xl font-bold text-destructive mb-2">{t("common.error")}</h2>
          <p className="text-muted-foreground">{errorMessage}</p>
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

  if (!gameState) {
    if (loadingTimedOut) {
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
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">{t("common.loading")}</p>
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
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t("games.codenames.name")}</h1>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded-full bg-red-500" />
            <span className="text-sm font-medium">{gameState.red_remaining}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded-full bg-blue-500" />
            <span className="text-sm font-medium">{gameState.blue_remaining}</span>
          </div>
        </div>
      </div>

      {/* Your Turn Indicator */}
      {isMyTurn && gameState.status !== "finished" && (
        <div className="mb-4 rounded-lg bg-primary/10 border border-primary/30 p-3 text-center animate-pulse">
          <span className="font-semibold text-primary">{t("game.codenames.yourTurn")}</span>
        </div>
      )}

      {/* Turn Info */}
      <div className="mb-4 rounded-lg bg-muted/50 p-3 text-center">
        <span
          className={cn(
            "font-semibold",
            gameState.current_team === "red" ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400",
          )}
        >
          {gameState.current_team === "red"
            ? t("games.codenames.teams.red")
            : t("games.codenames.teams.blue")}
        </span>
        {gameState.current_turn?.clue_word && (
          <span className="ml-2 text-muted-foreground">
            — {gameState.current_turn.clue_word} ({gameState.current_turn.clue_number})
            {gameState.current_turn.max_guesses != null && (
              <span className="ml-2 text-xs">
                {t("game.codenames.guessesRemaining", {
                  made: gameState.current_turn.guesses_made,
                  max: gameState.current_turn.max_guesses,
                })}
              </span>
            )}
          </span>
        )}
      </div>

      {/* Board */}
      <div className="grid grid-cols-5 gap-2 mb-6">
        {gameState.board.map((card, index) => {
          const showColor = card.revealed || isSpymaster
          let bgColor = "bg-card hover:bg-muted"

          if (showColor) {
            switch (card.card_type) {
              case "red":
                bgColor = card.revealed
                  ? "bg-red-500 text-white"
                  : "bg-red-200 dark:bg-red-900/40 text-red-900 dark:text-red-200"
                break
              case "blue":
                bgColor = card.revealed
                  ? "bg-blue-500 text-white"
                  : "bg-blue-200 dark:bg-blue-900/40 text-blue-900 dark:text-blue-200"
                break
              case "neutral":
                bgColor = card.revealed
                  ? "bg-amber-200 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200"
                  : "bg-amber-50 dark:bg-amber-950/20"
                break
              case "assassin":
                bgColor = card.revealed
                  ? "bg-gray-900 text-white"
                  : "bg-gray-800 text-white"
                break
            }
          }

          return (
            <button
              key={index}
              type="button"
              onClick={() => handleGuessCard(index)}
              disabled={!canGuess || card.revealed || gameState.status === "finished"}
              className={cn(
                "rounded-lg border p-3 text-center text-sm font-medium transition-all min-h-[60px] flex items-center justify-center",
                bgColor,
                card.revealed && "opacity-75",
                canGuess && !card.revealed && "cursor-pointer hover:shadow-md",
                (!canGuess || card.revealed) && "cursor-default",
              )}
            >
              {card.word}
            </button>
          )
        })}
      </div>

      {/* Spymaster Clue Input */}
      {canGiveClue && (
        <div className="rounded-xl border bg-card p-4 mb-4">
          <h3 className="font-semibold mb-3">{t("game.codenames.giveClue")}</h3>
          <div className="flex gap-3">
            <input
              type="text"
              value={clueWord}
              onChange={(e) => setClueWord(e.target.value)}
              placeholder={t("game.codenames.cluePlaceholder")}
              className="flex-1 rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="number"
              value={clueNumber}
              onChange={(e) => setClueNumber(parseInt(e.target.value) || 1)}
              min={1}
              max={9}
              className="w-16 rounded-md border bg-background px-3 py-2 text-sm text-center focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="button"
              onClick={handleGiveClue}
              disabled={isSubmittingClue}
              className={cn(
                "rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90",
                isSubmittingClue && "opacity-50 cursor-not-allowed",
              )}
            >
              {isSubmittingClue ? t("game.codenames.sending") : t("common.submit")}
            </button>
          </div>
        </div>
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
        <div className="rounded-xl border bg-card p-8 text-center mt-6">
          <h2 className="text-3xl font-bold">{t("game.gameOver")}</h2>
          <p
            className={cn(
              "text-xl mt-4 font-semibold",
              gameState.winner === "red" ? "text-red-600" : "text-blue-600",
            )}
          >
            {gameState.winner === "red"
              ? t("games.codenames.teams.red")
              : t("games.codenames.teams.blue")}{" "}
            {t("game.codenames.wins")}
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
