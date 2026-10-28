import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { useGetActiveRoomApiV1RoomsActiveGet, useGetRoomStateApiV1RoomsRoomIdStateGet } from "@/api/generated"
import type { RoomPlayerState } from "@/api/generated/types/RoomPlayerState"
import { Halqa, type HalqaSeat } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/providers/AuthProvider"

/**
 * The halqa card beside the hero (sketch A/E/F/G): the circle of seats around a room code.
 *
 * - Signed in and seated in a room: the REAL room (active room + room state), with a
 *   way back to it.
 * - Otherwise: an illustration of how a room fills. The picture and its feed are hidden
 *   from assistive tech and the card says, in words, that it is an example, so nobody
 *   takes Yusuf's majlis for a room they could join. Its button sends focus to the real
 *   join form.
 */

const GAME_NAME_KEY: Record<string, string> = {
  undercover: "games.undercover.name",
  codenames: "games.codenames.name",
  word_quiz: "games.wordQuiz.name",
  mcq_quiz: "games.mcqQuiz.name",
}
/** Seated players needed to start (backend MIN_PLAYERS_*). */
const QUORUM: Record<string, number> = { undercover: 3, codenames: 4, word_quiz: 1, mcq_quiz: 1 }
/** Seats a table can hold (backend MAX_PLAYERS_*; the quizzes have none, the ring stops at 12). */
const CAPACITY: Record<string, number> = { undercover: 12, codenames: 10 }

export interface LiveSeating {
  seats: HalqaSeat[]
  spectators: string[]
  capacity: number
  quorum?: number
  hostName?: string
}

/**
 * Room state → ring seats: the host at the ṣadr, then everyone else in the order the
 * server lists them; spectators are named under the ring, never seated (sketch D).
 */
export function seatRoom(
  players: RoomPlayerState[],
  gameType: string | null | undefined,
  myId: string | undefined,
  labels: { host: string; you: string },
): LiveSeating {
  const seated = players.filter((p) => !p.is_spectator)
  const host = seated.find((p) => p.is_host)
  const ordered = host ? [host, ...seated.filter((p) => p !== host)] : seated
  const seats: HalqaSeat[] = ordered.map((p) => {
    const me = p.user_id === myId
    const sub = [me ? labels.you : null, p.is_host ? labels.host : null].filter(Boolean).join(" · ")
    return {
      id: p.user_id,
      // the ring is a picture with little room around it: long names are clipped there
      name: Array.from(p.username).length > 12 ? `${Array.from(p.username).slice(0, 11).join("")}…` : p.username,
      sub: sub || undefined,
      state: p.is_host ? "host" : p.is_disconnected ? "away" : "in",
      me,
    }
  })
  const cap = (gameType && CAPACITY[gameType]) || 12
  return {
    seats,
    spectators: players.filter((p) => p.is_spectator).map((p) => p.username),
    capacity: Math.min(cap, 12, Math.max(seats.length + 2, 6)),
    quorum: gameType ? QUORUM[gameType] : undefined,
    hostName: host?.username,
  }
}

function ExampleCard({ onTakeSeat }: { onTakeSeat: () => void }) {
  const { t } = useTranslation()
  const names = t("home.halqa.exampleNames").split(",")
  const seats: HalqaSeat[] = [
    { id: "host", name: t("home.halqa.exampleHost"), state: "host" },
    ...names.map((name, i) => ({ id: `p${i}`, name, state: "in" as const })),
    { id: "you", name: t("home.halqa.yourSeat"), state: "you" },
  ]
  return (
    <aside className="halqa-card panel-nodes" aria-labelledby="halqa-example-title" aria-describedby="halqa-example-caption">
      <div className="hc-head">
        <p id="halqa-example-title" className="hc-title">
          {t("home.halqa.exampleTitle")}
        </p>
        <span>{t("home.halqa.exampleSub")}</span>
      </div>
      <div className="hc-body">
        <Halqa seats={seats} capacity={8} fontSize={17} padX={66} padY={46} center={{ code: "LULIM", label: t("home.halqa.roomCode") }} />
        <div className="hc-side">
          <ul className="hc-feed" aria-hidden="true">
            <li>
              <span>
                <Trans i18nKey="home.halqa.exampleFeed1" components={{ b: <b /> }} />
              </span>
            </li>
            <li>
              <span>
                <Trans i18nKey="home.halqa.exampleFeed2" components={{ b: <b /> }} />
              </span>
            </li>
            <li>
              <span>{t("home.halqa.exampleFeed3")}</span>
            </li>
          </ul>
          <Button
            size="sm"
            className="min-[2200px]:h-[46px] min-[2200px]:text-[15.5px]"
            onClick={onTakeSeat}
            iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
          >
            {t("home.halqa.takeSeat")}
          </Button>
        </div>
      </div>
      <p id="halqa-example-caption" className="hc-caption">
        {t("home.halqa.exampleCaption")}
      </p>
    </aside>
  )
}

