import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowRight, Plus } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Alert } from "@/components/ui/alert"
import { useGetActiveRoomApiV1RoomsActiveGet, useJoinRoomApiV1RoomsJoinPatch, useLeaveRoomApiV1RoomsLeavePatch } from "@/api/generated"
import { CodeTiles, CodeTilesInput } from "@/components/brand"
import { roomErrorMessage } from "@/components/rooms/errors"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { trackEvent } from "@/lib/analytics"
import { takeRoomNotice } from "@/lib/room-notice"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/")({
  component: RoomsPage,
})

const CODE_LENGTH = 5
const PIN_LENGTH = 4

/**
 * Rooms: sit down at a friend's table with its code and PIN (the tiles, read aloud), see
 * the room you are seated in (a player has at most one), or open your own. One column on
 * phones; the join panel and "your room" side by side from 768 px.
 *
 * E2E fills `#room-code` and the `Password digit N` cells, then the one submit button;
 * a refused join is said once, in the line under the tiles (`data-testid="join-error"`,
 * an alert), with its repair: no toast on top of it.
 */
function RoomsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [roomCode, setRoomCode] = useState("")
  const [pin, setPin] = useState("")
  const [showIncomplete, setShowIncomplete] = useState(false)
  const [joinError, setJoinError] = useState<string | null>(null)
  // "The host removed you" lands here as a line on the page, never a toast: the player
  // did not cause it. Taken once, so a later visit does not repeat it.
  const [notice] = useState(takeRoomNotice)

  const joinMutation = useJoinRoomApiV1RoomsJoinPatch({
    mutation: {
      onSuccess: (data) => {
        const d = data as { id?: string }
        if (d.id) {
          trackEvent("room-join")
          navigate({ to: "/rooms/$roomId", params: { roomId: d.id } })
        }
      },
      onError: (err) => {
        setJoinError(roomErrorMessage(err, t("room.joinPage.unreachable")))
      },
    },
  })

  const complete = roomCode.length === CODE_LENGTH && pin.length === PIN_LENGTH

  const handleJoin = (e: FormEvent) => {
    e.preventDefault()
    setJoinError(null)
    if (!complete) {
      setShowIncomplete(true)
      return
    }
    if (!user || joinMutation.isPending) return
    joinMutation.mutate({ data: { public_room_id: roomCode, password: pin } })
  }

  const {
    data: activeRoom,
    isLoading: activeLoading,
    refetch: refetchActiveRoom,
  } = useGetActiveRoomApiV1RoomsActiveGet({
    query: { staleTime: 10_000 },
  })

  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch({
    mutation: {
      onSuccess: () => {
        toast.success(t("toast.youLeftRoom"))
        refetchActiveRoom()
      },
      onError: (err) => toast.error(roomErrorMessage(err, t("room.indexPage.leaveFailed"))),
    },
  })

  const incomplete = showIncomplete && !complete
  const describedBy = incomplete ? "join-incomplete" : joinError ? "join-error" : "join-hint"

  return (
    <div className="page-wrap py-[clamp(40px,6vw,96px)]">
      <div className="mx-auto max-w-[1040px]">
        <header className="max-w-[44rem]">
          <h1 className="type-h2">{t("nav.rooms")}</h1>
          <p className="type-lede mt-4">{t("room.indexPage.lede")}</p>
        </header>

        {notice === "kicked" ? (
          <Alert tone="info" data-testid="room-notice" className="mt-6 max-w-[44rem]">
            {t("room.youWereKicked")}
          </Alert>
        ) : null}

        <div className="mt-[clamp(32px,4vw,56px)] grid items-start gap-8 md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-14">
          <Panel tone="brass" aria-labelledby="join-title" className="sm:p-7">
            <h2 id="join-title" className="type-title text-[24px] sm:text-[26px]">
              {t("room.indexPage.joinTitle")}
            </h2>
            <form onSubmit={handleJoin} noValidate className="mt-6 grid gap-5">
              {/* code then PIN, left to right in every language, as on the home's join row
                  and the lobby: one order for the pair everywhere (labels stay translated) */}
              <div dir="ltr" className="flex flex-wrap items-end gap-x-6 gap-y-4">
                <CodeTilesInput
                  id="room-code"
                  label={t("room.codeLabel")}
                  length={CODE_LENGTH}
                  size="lg"
                  value={roomCode}
                  onChange={(v) => {
                    setRoomCode(v)
                    setShowIncomplete(false)
                    setJoinError(null)
                  }}
                  charset="alnum"
                  autoFocus
                  invalid={incomplete && roomCode.length !== CODE_LENGTH}
                  describedBy={describedBy}
                />
                <CodeTilesInput
                  id="room-pin"
                  split
                  kind="pin"
                  label={t("room.pinLabel")}
                  length={PIN_LENGTH}
                  size="lg"
                  value={pin}
                  onChange={(v) => {
                    setPin(v)
                    setShowIncomplete(false)
                    setJoinError(null)
                  }}
                  charset="digits"
                  // E2E fills these by name
                  cellLabel={(i) => `Password digit ${i + 1}`}
                  invalid={incomplete && pin.length !== PIN_LENGTH}
                  describedBy={describedBy}
                />
              </div>
              {incomplete ? (
                <p id="join-incomplete" role="alert" className="text-[14px] leading-[1.45] text-ember">
                  {t("room.indexPage.incomplete")}
                </p>
              ) : joinError ? (
                <p id="join-error" role="alert" data-testid="join-error" className="text-[14px] leading-[1.45] text-ember">
                  {joinError} {t("room.indexPage.joinRepair")}
                </p>
              ) : (
                <p id="join-hint" className="text-[14px] leading-[1.45] text-muted-foreground">
                  {t("room.indexPage.joinHint")}
                </p>
              )}
              <Button type="submit" block loading={joinMutation.isPending} iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
                {t("room.indexPage.joinSubmit")}
              </Button>
            </form>
          </Panel>

          {/* the same shape as the join panel: the title inside its hairline */}
          <Panel aria-labelledby="your-room-title" className="grid content-start gap-5 sm:p-7">
            <h2 id="your-room-title" className="type-title text-[24px] sm:text-[26px]">
              {t("room.indexPage.yourRoomTitle")}
            </h2>
            {activeLoading ? (
              <Skeleton className="h-36 w-full" />
            ) : activeRoom ? (
              <div className="grid gap-5 border-t border-line pt-5">
                <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
                  <CodeTiles label={t("room.codeLabel")} value={activeRoom.public_id} size="sm" />
                  <p className="pb-1 text-[14px] leading-snug text-muted-foreground">
                    {activeRoom.is_connected ? t("room.indexPage.yourRoomSeated") : t("room.indexPage.yourRoomAway")}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2.5">
                  <Button asChild iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
                    <Link to="/rooms/$roomId" params={{ roomId: activeRoom.room_id }}>
                      {t("room.indexPage.return")}
                    </Link>
                  </Button>
                  <Button
                    variant="secondary"
                    loading={leaveMutation.isPending}
                    onClick={() => user && leaveMutation.mutate({ data: { room_id: activeRoom.room_id } })}
                  >
                    {t("room.lobbyPage.leave")}
                  </Button>
                </div>
              </div>
            ) : (
              <EmptyState
                titleAs="p"
                className="border-t border-line pb-2 pt-8"
                title={t("room.indexPage.emptyTitle")}
                description={t("room.indexPage.emptyBody")}
                action={
                  <Button asChild iconStart={<Plus aria-hidden="true" />}>
                    <Link to="/rooms/create">{t("room.indexPage.open")}</Link>
                  </Button>
                }
              />
            )}
            {activeRoom ? (
              <Button asChild variant="link" className="min-h-11 justify-self-start" iconStart={<Plus aria-hidden="true" />}>
                <Link to="/rooms/create">{t("room.indexPage.open")}</Link>
              </Button>
            ) : null}
          </Panel>
        </div>
      </div>
    </div>
  )
}
