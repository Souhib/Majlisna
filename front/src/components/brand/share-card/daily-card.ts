import type { DailyWordState } from "@/api/generated"
import { categoryKey, DAILY_ARABIC_NAME, DAILY_SHARE_URL, formatDailyDate, resultLine } from "@/components/daily/daily"
import { dirOf, type T } from "./game-card"
import type { DailyCardInput } from "./model"

/**
 * What the word of the day's card says, in the player's language. Of the day's state
 * only the number, the day, the theme, the ladder's length, the rungs opened, the rung
 * it was found at, the score and the streaks are read: NEVER the answer, its forms, its
 * explanation, a hint or a guess (`__tests__/inputs.test.ts` checks the input and every
 * line drawn from it). Pure: `t` is passed in.
 */
export function dailyCardInput(state: DailyWordState, t: T, lang: string): DailyCardInput {
  const arabicUi = lang.startsWith("ar")
  const category = categoryKey(state.category)
  const meta = [t("daily.number", { number: state.number }), formatDailyDate(state.day, lang), ...(category ? [t(category)] : [])].filter(Boolean)
  return {
    kind: "daily",
    dir: dirOf(lang),
    arabicName: DAILY_ARABIC_NAME,
    latinName: arabicUi ? undefined : t("daily.name"),
    meta,
    footer: DAILY_SHARE_URL,
    rungs: {
      total: state.max_hints,
      revealed: Math.min(state.hints_revealed, state.max_hints),
      found: state.status === "solved" ? state.hints_revealed : null,
    },
    result: resultLine(state, t),
    streak:
      state.streak != null
        ? [
            { label: t("daily.reveal.streak"), value: state.streak },
            { label: t("daily.reveal.bestStreak"), value: state.best_streak ?? state.streak },
          ]
        : undefined,
  }
}

/** The share sheet's title for the day: "Word of the day · #2". */
export function dailyCardTitle(state: Pick<DailyWordState, "number">, t: T): string {
  return `${t("daily.name")} · ${t("daily.number", { number: state.number })}`
}

/** The PNG's name, plain ASCII: "majlisna-word-of-the-day-2.png". */
export function dailyCardFileName(state: Pick<DailyWordState, "number">): string {
  return `majlisna-word-of-the-day-${state.number}.png`
}
