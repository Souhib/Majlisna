import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowRight, Loader2, LogIn, LogOut, Plus } from "lucide-react"
import { useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { motion } from "motion/react"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { useJoinRoomApiV1RoomsJoinPatch, useGetActiveRoomApiV1RoomsActiveGet, useLeaveRoomApiV1RoomsLeavePatch } from "@/api/generated"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/")({
  component: RoomsPage,
})

function RoomsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [roomCode, setRoomCode] = useState("")
  const [password, setPassword] = useState(["", "", "", ""])
  const pinRefs = useRef<(HTMLInputElement | null)[]>([])

  const handleRoomCodeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, 5)
    setRoomCode(value)
  }, [])

  const handlePinChange = useCallback((index: number, value: string) => {
    if (value.length > 1) {
      value = value.slice(-1)
    }
    if (value && !/^\d$/.test(value)) return

    setPassword((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })

    // Auto-advance to next input
    if (value && index < 3) {
      pinRefs.current[index + 1]?.focus()
    }
  }, [])

  const handlePinKeyDown = useCallback((index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !password[index] && index > 0) {
      pinRefs.current[index - 1]?.focus()
    }
  }, [password])

  const handlePinPaste = useCallback((e: React.ClipboardEvent) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 4)
    if (!pasted) return
    const digits = pasted.split("")
    setPassword((prev) => {
      const next = [...prev]
      digits.forEach((d, i) => {
        next[i] = d
      })
      return next
    })
    const focusIndex = Math.min(digits.length, 3)
    pinRefs.current[focusIndex]?.focus()
  }, [])

  const joinMutation = useJoinRoomApiV1RoomsJoinPatch({
    mutation: {
      onSuccess: (data) => {
        const d = data as { id?: string }
        if (d.id) {
          navigate({ to: "/rooms/$roomId", params: { roomId: d.id } })
        }
      },
      onError: (err) => {
        toast.error(getApiErrorMessage(err, t("room.joinFailed")))
      },
    },
  })

  const handleJoin = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (roomCode.length !== 5) {
        toast.error(t("room.invalidCode"))
        return
      }
      const pin = password.join("")
      if (pin.length !== 4) {
        toast.error(t("room.invalidPassword"))
        return
      }
      if (!user) return

      joinMutation.mutate({
        data: {
          user_id: user.id,
          public_room_id: roomCode,
          password: pin,
        },
      })
    },
    [roomCode, password, user, t, joinMutation],
  )

  const isJoining = joinMutation.isPending

  const isFormValid = roomCode.length === 5 && password.every((d) => d !== "")

  const { data: activeRoom, refetch: refetchActiveRoom } = useGetActiveRoomApiV1RoomsActiveGet({
    query: { staleTime: 10_000 },
  })

  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch({
    mutation: {
      onSuccess: () => {
        toast.success(t("toast.youLeftRoom"))
        refetchActiveRoom()
      },
      onError: (err) => toast.error(getApiErrorMessage(err)),
    },
  })

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 animate-slide-up">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-extrabold tracking-tight gradient-text">{t("nav.rooms")}</h1>
      </div>

      {/* Rejoin Room Banner */}
      {activeRoom && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 glass rounded-2xl border-primary/30 px-5 py-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-extrabold tracking-tight">{t("room.rejoinRoom")}</p>
              <p className="text-xs text-muted-foreground">
                {t("room.roomCode")}: <span className="font-mono tabular-nums">{activeRoom.public_id}</span>
              </p>
            </div>
            <Link
              to="/rooms/$roomId"
              params={{ roomId: activeRoom.room_id }}
              className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg transition-all duration-200"
            >
              {t("room.rejoinButton")}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <button
            type="button"
            onClick={() => user && leaveMutation.mutate({ data: { user_id: user.id, room_id: activeRoom.room_id } })}
            disabled={leaveMutation.isPending}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive transition-colors duration-200"
          >
            <LogOut className="h-3 w-3" />
            {t("room.leave")}
          </button>
        </motion.div>
      )}

      <div className="grid gap-6 sm:grid-cols-2">
        {/* Create Room Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Link
            to="/rooms/create"
            className="group card-hover flex flex-col items-center gap-4 glass rounded-2xl p-8 text-center hover:-translate-y-0.5 hover:shadow-lg hover:border-primary/40 transition-all duration-200"
          >
            <div className="relative">
              <div className="absolute -inset-2 rounded-full bg-primary/20 blur-md opacity-0 group-hover:opacity-100 transition-all duration-200" />
              <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary/80 text-primary-foreground shadow-lg shadow-primary/25 group-hover:scale-105 transition-all duration-200">
                <Plus className="h-7 w-7" />
              </div>
            </div>
            <div>
              <h2 className="text-lg font-extrabold tracking-tight">{t("room.create")}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t("home.createRoom")}
              </p>
            </div>
          </Link>
        </motion.div>

        {/* Join Room Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="glass rounded-2xl p-8">
            <div className="flex flex-col items-center gap-4 mb-6">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/80 to-primary/60 text-primary-foreground shadow-lg shadow-primary/15">
                <LogIn className="h-7 w-7" />
              </div>
              <h2 className="text-lg font-extrabold tracking-tight">{t("room.join")}</h2>
            </div>

            <form onSubmit={handleJoin} className="space-y-5">
              {/* Room Code Input */}
              <div>
                <label htmlFor="room-code" className="block text-sm font-medium mb-2">
                  {t("room.roomCode")}
                </label>
                <input
                  id="room-code"
                  type="text"
                  value={roomCode}
                  onChange={handleRoomCodeChange}
                  placeholder={t("room.enterCode")}
                  autoFocus
                  maxLength={5}
                  className="w-full rounded-xl border border-border/30 bg-background px-4 py-3 text-center font-mono text-xl font-extrabold uppercase tracking-[0.3em] focus:outline-none focus:ring-2 focus:ring-primary placeholder:text-sm placeholder:tracking-normal placeholder:normal-case placeholder:font-normal transition-all duration-200"
                />
              </div>

              {/* Password PIN Input */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  {t("room.password")}
                </label>
                <div className="flex justify-center gap-3" onPaste={handlePinPaste}>
                  {password.map((digit, index) => (
                    <input
                      key={index}
                      ref={(el) => { pinRefs.current[index] = el }}
                      type="text"
                      inputMode="numeric"
                      pattern="\d*"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handlePinChange(index, e.target.value)}
                      onKeyDown={(e) => handlePinKeyDown(index, e)}
                      className="h-14 w-14 rounded-xl border border-border/30 bg-background text-center text-2xl font-mono font-extrabold focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary/50 transition-all duration-200"
                      aria-label={`Password digit ${index + 1}`}
                    />
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted-foreground text-center">
                  {t("room.enterPassword")}
                </p>
              </div>

              {/* Join Button */}
              <button
                type="submit"
                disabled={!isFormValid || isJoining}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-3 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg disabled:opacity-50 transition-all duration-200"
              >
                {isJoining ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t("room.joining")}
                  </>
                ) : (
                  t("room.join")
                )}
              </button>
            </form>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
