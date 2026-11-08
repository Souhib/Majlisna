import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRight, Check, ChevronLeft, Eye, Share2, UserPlus } from "lucide-react"
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { CodeTiles, CodeTilesInput, Halqa, Lozenge, type LozengeState } from "@/components/brand"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ChatPanel } from "@/components/rooms/ChatPanel"
import { ROOM_ERROR_KEYS, roomErrorKey, roomErrorMessage } from "@/components/rooms/errors"
import { InviteFriendModal } from "@/components/rooms/InviteFriendModal"
import {
  awayCountdown,
  awayLabel,
  GAME_NAME_KEY,
  GAME_TYPES,
  isGameType,
  type LobbyEvent,
  type LobbyMember,
  rosterEvents,
  seatLobby,
  stableOrder,
  tableState,
} from "@/components/rooms/lobby"
import { PlayerRoster } from "@/components/rooms/PlayerRoster"
import { RoomBans } from "@/components/rooms/RoomBans"
import { RoomSettings } from "@/components/rooms/RoomSettings"
import { LOBBY_RIDDLE_SCOPE } from "@/components/rooms/samar-riddle"
import { SamarRiddle } from "@/components/rooms/SamarRiddle"
import { useJoinRoom } from "@/components/rooms/use-join-room"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useNow } from "@/components/games/shared/quiz-utils"
import { useDocumentTitle } from "@/hooks/use-document-title"
import { useRoomLobby } from "@/hooks/use-room-lobby"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/$roomId")({
  component: RoomLobbyPage,
})

/** A room's code and PIN (the join form's tiles; the server's own lengths). */
const CODE_LENGTH = 5
const PIN_LENGTH = 4

const ACTIVITY_KEY: Record<LobbyEvent["kind"], string> = {
  joined: "room.lobbyPage.activityJoined",
  watching: "room.lobbyPage.activityWatching",
  left: "room.lobbyPage.activityLeft",
  away: "room.lobbyPage.activityAway",
  back: "room.lobbyPage.activityBack",
  host: "room.lobbyPage.activityHost",
  removed: "room.lobbyPage.activityRemoved",
  banned: "room.lobbyPage.activityBanned",
}

/**
 * The lobby (sketch D, first phone): the room's name and who hosts it, the code and PIN
 * as tiles to read aloud, the host's game picker, and the HALQA: the ring of seats with
 * the host at the ṣadr, which closes when enough players are seated and wakes Start.
 * Spectators are named under the ring, never seated. Under the buttons, one quiet line
 * says what just happened (who sat down, who left, whom the host removed or banned):
 * roster changes are not toasts.
 *
 * The ring is a picture; the real list (PlayerRoster, "Players (N)") sits beside it on
 * wide screens and under it on phones, with the host's Remove and Ban on each row, then
 * the settings and the chat.
 *
 * The client logic (reading the room and its socket, polling while the socket is down,
 * following the table into a game, start, pick, kick, ban, leave, share) is `useRoomLobby`
 * (hooks/use-room-lobby.ts); this page draws it. The host also gets the banned players
 * under the roster (`RoomBans`); Remove and Ban each ask first (PlayerRoster). A kick
 * (Remove) only takes the seat; a ban keeps the player out and rotates the PIN (owner
 * decision, 2 November 2026).
 *
 * A refused room state with nothing on screen (no such room, or no seat in it) is final:
 * not retried, not polled, and said once (`LobbyRefusal`), with "Join this room" (code
 * and PIN) for a player who has no seat here (FR-5).
 */
