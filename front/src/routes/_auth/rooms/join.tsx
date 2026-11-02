import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowRight, ChevronLeft } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { CodeTiles } from "@/components/brand"
import { joinRepairFor } from "@/components/rooms/errors"
import { useJoinRoom } from "@/components/rooms/use-join-room"
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
 * Take the code and PIN out of the address bar, keeping the router's history state: the
 * PIN would otherwise stay in the browser history and in every analytics page view
 * (SEC F06). TanStack's history hears the replace, so the router then reads an empty
 * search: the page works from the values it read first.
 */
function scrubShareLinkFromAddress() {
  const url = new URL(window.location.href)
  if (!url.searchParams.has("code") && !url.searchParams.has("pin")) return
  url.searchParams.delete("code")
  url.searchParams.delete("pin")
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`)
}

/**
 * The share link (/rooms/join?code=…&pin=…), also used by the home's join row (a friend's
 * invite does not come here: its strip accepts it by id, without the PIN): it joins, then
 * opens the lobby. While it works it says so quietly over
 * the code it is using; when the server refuses, it stays here and names the repair
 * (ask for a fresh link, or type the code). The refusal is said once, on the page
 * (`data-testid="join-error"`): no toast on top of it, which at 390 px hid the title.
 *
 * The code and PIN are read once, then dropped from the address before the join is sent.
 * A player already seated in another room (409) is offered "Leave {{room}} and join"
 * (`useJoinRoom`); a ban (403 `roomBanned`) is said in the server's words, and that is all:
 * no repair, no "type the code" — a ban holds whatever the code and PIN (review F2). A
 * refused PIN says the PIN may have changed since the link was made: every ban rotates
 * it, a kick does not (review F1).
 */
function JoinByLink() {
  const search = Route.useSearch()
  // Read once per link: the address is cleaned right after (the router then reads no code
  // and no PIN), so the page keeps what the link said. A new link opened while the page is
  // open takes its place, and is tried once in turn.
  const [link, setLink] = useState(() => ({ code: search.code, pin: search.pin }))
  if (search.code && search.pin && (search.code !== link.code || search.pin !== link.pin)) {
    setLink({ code: search.code, pin: search.pin })
  }
  const { code, pin } = link
  const navigate = useNavigate()
  const { user } = useAuth()
  const { t } = useTranslation()
  // the link last tried, so StrictMode's second effect run does not join twice
  const attemptedRef = useRef<string | null>(null)
  const missing = !code || !pin
  const flow = useJoinRoom((roomId) => navigate({ to: "/rooms/$roomId", params: { roomId }, replace: true }))
  const { error, seatElsewhere } = flow
  const repair = missing ? "generic" : joinRepairFor(flow.errorKey)

  // before the join below: the request must not leave the PIN in the address meanwhile
  useEffect(() => {
    scrubShareLinkFromAddress()
  }, [search.code, search.pin])

  useEffect(() => {
    const attempt = `${code}\n${pin}`
    if (missing || !user || attemptedRef.current === attempt) return
    attemptedRef.current = attempt
    void flow.join(code, pin)
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
          {seatElsewhere || repair === "none" ? null : (
            <p className="type-body text-muted-foreground">
              {missing ? t("room.joinPage.missingBody") : repair === "pinChanged" ? t("room.joinPage.pinChangedRepair") : t("room.joinPage.errorRepair")}
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2.5">
            {seatElsewhere ? (
              <>
                <Button
                  onClick={() => void flow.leaveAndJoin()}
                  loading={flow.busy || !seatElsewhere.code}
                  iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
                >
                  {t("room.joinPage.leaveAndJoin", { room: seatElsewhere.code ?? "…" })}
                </Button>
                {seatElsewhere.roomId ? (
                  <Button asChild variant="secondary">
                    <Link to="/rooms/$roomId" params={{ roomId: seatElsewhere.roomId }}>
                      {t("room.indexPage.return")}
                    </Link>
                  </Button>
                ) : null}
              </>
            ) : (
              <>
                {repair === "none" ? null : (
                  <Button asChild>
                    <Link to="/rooms">{t("room.joinPage.typeCode")}</Link>
                  </Button>
                )}
                <Button asChild variant="secondary" iconStart={<ChevronLeft className="rtl-flip" aria-hidden="true" />}>
                  <Link to="/">{t("common.goHome")}</Link>
                </Button>
              </>
            )}
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