function LiveCard({ roomId, code }: { roomId: string; code: string }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { data: room } = useGetRoomStateApiV1RoomsRoomIdStateGet(
    { room_id: roomId },
    { query: { refetchOnWindowFocus: true, staleTime: 5_000, retry: 1 } },
  )
  const players = Array.isArray(room?.players) ? room.players : []
  const gameType = room?.game_type ?? null
  const seating = seatRoom(players, gameType, user?.id, { host: t("home.halqa.host"), you: t("home.halqa.you") })
  const gameName = gameType && GAME_NAME_KEY[gameType] ? t(GAME_NAME_KEY[gameType]) : null
  const status = room?.active_game_id ? t("home.halqa.inGame") : gameName ? t("home.halqa.waiting") : t("home.halqa.noGame")
  const roomCode = room?.public_id ?? code

  return (
    <aside className="halqa-card panel-nodes" aria-labelledby="halqa-live-title">
      <div className="hc-head">
        <h2 id="halqa-live-title" className="hc-title">
          {t("home.halqa.yourTitle")}
        </h2>
        <span>{[gameName, status].filter(Boolean).join(" · ")}</span>
      </div>
      <div className="hc-body">
        <Halqa
          seats={seating.seats}
          capacity={seating.capacity}
          quorum={seating.quorum}
          // real seats carry a second line ("you · host"): leave room above the ṣadr
          fontSize={17}
          padX={72}
          padY={68}
          center={{ code: roomCode, label: t("home.halqa.roomCode") }}
          label={t("home.halqa.ringLabel", { count: seating.seats.length, code: roomCode })}
        />
        <div className="hc-side">
          <ul className="hc-feed">
            {seating.hostName ? (
              <li>
                <span>
                  <Trans i18nKey="home.halqa.hostLine" values={{ name: seating.hostName }} components={{ b: <b dir="auto" /> }} />
                </span>
              </li>
            ) : null}
            <li>
              <span className="num">{t("home.halqa.seated", { count: seating.seats.length })}</span>
            </li>
            {seating.quorum ? (
              <li>
                <span className="num">{t("home.halqa.needed", { count: seating.quorum })}</span>
              </li>
            ) : null}
            {seating.spectators.length > 0 ? (
              <li>
                <span>{t("home.halqa.watching", { names: seating.spectators.join(", ") })}</span>
              </li>
            ) : null}
          </ul>
          <Button
            asChild
            size="sm"
            className="h-auto min-h-10 max-w-full whitespace-normal py-2 text-start min-[2200px]:min-h-[46px] min-[2200px]:text-[15.5px]"
            iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
          >
            <Link to="/rooms/$roomId" params={{ roomId }}>
              {t("home.halqa.return")}
            </Link>
          </Button>
        </div>
      </div>
    </aside>
  )
}

export function HalqaCard({ onTakeSeat }: { onTakeSeat: () => void }) {
  const { isAuthenticated } = useAuth()
  const { data: activeRoom } = useGetActiveRoomApiV1RoomsActiveGet({
    query: { enabled: isAuthenticated, staleTime: 10_000, retry: false },
  })
  if (isAuthenticated && activeRoom?.room_id) {
    return <LiveCard roomId={activeRoom.room_id} code={activeRoom.public_id} />
  }
  return <ExampleCard onTakeSeat={onTakeSeat} />
}
