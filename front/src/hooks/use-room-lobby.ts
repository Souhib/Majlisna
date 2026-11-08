import { replaceEqualDeep, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  useBanPlayerApiV1RoomsRoomIdBansPost,
  useGetRoomStateApiV1RoomsRoomIdStateGet,
  useKickPlayerApiV1RoomsRoomIdKickPatch,
  useLeaveRoomApiV1RoomsLeavePatch,
  useStartCodenamesGameApiV1CodenamesGamesRoomIdStartPost,
  useStartMcqquizGameApiV1McqquizGamesRoomIdStartPost,
  useStartUndercoverGameApiV1UndercoverGamesRoomIdStartPost,
  useStartWordquizGameApiV1WordquizGamesRoomIdStartPost,
  useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import type { ChatMessage } from "@/components/rooms/ChatPanel"
import { ROOM_ERROR_KEYS, retryUnlessRefused, roomErrorKey, roomErrorMessage } from "@/components/rooms/errors"
import { type GameType, isGameType, type LobbyEvent, type LobbyMember, type RemovalKind, toMembers } from "@/components/rooms/lobby"
import { answerRoomRiddle } from "@/components/rooms/samar-riddle"
import { useLeaveAfterKick } from "@/hooks/use-leave-after-kick"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { newerRoomState } from "@/lib/room-state"
import { storeRoomIdForGame } from "@/lib/room-session"
import { useAuth } from "@/providers/AuthProvider"

const GAME_ROUTE = {
  undercover: "/game/undercover/$gameId",
  codenames: "/game/codenames/$gameId",
  word_quiz: "/game/wordquiz/$gameId",
  mcq_quiz: "/game/mcqquiz/$gameId",
} as const

/** Polling of the room state while the socket is down. */
export const LOBBY_POLL_INTERVAL_MS = 2_000

/** How long the Share button says "Link copied". */
const SHARE_COPIED_MS = 1_500

/** The room as the lobby reads it from its state (REST or a socket push). */
export interface LobbyRoom {
  id: string
  publicId: string
  ownerId: string
  /** The PIN. It changes when the host bans a player (a kick keeps it). */
  password: string
  activeGameId: string | null
  gameType: string | null
  settings: Record<string, unknown> | null
  members: LobbyMember[]
}

export interface RoomLobby {
  /** The room on screen; undefined before its first state, after a refusal, or for a malformed push. */
  room: LobbyRoom | undefined
  members: LobbyMember[]
  isHost: boolean
  isSpectator: boolean
  hostName: string | undefined
  /** The game on the table: the room's, or the host's pick while it is on its way. */
  gameType: GameType
  /** When the state on screen arrived (a push resets it too): the away countdowns start there. */
  dataUpdatedAt: number
  /** The latest read failed: with a roster on screen, the page says it is stale. */
  isError: boolean
  error: unknown
  /** The refusal with nothing on screen, held while it is asked again (final for a 4xx). */
  refusal: unknown
  /** The refusal says the player has no seat here: the page offers "Join this room". */
  notSeated: boolean
  socketConnected: boolean
  lastChatMessage: ChatMessage | null
  /** Seated from the refusal page: re-read this room, or open the one joined. */
  onJoinedFromRefusal: (joinedRoomId: string) => void
  /** The host starts the game on the table (the page checks the table is ready). */
  startGame: (playerCount: number) => void
  isStartingGame: boolean
  pickGame: (next: GameType) => Promise<void>
  /** The host removes a player who left without quitting: no ban, the same PIN; they may come back. */
  kickPlayer: (member: LobbyMember) => Promise<void>
  /** The host bans a player: removed, kept out (joins, invites) until lifted, and a new PIN. */
  banPlayer: (member: LobbyMember) => Promise<void>
  /** The seat being removed (a kick or a ban) until its request has settled. */
  removingId: string | null
  /** The host's removals, by seat (from this screen, or told by the room): the activity line says "removed" or "banned". */
  removals: ReadonlyMap<string, RemovalKind>
  /**
   * The latest ban of a player with no seat (removed earlier, banned from the host's "Removed"
   * list): no roster change says it, so the room's word does, for the activity line (owner
   * decision, 8 November 2026). A new object for each ban; null until one.
   */
  offTableEvent: LobbyEvent | null
  leaveRoom: () => Promise<void>
  isLeaving: boolean
  /** Copy the share link, built from the PIN the room state carries now. */
  shareRoom: () => Promise<void>
  shareCopied: boolean
}

/** Copy text, falling back to a hidden textarea where the async clipboard is refused. */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const textarea = document.createElement("textarea")
    textarea.value = text
    textarea.style.position = "fixed"
    textarea.style.opacity = "0"
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand("copy")
    document.body.removeChild(textarea)
    return ok
  }
}

