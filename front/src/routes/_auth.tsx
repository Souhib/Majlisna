import { createFileRoute, Outlet, useLocation, useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { io } from "socket.io-client"
import type { RoomInviteView } from "@/api/generated"
import { RoomInviteStrip } from "@/components/rooms/RoomInviteStrip"
import { useRoomInvites } from "@/components/rooms/use-room-invites"
import type { YouWereKicked } from "@/hooks/use-socket"
import { BusyLozenges } from "@/components/ui/button"
import { getStoredToken, onTokenStored } from "@/lib/auth"
import { useAuth } from "@/providers/AuthProvider"

const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin

export const Route = createFileRoute("/_auth")({
  component: AuthLayout,
})

function AuthLayout() {
  const { isAuthenticated, isLoading, user } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const location = useLocation()
  // The latest friend's invite, shown as a strip under the nav until answered: pushed on
  // the personal socket, or (sent while the page was closed) read from the server.
  const { invite, receive: receiveInvite, answer: answerInvite, refresh: refreshInvites, forgetRoom: forgetInvitesTo } = useRoomInvites(user?.id ?? null)

  // Carry the page the visitor wanted through the login, so a shared
  // /rooms/join?code=…&pin=… link still joins the room after authenticating.
  useEffect(() => {
    // The layout stays mounted while the router moves to the login page, so this effect
    // runs again with location = /auth/login?redirect=…; navigating from there replaced
    // the redirect with the login URL itself (which safeRedirect drops) and lost it.
    if (!isLoading && !isAuthenticated && !location.pathname.startsWith("/auth/")) {
      navigate({ to: "/auth/login", search: { redirect: location.href } })
    }
  }, [isAuthenticated, isLoading, navigate, location.href])

  // The player's personal Socket.IO channel (no room): a friend's room invite reaches
  // them on any signed-in page. The server used to refuse a connection without a room,
  // so no invite ever arrived. The push is the stored invite (its id, the code, who sent
  // it), never the PIN; a reconnect reads the stored invites again, since python-socketio
  // replays nothing sent while the socket was away. A ban from a room (`you_were_kicked`
  // with `banned`) drops that room's invite: the server deleted it.
  useEffect(() => {
    if (!user?.id || !getStoredToken()) return

    const socket = io(API_BASE_URL, {
      // read on every (re)connect: a token captured at mount expires after 15 min
      auth: (cb) => cb({ token: getStoredToken() }),
      transports: ["websocket"],
      reconnection: true,
    })

    socket.on("room_invite", (data: RoomInviteView) => receiveInvite(data))
    socket.on("you_were_kicked", (data: YouWereKicked) => {
      if (data.banned === true) forgetInvitesTo(data.room_id)
    })
    let connectedBefore = false
    socket.on("connect", () => {
      if (connectedBefore) refreshInvites()
      connectedBefore = true
    })

    // A refused handshake (an expired token) is never retried by socket.io-client:
    // connect again once there is a fresh token to show.
    const offToken = onTokenStored(() => {
      if (!socket.connected && !socket.active) socket.connect()
    })

    return () => {
      offToken()
      socket.disconnect()
    }
  }, [user?.id, receiveInvite, refreshInvites, forgetInvitesTo])

  if (isLoading) {
    // Still: no spinner, no pulse (nothing loops but the visible clock).
    return (
      <div className="page-wrap grid min-h-[calc(100svh-var(--navh))] place-items-center py-16" aria-busy="true">
        <p role="status" className="flex items-center gap-3 text-[15px] text-muted-foreground">
          <BusyLozenges className="text-brass" />
          {t("common.loading")}
        </p>
      </div>
    )
  }

  if (!isAuthenticated) return null

  // A game is the whole table: an invite waits until the player is out of it.
  const showInvite = !!invite && !location.pathname.startsWith("/game/")

  return (
    <>
      {showInvite ? (
        <div className="page-wrap pt-4">
          {/* keyed by the invite as sent: a new one (or a re-invite) starts with a fresh Join */}
          <RoomInviteStrip
            key={`${invite.id}@${invite.expires_at}`}
            invite={invite}
            onJoined={(roomId) => {
              answerInvite(invite)
              navigate({ to: "/rooms/$roomId", params: { roomId } })
            }}
            onDismiss={() => answerInvite(invite)}
          />
        </div>
      ) : null}
      <Outlet />
    </>
  )
}
