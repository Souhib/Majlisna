import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Check, Copy, Crown, Eye, KeyRound, LogOut, Users, X } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import apiClient, { getApiErrorMessage } from "@/api/client"
import { ChatPanel } from "@/components/rooms/ChatPanel"
import { RoomSettings } from "@/components/rooms/RoomSettings"
import { useSocket } from "@/hooks/use-socket"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"

interface RoomData {
  id: string
  public_id: string
  owner_id: string
  password: string
  active_game_id?: string | null
  game_type?: string | null
  settings?: Record<string, unknown> | null
  users: { id: string; username: string; is_spectator?: boolean }[]
}

interface Player {
  id: string
  username: string
  is_host: boolean
  is_spectator?: boolean
}

export const Route = createFileRoute("/_auth/rooms/$roomId")({
  component: RoomLobbyPage,
})

type GameType = "undercover" | "codenames"

function RoomLobbyPage() {
  const { roomId } = Route.useParams()
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [copied, setCopied] = useState("")
  const [gameType, setGameType] = useState<GameType>("undercover")
  const [isStartingGame, setIsStartingGame] = useState(false)
  const queryClient = useQueryClient()
  const joinedRef = useRef(false)
  const navigatingToGameRef = useRef(false)
  const previousPlayerIdsRef = useRef<Map<string, string>>(new Map())

  // Socket.IO for real-time updates (replaces polling)
  useSocket({ roomId, enabled: !!user })

  // Join room via REST on mount
  useEffect(() => {
    if (!user || joinedRef.current) return
    joinedRef.current = true

    // We join via REST — the heartbeat is handled by polling GET /rooms/{roomId}
    apiClient({
      method: "PATCH",
      url: "/api/v1/rooms/join",
      data: { user_id: user.id, room_id: roomId },
    }).catch(() => {
      // Join might fail if already in room (re-join) — that's fine
    })
  }, [user, roomId])

  // Poll room state every 2 seconds (uses /state endpoint for heartbeat + connection status)
  const { data: roomData, isLoading, error: queryError } = useQuery({
    queryKey: ["room", roomId],
    queryFn: async () => {
      const res = await apiClient({
        method: "GET",
        url: `/api/v1/rooms/${roomId}/state`,
      })
      const state = res.data as {
        id: string
        public_id: string
        owner_id: string
        password: string
        active_game_id: string | null
        game_type: string | null
        settings: Record<string, unknown> | null
        players: { user_id: string; username: string; is_connected: boolean; is_disconnected: boolean; is_host: boolean; is_spectator: boolean }[]
        type: string
      }
      return {
        id: state.id,
        public_id: state.public_id,
        owner_id: state.owner_id,
        password: state.password,
        active_game_id: state.active_game_id,
        game_type: state.game_type,
        settings: state.settings,
        users: state.players.map((p) => ({
          id: p.user_id,
          username: p.username,
          is_spectator: p.is_spectator,
        })),
      } as RoomData
    },
    refetchOnWindowFocus: true,
    refetchInterval: 5000,
    enabled: !!user,
  })

  // Derive players and spectators from room data
  const allUsers: Player[] = roomData
    ? roomData.users.map((u) => ({
        id: u.id,
        username: u.username,
        is_host: u.id === roomData.owner_id,
        is_spectator: u.is_spectator,
      }))
    : []

  const players = allUsers.filter((u) => !u.is_spectator)
  const spectators = allUsers.filter((u) => u.is_spectator)
  const isHost = roomData?.owner_id === user?.id
  const isSpectator = allUsers.some((u) => u.id === user?.id && u.is_spectator)

  // Toast notifications when players join or leave
  useEffect(() => {
    if (!allUsers.length || !user) return
    const currentMap = new Map(allUsers.map((u) => [u.id, u.username]))
    const previousMap = previousPlayerIdsRef.current

    // Skip first render (ref is empty) to avoid toasting every existing player
    if (previousMap.size > 0) {
      for (const [id, username] of currentMap) {
        if (!previousMap.has(id) && id !== user.id) {
          toast.info(t("toast.playerJoined", { username }))
        }
      }
      for (const [id, username] of previousMap) {
        if (!currentMap.has(id) && id !== user.id) {
          toast.info(t("toast.playerLeft", { username }))
        }
      }
    }

    previousPlayerIdsRef.current = currentMap
  }, [allUsers, user, t])

  // Auto-navigate when game starts (active_game_id appears)
  useEffect(() => {
    if (!roomData?.active_game_id || navigatingToGameRef.current) return
    navigatingToGameRef.current = true
    toast.success(t("toast.gameStarting"))
    const gt = roomData.game_type || gameType
    if (gt === "codenames") {
      navigate({ to: "/game/codenames/$gameId", params: { gameId: roomData.active_game_id } })
    } else {
      navigate({ to: "/game/undercover/$gameId", params: { gameId: roomData.active_game_id } })
    }
  }, [roomData?.active_game_id, roomData?.game_type, gameType, navigate, t])

  const handleStartGame = async () => {
    if (!roomData || isStartingGame) return
    setIsStartingGame(true)
    try {
      const url =
        gameType === "codenames"
          ? `/api/v1/codenames/games/${roomData.id}/start`
          : `/api/v1/undercover/games/${roomData.id}/start`
      const res = await apiClient({ method: "POST", url })
      const data = res.data as { game_id: string; room_id: string }
      navigatingToGameRef.current = true
      toast.success(t("toast.gameStarting"))
      if (gameType === "undercover") {
        navigate({ to: "/game/undercover/$gameId", params: { gameId: data.game_id } })
      } else {
        navigate({ to: "/game/codenames/$gameId", params: { gameId: data.game_id } })
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to start game"))
    } finally {
      setIsStartingGame(false)
    }
  }

  const handleLeaveRoom = async () => {
    if (!user || !roomData) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await apiClient({
        method: "PATCH",
        url: "/api/v1/rooms/leave",
        data: { user_id: user.id, room_id: roomData.id },
      })
    } catch {
      // Ignore errors — navigate anyway
    }
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }

  // Detect being kicked: if current user was in the list but disappears
  useEffect(() => {
    if (!user || !roomData) return
    const wasInRoom = previousPlayerIdsRef.current.has(user.id)
    const isInRoom = allUsers.some((u) => u.id === user.id)
    if (wasInRoom && !isInRoom) {
      toast.error(t("toast.youWereKicked"))
      navigate({ to: "/rooms" })
    }
  }, [allUsers, user, roomData, navigate, t])

  const handleKickPlayer = async (userId: string) => {
    if (!roomData) return
    try {
      await apiClient({
        method: "PATCH",
        url: `/api/v1/rooms/${roomData.id}/kick`,
        data: { user_id: userId },
      })
      queryClient.invalidateQueries({ queryKey: ["room", roomId] })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to kick player"))
    }
  }

  const minPlayers = gameType === "codenames" ? 4 : 3

  const copyToClipboard = useCallback((text: string, label: string) => {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(
        () => {
          setCopied(label)
          toast.success(t("toast.copied", { label }))
          setTimeout(() => setCopied(""), 1500)
        },
        () => fallbackCopy(text, label),
      )
    } else {
      fallbackCopy(text, label)
    }
  }, [t])

  const fallbackCopy = useCallback((text: string, label: string) => {
    const textarea = document.createElement("textarea")
    textarea.value = text
    textarea.style.position = "fixed"
    textarea.style.opacity = "0"
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand("copy")
    document.body.removeChild(textarea)
    setCopied(label)
    toast.success(t("toast.copied", { label }))
    setTimeout(() => setCopied(""), 1500)
  }, [t])

  if (isLoading && !roomData) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-muted-foreground">{t("common.loading")}</p>
      </div>
    )
  }

  if (queryError && !roomData) {
    return (
      <div className="mx-auto max-w-lg px-4 py-8">
        <div className="rounded-md bg-destructive/10 p-4 text-center text-destructive">
          {getApiErrorMessage(queryError, "Failed to load room details")}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold">{t("room.lobby")}</h1>
      </div>

      {/* Room Info */}
      {roomData && (
        <div className="rounded-xl border bg-card p-6 mb-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-muted-foreground">Room Code</span>
            <button
              type="button"
              onClick={() => copyToClipboard(roomData.public_id, "Room Code")}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-1.5 font-mono text-lg font-bold transition-colors",
                copied === "Room Code" ? "bg-primary/10 text-primary" : "bg-muted hover:bg-muted/80",
              )}
            >
              <span className="tracking-widest">{roomData.public_id}</span>
              {copied === "Room Code" ? (
                <Check className="h-4 w-4 text-primary" />
              ) : (
                <Copy className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Password</span>
            <button
              type="button"
              onClick={() => copyToClipboard(roomData.password, "Password")}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-1.5 font-mono text-lg font-bold transition-colors",
                copied === "Password" ? "bg-primary/10 text-primary" : "bg-muted hover:bg-muted/80",
              )}
            >
              <KeyRound className="h-4 w-4 text-muted-foreground" />
              <span className="tracking-widest">{roomData.password}</span>
              {copied === "Password" ? (
                <Check className="h-4 w-4 text-primary" />
              ) : (
                <Copy className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          </div>
        </div>
      )}

      {/* Players */}
      <div className="rounded-xl border bg-card p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-5 w-5 text-muted-foreground" />
          <h2 className="font-semibold">
            {t("room.players")} ({players.length})
          </h2>
        </div>

        {players.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("room.waitingForPlayers")}</p>
        ) : (
          <div className="space-y-2">
            {players.map((player) => (
              <div
                key={player.id}
                className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-2.5"
              >
                <span className="text-sm font-medium">{player.username}</span>
                <div className="flex items-center gap-2">
                  {player.is_host && (
                    <span className="flex items-center gap-1 text-xs text-accent">
                      <Crown className="h-3 w-3" />
                      {t("room.host")}
                    </span>
                  )}
                  {isHost && player.id !== user?.id && (
                    <button
                      type="button"
                      onClick={() => handleKickPlayer(player.id)}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      title={t("room.kick")}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Spectators */}
      {spectators.length > 0 && (
        <div className="rounded-xl border bg-card p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Eye className="h-5 w-5 text-muted-foreground" />
            <h2 className="font-semibold">
              {t("room.spectators")} ({spectators.length})
            </h2>
          </div>
          <div className="space-y-2">
            {spectators.map((spec) => (
              <div key={spec.id} className="flex items-center rounded-lg bg-muted/30 px-4 py-2">
                <Eye className="mr-2 h-3 w-3 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">{spec.username}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Room Settings (host only) */}
      {isHost && !isSpectator && roomData && (
        <RoomSettings
          roomId={roomData.id}
          settings={roomData.settings ?? null}
          gameType={gameType}
          playerCount={players.length}
        />
      )}

      {/* Game Type Selector + Start Button (host only) */}
      {isHost && !isSpectator && (
        <div className="mt-4 space-y-4">
          <div className="rounded-xl border bg-card p-4">
            <h3 className="text-sm font-semibold mb-3">Game Type</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setGameType("undercover")}
                className={cn(
                  "flex-1 rounded-md px-4 py-2.5 text-sm font-medium transition-colors",
                  gameType === "undercover"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted hover:bg-muted/80",
                )}
              >
                Undercover
              </button>
              <button
                type="button"
                onClick={() => setGameType("codenames")}
                className={cn(
                  "flex-1 rounded-md px-4 py-2.5 text-sm font-medium transition-colors",
                  gameType === "codenames"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted hover:bg-muted/80",
                )}
              >
                Codenames
              </button>
            </div>
          </div>

          {players.length < minPlayers && (
            <p className="text-center text-sm text-muted-foreground">
              {t("room.minPlayers", { count: minPlayers })}
            </p>
          )}
          <button
            type="button"
            onClick={handleStartGame}
            disabled={players.length < minPlayers || isStartingGame}
            className="w-full rounded-md bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isStartingGame ? t("common.loading") : t("room.startGame")}
          </button>
        </div>
      )}

      {/* Leave Room */}
      <button
        type="button"
        onClick={handleLeaveRoom}
        className="mt-6 w-full flex items-center justify-center gap-2 rounded-md border border-destructive/30 px-4 py-2.5 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors"
      >
        <LogOut className="h-4 w-4" />
        {t("room.leave")}
      </button>

      {/* Chat Panel */}
      {user && <ChatPanel roomId={roomId} currentUserId={user.id} />}
    </div>
  )
}