/** The room state as the lobby reads it; undefined for a malformed socket payload. */
function readRoom(raw: unknown): LobbyRoom | undefined {
  if (!raw || typeof raw !== "object") return undefined
  const state = raw as Record<string, unknown>
  if (!state.id || !state.public_id || !state.owner_id) return undefined
  return {
    id: state.id as string,
    publicId: state.public_id as string,
    ownerId: state.owner_id as string,
    password: (state.password as string) ?? "",
    activeGameId: (state.active_game_id as string | null | undefined) ?? null,
    gameType: (state.game_type as string | null | undefined) ?? null,
    settings: (state.settings as Record<string, unknown> | null | undefined) ?? null,
    members: toMembers(state.players, state.owner_id as string),
  }
}

/**
 * The lobby's client logic (/rooms/$roomId), out of the page so it can be tested with fake
 * timers (TQ-12): reading the room, its socket, following the table into a game, and the
 * host's and the player's actions.
 *
 * - Real time: Socket.IO pushes `room_state` into the query cache; polling (2 s) runs only
 *   while the socket is down. Only a REconnect invalidates (`useSocket`).
 * - A refusal with nothing on screen is final (FR-5): never retried (`retryUnlessRefused`),
 *   not polled, and held while asked again (a refocus), so no skeleton between two errors.
 *   For `userNotInRoom` the socket stays closed: the server refuses a non-member's socket,
 *   and socket.io-client never retries a refused one.
 * - Removed by the host: the `you_were_kicked` event (`banned` says a ban from a kick, for
 *   the notice on /rooms), or (on the polling fallback, where no event arrives) the
 *   player's seat gone from the state without having left: a "removed" notice then, which
 *   promises nothing. Another member removed: `member_removed_by_host` names it for the
 *   activity line.
 * - The host's two removals (owner decision, 2 November 2026). A kick (Remove) only takes
 *   the seat: the room state and the host's removed players (RoomBans, "Removed": the host
 *   may still ban them, owner request of 3 November 2026) are read again. A ban also keeps
 *   the player out and rotates the PIN: the room state, both of the host's lists and the
 *   share link are read again; a new PIN in the room state does the same, so a ban from the
 *   host's other device reaches this screen's lists too. The room's word of a removal
 *   (`member_removed_by_host`) re-reads the removed players (and the bans, for a ban), and
 *   so does a newcomer at the table: a removed player who sat down again leaves that list.
 *   A guest has no such list on screen: an invalidated query nobody watches is not fetched.
 */
