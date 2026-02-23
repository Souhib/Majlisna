import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Check, Copy, Crown, KeyRound, LogOut, Users } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import apiClient from "@/api/client"
import { useSocket } from "@/hooks/use-socket"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"

interface RoomData {
  id: string
  public_id: string
  owner_id: string
  password: string
  users: { id: string; username: string }[]
}

interface Player {
  id: string
  username: string
  is_host: boolean
  is_disconnected?: boolean
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
  const { emit, on, isConnected } = useSocket()
  const [players, setPlayers] = useState<Player[]>([])
  const [roomData, setRoomData] = useState<RoomData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")
  const [copied, setCopied] = useState("")
  const [gameType, setGameType] = useState<GameType>("undercover")
  const joinedRef = useRef(false)
  const navigatingToGameRef = useRef(false)
  const roleDataRef = useRef<{ role: string; word: string | null } | null>(null)

  const isHost = roomData?.owner_id === user?.id

  // Fetch room details via REST
  useEffect(() => {
    apiClient({ method: "GET", url: `/api/v1/rooms/${roomId}` })
      .then((res) => {
        const data = res.data as RoomData
        setRoomData(data)
        // Set initial players from REST data
        setPlayers(
          data.users.map((u) => ({
            id: u.id,
            username: u.username,
            is_host: u.id === data.owner_id,
          })),
        )
      })
      .catch(() => setError("Failed to load room details"))
      .finally(() => setIsLoading(false))
  }, [roomId])

  // Socket.IO join room + leave on unmount
  useEffect(() => {
    if (!isConnected || !roomData || !user) return
    if (joinedRef.current) return
    joinedRef.current = true

    emit("join_room", {
      user_id: user.id,
      public_room_id: roomData.public_id,
      password: roomData.password,
    })

    return () => {
      // Leave room on unmount unless navigating to a game page
      if (!navigatingToGameRef.current && joinedRef.current) {
        emit("leave_room", {
          user_id: user.id,
          room_id: roomData.id,
          username: user.username,
        })
      }
      joinedRef.current = false
    }
  }, [isConnected, roomData, user, emit])

