import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { io, type Socket } from 'socket.io-client'
import { getStoredToken } from '@/lib/auth'

interface UseSocketOptions {
  roomId: string | null | undefined
  gameId?: string | null
  gameType?: 'undercover' | 'codenames'
  enabled?: boolean
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
export function useSocket({ roomId, gameId, gameType, enabled = true }: UseSocketOptions) {
  const queryClient = useQueryClient()
  const socketRef = useRef<Socket | null>(null)
  const gameIdRef = useRef<string | null | undefined>(null)
  const gameTypeRef = useRef<string | undefined>(gameType)

  // Keep gameType ref in sync
  gameTypeRef.current = gameType

  // Main connection effect
  useEffect(() => {
    if (!enabled || !roomId) return

    const token = getStoredToken()
    if (!token) return

    const socket = io(window.location.origin, {
      path: '/socket.io',
      auth: { token, room_id: roomId },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: Infinity,
    })

    socketRef.current = socket

    socket.on('room_state', (state: Record<string, unknown>) => {
      // Transform to match the queryFn shape used by $roomId.tsx
      const players = state.players as { user_id: string; username: string; is_spectator: boolean }[]
      queryClient.setQueryData(['room', roomId], {
        id: state.id,
        public_id: state.public_id,
        owner_id: state.owner_id,
        password: state.password,
        active_game_id: state.active_game_id,
        game_type: state.game_type,
        settings: state.settings,
        users: players
          ? players.map((p) => ({
              id: p.user_id,
              username: p.username,
              is_spectator: p.is_spectator,
            }))
          : [],
      })
    })

    // Server sends initial game_state on join_game (per-user, role-aware)
    socket.on('game_state', (state: Record<string, unknown>) => {
      if (gameIdRef.current && gameTypeRef.current) {
        queryClient.setQueryData([gameTypeRef.current, gameIdRef.current], state)
      }
    })

    // Server sends game_updated signal after mutations — invalidate to trigger re-fetch
    socket.on('game_updated', () => {
      if (gameIdRef.current && gameTypeRef.current) {
        queryClient.invalidateQueries({ queryKey: [gameTypeRef.current, gameIdRef.current] })
      }
    })

    // When connection is established (or re-established), join game room if gameId is pending
    socket.on('connect', () => {
      if (gameIdRef.current) {
        socket.emit('join_game', { game_id: gameIdRef.current })
      }
    })

    socket.on('connect_error', (err: Error) => {
      console.error('Socket.IO connection error:', err.message)
    })

    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [enabled, roomId, queryClient])

  // Join game room when gameId changes (handles late gameId arrival)
  useEffect(() => {
    gameIdRef.current = gameId
    if (socketRef.current?.connected && gameId) {
      socketRef.current.emit('join_game', { game_id: gameId })
    }
  }, [gameId])
}
