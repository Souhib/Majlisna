import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { io, type Socket } from 'socket.io-client'
import { queryKeys } from '@/api/queryKeys'
import { getStoredToken } from '@/lib/auth'

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
  gameType?: 'undercover' | 'codenames' | 'word_quiz' | 'mcq_quiz'
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
 * - On join_game: server sends initial game_state
 * - room_state events update ["room", roomId] query cache directly
 * - game_updated events invalidate [gameType, gameId] query, triggering a REST re-fetch
 *
 * Mutations still go through REST. Socket.IO is notification-only.
 */
export function useSocket({ roomId, gameId, gameType, enabled = true, onKicked, onChatMessage }: UseSocketOptions): { connected: boolean } {
  const queryClient = useQueryClient()
  const socketRef = useRef<Socket | null>(null)
  const gameIdRef = useRef<string | null | undefined>(null)
  const gameTypeRef = useRef<string | undefined>(gameType)
  const [connected, setConnected] = useState(false)

  const onKickedRef = useRef(onKicked)
  onKickedRef.current = onKicked

  const onChatMessageRef = useRef(onChatMessage)
  onChatMessageRef.current = onChatMessage

  // Keep gameType ref in sync
  gameTypeRef.current = gameType

  const handleConnect = useCallback(() => {
    setConnected(true)
    if (gameIdRef.current) {
      socketRef.current?.emit('join_game', { game_id: gameIdRef.current })
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
  }, [roomId, queryClient])

  const handleDisconnect = useCallback(() => {
    setConnected(false)
  }, [])

  // Main connection effect
  useEffect(() => {
    if (!enabled || !roomId) return

    const token = getStoredToken()
    if (!token) return

    const socket = io(window.location.origin, {
      path: '/socket.io',
      auth: { token, room_id: roomId },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 3000,
      reconnectionAttempts: Infinity,
    })

    socketRef.current = socket

    socket.on('room_state', (state: Record<string, unknown>) => {
      queryClient.setQueryData(
        queryKeys.room.state(roomId),
        state,
      )
    })

    // Server sends initial game_state on join_game (per-user, role-aware)
    socket.on('game_state', (state: Record<string, unknown>) => {
      if (gameIdRef.current && gameTypeRef.current) {
        const keyPrefix = getGameQueryKeyPrefix(gameTypeRef.current, gameIdRef.current)
        if (gameTypeRef.current === 'word_quiz' || gameTypeRef.current === 'mcq_quiz') {
          // Word Quiz / MCQ Quiz needs lang-aware fetch — invalidate to trigger REST refetch
          queryClient.invalidateQueries({ queryKey: keyPrefix })
        } else {
          queryClient.setQueriesData({ queryKey: keyPrefix }, state)
        }
      }
    })

    // Server sends game_updated signal after mutations — invalidate to trigger REST re-fetch
    socket.on('game_updated', () => {
      if (gameIdRef.current && gameTypeRef.current) {
        const keyPrefix = getGameQueryKeyPrefix(gameTypeRef.current, gameIdRef.current)
        queryClient.invalidateQueries({ queryKey: keyPrefix })
      }
    })

    socket.on('connect', handleConnect)
    socket.on('disconnect', handleDisconnect)

    socket.on('you_were_kicked', (data: { room_id: string }) => {
      onKickedRef.current?.(data.room_id)
    })

    socket.on('chat_message', (data: ChatMessage) => {
      onChatMessageRef.current?.(data)
    })

    socket.on('connect_error', (err: Error) => {
      console.error('Socket.IO connection error:', err.message)
    })

    // Send periodic heartbeat to prevent stale-user detection (20s threshold)
    const heartbeatInterval = setInterval(() => {
      if (socket.connected) {
        socket.emit('heartbeat')
      }
    }, 10_000)

    return () => {
      clearInterval(heartbeatInterval)
      socket.disconnect()
      socketRef.current = null
      setConnected(false)
    }
  }, [enabled, roomId, queryClient, handleConnect, handleDisconnect])

  // Join game room when gameId changes (handles late gameId arrival)
  useEffect(() => {
    gameIdRef.current = gameId
    if (socketRef.current?.connected && gameId) {
      socketRef.current.emit('join_game', { game_id: gameId })
    }
  }, [gameId])

  return { connected }
}
