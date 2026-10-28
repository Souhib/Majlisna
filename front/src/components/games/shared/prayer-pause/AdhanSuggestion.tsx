import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand/Lozenge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface AdhanSuggestionProps {
  /** The prayer whose time has come (`asr`…), named through `prayer.names.*`. */
  prayerKey: string
  onPause: () => void
  onDismiss: () => void
  pausing?: boolean
  className?: string
}

/**
 * The host's quiet strip when a prayer time arrives mid-game: "It's ʿAṣr. Pause the
 * majlis for ṣalāh?" [Pause] [Not now]. Not a toast and not a modal: it sits at the top
 * of the game in a brass hairline, takes no focus, and is answered once
 * (useAdhanSuggestion remembers it). Its Pause is a hairline too: the game keeps the
 * screen's one filled action.
 */
export function AdhanSuggestion({ prayerKey, onPause, onDismiss, pausing = false, className }: AdhanSuggestionProps) {
  const { t } = useTranslation()
  const prayer = t(`prayer.names.${prayerKey}`)
  return (
    <section
      aria-label={t("pause.suggestLabel")}
      data-testid="adhan-suggestion"
      className={cn(
        "flex animate-fade-in flex-wrap items-center gap-x-4 gap-y-2.5 rounded-lg border border-line-brass bg-surface px-4 py-3",
        className,
      )}
    >
      <p role="status" className="flex min-w-0 flex-[1_1_16rem] items-baseline gap-2.5 text-[15px] leading-snug">
        <Lozenge state="brass" size={7} className="relative -top-px" />
        <span>{t("pause.suggest", { prayer })}</span>
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={onPause} loading={pausing}>
          {t("pause.suggestPause")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          {t("pause.notNow")}
        </Button>
      </div>
    </section>
  )
}