export function useRoomLobby(roomId: string): RoomLobby {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // The host's pick while it is on its way to the server (see `gameType` below).
  const [pendingPick, setPendingPick] = useState<GameType | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)
  // The host's removals, by seat, so the activity line says "removed" or "banned" rather
  // than "left": from this screen, noted BEFORE the request (the route pushes the room
  // state before it answers) and dropped when it fails; from the room
  // (`member_removed_by_host`, every member's screen and the host's other devices). Dropped
  // once the player is back.
  const removalsRef = useRef(new Map<string, RemovalKind>())
  const removingRef = useRef<string | null>(null)
  const [offTableEvent, setOffTableEvent] = useState<LobbyEvent | null>(null)
  // The roster on screen, for the room's word of a ban: seated, the roster's change says it.
  const membersRef = useRef<LobbyMember[]>([])
  const [shareCopied, setShareCopied] = useState(false)
  const [lastChatMessage, setLastChatMessage] = useState<ChatMessage | null>(null)
  const navigatingToGameRef = useRef(false)
  const isLeavingRef = useRef(false)
  // set before the request, so a double tap on Start sends one (isPending arrives a tick later)
  const startingRef = useRef(false)
  const shareTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const leaveAfterKick = useLeaveAfterKick()

  const handleChatMessage = useCallback((msg: ChatMessage) => setLastChatMessage(msg), [])

  // The socket's state comes from useSocket below (which needs this query's answer first);
  // TanStack reads the interval after each render, by when the ref holds it.
  const socketConnectedRef = useRef(false)
  const {
    data: rawRoomData,
    dataUpdatedAt,
    isError,
    error,
  } = useGetRoomStateApiV1RoomsRoomIdStateGet(
    { room_id: roomId },
    {
      query: {
        refetchOnWindowFocus: true,
        // an error with nothing on screen is the server's no: asking every 2 s drew the
        // skeleton between two error pages (a no-data query is pending again at each fetch)
        refetchInterval: (query) =>
          query.state.status === "error" && query.state.data === undefined ? false : socketConnectedRef.current ? false : LOBBY_POLL_INTERVAL_MS,
        enabled: !!user,
        retry: retryUnlessRefused,
        // a read that started before the state on screen never replaces it (lib/room-state.ts)
        structuralSharing: (old: unknown, next: unknown) => {
          const kept = newerRoomState(old, next)
          return kept === old ? old : replaceEqualDeep(old, next)
        },
      },
    },
  )

  // Socket.IO payloads land in the same cache: guard against a malformed one.
  const room = useMemo(() => readRoom(rawRoomData), [rawRoomData])

  // The refusal on screen, kept while it is asked again (a refocus refetches, and the
  // query is pending meanwhile). Idempotent, so writing the ref while rendering is safe
  // under StrictMode.
  const refusalRef = useRef<unknown>(null)
  if (room) refusalRef.current = null
  else if (error) refusalRef.current = error
  const refusal = room ? null : refusalRef.current
  const notSeated = !!refusal && roomErrorKey(refusal) === ROOM_ERROR_KEYS.notInRoom

  // Another member's seat taken by the host (from any device): the room is told which
  // removal it was before the room state that drops the seat, so this line names it too.
  // The host's lists (RoomBans) follow it: a kick from the host's other device adds a
  // removed player, a ban (a seat, or a removed player who had none) moves one.
  const noteRemovalByHost = useCallback(
    (userId: string, banned: boolean, username: string | null) => {
      removalsRef.current.set(userId, banned ? "banned" : "removed")
      // A player the host had removed earlier has no seat: no roster change will say the ban
      if (banned && username && !membersRef.current.some((m) => m.id === userId)) setOffTableEvent({ kind: "banned", name: username })
      void queryClient.invalidateQueries({ queryKey: queryKeys.room.removals(roomId) }, { cancelRefetch: false })
      if (banned) void queryClient.invalidateQueries({ queryKey: queryKeys.room.bans(roomId) }, { cancelRefetch: false })
    },
    [queryClient, roomId],
  )

  const { connected: socketConnected } = useSocket({
    roomId,
    enabled: !!user && !notSeated,
    onKicked: leaveAfterKick,
    onMemberRemoved: noteRemovalByHost,
    onChatMessage: handleChatMessage,
  })
  socketConnectedRef.current = socketConnected

  const onJoinedFromRefusal = useCallback(
    (joinedRoomId: string) => {
      if (joinedRoomId === roomId) void queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
      else navigate({ to: "/rooms/$roomId", params: { roomId: joinedRoomId }, replace: true })
    },
    [navigate, queryClient, roomId],
  )

  const members = useMemo(() => room?.members ?? [], [room])
  membersRef.current = members
  const isHost = !!room && room.ownerId === user?.id
  const isSpectator = !!members.find((m) => m.id === user?.id)?.isSpectator
  const hostName = members.find((m) => m.isHost)?.username

  // The game on the table is the room's, for everyone: the host's pick is stored in the
  // room's settings and comes back in every member's room state. While the host's pick
  // is in flight, theirs is shown.
  const roomGameType: GameType = isGameType(room?.gameType) ? room.gameType : "undercover"
  const gameType: GameType = (isHost && pendingPick) || roomGameType

  // A new PIN means a player was banned (the PIN rotates on every ban, from any of the
  // host's devices; a kick keeps it): the share link and the host's lists are stale.
  const pinRef = useRef<string | null>(null)
  const pin = room?.password || null
  useEffect(() => {
    const previous = pinRef.current
    pinRef.current = pin
    if (!previous || !pin || previous === pin) return
    // a re-read already on its way (the ban's own, just below) is reused, not restarted
    void queryClient.invalidateQueries({ queryKey: queryKeys.room.shareLink(roomId) }, { cancelRefetch: false })
    void queryClient.invalidateQueries({ queryKey: queryKeys.room.bans(roomId) }, { cancelRefetch: false })
    void queryClient.invalidateQueries({ queryKey: queryKeys.room.removals(roomId) }, { cancelRefetch: false })
  }, [pin, queryClient, roomId])

  // A newcomer at the table may be a removed player back with the code and PIN (or an
  // invite): the server deleted their removal record, and the host's "Removed" list is stale.
  // Not on the first state (nobody arrived), nor on a departure.
  const seatedIdsRef = useRef<ReadonlySet<string> | null>(null)
  useEffect(() => {
    const previous = seatedIdsRef.current
    const seated = new Set(members.map((m) => m.id))
    seatedIdsRef.current = seated
    if (!previous || ![...seated].some((id) => !previous.has(id))) return
    void queryClient.invalidateQueries({ queryKey: queryKeys.room.removals(roomId) }, { cancelRefetch: false })
  }, [members, queryClient, roomId])

  // Reset navigating ref when game ends (active_game_id disappears)
  useEffect(() => {
    if (!room?.activeGameId) navigatingToGameRef.current = false
  }, [room?.activeGameId])

  // Follow the table into the game when it starts (non-hosts learn it from the room state)
  useEffect(() => {
    if (!room?.activeGameId || navigatingToGameRef.current) return
    navigatingToGameRef.current = true
    storeRoomIdForGame(room.activeGameId, room.id)
    // the samar riddle on screen is answered "when the game starts": at the room's next wait
    answerRoomRiddle(room.id)
    const gt = isGameType(room.gameType) ? room.gameType : gameType
    navigate({ to: GAME_ROUTE[gt], params: { gameId: room.activeGameId } })
  }, [room?.activeGameId, room?.gameType, room?.id, gameType, navigate])

  // A seat the host took is back at the table (a kicked player joined again): the next
  // departure of that player is theirs, a leave. Never the one whose request is in flight.
  useEffect(() => {
    const removals = removalsRef.current
    for (const id of removals.keys()) {
      if (id !== removingRef.current && members.some((m) => m.id === id)) removals.delete(id)
    }
  }, [members])

  // Removed: the player was in the list and is not any more, without having left. This
  // tracks membership in its OWN ref, so it works on the 2 s polling fallback too, where
  // the `you_were_kicked` socket event never arrives.
  const wasRoomMemberRef = useRef(false)
  useEffect(() => {
    if (!user || !room || isLeavingRef.current) return
    const isInRoom = members.some((u) => u.id === user.id)
    if (wasRoomMemberRef.current && !isInRoom) {
      wasRoomMemberRef.current = false
      leaveAfterKick()
      return
    }
    wasRoomMemberRef.current = isInRoom
  }, [members, user, room, leaveAfterKick])

  useEffect(() => () => clearTimeout(shareTimerRef.current), [])

  const startOptions = (gt: GameType) => ({
    mutation: {
      onSuccess: (data: unknown) => {
        const d = data as { game_id: string; room_id: string }
        navigatingToGameRef.current = true
        storeRoomIdForGame(d.game_id, d.room_id)
        answerRoomRiddle(d.room_id)
        // no toast: the game page is the answer, and a toast sat over its header (F10)
        navigate({ to: GAME_ROUTE[gt], params: { gameId: d.game_id } })
      },
      onError: (err: unknown) => toast.error(roomErrorMessage(err, t("room.lobbyPage.startFailed"))),
    },
  })
  const startUndercover = useStartUndercoverGameApiV1UndercoverGamesRoomIdStartPost(startOptions("undercover"))
  const startCodenames = useStartCodenamesGameApiV1CodenamesGamesRoomIdStartPost(startOptions("codenames"))
  const startWordQuiz = useStartWordquizGameApiV1WordquizGamesRoomIdStartPost(startOptions("word_quiz"))
  const startMcqQuiz = useStartMcqquizGameApiV1McqquizGamesRoomIdStartPost(startOptions("mcq_quiz"))
  const isStartingGame = startUndercover.isPending || startCodenames.isPending || startWordQuiz.isPending || startMcqQuiz.isPending

  const startGame = (playerCount: number) => {
    if (!room || startingRef.current) return
    startingRef.current = true
    trackEvent("game-start", { game: gameType, players: playerCount })
    const vars = { room_id: room.id }
    const started =
      gameType === "codenames"
        ? startCodenames.mutateAsync(vars)
        : gameType === "word_quiz"
          ? startWordQuiz.mutateAsync(vars)
          : gameType === "mcq_quiz"
            ? startMcqQuiz.mutateAsync(vars)
            : startUndercover.mutateAsync(vars)
    // refused (said by onError): the host may try again; started: the page is leaving
    started.catch(() => {
      startingRef.current = false
    })
  }

  const pickMutation = useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch()
  const pickGame = async (next: GameType) => {
    if (!room || next === gameType) return
    setPendingPick(next)
    try {
      await pickMutation.mutateAsync({ room_id: room.id, data: { game_type: next } })
      // the push (or the next poll) brings it back for everyone; write it now so the
      // host's own screen does not step back to the old game in between
      queryClient.setQueryData(queryKeys.room.state(roomId), (old: unknown) =>
        old && typeof old === "object" ? { ...old, game_type: next, settings: { ...(old as { settings?: object }).settings, game_type: next } } : old,
      )
    } catch (err) {
      toast.error(roomErrorMessage(err, t("room.lobbyPage.pickFailed")))
    } finally {
      setPendingPick(null)
    }
  }

  const kickMutation = useKickPlayerApiV1RoomsRoomIdKickPatch()
  const banMutation = useBanPlayerApiV1RoomsRoomIdBansPost()
  const removePlayer = async (member: LobbyMember, kind: RemovalKind) => {
    if (!room) return
    removingRef.current = member.id
    removalsRef.current.set(member.id, kind)
    setRemovingId(member.id)
    try {
      const vars = { room_id: room.id, data: { user_id: member.id } }
      if (kind === "banned") {
        await banMutation.mutateAsync(vars)
        // the seat, the new PIN (the share link) and the host's two lists
        void queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.room.shareLink(roomId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.room.bans(roomId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.room.removals(roomId) })
      } else {
        await kickMutation.mutateAsync(vars)
        // the seat, and the host's removed players (a kick changes neither the PIN nor the bans)
        void queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.room.removals(roomId) })
      }
    } catch (err) {
      removalsRef.current.delete(member.id)
      toast.error(roomErrorMessage(err, t(kind === "banned" ? "room.lobbyPage.banFailed" : "room.lobbyPage.kickFailed")))
    } finally {
      removingRef.current = null
      setRemovingId(null)
    }
  }
  const kickPlayer = (member: LobbyMember) => removePlayer(member, "removed")
  const banPlayer = (member: LobbyMember) => removePlayer(member, "banned")

  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()
  const leaveRoom = async () => {
    isLeavingRef.current = true
    if (!user || !room) {
      navigate({ to: "/rooms" })
      return
    }
    try {
      await leaveMutation.mutateAsync({ data: { room_id: room.id } })
    } catch {
      // Leaving is best effort: the grace period frees the seat anyway.
    }
    toast.info(t("toast.youLeftRoom"))
    navigate({ to: "/rooms" })
  }

  const shareRoom = async () => {
    if (!room) return
    const shareUrl = `${window.location.origin}/rooms/join?code=${room.publicId}&pin=${room.password}`
    if (!(await copyText(shareUrl))) return
    setShareCopied(true)
    toast.success(t("room.lobbyPage.shareToast"))
    clearTimeout(shareTimerRef.current)
    shareTimerRef.current = setTimeout(() => setShareCopied(false), SHARE_COPIED_MS)
  }

  return {
    room,
    members,
    isHost,
    isSpectator,
    hostName,
    gameType,
    dataUpdatedAt,
    isError,
    error,
    refusal,
    notSeated,
    socketConnected,
    lastChatMessage,
    onJoinedFromRefusal,
    startGame,
    isStartingGame,
    pickGame,
    kickPlayer,
    banPlayer,
    removingId,
    removals: removalsRef.current,
    offTableEvent,
    leaveRoom,
    isLeaving: leaveMutation.isPending,
    shareRoom,
    shareCopied,
  }
}
