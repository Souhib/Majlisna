import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowRight, Check, ChevronLeft, Eye, Share2, UserPlus } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
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
import { CodeTiles, Halqa, Lozenge, type LozengeState } from "@/components/brand"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ChatPanel, type ChatMessage } from "@/components/rooms/ChatPanel"
import { roomErrorMessage } from "@/components/rooms/errors"
import { InviteFriendModal } from "@/components/rooms/InviteFriendModal"
import {
  awayCountdown,
  awayLabel,
  GAME_NAME_KEY,
  GAME_TYPES,
  type GameType,
  isGameType,
  type LobbyEvent,
  type LobbyMember,
  rosterEvents,
  seatLobby,
  stableOrder,
  tableState,
  toMembers,
} from "@/components/rooms/lobby"
import { PlayerRoster } from "@/components/rooms/PlayerRoster"
import { RoomSettings } from "@/components/rooms/RoomSettings"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useNow } from "@/components/games/shared/quiz-utils"
import { useDocumentTitle } from "@/hooks/use-document-title"
import { useSocket } from "@/hooks/use-socket"
import { trackEvent } from "@/lib/analytics"
import { noteRoomNotice } from "@/lib/room-notice"
import { storeRoomIdForGame } from "@/lib/room-session"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/$roomId")({
  component: RoomLobbyPage,
})

const GAME_ROUTE = {
  undercover: "/game/undercover/$gameId",
  codenames: "/game/codenames/$gameId",
  word_quiz: "/game/wordquiz/$gameId",
  mcq_quiz: "/game/mcqquiz/$gameId",
} as const