  // Listen for socket events (separate effect to avoid re-subscribing on roomData change)
  useEffect(() => {
    if (!isConnected || !roomData) return

    // room_status: sent to the joining user with full room data
    const offStatus = on("room_status", (data: unknown) => {
      const payload = data as { data: { users: { id: string; username: string }[]; owner_id: string } }
      if (payload.data?.users) {
        toast.success(t("toast.roomJoined"))
        setPlayers(
          payload.data.users.map((u) => ({
            id: u.id,
            username: u.username,
            is_host: u.id === payload.data.owner_id,
          })),
        )
      }
    })

    // new_user_joined: sent to room when another user joins
    const offNewUser = on("new_user_joined", (data: unknown) => {
      const payload = data as { data: { users: { id: string; username: string }[]; owner_id: string } }
      if (payload.data?.users) {
        setPlayers((prev) => {
          const prevIds = new Set(prev.map((p) => p.id))
          const newUser = payload.data.users.find((u) => !prevIds.has(u.id))
          if (newUser) {
            toast.info(t("toast.playerJoined", { username: newUser.username }))
          }
          return payload.data.users.map((u) => ({
            id: u.id,
            username: u.username,
            is_host: u.id === payload.data.owner_id,
          }))
        })
      }
    })

    // user_left: sent to room when a user leaves
    const offUserLeft = on("user_left", (data: unknown) => {
      const payload = data as { data: { users: { id: string; username: string }[]; owner_id: string } }
      if (payload.data?.users) {
        setPlayers((prev) => {
          const newIds = new Set(payload.data.users.map((u) => u.id))
          const leftUser = prev.find((p) => !newIds.has(p.id))
          if (leftUser) {
            toast(t("toast.playerLeft", { username: leftUser.username }))
          }
          return payload.data.users.map((u) => ({
            id: u.id,
            username: u.username,
            is_host: u.id === payload.data.owner_id,
          }))
        })
      }
    })

    // role_assigned: capture undercover role data before game_started navigates away
    const offRoleAssigned = on("role_assigned", (data: unknown) => {
      roleDataRef.current = data as { role: string; word: string | null }
    })

    // game_started: undercover game started, navigate to game page with role data
    const offGameStarted = on("game_started", (data: unknown) => {
      toast.success(t("toast.gameStarting"))
      navigatingToGameRef.current = true
      const { game_id, game_type, players: playerNames, mayor } = data as {
        game_id: string; game_type: string; players: string[]; mayor: string
      }
      if (game_type === "undercover") {
        const doNavigate = () => {
          // Always store game_started data; include role data if available
          sessionStorage.setItem(
            `ibg-game-init-${game_id}`,
            JSON.stringify({ roleData: roleDataRef.current, players: playerNames, mayor, roomId: roomData?.id }),
          )
          navigate({ to: "/game/undercover/$gameId", params: { gameId: game_id } })
        }

        if (roleDataRef.current) {
          doNavigate()
        } else {
          // role_assigned may not have been processed yet — wait briefly
          setTimeout(() => doNavigate(), 150)
        }
      }
    })

    // codenames_game_started: codenames game started, navigate to game page
    const offCodenamesStarted = on("codenames_game_started", (data: unknown) => {
      toast.success(t("toast.gameStarting"))
      navigatingToGameRef.current = true
      const { game_id } = data as { game_id: string }
      sessionStorage.setItem(`ibg-game-room-${game_id}`, roomData?.id || "")
      navigate({ to: "/game/codenames/$gameId", params: { gameId: game_id } })
    })

    // player_disconnected: a player's connection dropped (grace period active)
    const offPlayerDisconnected = on("player_disconnected", (data: unknown) => {
      const payload = data as { user_id: string }
      setPlayers((prev) => {
        const player = prev.find((p) => p.id === payload.user_id)
        if (player) {
          toast.warning(t("toast.playerDisconnected", { username: player.username }))
        }
        return prev.map((p) => (p.id === payload.user_id ? { ...p, is_disconnected: true } : p))
      })
    })

    // player_reconnected: a player reconnected within grace period
    const offPlayerReconnected = on("player_reconnected", (data: unknown) => {
      const payload = data as { user_id: string; data?: { users: { id: string; username: string }[]; owner_id: string } }
      if (payload.data?.users) {
        const reconnectedUser = payload.data.users.find((u) => u.id === payload.user_id)
        if (reconnectedUser) {
          toast.success(t("toast.playerReconnected", { username: reconnectedUser.username }))
        }
        setPlayers(
          payload.data.users.map((u) => ({
            id: u.id,
            username: u.username,
            is_host: u.id === payload.data!.owner_id,
            is_disconnected: false,
          })),
        )
      } else {
        setPlayers((prev) => {
          const player = prev.find((p) => p.id === payload.user_id)
          if (player) {
            toast.success(t("toast.playerReconnected", { username: player.username }))
          }
          return prev.map((p) => (p.id === payload.user_id ? { ...p, is_disconnected: false } : p))
        })
      }
    })

    // player_left_permanently: grace period expired, player removed
    const offPlayerLeftPermanently = on("player_left_permanently", (data: unknown) => {
      const payload = data as { user_id: string }
      setPlayers((prev) => {
        const player = prev.find((p) => p.id === payload.user_id)
        if (player) {
          toast.error(t("toast.playerLeftPermanently", { username: player.username }))
        }
        return prev.filter((p) => p.id !== payload.user_id)
      })
    })

    // owner_changed: room ownership transferred
    const offOwnerChanged = on("owner_changed", (data: unknown) => {
      const payload = data as { new_owner_id: string }
      setPlayers((prev) => {
        const newOwner = prev.find((p) => p.id === payload.new_owner_id)
        if (newOwner) {
          toast.info(t("toast.ownerChanged", { username: newOwner.username }))
        }
        return prev.map((p) => ({ ...p, is_host: p.id === payload.new_owner_id }))
      })
      setRoomData((prev) => (prev ? { ...prev, owner_id: payload.new_owner_id } : prev))
    })

    // user_disconnected: legacy event (backward compat)
    const offUserDisconnected = on("user_disconnected", (data: unknown) => {
      const payload = data as { user_id: string }
      setPlayers((prev) => prev.filter((p) => p.id !== payload.user_id))
    })

    // error: socket error events
    const offError = on("error", (data: unknown) => {
      const payload = data as { frontend_message?: string; message: string }
      const msg = payload.frontend_message || payload.message || "Socket error"
      setError(msg)
      toast.error(msg)
    })

    return () => {
      offStatus()
      offNewUser()
      offUserLeft()
      offRoleAssigned()
      offGameStarted()
      offCodenamesStarted()
      offPlayerDisconnected()
      offPlayerReconnected()
      offPlayerLeftPermanently()
      offOwnerChanged()
      offUserDisconnected()
      offError()
    }
  }, [isConnected, roomData, on, navigate])

  const handleStartGame = () => {
    if (gameType === "codenames") {
      emit("start_codenames_game", { room_id: roomId, user_id: user?.id, word_pack_ids: null })
    } else {
      emit("start_undercover_game", { room_id: roomId, user_id: user?.id })
    }
  }

  const handleLeaveRoom = () => {
    if (!user || !roomData) return
    emit("leave_room", {
      user_id: user.id,
      room_id: roomData.id,
      username: user.username,
    })
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }

  const minPlayers = gameType === "codenames" ? 4 : 3

  const copyToClipboard = useCallback((text: string, label: string) => {
    // navigator.clipboard requires HTTPS; use fallback for HTTP
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-muted-foreground">{t("common.loading")}</p>
      </div>
    )
  }

  if (error && !roomData) {
    return (
      <div className="mx-auto max-w-lg px-4 py-8">
        <div className="rounded-md bg-destructive/10 p-4 text-center text-destructive">{error}</div>
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

      {error && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive mb-4">{error}</div>
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
                className={cn(
                  "flex items-center justify-between rounded-lg px-4 py-2.5",
                  player.is_disconnected ? "bg-destructive/10 opacity-60" : "bg-muted/50",
                )}
              >
                <span className="text-sm font-medium">{player.username}</span>
                <div className="flex items-center gap-2">
                  {player.is_disconnected && (
                    <span className="text-xs text-destructive animate-pulse">Reconnecting...</span>
                  )}
                  {player.is_host && (
                    <span className="flex items-center gap-1 text-xs text-accent">
                      <Crown className="h-3 w-3" />
                      {t("room.host")}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Game Type Selector + Start Button (host only) */}
      {isHost && (
        <div className="space-y-4">
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
            disabled={players.length < minPlayers}
            className="w-full rounded-md bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {t("room.startGame")}
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

      {!isConnected && (
        <div className="mt-4 rounded-md bg-destructive/10 p-3 text-center text-sm text-destructive">
          Connecting to server...
        </div>
      )}
    </div>
  )
}
