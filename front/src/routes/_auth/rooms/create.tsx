import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useCreateRoomApiV1RoomsPost, useGetActiveRoomApiV1RoomsActiveGet, useLeaveRoomApiV1RoomsLeavePatch } from "@/api/generated"
import { CodeTiles, Lozenge } from "@/components/brand"
import { currentLanguage } from "@/components/layout/language-switch"
import { roomErrorMessage } from "@/components/rooms/errors"
import { GAME_TYPES, type GameType } from "@/components/rooms/lobby"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { trackEvent } from "@/lib/analytics"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/rooms/create")({
  component: CreateRoomPage,
})

/** Each game's keys: its name (games.*), its Arabic name with the kashida (home.fihrist.*.arabic), its count. */
const GAMES: Record<GameType, { key: string; count: string; countKey: string }> = {
  undercover: { key: "undercover", count: "3–12", countKey: "home.fihrist.players" },
  codenames: { key: "codenames", count: "4–10", countKey: "home.fihrist.playersTeams" },
  word_quiz: { key: "wordQuiz", count: "1+", countKey: "home.fihrist.soloOrTogether" },
  mcq_quiz: { key: "mcqQuiz", count: "1+", countKey: "home.fihrist.soloOrTogether" },
}

/**
 * Open a room: choose the first game, then open. The four games are a list, not a wall
 * of tiles (DESIGN.md §9, §10): the Arabic name large in Amiri brass with its kashida,
 * the Latin name under it in Marcellus (Arabic pages show the Arabic name alone), one
 * line on how it plays, and the player count in Readex figures.
 *
 * The list is a radio group of buttons (one tab stop, arrows move the choice): E2E
 * clicks `button:has-text("Undercover")`, then the form's one submit button.
 */
