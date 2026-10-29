import { useTranslation } from "react-i18next"
import { useNow } from "@/components/games/shared/quiz-utils"
import { serverNow } from "@/lib/server-clock"
import { cn } from "@/lib/utils"
import { countdownDuration, formatCountdown, msUntil } from "./daily"

/**
 * "Next word in 05:12:33 · at midnight in Makkah". Counted on the server's clock
 * (`lib/server-clock`) toward the state's `next_day_at`, one step a second. A timer is
 * not a live region: it is read when the reader reaches it, never every second.
 */
export function DailyCountdown({ nextDayAt, className }: { nextDayAt: string; className?: string }) {
  const { t } = useTranslation()
  useNow(true)
  const left = msUntil(nextDayAt, serverNow())
  return (
    <p className={cn("type-meta", className)}>
      {t("daily.nextIn")}{" "}
      <time role="timer" dateTime={countdownDuration(left)} className="num font-medium text-foreground" dir="ltr">
        {formatCountdown(left)}
      </time>{" "}
      <span aria-hidden="true" className="mx-0.5 inline-block size-1 -translate-y-0.5 rotate-45 bg-brass" /> {t("daily.midnight")}
    </p>
  )
}
