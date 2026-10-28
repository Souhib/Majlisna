import { Eye, LogOut } from "lucide-react"
import { type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Chip } from "@/components/ui/chip"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

/**
 * The frame of both quiz screens (Kalimat and The Quiz), sketch sections C and D: one
 * play panel, and the table's scores beside it (under it on phones). No scenery: the
 * palette, a hairline, the thread clock. `relative` on purpose: a page-level veil (the
 * prayer pause, a later stage) positions itself against this frame.
 */
export function QuizFrame({
  children,
  aside,
  className,
}: {
  children: ReactNode
  aside?: ReactNode
  className?: string
}) {
  return (
    <div data-slot="quiz-frame" className={cn("page-wrap relative pt-5 pb-14 sm:pt-8 lg:pt-10", className)}>
      <div
        className={cn(
          "mx-auto grid w-full items-start gap-5",
          aside ? "max-w-[1040px] lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-8" : "max-w-[640px]",
        )}
      >
        <div className="min-w-0">{children}</div>
        {aside ? <aside className="grid min-w-0 gap-3 lg:sticky lg:top-[calc(var(--navh)+24px)]">{aside}</aside> : null}
      </div>
    </div>
  )
}

/**
 * The panel head: the game's name (the page's h1, Readex 500 as in the sketch), what
 * round this is, and a status or the clock at the inline end. On phones the round sits
 * under the name so the clock keeps its row.
 */
export function QuizHeader({
  title,
  sub,
  end,
  spectating,
  className,
}: {
  title: ReactNode
  sub?: ReactNode
  end?: ReactNode
  spectating?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <header className={cn("mb-4 flex flex-wrap items-center gap-x-4 gap-y-2", className)}>
      <div className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3.5">
        <h1 className="quiz-title">{title}</h1>
        {sub ? <p className="text-[13px] leading-tight text-muted-foreground">{sub}</p> : null}
      </div>
      {spectating || end ? (
        <div className="ms-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1.5">
          {spectating ? (
            <Chip tone="outline" mark={<Eye className="size-3.5" aria-hidden="true" />}>
              {t("game.spectating")}
            </Chip>
          ) : null}
          {end}
        </div>
      ) : null}
    </header>
  )
}

/** "Leave the room", quiet: the one way out of a game in progress (the label of every leave). */
export function QuizLeaveButton({ onLeave, className }: { onLeave: () => void; className?: string }) {
  const { t } = useTranslation()
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onLeave}
      iconStart={<LogOut className="rtl-flip" aria-hidden="true" />}
      className={cn("justify-self-start text-muted-foreground hover:text-foreground", className)}
    >
      {t("room.lobbyPage.leave")}
    </Button>
  )
}

/** The game is gone (ended elsewhere, removed): say so, then the page goes home. */
export function QuizGoneNotice({ message }: { message: string }) {
  const { t } = useTranslation()
  return (
    <QuizFrame>
      <Panel>
        <h2 className="type-title">{t("game.gameOver")}</h2>
        <Alert tone="info" className="mt-4">
          <p>{message}</p>
          <p className="mt-1 text-muted-foreground">{t("game.quiz.redirecting")}</p>
        </Alert>
      </Panel>
    </QuizFrame>
  )
}

/** The panel before the first state arrives: the name is known, the rest is bare warp. */
export function QuizLoading({ title }: { title: ReactNode }) {
  const { t } = useTranslation()
  return (
    <QuizFrame>
      <Panel aria-busy="true">
        <QuizHeader title={title} />
        <p className="sr-only" role="status">
          {t("common.loading")}
        </p>
        <div className="grid gap-3" aria-hidden="true">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-4/5" />
        </div>
      </Panel>
    </QuizFrame>
  )
}
