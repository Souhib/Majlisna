import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Check, Copy, Crown, Eye, KeyRound, LogOut, UserPlus, Users, X } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  useGetRoomStateApiV1RoomsRoomIdStateGet,
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey,
  useStartUndercoverGameApiV1UndercoverGamesRoomIdStartPost,
  useStartCodenamesGameApiV1CodenamesGamesRoomIdStartPost,
  useStartWordquizGameApiV1WordquizGamesRoomIdStartPost,
  useStartMcqquizGameApiV1McqquizGamesRoomIdStartPost,
  useLeaveRoomApiV1RoomsLeavePatch,
  useKickPlayerApiV1RoomsRoomIdKickPatch,
} from "@/api/generated"
import { ChatPanel } from "@/components/rooms/ChatPanel"
import { InviteFriendModal } from "@/components/rooms/InviteFriendModal"
import { RoomSettings } from "@/components/rooms/RoomSettings"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"
import { storeRoomIdForGame } from "@/lib/room-session"

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

type GameType = "undercover" | "codenames" | "word_quiz" | "mcq_quiz"

function RoomLobbyPage() {
  const { roomId } = Route.useParams()
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [copied, setCopied] = useState("")
  const [gameType, setGameType] = useState<GameType>("undercover")
  const gameTypeSyncedRef = useRef(false)
  const queryClient = useQueryClient()
  const navigatingToGameRef = useRef(false)
  const previousPlayerIdsRef = useRef<Map<string, string>>(new Map())
  const [showInviteModal, setShowInviteModal] = useState(false)

  // Socket.IO for real-time updates
  const handleKicked = useCallback(() => {
    toast.error(t("youWereKicked"))
    navigate({ to: "/rooms" })
  }, [navigate, t])

  const { connected: socketConnected } = useSocket({
    roomId,
    enabled: !!user,
    onKicked: handleKicked,
  })

  // Poll room state as fallback when Socket.IO is disconnected
  const { data: rawRoomData, isLoading, error: queryError } = useGetRoomStateApiV1RoomsRoomIdStateGet(
    { room_id: roomId },
    {
      query: {
        refetchOnWindowFocus: true,
        refetchInterval: socketConnected ? false : 2_000,
        enabled: !!user,
      },
    },
  )

  // Transform raw API data to component shape
  const roomData: RoomData | undefined = rawRoomData ? {
    id: (rawRoomData as Record<string, unknown>).id as string,
    public_id: (rawRoomData as Record<string, unknown>).public_id as string,
    owner_id: (rawRoomData as Record<string, unknown>).owner_id as string,
    password: (rawRoomData as Record<string, unknown>).password as string,
    active_game_id: (rawRoomData as Record<string, unknown>).active_game_id as string | null,
    game_type: (rawRoomData as Record<string, unknown>).game_type as string | null,
    settings: (rawRoomData as Record<string, unknown>).settings as Record<string, unknown> | null,
    users: ((rawRoomData as Record<string, unknown>).players as { user_id: string; username: string; is_spectator: boolean }[] || []).map((p) => ({
      id: p.user_id,
      username: p.username,
      is_spectator: p.is_spectator,
    })),
  } : undefined

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

  // Sync game type from server on first load
  useEffect(() => {
    if (!gameTypeSyncedRef.current && roomData?.game_type) {
      const serverType = roomData.game_type as GameType
      if (["undercover", "codenames", "word_quiz", "mcq_quiz"].includes(serverType)) {
        setGameType(serverType)
      }
      gameTypeSyncedRef.current = true
    }
  }, [roomData?.game_type])

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
    storeRoomIdForGame(roomData.active_game_id, roomData.id)
    toast.success(t("toast.gameStarting"))
    const gt = roomData.game_type || gameType
    if (gt === "codenames") {
      navigate({ to: "/game/codenames/$gameId", params: { gameId: roomData.active_game_id } })
    } else if (gt === "word_quiz") {
      navigate({ to: "/game/wordquiz/$gameId", params: { gameId: roomData.active_game_id } })
    } else if (gt === "mcq_quiz") {
      navigate({ to: "/game/mcqquiz/$gameId", params: { gameId: roomData.active_game_id } })
    } else {
      navigate({ to: "/game/undercover/$gameId", params: { gameId: roomData.active_game_id } })
    }
  }, [roomData?.active_game_id, roomData?.game_type, gameType, navigate, t])

  const startUndercoverMutation = useStartUndercoverGameApiV1UndercoverGamesRoomIdStartPost({
    mutation: {
      onSuccess: (data) => {
        const d = data as { game_id: string; room_id: string }
        navigatingToGameRef.current = true
        storeRoomIdForGame(d.game_id, d.room_id)
        toast.success(t("toast.gameStarting"))
        navigate({ to: "/game/undercover/$gameId", params: { gameId: d.game_id } })
      },
      onError: (err) => toast.error(getApiErrorMessage(err, "Failed to start game")),
    },
  })

  const startCodenamesMutation = useStartCodenamesGameApiV1CodenamesGamesRoomIdStartPost({
    mutation: {
      onSuccess: (data) => {
        const d = data as { game_id: string; room_id: string }
        navigatingToGameRef.current = true
        storeRoomIdForGame(d.game_id, d.room_id)
        toast.success(t("toast.gameStarting"))
        navigate({ to: "/game/codenames/$gameId", params: { gameId: d.game_id } })
      },
      onError: (err) => toast.error(getApiErrorMessage(err, "Failed to start game")),
    },
  })

  const startWordQuizMutation = useStartWordquizGameApiV1WordquizGamesRoomIdStartPost({
    mutation: {
      onSuccess: (data) => {
        const d = data as { game_id: string; room_id: string }
        navigatingToGameRef.current = true
        storeRoomIdForGame(d.game_id, d.room_id)
        toast.success(t("toast.gameStarting"))
        navigate({ to: "/game/wordquiz/$gameId", params: { gameId: d.game_id } })
      },
      onError: (err) => toast.error(getApiErrorMessage(err, "Failed to start game")),
    },
  })

  const startMcqQuizMutation = useStartMcqquizGameApiV1McqquizGamesRoomIdStartPost({
    mutation: {
      onSuccess: (data) => {
        const d = data as { game_id: string; room_id: string }
        navigatingToGameRef.current = true
        storeRoomIdForGame(d.game_id, d.room_id)
        toast.success(t("toast.gameStarting"))
        navigate({ to: "/game/mcqquiz/$gameId", params: { gameId: d.game_id } })
      },
      onError: (err) => toast.error(getApiErrorMessage(err, "Failed to start game")),
    },
  })

  const isStartingGame = startUndercoverMutation.isPending || startCodenamesMutation.isPending || startWordQuizMutation.isPending || startMcqQuizMutation.isPending

  const handleStartGame = () => {
    if (!roomData || isStartingGame) return
    trackEvent("game-start", { game: gameType, players: players.length })
    if (gameType === "codenames") {
      startCodenamesMutation.mutate({ room_id: roomData.id })
    } else if (gameType === "word_quiz") {
      startWordQuizMutation.mutate({ room_id: roomData.id })
    } else if (gameType === "mcq_quiz") {
      startMcqQuizMutation.mutate({ room_id: roomData.id })
    } else {
      startUndercoverMutation.mutate({ room_id: roomData.id })
    }
  }

  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  const handleLeaveRoom = async () => {
    if (!user || !roomData) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await leaveMutation.mutateAsync({ data: { user_id: user.id, room_id: roomData.id } })
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

  const kickMutation = useKickPlayerApiV1RoomsRoomIdKickPatch()

  const handleKickPlayer = async (userId: string) => {
    if (!roomData) return
    try {
      await kickMutation.mutateAsync({ room_id: roomData.id, data: { user_id: userId } })
      queryClient.invalidateQueries({ queryKey: getRoomStateApiV1RoomsRoomIdStateGetQueryKey({ room_id: roomId }) })
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to kick player"))
    }
  }

  const minPlayers = gameType === "codenames" ? 4 : (gameType === "word_quiz" || gameType === "mcq_quiz") ? 1 : 3

  const copyToClipboard = useCallback((text: string, key: string, label: string) => {
    const onSuccess = () => {
      setCopied(key)
      toast.success(t("toast.copied", { label }))
      setTimeout(() => setCopied(""), 1500)
    }
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(onSuccess, () => {
        const textarea = document.createElement("textarea")
        textarea.value = text
        textarea.style.position = "fixed"
        textarea.style.opacity = "0"
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand("copy")
        document.body.removeChild(textarea)
        onSuccess()
      })
    } else {
      const textarea = document.createElement("textarea")
      textarea.value = text
      textarea.style.position = "fixed"
      textarea.style.opacity = "0"
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand("copy")
      document.body.removeChild(textarea)
      onSuccess()
    }
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
        <div className="glass rounded-2xl p-6 text-center text-destructive border-destructive/30">
          {getApiErrorMessage(queryError, "Failed to load room details")}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8 animate-slide-up">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight gradient-text">{t("room.lobby")}</h1>
        <button
          type="button"
          onClick={handleLeaveRoom}
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all duration-200"
        >
          <LogOut className="h-3.5 w-3.5" />
          {t("room.leave")}
        </button>
      </div>

      {/* Room Info */}
      {roomData && (
        <div className="glass rounded-2xl p-6 mb-6 animate-scale-in">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm text-muted-foreground">{t("room.roomCode")}</span>
            <button
              type="button"
              onClick={() => copyToClipboard(roomData.public_id, "code", t("room.roomCode"))}
              className={cn(
                "flex items-center gap-2.5 rounded-xl px-4 py-2 font-mono text-2xl font-extrabold transition-all duration-200",
                copied === "code" ? "bg-primary/10 text-primary shadow-md shadow-primary/10" : "bg-muted/50 hover:bg-muted/80",
              )}
            >
              <span className="tracking-[0.3em] tabular-nums">{roomData.public_id}</span>
              {copied === "code" ? (
                <Check className="h-4 w-4 text-primary" />
              ) : (
                <Copy className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          </div>
          <div className="flex items-center justify-between pt-4 border-t border-border/30">
            <span className="text-sm text-muted-foreground">{t("room.password")}</span>
            <button
              type="button"
              onClick={() => copyToClipboard(roomData.password, "pw", t("room.password"))}
              className={cn(
                "flex items-center gap-2.5 rounded-xl px-4 py-2 font-mono text-xl font-extrabold transition-all duration-200",
                copied === "pw" ? "bg-primary/10 text-primary shadow-md shadow-primary/10" : "bg-muted/50 hover:bg-muted/80",
              )}
            >
              <KeyRound className="h-4 w-4 text-muted-foreground" />
              <span className="tracking-[0.3em] tabular-nums">{roomData.password}</span>
              {copied === "pw" ? (
                <Check className="h-4 w-4 text-primary" />
              ) : (
                <Copy className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          </div>
        </div>
      )}

      {/* Players */}
      <div className="glass rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-5 w-5 text-primary" />
          <h2 className="font-extrabold tracking-tight">
            {t("room.players")} <span className="font-mono tabular-nums">({players.length})</span>
          </h2>
        </div>

        {players.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("room.waitingForPlayers")}</p>
        ) : (
          <div className="space-y-2">
            {players.map((player) => (
              <div
                key={player.id}
                className="flex items-center justify-between rounded-xl bg-muted/30 px-4 py-3 border border-border/30 hover:bg-muted/50 transition-all duration-200"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/70 text-xs font-bold text-primary-foreground shadow-sm">
                    {player.username.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium">{player.username}</span>
                </div>
                <div className="flex items-center gap-2">
                  {player.is_host && (
                    <span className="flex items-center gap-1 rounded-lg bg-accent/10 px-2 py-1 text-xs font-bold text-accent">
                      <Crown className="h-3 w-3" />
                      {t("room.host")}
                    </span>
                  )}
                  {isHost && player.id !== user?.id && (
                    <button
                      type="button"
                      onClick={() => handleKickPlayer(player.id)}
                      className="rounded-lg p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-all duration-200"
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
        <div className="glass rounded-2xl p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Eye className="h-5 w-5 text-muted-foreground" />
            <h2 className="font-extrabold tracking-tight">
              {t("room.spectators")} <span className="font-mono tabular-nums">({spectators.length})</span>
            </h2>
          </div>
          <div className="space-y-2">
            {spectators.map((spec) => (
              <div key={spec.id} className="flex items-center rounded-xl bg-muted/20 border border-border/30 px-4 py-2.5 transition-all duration-200">
                <Eye className="mr-2 h-3 w-3 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">{spec.username}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Invite Friend Button */}
      {roomData && !isSpectator && (
        <div className="mb-6">
          <button
            type="button"
            onClick={() => setShowInviteModal(true)}
            className="w-full flex items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-primary/30 bg-primary/5 px-4 py-3.5 text-sm font-medium text-primary hover:bg-primary/10 hover:border-primary/50 transition-all duration-200"
          >
            <UserPlus className="h-4 w-4" />
            {t("room.inviteFriend")}
          </button>
        </div>
      )}

      {/* Chat Panel — integrated inline */}
      {user && <ChatPanel roomId={roomId} currentUserId={user.id} />}

      {/* Room Settings (host only, not for word_quiz which uses defaults) */}
      {isHost && !isSpectator && roomData && (
        <div className="mt-6">
        <RoomSettings
          roomId={roomData.id}
          settings={roomData.settings ?? null}
          gameType={gameType}
          playerCount={players.length}
        />
        </div>
      )}

      {/* Game Type Selector + Start Button (host only) */}
      {isHost && !isSpectator && (
        <div className="mt-4 space-y-4">
          <div className="glass rounded-2xl p-5">
            <h3 className="text-sm font-extrabold tracking-tight mb-3">{t("room.gameType")}</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setGameType("undercover")}
                className={cn(
                  "flex-1 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer",
                  gameType === "undercover"
                    ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-md shadow-primary/20"
                    : "glass hover:bg-muted/80",
                )}
              >
                Undercover
              </button>
              <button
                type="button"
                onClick={() => setGameType("codenames")}
                className={cn(
                  "flex-1 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer",
                  gameType === "codenames"
                    ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-md shadow-primary/20"
                    : "glass hover:bg-muted/80",
                )}
              >
                Codenames
              </button>
              <button
                type="button"
                onClick={() => setGameType("word_quiz")}
                className={cn(
                  "flex-1 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer",
                  gameType === "word_quiz"
                    ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-md shadow-primary/20"
                    : "glass hover:bg-muted/80",
                )}
              >
                {t("games.wordQuiz.name")}
              </button>
              <button
                type="button"
                onClick={() => setGameType("mcq_quiz")}
                className={cn(
                  "flex-1 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer",
                  gameType === "mcq_quiz"
                    ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-md shadow-primary/20"
                    : "glass hover:bg-muted/80",
                )}
              >
                {t("games.mcqQuiz.name")}
              </button>
            </div>
          </div>

          {players.length < minPlayers && (
            <p className="text-center text-sm text-muted-foreground font-mono tabular-nums">
              {t("room.minPlayers", { count: minPlayers })}
            </p>
          )}
          <button
            type="button"
            onClick={handleStartGame}
            disabled={players.length < minPlayers || isStartingGame}
            className="w-full rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-3.5 text-base font-extrabold tracking-tight text-primary-foreground shadow-lg shadow-primary/25 hover:shadow-xl hover:shadow-primary/30 hover:-translate-y-0.5 disabled:opacity-50 transition-all duration-200 cursor-pointer"
          >
            {isStartingGame ? t("common.loading") : t("room.startGame")}
          </button>
        </div>
      )}

      {/* Invite Friend Modal */}
      {showInviteModal && roomData && (
        <InviteFriendModal
          roomId={roomData.id}
          onClose={() => setShowInviteModal(false)}
        />
      )}
    </div>
  )
}
