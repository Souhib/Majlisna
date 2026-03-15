import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowRight, LogOut } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { motion } from "motion/react"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { useCreateRoomApiV1RoomsPost, useGetActiveRoomApiV1RoomsActiveGet, useLeaveRoomApiV1RoomsLeavePatch } from "@/api/generated"
import { trackEvent } from "@/lib/analytics"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/create")({
  component: CreateRoomPage,
})

function CreateRoomPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [gameType, setGameType] = useState<"undercover" | "codenames" | "word_quiz" | "mcq_quiz">("undercover")
  const [error, setError] = useState("")

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

  const createMutation = useCreateRoomApiV1RoomsPost({
    mutation: {
      onSuccess: (data) => {
        const room = data as { id: string }
        trackEvent("room-create", { game: gameType })
        toast.success(t("toast.roomCreated"))
        navigate({ to: "/rooms/$roomId", params: { roomId: room.id } })
      },
      onError: (err) => setError(getApiErrorMessage(err)),
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    createMutation.mutate({ data: { game_type: gameType } })
  }

  const isLoading = createMutation.isPending

  return (
    <div className="mx-auto max-w-xl px-4 py-8 animate-slide-up">
      <h1 className="text-3xl font-extrabold tracking-tight gradient-text mb-8">{t("room.create")}</h1>

      {/* Rejoin / Leave Room Banner */}
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

      <form onSubmit={handleSubmit} className="space-y-6">
        {error && (
          <div className="rounded-2xl bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive animate-scale-in">{error}</div>
        )}

        {/* Game Type */}
        <div>
          <label className="block text-sm font-medium mb-3">{t("room.gameType")}</label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4">
            {(["undercover", "codenames", "word_quiz", "mcq_quiz"] as const).map((type) => {
              const selected = gameType === type
              const config = {
                undercover: { icon: "🕵️", players: "3-12", nameKey: "undercover" },
                codenames: { icon: "🔤", players: "4-10", nameKey: "codenames" },
                word_quiz: { icon: "❓", players: "1+", nameKey: "wordQuiz" },
                mcq_quiz: { icon: "📝", players: "1+", nameKey: "mcqQuiz" },
              }[type]
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => setGameType(type)}
                  className={`relative card-hover rounded-2xl border-2 p-3 sm:p-6 text-center transition-all duration-200 hover:-translate-y-0.5 overflow-hidden flex flex-col items-center ${
                    selected
                      ? "border-primary bg-primary/10 shadow-lg shadow-primary/20 ring-2 ring-primary/30 scale-[1.02]"
                      : "border-border/30 glass hover:border-primary/40 hover:shadow-lg opacity-70 hover:opacity-100"
                  }`}
                >
                  {selected && (
                    <div className="absolute top-2 right-2 sm:top-2.5 sm:right-2.5 size-5 rounded-full bg-primary flex items-center justify-center">
                      <svg className="size-3 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  )}
                  <div className="text-2xl sm:text-3xl h-8 sm:h-10 flex items-center justify-center mb-2 sm:mb-3">{config.icon}</div>
                  <div className={`text-xs sm:text-base font-extrabold tracking-tight break-words flex-1 flex items-center ${selected ? "text-primary" : ""}`}>{t(`games.${config.nameKey}.name`)}</div>
                  <div className="mt-1 sm:mt-1.5 text-[10px] sm:text-xs text-muted-foreground font-mono tabular-nums">{config.players} {t("room.players")}</div>
                </button>
              )
            })}
          </div>
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-3 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg disabled:opacity-50 transition-all duration-200"
        >
          {isLoading ? t("common.loading") : t("room.create")}
        </button>
      </form>
    </div>
  )
}