function RoomLobbyPage() {
  const { roomId } = Route.useParams()
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const lobby = useRoomLobby(roomId)
  const { room, members, isHost, isSpectator, hostName, gameType, refusal, socketConnected } = lobby
  const [showInvite, setShowInvite] = useState(false)
  const [activity, setActivity] = useState<LobbyEvent | null>(null)
  const previousMembersRef = useRef<LobbyMember[]>([])

  // the tab names the room as its heading does: "Yusuf’s majlis · Majlisna"
  useDocumentTitle(hostName ? t("room.lobbyPage.title", { name: hostName }) : null)

  // How long each away seat is still kept: the server's `away_seconds_left` (its own grace
  // rule) counted down here from the moment that state arrived, a tick a second while
  // someone is away. The next state (push or poll) resets it to the server's figure.
  const someoneAway = members.some((m) => m.isAway && m.awaySecondsLeft != null)
  const now = useNow(someoneAway, 1000)
  const awayLeft = useMemo(() => awayCountdown(members, lobby.dataUpdatedAt, now), [members, lobby.dataUpdatedAt, now])

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
    const events = rosterEvents(previousMembersRef.current, members, user?.id, lobby.removals)
    if (events.length > 0) setActivity(events[events.length - 1])
    previousMembersRef.current = members
  }, [room, members, user?.id, lobby.removals])

  // A ban of a player with no seat (the host had removed them): no roster change says it
  useEffect(() => {
    if (lobby.offTableEvent) setActivity(lobby.offTableEvent)
  }, [lobby.offTableEvent])

  const handleStartGame = () => {
    if (table.kind !== "ready") return
    lobby.startGame(players.length)
  }

  // Full-page error only when there is nothing to show (the query is in error, with its
  // retries spent, and no room). When we already have a roster on screen, a failing
  // refetch gets the banner further down instead: replacing a live lobby over one bad
  // poll would be worse than the stale data.
  if (!room && refusal) return <LobbyRefusal error={refusal} onJoined={lobby.onJoinedFromRefusal} />

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

  // A samar riddle while the table waits: for its quorum (everyone), or for the host (every
  // guest and spectator). Not for a host whose table is ready, or too full: the next move is
  // theirs. Not mounted, it asks nothing.
  const tableWaits = table.kind === "short" || !isHost

  const startLabel = lobby.isStartingGame
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
              loading={lobby.isStartingGame}
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
        data-testid="lobby-activity"
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

      {tableWaits ? (
        // keyed by room: another room's lobby has its own riddle. A Kalimat table gets its
        // answer after the game only: the word could come up in it.
        <SamarRiddle
          key={`riddle:${room.id}`}
          roomId={room.id}
          scope={LOBBY_RIDDLE_SCOPE}
          waitKey={LOBBY_RIDDLE_SCOPE}
          note={gameType === "word_quiz" ? "kalimat" : "lobby"}
          className="w-full max-w-[420px] pt-1"
        />
      ) : null}
    </div>
  )

  return (
    <div className="page-wrap pt-4 pb-16 sm:pt-8 lg:pt-12">
      <ConnectionStatus connected={socketConnected} />
      <div className="mx-auto grid max-w-[1180px] gap-x-[clamp(32px,4.5vw,80px)] gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,400px)] lg:gap-y-10 min-[2200px]:max-w-[1360px] min-[2200px]:grid-cols-[minmax(0,1fr)_minmax(400px,460px)]">
        {/* The roster below is stale: the room state stopped refreshing. Say so rather
            than let the player act on data that no longer matches the server. */}
        {lobby.isError ? <Alert className="lg:col-span-2">{roomErrorMessage(lobby.error, t("room.staleState"))}</Alert> : null}

        <header className="lobby-head lg:col-span-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void lobby.leaveRoom()}
            loading={lobby.isLeaving}
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
            onClick={() => void lobby.shareRoom()}
            className="lh-share max-sm:size-11 max-sm:px-0 lg:h-[52px]"
            iconStart={lobby.shareCopied ? <Check aria-hidden="true" /> : <Share2 aria-hidden="true" />}
          >
            <span className="max-sm:sr-only">{lobby.shareCopied ? t("room.lobbyPage.shareCopied") : t("room.lobbyPage.share")}</span>
          </Button>
        </header>

        <section aria-label={title} className="grid min-w-0 content-start gap-5">
          {isHost && !isSpectator ? (
            // Radix stamps dir="ltr" on the root unless told otherwise (no DirectionProvider):
            // that turned the whole Arabic stage left to right and reversed the arrow keys.
            <Tabs dir={i18n.dir()} value={gameType} onValueChange={(v) => isGameType(v) && void lobby.pickGame(v)}>
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
          <PlayerRoster
            players={players}
            myId={user?.id}
            canKick={isHost}
            removingId={lobby.removingId}
            onKick={(member) => void lobby.kickPlayer(member)}
            onBan={(member) => void lobby.banPlayer(member)}
            awayLeft={awayLeft}
          />
          {/* keyed by room, as the chat: another room's lobby starts its own list. Each key
              names its own panel: two siblings sharing one is unsupported in React (F3) */}
          <RoomBans key={`bans:${room.id}`} roomId={room.id} isHost={isHost} />
          {isHost && !isSpectator ? <RoomSettings roomId={room.id} settings={room.settings} gameType={gameType} playerCount={players.length} /> : null}
          {/* keyed by room: another room's lobby starts its own chat */}
          {user ? <ChatPanel key={`chat:${roomId}`} roomId={roomId} currentUserId={user.id} incomingMessage={lobby.lastChatMessage} /> : null}
        </aside>
      </div>

      <InviteFriendModal roomId={room.id} open={showInvite} onOpenChange={setShowInvite} />
    </div>
  )
}

/**
 * The lobby that did not open: the server refused its state. A player with no seat in
 * this room (`userNotInRoom`: they opened the lobby's address instead of the share link,
 * or the grace sweep freed their seat) can sit down from here with the code and PIN.
 */
function LobbyRefusal({ error, onJoined }: { error: unknown; onJoined: (roomId: string) => void }) {
  const { t } = useTranslation()
  const notSeated = roomErrorKey(error) === ROOM_ERROR_KEYS.notInRoom
  const detail = roomErrorMessage(error, "")
  return (
    <div className="page-wrap py-[clamp(48px,8vw,112px)]">
      <div className="mx-auto grid max-w-[34rem] justify-items-start gap-4">
        <h1 className="type-title">{t("room.lobbyPage.errorTitle")}</h1>
        <p className="type-body text-muted-foreground">{t("room.lobbyPage.errorBody")}</p>
        {detail ? <p className="text-[14px] text-muted-foreground">{detail}</p> : null}
        {notSeated ? <LobbyJoinEntry onJoined={onJoined} /> : null}
        <Button asChild variant={notSeated ? "secondary" : undefined} className="mt-2" iconStart={<ChevronLeft className="rtl-flip" aria-hidden="true" />}>
          <Link to="/rooms">{t("room.lobbyPage.backToRooms")}</Link>
        </Button>
      </div>
    </div>
  )
}

/**
 * "Join this room": the code and PIN as on /rooms (code then PIN, left to right in every
 * language), through the same join flow as the share link, so a player seated elsewhere
 * is offered to leave that room first.
 */
function LobbyJoinEntry({ onJoined }: { onJoined: (roomId: string) => void }) {
  const { t } = useTranslation()
  const [code, setCode] = useState("")
  const [pin, setPin] = useState("")
  const flow = useJoinRoom(onJoined)
  const complete = code.length === CODE_LENGTH && pin.length === PIN_LENGTH
  const describedBy = flow.error ? "lobby-join-error" : undefined

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!complete || flow.busy) return
    void flow.join(code, pin)
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mt-2 grid w-full gap-4 border-t border-line pt-5">
      <div dir="ltr" className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <CodeTilesInput
          id="lobby-join-code"
          label={t("room.codeLabel")}
          length={CODE_LENGTH}
          value={code}
          onChange={setCode}
          charset="alnum"
          invalid={!!flow.error}
          describedBy={describedBy}
        />
        <CodeTilesInput
          id="lobby-join-pin"
          kind="pin"
          label={t("room.pinLabel")}
          length={PIN_LENGTH}
          value={pin}
          onChange={setPin}
          charset="digits"
          invalid={!!flow.error}
          describedBy={describedBy}
        />
      </div>
      {flow.error ? (
        <p id="lobby-join-error" role="alert" className="text-[14px] leading-[1.45] text-ember">
          {flow.error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2.5">
        {flow.seatElsewhere ? (
          <Button onClick={() => void flow.leaveAndJoin()} loading={flow.busy || !flow.seatElsewhere.code}>
            {t("room.joinPage.leaveAndJoin", { room: flow.seatElsewhere.code ?? "…" })}
          </Button>
        ) : null}
        <Button
          type="submit"
          variant={flow.seatElsewhere ? "secondary" : undefined}
          disabled={!complete}
          loading={flow.busy && !flow.seatElsewhere}
          iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
        >
          {t("room.lobbyPage.joinThisRoom")}
        </Button>
      </div>
    </form>
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