const ACTIVITY_KEY: Record<LobbyEvent["kind"], string> = {
  joined: "room.lobbyPage.activityJoined",
  watching: "room.lobbyPage.activityWatching",
  left: "room.lobbyPage.activityLeft",
  away: "room.lobbyPage.activityAway",
  back: "room.lobbyPage.activityBack",
  host: "room.lobbyPage.activityHost",
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

/**
 * The lobby (sketch D, first phone): the room's name and who hosts it, the code and PIN
 * as tiles to read aloud, the host's game picker, and the HALQA: the ring of seats with
 * the host at the ṣadr, which closes when enough players are seated and wakes Start.
 * Spectators are named under the ring, never seated. Under the buttons, one quiet line
 * says what just happened (who sat down, who left): roster changes are not toasts.
 *
 * The ring is a picture; the real list (PlayerRoster, "Players (N)") sits beside it on
 * wide screens and under it on phones, with the host's Remove buttons, then the settings
 * and the chat.
 *
 * Real time: Socket.IO pushes room_state into the query cache; polling (2 s) only runs
 * while the socket is down. When a game starts, every member is sent to it, with the
 * room id stored for the game page (storeRoomIdForGame).
 */
function RoomLobbyPage() {
  const { roomId } = Route.useParams()
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // The host's pick while it is on its way to the server (see `gameType` below).
  const [pendingPick, setPendingPick] = useState<GameType | null>(null)
  const navigatingToGameRef = useRef(false)
  const isLeavingRef = useRef(false)
  const kickedRef = useRef(false)
  const [showInvite, setShowInvite] = useState(false)
  const [shareCopied, setShareCopied] = useState(false)
  const [kickingId, setKickingId] = useState<string | null>(null)
  const [activity, setActivity] = useState<LobbyEvent | null>(null)
  const previousMembersRef = useRef<LobbyMember[]>([])

  // Chat messages from Socket.IO
  const [lastChatMessage, setLastChatMessage] = useState<ChatMessage | null>(null)

  const leaveAfterKick = useCallback(() => {
    if (kickedRef.current) return
    kickedRef.current = true
    // said on /rooms as a line on the page, not a toast: the player did not cause it
    noteRoomNotice("kicked")
    navigate({ to: "/rooms" })
  }, [navigate])

  const handleChatMessage = useCallback((msg: ChatMessage) => {
    setLastChatMessage(msg)
  }, [])

  const { connected: socketConnected } = useSocket({
    roomId,
    enabled: !!user,
    onKicked: leaveAfterKick,
    onChatMessage: handleChatMessage,
  })

  // Poll room state as fallback when Socket.IO is disconnected
  const {
    data: rawRoomData,
    dataUpdatedAt,
    isLoading,
    error: queryError,
    failureCount,
  } = useGetRoomStateApiV1RoomsRoomIdStateGet(
    { room_id: roomId },
    {
      query: {
        refetchOnWindowFocus: true,
        refetchInterval: socketConnected ? false : 2_000,
        enabled: !!user,
        retry: 2,
      },
    },
  )

  // Socket.IO payloads land in the same cache: guard against a malformed one.
  const room = useMemo(() => {
    if (!rawRoomData) return undefined
    const raw = rawRoomData as unknown as Record<string, unknown>
    if (!raw.id || !raw.public_id || !raw.owner_id) return undefined
    return {
      id: raw.id as string,
      publicId: raw.public_id as string,
      ownerId: raw.owner_id as string,
      password: (raw.password as string) ?? "",
      activeGameId: (raw.active_game_id as string | null | undefined) ?? null,
      gameType: (raw.game_type as string | null | undefined) ?? null,
      settings: (raw.settings as Record<string, unknown> | null | undefined) ?? null,
      members: toMembers(raw.players, raw.owner_id as string),
    }
  }, [rawRoomData])

  const members = useMemo(() => room?.members ?? [], [room])
  const me = members.find((m) => m.id === user?.id)
  const isHost = !!room && room.ownerId === user?.id
  const isSpectator = !!me?.isSpectator
  const hostName = members.find((m) => m.isHost)?.username

  // The game on the table is the room's, for everyone: the host's pick is stored in the
  // room's settings and comes back in every member's room state. It used to live in the
  // host's own state only, so a guest's status line, ring and legend described the game
  // the room was opened for. While the host's pick is in flight, theirs is shown.
  // the tab names the room as its heading does: "Yusuf’s majlis · Majlisna"
  useDocumentTitle(hostName ? t("room.lobbyPage.title", { name: hostName }) : null)

  const roomGameType: GameType = isGameType(room?.gameType) ? room.gameType : "undercover"
  const gameType: GameType = (isHost && pendingPick) || roomGameType

  // How long each away seat is still kept: the server's `away_seconds_left` (its own grace
  // rule) counted down here from the moment that state arrived, a tick a second while
  // someone is away. The next state (push or poll) resets it to the server's figure.
  const someoneAway = members.some((m) => m.isAway && m.awaySecondsLeft != null)
  const now = useNow(someoneAway, 1000)
  const awayLeft = useMemo(() => awayCountdown(members, dataUpdatedAt, now), [members, dataUpdatedAt, now])

  // Seats keep the order players were first seen in (stableOrder): idempotent, so
  // updating the ref while rendering is safe under StrictMode's double render.
  const seatOrderRef = useRef<string[]>([])
  const seating = useMemo(() => {
    seatOrderRef.current = stableOrder(seatOrderRef.current, members)
    return seatLobby(
      members,
      gameType,
      user?.id,
      {
        you: t("room.lobbyPage.seatYou"),
        host: t("room.lobbyPage.seatHost"),
        youHost: t("room.lobbyPage.seatYouHost"),
        away: t("room.lobbyPage.seatAway"),
      },
      seatOrderRef.current,
      awayLeft,
    )
  }, [members, gameType, user?.id, t, awayLeft])
  const players = seating.seated
  const table = tableState(players.length, gameType)
  const gameName = t(GAME_NAME_KEY[gameType])

  // What just happened, for the activity line (and its polite live region).
  useEffect(() => {
    if (!room) return
    const events = rosterEvents(previousMembersRef.current, members, user?.id)
    if (events.length > 0) setActivity(events[events.length - 1])
    previousMembersRef.current = members
  }, [room, members, user?.id])

  // Reset navigating ref when game ends (active_game_id disappears)
  useEffect(() => {
    if (!room?.activeGameId) navigatingToGameRef.current = false
  }, [room?.activeGameId])

  // Follow the table into the game when it starts (non-hosts learn it from the room state)
  useEffect(() => {
    if (!room?.activeGameId || navigatingToGameRef.current) return
    navigatingToGameRef.current = true
    storeRoomIdForGame(room.activeGameId, room.id)
    const gt = isGameType(room.gameType) ? room.gameType : gameType
    navigate({ to: GAME_ROUTE[gt], params: { gameId: room.activeGameId } })
  }, [room?.activeGameId, room?.gameType, room?.id, gameType, navigate])

  const startOptions = (gt: GameType) => ({
    mutation: {
      onSuccess: (data: unknown) => {
        const d = data as { game_id: string; room_id: string }
        navigatingToGameRef.current = true
        storeRoomIdForGame(d.game_id, d.room_id)
        toast.success(t("toast.gameStarting"))
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

  const handleStartGame = () => {
    if (!room || isStartingGame || table.kind !== "ready") return
    trackEvent("game-start", { game: gameType, players: players.length })
    const vars = { room_id: room.id }
    if (gameType === "codenames") startCodenames.mutate(vars)
    else if (gameType === "word_quiz") startWordQuiz.mutate(vars)
    else if (gameType === "mcq_quiz") startMcqQuiz.mutate(vars)
    else startUndercover.mutate(vars)
  }

  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch()

  const handleLeaveRoom = async () => {
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

  // Detect being kicked: the current user was in the list and disappeared, without
  // having left voluntarily. This tracks membership in its OWN ref (the activity effect
  // above rewrites its own), so it still works on the 2 s polling fallback, where the
  // `you_were_kicked` socket event never arrives.
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

  const kickMutation = useKickPlayerApiV1RoomsRoomIdKickPatch()
  const pickMutation = useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch()

  const handlePickGame = async (next: GameType) => {
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

  const handleKickPlayer = async (member: LobbyMember) => {
    if (!room) return
    setKickingId(member.id)
    try {
      await kickMutation.mutateAsync({ room_id: room.id, data: { user_id: member.id } })
      queryClient.invalidateQueries({ queryKey: queryKeys.room.state(roomId) })
    } catch (err) {
      toast.error(roomErrorMessage(err, t("room.lobbyPage.kickFailed")))
    } finally {
      setKickingId(null)
    }
  }

  const handleShare = async () => {
    if (!room) return
    const shareUrl = `${window.location.origin}/rooms/join?code=${room.publicId}&pin=${room.password}`
    if (await copyText(shareUrl)) {
      setShareCopied(true)
      toast.success(t("room.lobbyPage.shareToast"))
      setTimeout(() => setShareCopied(false), 1500)
    }
  }

  if (isLoading && !room) {
    return <LobbySkeleton />
  }

  // Full-page error only when there is nothing to show. When we already have a roster
  // on screen, a failing refetch gets the banner further down instead: replacing a live
  // lobby over one bad poll would be worse than the stale data.
  if (!room && queryError && failureCount > 2) {
    return (
      <div className="page-wrap py-[clamp(48px,8vw,112px)]">
        <div className="mx-auto grid max-w-[34rem] justify-items-start gap-4">
          <h1 className="type-title">{t("room.lobbyPage.errorTitle")}</h1>
          <p className="type-body text-muted-foreground">{t("room.lobbyPage.errorBody")}</p>
          {roomErrorMessage(queryError, "") ? <p className="text-[14px] text-muted-foreground">{roomErrorMessage(queryError, "")}</p> : null}
          <Button asChild className="mt-2" iconStart={<ChevronLeft className="rtl-flip" aria-hidden="true" />}>
            <Link to="/rooms">{t("room.lobbyPage.backToRooms")}</Link>
          </Button>
        </div>
      </div>
    )
  }

  if (!room) return <LobbySkeleton />

  const sub = isHost ? t("room.lobbyPage.subHost") : isSpectator ? t("room.lobbyPage.subSpectator") : t("room.lobbyPage.subPlayer")
  const title = hostName ? t("room.lobbyPage.title", { name: hostName }) : t("room.lobbyPage.titleFallback")
  const openSeats = Math.max(0, seating.capacity - seating.seats.length)
  const awayPlayers = players.filter((p) => p.isAway)

  // one player away: the legend carries their countdown too ("Away · 9:58", sketch D)
  const awayLegend = t("room.lobbyPage.legendAway")
  const legend: { state: LozengeState; label: string }[] = [
    { state: "host", label: t("room.lobbyPage.legendHost") },
    ...(players.some((p) => !p.isHost && !p.isAway) ? [{ state: "ready" as const, label: t("room.lobbyPage.legendHere") }] : []),
    ...(awayPlayers.length > 0
      ? [{ state: "away" as const, label: awayPlayers.length === 1 ? awayLabel(awayLegend, awayLeft.get(awayPlayers[0].id)) : awayLegend }]
      : []),
    ...(openSeats > 0 ? [{ state: "open" as const, label: t("room.lobbyPage.legendOpen") }] : []),
  ]

  const statusTitle = isSpectator
    ? t("room.lobbyPage.spectatorTitle")
    : table.kind === "short"
      ? t("room.lobbyPage.shortTitle")
      : table.kind === "over"
        ? t("room.lobbyPage.overTitle")
        : isHost
          ? t("room.lobbyPage.readyTitle")
          : t("room.lobbyPage.guestReadyTitle", { host: hostName ?? "" })
  const statusBody = isSpectator
    ? t("room.lobbyPage.spectatorBody", { host: hostName ?? "" })
    : table.kind === "short"
      ? t("room.lobbyPage.shortBody", { game: gameName, count: seating.quorum })
      : table.kind === "over"
        ? t("room.lobbyPage.overBody", { game: gameName, count: table.max })
        : null
  const awayNote =
    awayPlayers.length === 1 ? t("room.lobbyPage.awayOne", { name: awayPlayers[0].username }) : awayPlayers.length > 1 ? t("room.lobbyPage.awayMany") : null

  const startLabel = isStartingGame
    ? t("room.lobbyPage.starting")
    : table.kind === "short"
      ? t("room.lobbyPage.waitingMore", { count: table.missing })
      : t("room.lobbyPage.start", { game: gameName })

  const stage = (
    <div className="grid justify-items-center gap-4">
      <div className="lobby-ring w-full max-w-[400px] lg:max-w-[460px] min-[2200px]:max-w-[540px]">
        <Halqa
          seats={seating.seats}
          capacity={seating.capacity}
          quorum={seating.quorum}
          fontSize={13}
          radius={100}
          padX={95}
          padY={56}
          center={{ count: seating.seats.length, label: t("room.lobbyPage.centerPlayers", { count: seating.seats.length }) }}
          label={t("room.lobbyPage.ringLabel", { count: seating.seats.length, open: openSeats })}
        />
      </div>

      <ul
        aria-label={t("room.lobbyPage.legendLabel")}
        className="flex flex-wrap justify-center gap-x-3.5 gap-y-1.5 text-[12.5px] leading-tight text-muted-foreground"
      >
        {legend.map((item) => (
          <li key={item.state} className="inline-flex items-center gap-1.5 num">
            <Lozenge state={item.state} size={8} />
            {item.label}
          </li>
        ))}
      </ul>

      {seating.spectators.length > 0 ? (
        <div className="flex max-w-full flex-wrap items-baseline justify-center gap-x-2 gap-y-1 text-[13.5px] leading-snug text-muted-foreground">
          <h2 className="sr-only">
            {t("room.spectators")} <span className="num">({seating.spectators.length})</span>
          </h2>
          <Eye className="size-[17px] shrink-0 translate-y-[3px]" aria-hidden="true" />
          <span aria-hidden="true">{t("room.lobbyPage.watching")}</span>
          <ul className="flex flex-wrap gap-x-1.5">
            {seating.spectators.map((s, i) => (
              <li key={s.id}>
                <b dir="auto" className="font-medium text-foreground">
                  {s.username}
                </b>
                {i < seating.spectators.length - 1 ? <span aria-hidden="true">{i18n.dir() === "rtl" ? "،" : ","}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="max-w-[46ch] text-center text-[14px] leading-normal text-muted-foreground text-pretty">
        <b className="font-medium text-foreground">{statusTitle}</b>
        {statusBody ? ` ${statusBody}` : null}
        {awayNote && !isSpectator ? ` ${awayNote}` : null}
      </p>

      {!isSpectator ? (
        <div className="grid w-full max-w-[420px] gap-2.5">
          {isHost ? (
            <Button
              block
              onClick={handleStartGame}
              disabled={table.kind !== "ready"}
              loading={isStartingGame}
              aria-label={startLabel}
              iconEnd={table.kind === "ready" ? <ArrowRight className="rtl-flip" aria-hidden="true" /> : undefined}
            >
              {/* E2E finds this button by "Start Game"; the visible label names the game,
                  drawn from data-label so the game's name is not in the button's text
                  (the picker's tabs are found by those names). */}
              <span className="sr-only">{t("room.startGame")}</span>
              <span aria-hidden="true" data-label={startLabel} className="before:content-[attr(data-label)]" />
            </Button>
          ) : null}
          <Button variant="secondary" block onClick={() => setShowInvite(true)} iconStart={<UserPlus aria-hidden="true" />}>
            {t("room.lobbyPage.invite")}
          </Button>
        </div>
      ) : null}

      <p
        role="status"
        className="flex w-full max-w-[420px] items-baseline gap-2.5 border-t border-line pt-3 text-[13.5px] leading-normal text-muted-foreground [&_b]:font-medium [&_b]:text-foreground"
      >
        <Lozenge state="brass" size={5} className="-translate-y-0.5" />
        <span className="min-w-0">
          {activity ? (
            <Trans i18nKey={ACTIVITY_KEY[activity.kind]} values={{ name: activity.name }} components={{ b: <b dir="auto" /> }} />
          ) : isHost ? (
            t("room.lobbyPage.hintHost")
          ) : (
            <Trans i18nKey="room.lobbyPage.hintGuest" values={{ host: hostName ?? "" }} components={{ b: <b dir="auto" /> }} />
          )}
        </span>
      </p>
    </div>
  )

  return (
    <div className="page-wrap pt-4 pb-16 sm:pt-8 lg:pt-12">
      <ConnectionStatus connected={socketConnected} />
      <div className="mx-auto grid max-w-[1180px] gap-x-[clamp(32px,4.5vw,80px)] gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,400px)] lg:gap-y-10 min-[2200px]:max-w-[1360px] min-[2200px]:grid-cols-[minmax(0,1fr)_minmax(400px,460px)]">
        {/* The roster below is stale: the room state stopped refreshing. Say so rather
            than let the player act on data that no longer matches the server. */}
        {queryError && failureCount > 2 ? <Alert className="lg:col-span-2">{roomErrorMessage(queryError, t("room.staleState"))}</Alert> : null}

        <header className="lobby-head lg:col-span-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLeaveRoom}
            loading={leaveMutation.isPending}
            className="lh-back -ms-2 px-2 max-sm:w-11 max-sm:px-0 lg:mt-2"
            iconStart={<ChevronLeft className="rtl-flip" aria-hidden="true" />}
          >
            <span className="max-sm:sr-only">{t("room.lobbyPage.leave")}</span>
          </Button>
          <div className="lh-title pt-1 sm:pt-0.5">
            <h1 dir="auto" className="type-title text-[24px] break-words sm:text-[28px] lg:text-[40px]">
              {title}
            </h1>
            <p className="mt-0.5 text-[13.5px] leading-snug text-muted-foreground lg:mt-1.5 lg:text-[15px]">{sub}</p>
          </div>
          {/* code then PIN, left to right in every language, as on the home's join row and
              /rooms: one order for the pair everywhere (labels stay translated) */}
          <div dir="ltr" className="lh-codes flex items-end justify-between gap-x-4 sm:justify-start sm:gap-x-8 lg:gap-x-6">
            <CodeTiles label={t("room.codeLabel")} value={room.publicId} />
            <CodeTiles label={t("room.pinLabel")} value={room.password} kind="pin" className="max-sm:justify-items-end" />
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleShare}
            className="lh-share max-sm:size-11 max-sm:px-0 lg:h-[52px]"
            iconStart={shareCopied ? <Check aria-hidden="true" /> : <Share2 aria-hidden="true" />}
          >
            <span className="max-sm:sr-only">{shareCopied ? t("room.lobbyPage.shareCopied") : t("room.lobbyPage.share")}</span>
          </Button>
        </header>

        <section aria-label={title} className="grid min-w-0 content-start gap-5">
          {isHost && !isSpectator ? (
            // Radix stamps dir="ltr" on the root unless told otherwise (no DirectionProvider):
            // that turned the whole Arabic stage left to right and reversed the arrow keys.
            <Tabs dir={i18n.dir()} value={gameType} onValueChange={(v) => isGameType(v) && void handlePickGame(v)}>
              <TabsList aria-label={t("room.lobbyPage.gamePicker")} className="mx-auto w-full max-w-[560px]">
                {GAME_TYPES.map((g) => (
                  <TabsTrigger
                    key={g}
                    value={g}
                    className="text-[12px] min-[400px]:text-[13px]"
                    // only the open panel exists: an inactive tab must not point at a missing id
                    {...(g === gameType ? {} : { "aria-controls": undefined })}
                  >
                    {t(GAME_NAME_KEY[g])}
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value={gameType} tabIndex={-1} className="mt-5">
                {stage}
              </TabsContent>
            </Tabs>
          ) : (
            stage
          )}
        </section>

        <aside className="grid min-w-0 content-start gap-4" aria-label={t("room.players")}>
          <PlayerRoster players={players} myId={user?.id} canKick={isHost} kickingId={kickingId} onKick={handleKickPlayer} awayLeft={awayLeft} />
          {isHost && !isSpectator ? <RoomSettings roomId={room.id} settings={room.settings} gameType={gameType} playerCount={players.length} /> : null}
          {user ? <ChatPanel roomId={roomId} currentUserId={user.id} incomingMessage={lastChatMessage} /> : null}
        </aside>
      </div>

      <InviteFriendModal roomId={room.id} open={showInvite} onOpenChange={setShowInvite} />
    </div>
  )
}

/** The lobby before its first state: bare warp where the code, the ring and the list will be. */
function LobbySkeleton() {
  const { t } = useTranslation()
  return (
    <div className="page-wrap pt-4 pb-16 sm:pt-8 lg:pt-12" aria-busy="true">
      <p className="sr-only" role="status">
        {t("room.lobbyPage.loading")}
      </p>
      <div className="mx-auto grid max-w-[1180px] gap-x-[clamp(32px,4.5vw,80px)] gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,400px)] min-[2200px]:max-w-[1360px] min-[2200px]:grid-cols-[minmax(0,1fr)_minmax(400px,460px)]">
        <div className="grid gap-3 lg:col-span-2">
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-2 h-12 w-72" />
        </div>
        <div className="grid justify-items-center gap-4">
          <Skeleton className="h-10 w-full max-w-[560px]" />
          <Skeleton className={cn("aspect-square w-full max-w-[320px]")} />
        </div>
        <div className="grid content-start gap-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      </div>
    </div>
  )
}