function CreateRoomPage() {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"
  const { user } = useAuth()
  const navigate = useNavigate()
  const [gameType, setGameType] = useState<GameType>("undercover")
  const [error, setError] = useState("")
  const optionRefs = useRef<Partial<Record<GameType, HTMLButtonElement | null>>>({})

  const { data: activeRoom, refetch: refetchActiveRoom } = useGetActiveRoomApiV1RoomsActiveGet({
    query: { staleTime: 10_000 },
  })

  const leaveMutation = useLeaveRoomApiV1RoomsLeavePatch({
    mutation: {
      onSuccess: () => {
        toast.success(t("toast.youLeftRoom"))
        setError("")
        refetchActiveRoom()
      },
      onError: (err) => toast.error(roomErrorMessage(err, t("room.indexPage.leaveFailed"))),
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
      onError: (err) => setError(roomErrorMessage(err, t("room.createPage.failed"))),
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setError("")
    createMutation.mutate({ data: { game_type: gameType } })
  }

  const choose = (g: GameType, focus = false) => {
    setGameType(g)
    if (focus) optionRefs.current[g]?.focus()
  }

  // Radio group keys: arrows move the choice (left/right follow the reading direction).
  const onOptionKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = GAME_TYPES.indexOf(gameType)
    const rtl = document.documentElement.dir === "rtl"
    const next = { ArrowDown: 1, ArrowUp: -1, ArrowRight: rtl ? -1 : 1, ArrowLeft: rtl ? 1 : -1 }[e.key]
    if (next === undefined) return
    e.preventDefault()
    choose(GAME_TYPES[(i + next + GAME_TYPES.length) % GAME_TYPES.length], true)
  }

  return (
    <div className="page-wrap py-[clamp(40px,6vw,96px)]">
      <div className="mx-auto max-w-[52rem]">
        <header className="max-w-[44rem]">
          <h1 className="type-h2">{t("room.createPage.title")}</h1>
          <p className="type-lede mt-4">{t("room.createPage.lede")}</p>
        </header>

        {activeRoom ? (
          <Alert tone="info" className="mt-8 px-4 py-4 sm:px-5">
            <div className="grid gap-4">
              <div>
                <p className="font-medium">{t("room.createPage.seatedTitle")}</p>
                <p className="mt-0.5 text-muted-foreground">{t("room.createPage.seatedBody")}</p>
              </div>
              <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
                <CodeTiles label={t("room.codeLabel")} value={activeRoom.public_id} size="sm" />
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm" iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
                    <Link to="/rooms/$roomId" params={{ roomId: activeRoom.room_id }}>
                      {t("room.indexPage.return")}
                    </Link>
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={leaveMutation.isPending}
                    onClick={() => user && leaveMutation.mutate({ data: { room_id: activeRoom.room_id } })}
                  >
                    {t("room.lobbyPage.leave")}
                  </Button>
                </div>
              </div>
            </div>
          </Alert>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-[clamp(32px,4vw,52px)] grid gap-6">
          <div role="radiogroup" aria-labelledby="game-legend">
            <h2 id="game-legend" className="type-label">
              {t("room.createPage.gameLegend")}
            </h2>
            <ul className="mt-3 border-b border-line-brass">
              {GAME_TYPES.map((g) => {
                const { key, count, countKey } = GAMES[g]
                const checked = gameType === g
                const name = t(`games.${key}.name`)
                return (
                  <li key={g} className="border-t border-line-brass">
                    <button
                      ref={(el) => {
                        optionRefs.current[g] = el
                      }}
                      type="button"
                      role="radio"
                      aria-checked={checked}
                      tabIndex={checked ? 0 : -1}
                      onClick={() => choose(g)}
                      onKeyDown={onOptionKeyDown}
                      className={cn(
                        // phones: the count drops under the description; wider: its own column
                        "grid w-full cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 px-2 py-4 text-start sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:gap-x-6 sm:px-4 sm:py-5",
                        "transition-colors duration-(--dur-state) ease-out hover:bg-[color-mix(in_oklch,var(--brass)_6%,transparent)]",
                        "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
                        checked && "bg-[color-mix(in_oklch,var(--brass)_9%,transparent)] hover:bg-[color-mix(in_oklch,var(--brass)_9%,transparent)]",
                      )}
                    >
                      <Lozenge state={checked ? "brass" : "open"} size={12} className="mx-1 max-sm:row-span-2" />
                      <span className="grid min-w-0 gap-0.5">
                        {arabic ? (
                          <>
                            <span className="type-arabic-name text-[34px] sm:text-[40px]" aria-hidden="true">
                              {t(`home.fihrist.${key}.arabic`)}
                            </span>
                            <span className="sr-only">{name}</span>
                          </>
                        ) : (
                          <>
                            {/* the Arabic word keeps its own direction and sits at the line's start */}
                            <span className="type-arabic-name block text-[28px] sm:text-[34px]" aria-hidden="true">
                              <span lang="ar" dir="rtl">
                                {t(`home.fihrist.${key}.arabic`)}
                              </span>
                            </span>
                            <span className="font-display text-[21px] leading-tight text-foreground sm:text-[24px]">{name}</span>
                          </>
                        )}
                        <span className="mt-1 text-[14px] leading-snug text-muted-foreground text-pretty sm:text-[15px]">
                          {t(`room.createPage.${key}`)}
                        </span>
                      </span>
                      <span className="col-start-2 flex items-baseline gap-1.5 sm:col-start-3 sm:row-start-1 sm:grid sm:justify-items-end sm:gap-0 sm:text-end">
                        <span dir="ltr" className="num bidi-isolate text-[15px] font-medium text-foreground sm:text-[19px]">
                          {count}
                        </span>
                        <small className="text-[13px] leading-tight text-muted-foreground sm:max-w-[9rem] sm:text-[12.5px]">{t(countKey)}</small>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>

          {error ? <Alert>{error}</Alert> : null}

          <Button
            type="submit"
            size="lg"
            loading={createMutation.isPending}
            className="w-full sm:w-auto sm:justify-self-start"
            iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
          >
            {t("room.createPage.submit")}
          </Button>
        </form>
      </div>
    </div>
  )
}
