import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Figure, isArabicScript } from "@/components/games/shared/quiz-utils"
import { cn } from "@/lib/utils"

export interface LastRound {
  round: number
  answer: string
  /** The first to find it (the server sorts by points, then speed); absent when nobody did. */
  finder?: {
    username: string
    hint: number
    points: number
    /** What they wrote, as the server kept it (`typed_answer`); absent in older states. */
    wrote?: string | null
  }
}

/** The round that just ended, as the server reported it in its results phase. */
export function lastRoundFrom(state: {
  current_round: number
  correct_answer?: string | null
  round_results: { username: string; answered_at_hint: number | null; points: number; typed_answer?: string | null }[]
}): LastRound | null {
  if (!state.correct_answer) return null
  const first = state.round_results.find((r) => r.answered_at_hint != null && r.points > 0)
  return {
    round: state.current_round,
    answer: state.correct_answer,
    finder: first
      ? { username: first.username, hint: first.answered_at_hint ?? 0, points: first.points, wrote: first.typed_answer ?? null }
      : undefined,
  }
}

const storageKey = (gameId: string) => `majlisna-kalimat-last-round:${gameId}`

/**
 * The last round as this tab saw it in the results phase, kept for a reload: the next
 * round's state no longer carries the results. Best effort (storage can be refused).
 */
export function recallLastRound(gameId: string): LastRound | null {
  try {
    const raw = sessionStorage.getItem(storageKey(gameId))
    const last = raw ? (JSON.parse(raw) as LastRound) : null
    return last && typeof last.round === "number" && typeof last.answer === "string" ? last : null
  } catch {
    return null
  }
}

export function rememberLastRound(gameId: string, last: LastRound) {
  try {
    sessionStorage.setItem(storageKey(gameId), JSON.stringify(last))
  } catch {
    // a refused storage only costs the card after a reload
  }
}

/**
 * Under the answer row while the next round plays (sketch D, Kalimat phone): "Last round ·
 * Maryam wrote زكريّا · right at hint 5 · +5", what the first to find the word wrote (the
 * server's `typed_answer`), at which hint, for how much. When nobody found it, the word
 * itself. Arabic is set in Aref Ruqaa, the hand of what players write; Latin in Amiri.
 */
export const LastRoundCard = memo(function LastRoundCard({ last }: { last: LastRound }) {
  const { t } = useTranslation()
  const wrote = last.finder?.wrote?.trim() || null
  const shown = wrote ?? last.answer
  const arabic = isArabicScript(shown)

  return (
    <section
      aria-label={t("game.quiz.kalimat.lastRound")}
      className="mt-5 flex items-center gap-4 rounded-sm border border-line bg-surface px-4 py-3"
    >
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-snug text-muted-foreground">
          {t("game.quiz.kalimat.lastRound")}
          {" · "}
          {last.finder
            ? wrote
              ? t("game.quiz.kalimat.wrote", { name: `\u2068${last.finder.username}\u2069` })
              : t("game.quiz.kalimat.firstToFind", { name: `\u2068${last.finder.username}\u2069` })
            : t("game.quiz.kalimat.nobodyFound")}
        </p>
        <p
          {...(arabic ? { lang: "ar", dir: "rtl" } : { dir: "auto" })}
          className={cn(
            "break-words text-foreground",
            arabic ? "type-hand text-[30px]" : "font-nass text-[22px] leading-[1.4] font-bold",
          )}
        >
          {shown}
        </p>
      </div>
      {last.finder ? (
        <p className="shrink-0 text-end text-[13px] leading-snug text-muted-foreground">
          {wrote
            ? t("game.quiz.kalimat.rightAtHint", { number: last.finder.hint })
            : t("game.quiz.kalimat.atHint", { number: last.finder.hint })}
          <Figure className="block text-[18px] leading-tight font-medium text-brass">+{last.finder.points}</Figure>
        </p>
      ) : null}
    </section>
  )
})
