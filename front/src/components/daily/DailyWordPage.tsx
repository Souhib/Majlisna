import { Link } from "@tanstack/react-router"
import { ArrowRight, Flag, Plus } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import type { DailyWordState } from "@/api/generated"
import { Lozenge } from "@/components/brand"
import { Figure, isArabicScript, scriptAttrs } from "@/components/games/shared/quiz-utils"
import { AnswerInput } from "@/components/games/wordquiz/AnswerInput"
import { HintDisplay } from "@/components/games/wordquiz/HintDisplay"
import { Alert } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { DailyCountdown } from "./DailyCountdown"
import { DailyReveal } from "./DailyReveal"
import { categoryKey, DAILY_ARABIC_NAME, DAILY_WORD_ANSWER_MAX_LENGTH, formatDailyDate, isFinished, promptKey, stakes, triesOf } from "./daily"
import { useDailyWord } from "./use-daily-word"

/**
 * /today, the word of the day (كلمة اليوم): one Kalimat word a day, the same for
 * everyone, found from its six hints. The Arabic name leads in Amiri brass, the Latin
 * name under it in Marcellus (the Arabic interface reads the Arabic alone), then the
 * day's number, its Makkah date and its theme.
 *
 * - Open (signed in): Kalimat's ladder, its next rung offering "Another hint: 5 points
 *   instead of 6", the answer field (any language or script; a wrong try opens the next
 *   rung, and its error says which), the tries so far, and "Give up" behind a
 *   confirmation. A hint asked for takes focus, so it is read where it lands; after a
 *   wrong try focus stays in the field.
 * - Signed out: the number, the theme and hint 1; "Sign in to play" stands where the
 *   field would be (`/auth/login?redirect=/today`).
 * - Found or given up: the reveal card in the arch (`DailyReveal`), which takes focus
 *   when the move came from this page, then the ladder as it was played.
 *
 * The server owns everything (the day, the hints it releases, the score, the streak);
 * the page words what it sends. Moves: `useDailyWord`.
 */
