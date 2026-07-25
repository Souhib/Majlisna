import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef } from "react"
import { getApiErrorMessage } from "@/api/client"
import { useJoinRoomApiV1RoomsJoinPatch } from "@/api/generated"
import { useAuth } from "@/providers/AuthProvider"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"

export const Route = createFileRoute("/_auth/rooms/join")({
  validateSearch: (search: Record<string, unknown>) => ({
    code: String(search.code ?? ""),
    pin: String(search.pin ?? ""),
  }),
  component: JoinByLink,
})

function JoinByLink() {
  const { code, pin } = Route.useSearch()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { t } = useTranslation()
  const joinMutation = useJoinRoomApiV1RoomsJoinPatch()
  const attemptedRef = useRef(false)

  useEffect(() => {
    if (!code || !pin || !user || attemptedRef.current) return
    attemptedRef.current = true

    joinMutation.mutate(
      {
        data: {
          public_room_id: code,
          password: pin,
        },
      },
      {
        onSuccess: (room) => {
          const r = room as { id?: string }
          if (r.id) {
            navigate({ to: "/rooms/$roomId", params: { roomId: r.id } })
          }
        },
        onError: (err) => {
          toast.error(getApiErrorMessage(err, t("room.joinFailed")))
          navigate({ to: "/rooms" })
        },
      },
    )
  }, [code, pin, user])

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="glass rounded-2xl p-8 text-center">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4" />
        <p className="text-sm text-muted-foreground">{t("room.joiningRoom")}</p>
      </div>
    </div>
  )
}
