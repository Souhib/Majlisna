import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { io, type Socket } from "socket.io-client"
import { queryKeys } from "@/api/queryKeys"
import { getStoredToken, onTokenStored } from "@/lib/auth"
import { newerRoomState } from "@/lib/room-state"

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
  /** The host took this player's seat in THIS room: `banned` false for a kick (Remove), true for a ban. */
  onKicked?: (roomId: string, banned: boolean) => void
  /** The host took ANOTHER member's seat (`member_removed_by_host`, before the room state that drops it). */
  onMemberRemoved?: (userId: string, banned: boolean) => void
  onChatMessage?: (message: ChatMessage) => void
}

/** `you_were_kicked`: one event for the host's two removals. */
export interface YouWereKicked {
  room_id: string
  /** True for a ban; absent (a server from before the ban had its own action) is a kick. */
  banned?: boolean
}

/** `member_removed_by_host`, on the room's channel: which of the host's removals took a seat. */
export interface MemberRemovedByHost {
  room_id: string
  user_id: string
  banned: boolean
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
 * - member_removed_by_host (before the room_state that drops the seat) says which of the
 *   host's removals took it, for the lobby's activity line
 * - game_updated events invalidate [gameType, gameId] query, triggering a REST re-fetch
 * - a REconnect (never the first connect) invalidates the room state, the room's chat
 *   history and the game: events sent while the socket was down are not replayed
 *
 * Mutations still go through REST. Socket.IO is notification-only.
 */
export function useSocket({ roomId, gameId, gameType, enabled = true, onKicked, onMemberRemoved, onChatMessage }: UseSocketOptions): { connected: boolean } {
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
  // True once this socket has been connected, or has tried and failed: from then on a
  // connect is a REconnect, after which the page may have missed events.
  const hasConnectedRef = useRef(false)

  const onKickedRef = useRef(onKicked)
  onKickedRef.current = onKicked

  const onMemberRemovedRef = useRef(onMemberRemoved)
  onMemberRemovedRef.current = onMemberRemoved

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
    // The first connect re-reads the chat history only. The room and the game need no
    // catch-up: the server pushes room_state on connect and answers join_game with
    // game_state (refetching them too read the same state three times per load, FP-10).
    // But a chat line sent between the page's history read and this socket joining the
    // room was pushed to nobody, and stayed unseen until a reconnect (CI, 2026-11-01):
    // read after the join, the history holds it, and every later line is pushed here.
    const isReconnect = hasConnectedRef.current
    hasConnectedRef.current = true
    if (!isReconnect) {
      if (roomId) queryClient.invalidateQueries({ queryKey: queryKeys.room.messages(roomId) })
      return
    }
    // A reconnect: python-socketio replays nothing, so re-read what may have changed
    // while the socket was down, the chat included (nothing else re-reads it, FR-6).
    if (roomId) {
      queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.room.messages(roomId) })
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

    // a new socket (another room, or enabled again): its first connect is a first one
    hasConnectedRef.current = false
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

    // never over a state read later (pushes can cross: lib/room-state.ts)
    socket.on("room_state", (state: Record<string, unknown>) => {
      queryClient.setQueryData(queryKeys.room.state(roomId), (old: unknown) => newerRoomState(old, state))
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

    // Sent to the player's personal channel, which this room socket joins too: a removal
    // from ANOTHER room (one they had left away, or a ban after the host removed them)
    // reaches this page as well, and is not this room's
    socket.on("you_were_kicked", (data: YouWereKicked) => {
      if (data.room_id !== roomId) return
      onKickedRef.current?.(data.room_id, data.banned === true)
    })

    socket.on("member_removed_by_host", (data: MemberRemovedByHost) => {
      onMemberRemovedRef.current?.(data.user_id, data.banned === true)
    })

    socket.on("chat_message", (data: ChatMessage) => {
      onChatMessageRef.current?.(data)
    })

    socket.on("connect_error", (err: Error) => {
      console.error("Socket.IO connection error:", err.message)
      // the page was read at mount, then the socket could not connect: whatever was
      // said in between reached no socket of ours, so the connect that follows catches up
      hasConnectedRef.current = true
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