export function DailyWordPage() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const arabicUi = lang.startsWith("ar")
  const daily = useDailyWord()
  const { query, state, signedIn } = daily
  const finished = isFinished(state?.status)

  const revealTitleRef = useRef<HTMLHeadingElement>(null)
  const ladderRef = useRef<HTMLOListElement>(null)
  // Focus moves only after a move made here: a reload of a finished day takes none.
  const focusRevealNext = useRef(false)
  const focusRungNext = useRef<number | null>(null)
  // The rung the last wrong try opened (null: it was already the last one).
  const [openedRung, setOpenedRung] = useState<number | null>(null)

  useEffect(() => {
    if (!finished || !focusRevealNext.current) return
    focusRevealNext.current = false
    revealTitleRef.current?.focus()
  }, [finished])

  const hintsRevealed = state?.hints_revealed ?? 0
  useEffect(() => {
    const rung = focusRungNext.current
    if (rung == null || hintsRevealed < rung) return
    focusRungNext.current = null
    ladderRef.current?.querySelector<HTMLElement>(`[data-rung="${rung}"]`)?.focus()
  }, [hintsRevealed])

  const revealHint = async () => {
    if (!state) return
    focusRungNext.current = state.hints_revealed + 1
    if (!(await daily.revealHint())) focusRungNext.current = null
  }

  const submit = async (answer: string) => {
    focusRevealNext.current = true
    const before = state?.hints_revealed ?? 0
    const result = await daily.guess(answer)
    if (!result?.correct) focusRevealNext.current = false
    // A wrong try opens the next rung (the server's rule); the field's error names it.
    if (result && !result.correct) setOpenedRung(result.state.hints_revealed > before ? result.state.hints_revealed : null)
    return result ? { correct: result.correct, points_earned: result.state.score ?? 0 } : null
  }

  const wrongTryMessage = (guess: string) =>
    openedRung != null ? t("daily.play.wrongTry", { guess, number: openedRung }) : t("daily.play.wrongTryLast", { guess })

  const giveUp = async () => {
    focusRevealNext.current = true
    if (!(await daily.giveUp())) focusRevealNext.current = false
  }

  let body
  if (!state) {
    body =
      query.isError && !daily.authLoading ? (
        <div className="grid justify-items-start gap-4">
          <Alert tone="error">{getApiErrorMessage(query.error, t("daily.loadFailed"))}</Alert>
          <Button variant="secondary" onClick={() => void query.refetch()} loading={query.isRefetching}>
            {t("ui.tryAgain")}
          </Button>
        </div>
      ) : (
        <PanelSkeleton label={t("common.loading")} />
      )
  } else if (finished) {
    body = (
      <>
        <DailyReveal state={state} onKeep={daily.keep} keeping={daily.keeping} titleRef={revealTitleRef} />
        <Panel aria-labelledby="daily-ladder-title">
          <h2 id="daily-ladder-title" className="mb-3.5 type-panel">
            {t("daily.reveal.ladderTitle")}
          </h2>
          <HintDisplay
            hints={state.hints}
            hintsRevealed={state.hints_revealed}
            maxHints={state.max_hints}
            settled={state.status === "gave_up"}
            nowTag={state.status === "solved" ? t("daily.ladder.found") : undefined}
          />
          <Tries state={state} />
        </Panel>
      </>
    )
  } else {
    const { now, next } = stakes(state)
    body = (
      <>
        <Panel aria-labelledby="daily-play-title">
          <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1.5">
            <h2 id="daily-play-title" className="type-panel">
              {t(promptKey(state.category))}
            </h2>
            <p className="text-[14px] leading-snug text-muted-foreground">
              <Trans i18nKey="game.quiz.kalimat.worthNow" count={now} components={{ b: <b className="font-medium text-foreground" /> }} />
            </p>
          </div>
          <HintDisplay
            hints={state.hints}
            hintsRevealed={state.hints_revealed}
            maxHints={state.max_hints}
            focusableNow
            listRef={ladderRef}
            offer={
              signedIn && next != null ? (
                <Button
                  variant="secondary"
                  size="sm"
                  loading={daily.revealing}
                  onClick={() => void revealHint()}
                  iconStart={<Plus aria-hidden="true" />}
                  className="h-auto min-h-10 max-w-full whitespace-normal py-2 text-start leading-snug"
                >
                  {t("daily.ladder.another", { from: now, count: next })}
                </Button>
              ) : undefined
            }
          />
          {signedIn ? (
            <AnswerInput
              onSubmit={submit}
              disabled={false}
              answered={false}
              pointsEarned={0}
              hint={t("daily.play.fieldHint")}
              wrongGuessMessage={wrongTryMessage}
              maxLength={DAILY_WORD_ANSWER_MAX_LENGTH}
            />
          ) : (
            <SignInToPlay />
          )}
          <Tries state={state} />
          {signedIn ? <GiveUp onConfirm={() => void giveUp()} pending={daily.givingUp} /> : null}
        </Panel>
        <div className="grid gap-1.5">
          <p className="num text-[14px] text-muted-foreground">{t("daily.foundToday", { count: state.solvers_today })}</p>
          <DailyCountdown nextDayAt={state.next_day_at} />
        </div>
      </>
    )
  }

  return (
    <div className="page-wrap py-[clamp(28px,5vw,72px)]">
      <div className="mx-auto grid max-w-[42rem] gap-[clamp(24px,3.5vw,40px)]">
        <header>
          {arabicUi ? (
            <h1 className="daily-name type-arabic-name">{t("daily.name")}</h1>
          ) : (
            <>
              <p lang="ar" dir="rtl" aria-hidden="true" className="daily-name type-arabic-name w-fit">
                {DAILY_ARABIC_NAME}
              </p>
              <h1 className="daily-latin font-display">{t("daily.name")}</h1>
            </>
          )}
          {state ? <DayMeta state={state} lang={lang} /> : <Skeleton className="mt-3 h-4 w-56" aria-hidden="true" />}
          <p className="mt-3 type-lede max-w-[54ch]">{t("daily.lede")}</p>
        </header>
        {body}
      </div>
    </div>
  )
}

