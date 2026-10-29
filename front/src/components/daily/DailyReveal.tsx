import { Check, Copy } from "lucide-react"
import { type Ref, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { DailyWordState } from "@/api/generated"
import { ArchFrame, SaduBand, Seal } from "@/components/brand"
import { KeepAction } from "@/components/notebook/KeepWords"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/field"
import { DailyCountdown } from "./DailyCountdown"
import { answerForms, resultLine, shareLine } from "./daily"

/** How long "Copied" stays on the Share button. */
const COPIED_MS = 2500

/**
 * The word of the day's colophon (DESIGN.md §6, the colophon idiom): set in the arch
 * once the player has found the word or given up. The vocalised Arabic in Amiri, the
 * word as Kalimat shows it, its explanation; how the day went ("found at hint 3 ·
 * 4 points", sealed once, or "given up"); the streaks and how many found it; "Keep in
 * your kunnash"; "Share" (a plain line, never the answer); and when the next word is
 * out. One madd band closes the card, as on every colophon.
 *
 * The title takes focus when the page moves it there (the reveal that follows a right
 * guess or a give-up): `titleRef`, tabindex -1.
 */
export function DailyReveal({
  state,
  onKeep,
  keeping,
  titleRef,
}: {
  state: DailyWordState
  onKeep: () => unknown
  keeping: boolean
  titleRef?: Ref<HTMLHeadingElement>
}) {
  const { t, i18n } = useTranslation()
  const arabicUi = (i18n.language ?? "").startsWith("ar")
  const answer = state.answer
  const solved = state.status === "solved"
  const forms = answer ? answerForms(answer, arabicUi) : null

  return (
    <ArchFrame>
      <article
        data-slot="colophon"
        aria-labelledby="daily-reveal-title"
        className="relative z-[1] overflow-hidden rounded-sm border border-line-brass-strong bg-surface px-5 pt-[22px] text-foreground sm:px-6"
      >
        <h2 id="daily-reveal-title" ref={titleRef} tabIndex={-1} className="type-title outline-none">
          {solved ? t("daily.reveal.solvedTitle") : t("daily.reveal.gaveUpTitle")}
        </h2>
        <p className="mt-2 flex items-center gap-2.5 text-[14.5px] leading-snug text-muted-foreground">
          {solved ? <Seal size={18} /> : <span aria-hidden="true" className="loz bg-line-field [--loz:7px]" />}
          <span className="num">{resultLine(state, t)}</span>
        </p>

        {forms ? (
          <div className="mt-4 border-t border-line-brass pt-3">
            {forms.arabic ? (
              <p lang="ar" dir="rtl" className="daily-word w-fit type-word text-foreground">
                {forms.arabic}
              </p>
            ) : null}
            {forms.display ? (
              <p dir="auto" className="text-[19px] font-medium leading-tight">
                {forms.display}
              </p>
            ) : null}
            {answer?.explanation ? (
              <p dir="auto" className="mt-2.5 max-w-[56ch] text-[15px] leading-[1.6] text-muted-foreground">
                {answer.explanation}
              </p>
            ) : null}
          </div>
        ) : null}

        {state.streak != null ? (
          <dl className="mt-5 grid grid-cols-2 border-y border-line">
            <div className="flex flex-col-reverse gap-0.5 py-3 pe-3">
              <dt className="type-meta">{t("daily.reveal.streak")}</dt>
              <dd className="num text-[30px] font-[260] leading-none">{state.streak}</dd>
            </div>
            <div className="flex flex-col-reverse gap-0.5 border-s border-line py-3 ps-4">
              <dt className="type-meta">{t("daily.reveal.bestStreak")}</dt>
              <dd className="num text-[30px] font-[260] leading-none">{state.best_streak ?? state.streak}</dd>
            </div>
          </dl>
        ) : null}
        <p className="num mt-3 text-[14px] text-muted-foreground">{t("daily.foundToday", { count: state.solvers_today })}</p>

        <div className="mt-[18px] flex flex-wrap gap-2.5">
          {answer ? (
            <KeepAction kept={answer.kept} keeping={keeping} onKeep={onKeep} label={t("daily.reveal.keep")} keptLabel={t("daily.reveal.kept")} />
          ) : null}
          <ShareAction line={shareLine(state, t)} />
        </div>
        <DailyCountdown nextDayAt={state.next_day_at} className="mt-4 mb-5" />
        <SaduBand className="-mx-5 sm:-mx-6" />
      </article>
    </ArchFrame>
  )
}

/**
 * "Share": copies a short plain-text line (no emoji, no answer) to the clipboard and
 * says so, in the button and to screen readers. Where the clipboard is refused, the
 * line is set in a read-only field, selected, to copy by hand.
 */
function ShareAction({ line }: { line: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [manual, setManual] = useState(false)
  const fieldRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!copied) return
    const id = setTimeout(() => setCopied(false), COPIED_MS)
    return () => clearTimeout(id)
  }, [copied])

  useEffect(() => {
    if (manual) fieldRef.current?.select()
  }, [manual])

  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard")
      await navigator.clipboard.writeText(line)
      setManual(false)
      setCopied(true)
    } catch {
      setManual(true)
    }
  }

  return (
    <>
      <Button variant="secondary" onClick={() => void copy()} iconStart={copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}>
        {copied ? t("daily.share.copied") : t("daily.share.action")}
      </Button>
      <p className="sr-only" role="status">
        {copied ? t("daily.share.copiedSr") : ""}
      </p>
      {manual ? (
        <div className="grid w-full gap-1.5">
          <label htmlFor="daily-share-line" className="type-label">
            {t("daily.share.manual")}
          </label>
          <Input id="daily-share-line" ref={fieldRef} readOnly value={line} dir="auto" onFocus={(e) => e.currentTarget.select()} />
        </div>
      ) : null}
    </>
  )
}
