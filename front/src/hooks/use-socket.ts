import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { io, type Socket } from "socket.io-client"
import { queryKeys } from "@/api/queryKeys"
import { getStoredToken, onTokenStored } from "@/lib/auth"

interface ChatMessage {
  id: string
  room_id: string
  user_id: string
  username: string
  message: string
  created_at: string
}

interface UseSocketOptions {
  roomId: string | null | undefined
  gameId?: string | null
  gameType?: "undercover" | "codenames" | "word_quiz" | "mcq_quiz"
  enabled?: boolean
  onKicked?: (roomId: string) => void
  onChatMessage?: (message: ChatMessage) => void
}

function getGameQueryKeyPrefix(gameType: string, gameId: string) {
  return queryKeys.game.byType(gameType, gameId)
}

/**
 * Connects to Socket.IO and pushes real-time state into TanStack Query cache.
 *
 * - On connect: server sends room_state automatically
 * - On join_game: server sends initial game_state, read in the language sent with it
 *   (`{ game_id, lang }`): Undercover and Codenames write that push straight into the
 *   cache, so without `lang` an English push overwrote the Arabic meanings
 * - room_state events update ["room", roomId] query cache directly
 * - game_updated events invalidate [gameType, gameId] query, triggering a REST re-fetch
 *
 * Mutations still go through REST. Socket.IO is notification-only.
 */
export function useSocket({ roomId, gameId, gameType, enabled = true, onKicked, onChatMessage }: UseSocketOptions): { connected: boolean } {
  const queryClient = useQueryClient()
  const { i18n } = useTranslation()
  const socketRef = useRef<Socket | null>(null)
  const gameIdRef = useRef<string | null | undefined>(null)
  // The language the game pages read their state in (`?lang=`), read when a join is
  // sent; and the one the last join asked for, so its push lands in that query only.
  const langRef = useRef(i18n.language)
  langRef.current = i18n.language
  const joinedLangRef = useRef(i18n.language)
  const gameTypeRef = useRef<string | undefined>(gameType)
  const [connected, setConnected] = useState(false)

  const onKickedRef = useRef(onKicked)
  onKickedRef.current = onKicked

  const onChatMessageRef = useRef(onChatMessage)
  onChatMessageRef.current = onChatMessage

  // Keep gameType ref in sync
  gameTypeRef.current = gameType

  const joinGame = useCallback((socket: Socket | null, gameId: string) => {
    joinedLangRef.current = langRef.current
    socket?.emit("join_game", { game_id: gameId, lang: langRef.current })
  }, [])

  const handleConnect = useCallback(() => {
    setConnected(true)
    if (gameIdRef.current) {
      joinGame(socketRef.current, gameIdRef.current)
    }
    // On reconnect, invalidate queries to catch up on events missed while disconnected
    if (roomId) {
      queryClient.invalidateQueries({
        queryKey: queryKeys.room.state(roomId),
      })
    }
    if (gameIdRef.current && gameTypeRef.current) {
      const keyPrefix = getGameQueryKeyPrefix(gameTypeRef.current, gameIdRef.current)
      queryClient.invalidateQueries({ queryKey: keyPrefix })
    }
  }, [roomId, queryClient, joinGame])

  const handleDisconnect = useCallback(() => {
    setConnected(false)
  }, [])

  // Main connection effect
  useEffect(() => {
    if (!enabled || !roomId) return

    if (!getStoredToken()) return

    const socket = io(window.location.origin, {
      path: "/socket.io",
      // A function, so every (re)connect shows the token stored NOW: access tokens last
      // 15 min and AuthProvider refreshes them, while an object captured at mount kept
      // sending the expired one, which the server refuses.
      auth: (cb) => cb({ token: getStoredToken(), room_id: roomId, lang: langRef.current }),
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 3000,
      reconnectionAttempts: Infinity,
    })

    socketRef.current = socket

    socket.on("room_state", (state: Record<string, unknown>) => {
      queryClient.setQueryData(queryKeys.room.state(roomId), state)
    })

    // Server sends initial game_state on join_game (per-user, role-aware)
    socket.on("game_state", (state: Record<string, unknown>) => {
      if (gameIdRef.current && gameTypeRef.current) {
        const keyPrefix = getGameQueryKeyPrefix(gameTypeRef.current, gameIdRef.current)
        if (gameTypeRef.current === "word_quiz" || gameTypeRef.current === "mcq_quiz") {
          // Word Quiz / MCQ Quiz needs lang-aware fetch — invalidate to trigger REST refetch
          queryClient.invalidateQueries({ queryKey: keyPrefix })
        } else {
          // only the query read in the language this push was asked in (the pages key
          // their state by `{ lang }`): a cached query in another language keeps its own
          queryClient.setQueriesData({ queryKey: [...keyPrefix, { lang: joinedLangRef.current }] }, state)
        }
      }
    })

    // Server sends game_updated signal after mutations — invalidate to trigger REST re-fetch
    socket.on("game_updated", () => {
      if (gameIdRef.current && gameTypeRef.current) {
        const keyPrefix = getGameQueryKeyPrefix(gameTypeRef.current, gameIdRef.current)
        queryClient.invalidateQueries({ queryKey: keyPrefix })
      }
    })

    socket.on("connect", handleConnect)
    socket.on("disconnect", handleDisconnect)

    socket.on("you_were_kicked", (data: { room_id: string }) => {
      onKickedRef.current?.(data.room_id)
    })

    socket.on("chat_message", (data: ChatMessage) => {
      onChatMessageRef.current?.(data)
    })

    socket.on("connect_error", (err: Error) => {
      console.error("Socket.IO connection error:", err.message)
    })

    // socket.io-client never retries a handshake the server refused (`socket.active`
    // is false then): the page sat on "Reconnecting…" and 2 s polling for the rest of
    // the night. Connect again when there is a fresh token to show, once per token.
    const offToken = onTokenStored(() => {
      if (!socket.connected && !socket.active) socket.connect()
    })

    // Send periodic heartbeat to prevent stale-user detection (20s threshold)
    const heartbeatInterval = setInterval(() => {
      if (socket.connected) {
        socket.emit("heartbeat")
      }
    }, 10_000)

    // On tab refocus (mobile app switch, etc.), send immediate heartbeat
    // and invalidate queries to sync state that changed while backgrounded
    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return
      if (socket.connected) {
        socket.emit("heartbeat")
      }
      if (roomId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
      }
      if (gameIdRef.current && gameTypeRef.current) {
        const keyPrefix = getGameQueryKeyPrefix(gameTypeRef.current, gameIdRef.current)
        queryClient.invalidateQueries({ queryKey: keyPrefix })
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange)

    return () => {
      offToken()
      clearInterval(heartbeatInterval)
      document.removeEventListener("visibilitychange", handleVisibilityChange)
      socket.disconnect()
      socketRef.current = null
      setConnected(false)
    }
  }, [enabled, roomId, queryClient, handleConnect, handleDisconnect])

  // Join game room when gameId changes (handles late gameId arrival)
  useEffect(() => {
    gameIdRef.current = gameId
    if (socketRef.current?.connected && gameId) {
      joinGame(socketRef.current, gameId)
    }
  }, [gameId, joinGame])

  return { connected }
}