/** "#1 · Wednesday 28 October 2026 · a prophet": the number, the Makkah day, the theme. */
export function DayMeta({ state, lang, className }: { state: DailyWordState; lang: string; className?: string }) {
  const { t } = useTranslation()
  const category = categoryKey(state.category)
  return (
    <p className={cn("daily-meta", className)}>
      <Figure>{t("daily.number", { number: state.number })}</Figure> <Dot /> <time dateTime={state.day}>{formatDailyDate(state.day, lang)}</time>
      {category ? (
        <>
          {" "}
          <Dot /> <span>{t(category)}</span>
        </>
      ) : null}
    </p>
  )
}

/** The brass lozenge between the parts of a line; the spaces around it keep the words apart for screen readers. */
function Dot() {
  return <span aria-hidden="true" className="mx-1 inline-block size-[5px] -translate-y-0.5 rotate-45 bg-brass" />
}

/** The player's tries, oldest first: what they typed, Arabic in Aref Ruqaa; the right one in brass. */
function Tries({ state }: { state: DailyWordState }) {
  const { t } = useTranslation()
  const tries = triesOf(state)
  if (tries.length === 0) return null
  return (
    <section aria-labelledby="daily-tries-title" className="mt-5">
      <h3 id="daily-tries-title" className="type-label">
        {t("daily.play.tries", { count: state.attempts })}
      </h3>
      <ol className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
        {tries.map((guess, i) => (
          <li key={`${i}-${guess.text}`} className="inline-flex min-w-0 items-baseline gap-2">
            <Lozenge state={guess.right ? "brass" : "away"} size={7} className="-translate-y-px" />
            <span
              {...scriptAttrs(guess.text)}
              className={cn(
                "min-w-0 break-words",
                isArabicScript(guess.text) ? "type-hand text-[22px] leading-none" : "text-[15px]",
                guess.right ? "text-foreground" : "text-muted-foreground",
              )}
            >
              {guess.text}
            </span>
            {guess.right ? <span className="sr-only">{t("daily.play.rightTry")}</span> : null}
          </li>
        ))}
      </ol>
    </section>
  )
}

/** "Sign in to play", where the answer field stands for a player. */
function SignInToPlay() {
  const { t } = useTranslation()
  return (
    <div className="mt-5 grid justify-items-start gap-3 border-t border-line pt-4">
      <p className="max-w-[52ch] text-[15px] leading-normal text-muted-foreground">{t("daily.play.signInNote")}</p>
      <div className="flex flex-wrap gap-2.5">
        <Button asChild iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
          <Link to="/auth/login" search={{ redirect: "/today" }}>
            {t("daily.play.signIn")}
          </Link>
        </Button>
        <Button asChild variant="secondary">
          <Link to="/auth/register" search={{ redirect: "/today" }}>
            {t("nav.register")}
          </Link>
        </Button>
      </div>
    </div>
  )
}

/** "Give up", behind a confirmation (a dialog of the app, not the browser's). */
function GiveUp({ onConfirm, pending }: { onConfirm: () => void; pending: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line pt-4">
      <p className="text-[13.5px] leading-snug text-muted-foreground">{t("daily.play.giveUpNote")}</p>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="ghost" size="sm" loading={pending} iconStart={<Flag aria-hidden="true" />} className="text-muted-foreground hover:text-foreground">
            {t("daily.play.giveUp")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("daily.play.giveUpTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("daily.play.giveUpBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("daily.play.giveUpCancel")}</AlertDialogCancel>
            <AlertDialogAction variant="danger" onClick={onConfirm}>
              {t("daily.play.giveUpConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/** Before the first read: the panel's shape in bare warp. */
function PanelSkeleton({ label }: { label: string }) {
  return (
    <Panel aria-busy="true">
      <p className="sr-only" role="status">
        {label}
      </p>
      <div className="grid gap-3" aria-hidden="true">
        <Skeleton className="h-5 w-40" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
        <Skeleton className="mt-2 h-12 w-full" />
      </div>
    </Panel>
  )
}
