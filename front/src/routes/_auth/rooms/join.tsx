import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ChevronLeft } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useJoinRoomApiV1RoomsJoinPatch } from "@/api/generated"
import { CodeTiles } from "@/components/brand"
import { roomErrorMessage } from "@/components/rooms/errors"
import { BusyLozenges, Button } from "@/components/ui/button"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/join")({
  validateSearch: (search: Record<string, unknown>) => ({
    code: String(search.code ?? ""),
    pin: String(search.pin ?? ""),
  }),
  component: JoinByLink,
})

/**
 * The share link (/rooms/join?code=…&pin=…), also used by the home's join row and by
 * friend invites: it joins, then opens the lobby. While it works it says so quietly over
 * the code it is using; when the server refuses, it stays here and names the repair
 * (ask for a fresh link, or type the code). The refusal is said once, on the page
 * (`data-testid="join-error"`): no toast on top of it, which at 390 px hid the title.
 */
function JoinByLink() {
  const { code, pin } = Route.useSearch()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { t } = useTranslation()
  const joinMutation = useJoinRoomApiV1RoomsJoinPatch()
  const attemptedRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const missing = !code || !pin

  useEffect(() => {
    if (missing || !user || attemptedRef.current) return
    attemptedRef.current = true

    // mutateAsync, not mutate(vars, { onSuccess }): per-call callbacks belong to the
    // mutation observer, which StrictMode's mount/unmount/mount replaces, so they never
    // fired in development and the page sat on "Joining room…". The promise always settles.
    joinMutation
      .mutateAsync({
        data: {
          public_room_id: code,
          password: pin,
        },
      })
      .then(
        (room) => {
          const r = room as { id?: string }
          if (r.id) {
            navigate({ to: "/rooms/$roomId", params: { roomId: r.id }, replace: true })
          }
        },
        (err: unknown) => {
          const message = roomErrorMessage(err, t("room.joinPage.unreachable"))
          setError(message)
        },
      )
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one attempt per link
  }, [code, pin, user, missing])

  if (missing || error) {
    return (
      <div className="page-wrap py-[clamp(48px,9vw,128px)]">
        <div className="mx-auto grid max-w-[34rem] gap-4">
          <h1 className="type-title text-[28px] sm:text-[32px]">{missing ? t("room.joinPage.missingTitle") : t("room.joinPage.errorTitle")}</h1>
          {error ? (
            <p role="alert" data-testid="join-error" className="text-[15px] leading-normal text-ember">
              {error}
            </p>
          ) : null}
          <p className="type-body text-muted-foreground">{missing ? t("room.joinPage.missingBody") : t("room.joinPage.errorRepair")}</p>
          <div className="mt-3 flex flex-wrap gap-2.5">
            <Button asChild>
              <Link to="/rooms">{t("room.joinPage.typeCode")}</Link>
            </Button>
            <Button asChild variant="secondary" iconStart={<ChevronLeft className="rtl-flip" aria-hidden="true" />}>
              <Link to="/">{t("common.goHome")}</Link>
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-wrap grid min-h-[60vh] place-items-center py-16">
      <div className="grid justify-items-center gap-5 text-center" role="status">
        <div dir="ltr" className="flex items-end gap-4" aria-hidden="true">
          <CodeTiles value={code.slice(0, 5).toUpperCase()} size="sm" />
          <CodeTiles value={pin.slice(0, 4)} kind="pin" size="sm" />
        </div>
        <p className="flex items-center gap-3 text-[17px] text-foreground">
          {t("room.joinPage.joining")}
          <BusyLozenges className="text-brass" />
        </p>
      </div>
    </div>
  )
}
